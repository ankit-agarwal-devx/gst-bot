"""In-process httpx transport for the fake (FAILURE_CONTRACT.md §B3).

No sockets, no real waiting: delays run on the engine's (usually virtual) clock.
"""
from __future__ import annotations

import httpx

from fake_taxmodel.engine import FakeTaxModel

FAKE_HOST = "taxmodel.test"
NO_TIMEOUT_MESSAGE = "request sent without a timeout — this would hang forever in production"


class _DroppingStream(httpx.SyncByteStream):
    """Yields the first half of the body, then fails like a closed connection."""

    def __init__(self, body: bytes, request: httpx.Request) -> None:
        self._sent = body[: len(body) // 2]
        self._total = len(body)
        self._request = request

    def __iter__(self):
        yield self._sent
        raise httpx.RemoteProtocolError(
            "peer closed connection without sending complete message body: "
            f"received {len(self._sent)} bytes, expected {self._total}",
            request=self._request,
        )


class FakeTransport(httpx.BaseTransport):
    def __init__(self, engine: FakeTaxModel) -> None:
        self.engine = engine
        self.clock = engine.clock

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        timeout = request.extensions.get("timeout") or {}
        read_timeout = timeout.get("read")
        if read_timeout is None:
            message = f"{NO_TIMEOUT_MESSAGE} ({request.method} {request.url})"
            self.engine.violations.append(message)
            raise AssertionError(message)

        body = request.read()
        ticket = self.engine.begin(request.method, request.url.raw_path.decode(), request.headers, body)
        if ticket.delay > read_timeout:
            # The server keeps working; the client gives up. The ticket stays
            # pending until its virtual completion time.
            self.clock.advance(read_timeout)
            raise httpx.ReadTimeout("timed out", request=request)
        if ticket.delay > 0:
            self.clock.advance(ticket.delay)
        reply = self.engine.finish(ticket)

        if reply.drop:
            return httpx.Response(reply.status, headers=reply.headers,
                                  stream=_DroppingStream(reply.body, request), request=request)
        return httpx.Response(reply.status, headers=reply.headers, content=reply.body, request=request)


def install(monkeypatch, transport: FakeTransport, host: str = FAKE_HOST) -> None:
    """Route every httpx.Client request for `host` to the fake, however the client was built."""
    original = httpx.HTTPTransport.handle_request

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == host:
            return transport.handle_request(request)
        return original(self, request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle_request)
