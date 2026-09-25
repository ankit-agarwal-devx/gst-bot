"""Fake tax-model over real HTTP, for manual runs (FAILURE_CONTRACT.md §B3).

    python -m fake_taxmodel.server [--profile normal] [--port 8081] [--key cand_…]

Uses real time: a stall really takes 40 s.
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fake_taxmodel.clock import RealClock
from fake_taxmodel.engine import FakeTaxModel
from fake_taxmodel.roll import PROFILES

_CANDIDATE_KEY_RE = re.compile(r"^cand_[0-9a-f]{16}$")


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server: "FakeServer"

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        engine = self.server.engine
        ticket = engine.begin(self.command, self.path, dict(self.headers.items()), body)
        if ticket.delay > 0:
            engine.clock.sleep(ticket.delay)
        reply = engine.finish(ticket)
        try:
            self.send_response(reply.status)
            for k, v in reply.headers:
                self.send_header(k, v)
            self.end_headers()
            if reply.drop:
                self.wfile.write(reply.body[: len(reply.body) // 2])
                self.wfile.flush()
                self.connection.shutdown(socket.SHUT_RDWR)
                self.close_connection = True
            else:
                self.wfile.write(reply.body)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True  # client gave up (e.g. timed out on a stall)

    def log_message(self, fmt, *args) -> None:
        if self.server.verbose:
            super().log_message(fmt, *args)


class FakeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, engine: FakeTaxModel, host: str = "127.0.0.1", port: int = 0, verbose: bool = False):
        super().__init__((host, port), _Handler)
        self.engine = engine
        self.verbose = verbose

    @property
    def base_url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}"


def serve_in_thread(engine: FakeTaxModel, host: str = "127.0.0.1", port: int = 0) -> FakeServer:
    server = FakeServer(engine, host, port)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the fake tax-model over HTTP.")
    parser.add_argument("--key", help="API key to accept (default: the key in gstbot/variant.py, which the bot sends)")
    parser.add_argument("--profile", default="normal", choices=sorted(PROFILES))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--script", type=Path, help="JSON list of outcomes to play before random failures")
    parser.add_argument("--verbose", action="store_true", help="log every request")
    args = parser.parse_args()

    if args.key is None:
        try:
            from gstbot.variant import CANDIDATE_KEY
        except ImportError:
            parser.error("no --key given and gstbot/variant.py not found: run from the project root")
        args.key = CANDIDATE_KEY
    if not _CANDIDATE_KEY_RE.match(args.key):
        parser.error("key must look like cand_ followed by 16 hex characters")

    engine = FakeTaxModel.with_defaults(clock=RealClock())
    engine.register_key(args.key, profile=args.profile)
    if args.script:
        engine.set_script(args.key, json.loads(args.script.read_text()))

    server = FakeServer(engine, args.host, args.port, verbose=args.verbose)
    print(f"fake tax-model on {server.base_url}  (key {args.key}, profile {args.profile})", flush=True)
    print(f"  POST {server.base_url}/v1/chat/completions")
    print(f"  GET  {server.base_url}/_fake/stats?key={args.key}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
