import threading
import time
import uuid

import httpx
import pytest
from django.db import connection
from django.test import Client

from bot import chat
from fake_taxmodel.transport import FAKE_HOST


@pytest.fixture(autouse=True)
def _fresh_chat_state():
    chat.reset_state()
    yield
    chat.reset_state()


class TaxModel:
    """The fake tax-model as seen from the bot's tests."""

    def __init__(self, engine, key):
        self.engine = engine
        self.key = key

    def script(self, *outcomes: str) -> None:
        self.engine.set_script(self.key, list(outcomes))

    def stats(self) -> dict:
        return self.engine.stats(self.key)


@pytest.fixture
def taxmodel(fake_taxmodel, settings):
    """Fake tax-model registered for the bot's key. Every call succeeds unless a test scripts failures."""
    key = settings.TAXMODEL["API_KEY"]
    fake_taxmodel.register_key(key)
    fake_taxmodel.set_script(key, [])
    return TaxModel(fake_taxmodel, key)


@pytest.fixture
def unreachable_taxmodel(monkeypatch, virtual_clock):
    """For tests that must not depend on the tax-model client: every call is refused at once.

    Returns the list of refused requests, so a test can check nothing was sent.
    """
    original = httpx.HTTPTransport.handle_request
    refused = []

    def refuse(self, request):
        if request.url.host == FAKE_HOST:
            refused.append(request)
            raise httpx.ConnectError("tax-model is unreachable in this test", request=request)
        return original(self, request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    return refused


class Api:
    def __init__(self):
        self.http = Client()

    def new_conversation(self) -> int:
        r = self.http.post("/api/conversations")
        assert r.status_code == 201, r.content
        return r.json()["id"]

    def send(self, conversation_id: int, text: str, cmid: str | None = None):
        cmid = cmid or f"m-{uuid.uuid4().hex[:16]}"
        return self.http.post(f"/api/conversations/{conversation_id}/messages",
                              {"client_message_id": cmid, "text": text}, content_type="application/json")

    def ask(self, text: str, conversation_id: int | None = None) -> dict:
        """Send one message in a (new) conversation and return the reply."""
        r = self.send(conversation_id or self.new_conversation(), text)
        assert r.status_code == 201, r.content
        return r.json()["reply"]

    def calculate(self, payload: dict):
        return self.http.post("/api/gst/calculate", payload, content_type="application/json")


@pytest.fixture
def api(db):
    return Api()


_real_sleep = time.sleep  # captured before any test swaps in the virtual clock


def yielding(cls):
    """A subclass of `cls` that hands the GIL to another thread on every attribute read and write.

    CPython rarely switches threads in the middle of a statement, so `self.count += 1`
    without a lock usually *looks* safe in tests, then loses updates under real load
    (or on free-threaded Python). With this subclass, an unsynchronised read-modify-write
    or check-then-act always interleaves with other threads. Code that holds a lock is
    unaffected: the other threads simply wait for it.
    """
    class Yielding(cls):
        def __getattribute__(self, name):
            _real_sleep(0)
            return super().__getattribute__(name)

        def __setattr__(self, name, value):
            _real_sleep(0)
            super().__setattr__(name, value)

    Yielding.__name__ = f"Yielding{cls.__name__}"
    return Yielding


def run_concurrently(target, n: int) -> list:
    """Run target(i) in n threads released together. Each thread closes its own DB connection."""
    barrier = threading.Barrier(n)
    results: list = [None] * n
    errors: list = []

    def worker(i):
        try:
            barrier.wait(timeout=10)
            results[i] = target(i)
        except BaseException as exc:  # noqa: BLE001 - surfaced below
            errors.append(exc)
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    assert not any(t.is_alive() for t in threads), "worker threads hung"
    if errors:
        raise errors[0]
    return results
