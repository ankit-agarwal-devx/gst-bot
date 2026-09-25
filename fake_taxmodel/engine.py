"""The fake's state machine. Implements FAILURE_CONTRACT.md §A3–A8 and §B3.

Transport-agnostic: `begin()` runs evaluation steps 1–5 and returns a Ticket;
the caller waits `ticket.delay` on its clock, then calls `finish()` to get the
Reply. Both the in-process transport and the HTTP server drive it this way.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
from urllib.parse import parse_qs, urlsplit

from fake_taxmodel.clock import RealClock
from fake_taxmodel.roll import PROFILES, roll

CHAT_PATH = "/v1/chat/completions"

BUCKET_CAPACITY = 5
REFILL_PER_SEC = 20 / 60
PENALTY_S = 5.0
WINDOW_CAP_S = 60.0
FORCED_THROTTLE_RETRY_AFTER = 3
OVERLOAD_RETRY_AFTER = 2
IDEMPOTENCY_TTL_S = 600.0
STALL_S = 40.0
FORCED_OK_DELAY_S = 0.2

HTML_502 = b"<html><body><h1>502 Bad Gateway</h1></body></html>"

_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ROLES = {"system", "user", "assistant", "tool"}
_ANSWERS_PATH = Path(__file__).with_name("answers.json")


def normalise_question(text: str) -> str:
    return " ".join(text.lower().split())


def parse_outcome(value: str) -> tuple[str, float] | None:
    """Parse a scripted / forced outcome. Returns (mode, delay) or None if invalid."""
    value = value.strip()
    if value == "ok":
        return "ok", FORCED_OK_DELAY_S
    if value == "stall":
        return "stall", STALL_S
    if value in ("drop", "503", "502", "throttle"):
        return value, 0.0
    if value.startswith("slow:"):
        try:
            seconds = float(value[5:])
        except ValueError:
            return None
        return ("slow", seconds) if seconds >= 0 else None
    return None


@dataclass
class KeyConfig:
    profile: str = "normal"
    not_before: float | None = None   # epoch seconds
    not_after: float | None = None
    force_header: bool = False        # honours X-Chaos-Force (ctr_ keys only)


@dataclass
class Reply:
    status: int
    headers: list[tuple[str, str]]
    body: bytes
    drop: bool = False  # send headers + first half of body, then close the connection

    def header(self, name: str) -> str | None:
        name = name.lower()
        for k, v in self.headers:
            if k.lower() == name:
                return v
        return None


@dataclass
class Ticket:
    reply: Reply
    delay: float = 0.0
    completes_at: float | None = None
    api_key: str | None = None
    idempotency_key: str | None = None
    done: bool = True


@dataclass
class _IdemEntry:
    body_hash: str
    state: str                    # "in_progress" | "completed"
    reply: Reply | None = None
    completed_at: float | None = None
    hits: int = 0


@dataclass
class _KeyState:
    api_key: str
    tokens: float
    last_refill: float
    window_end: float | None = None
    n: int = 0
    script: list[str] | None = None   # None: roll; list (even empty): scripted, then "ok"
    idem: dict[str, _IdemEntry] = field(default_factory=dict)
    tokens_spent: int = 0
    work_done: int = 0
    requests_seen: int = 0
    throttle_window_max_s: int = 0


class FakeTaxModel:
    def __init__(self, clock=None, answers_path: Path = _ANSWERS_PATH) -> None:
        self.clock = clock or RealClock()
        self.keys: dict[str, KeyConfig] = {}
        self.violations: list[str] = []
        self._state: dict[str, _KeyState] = {}
        self._pending: list[Ticket] = []
        self._lock = threading.RLock()
        data = json.loads(answers_path.read_text())
        self._answers: dict[str, str] = {normalise_question(q): a for q, a in data["answers"].items()}
        self._fallback: str = data["fallback"]

    @classmethod
    def with_defaults(cls, clock=None) -> "FakeTaxModel":
        """Engine with the contract-suite keys registered (§B2)."""
        engine = cls(clock=clock)
        engine.register_key("ctr_contract_suite_01", force_header=True)
        engine.register_key("ctr_parity", force_header=True)
        engine.register_key("ctr_expired", not_after=0.0)
        return engine

    # ── configuration ────────────────────────────────────────────────────

    def register_key(self, api_key: str, profile: str = "normal", *, not_before: float | None = None,
                     not_after: float | None = None, force_header: bool = False) -> None:
        if profile not in PROFILES:
            raise ValueError(f"unknown profile {profile!r}; expected one of {sorted(PROFILES)}")
        with self._lock:
            self.keys[api_key] = KeyConfig(profile, not_before, not_after, force_header)

    def set_script(self, api_key: str, outcomes: list[str]) -> None:
        """Scripted mode (§B3): one outcome per request that reaches the rate limiter."""
        for o in outcomes:
            if parse_outcome(o) is None:
                raise ValueError(f"invalid scripted outcome {o!r}")
        with self._lock:
            self._key_state(api_key).script = list(outcomes)

    def reset_rate_limit(self, api_key: str) -> None:
        """Fake-only (§B3): full bucket, no throttle window, as if the key had been idle for a while."""
        with self._lock:
            ks = self._key_state(api_key)
            ks.tokens = float(BUCKET_CAPACITY)
            ks.last_refill = self.clock.monotonic()
            ks.window_end = None

    # ── request handling ─────────────────────────────────────────────────

    def begin(self, method: str, target: str, headers: Mapping[str, str], body: bytes) -> Ticket:
        with self._lock:
            now = self.clock.monotonic()
            self._finalize_due(now)
            h = {k.lower(): v for k, v in headers.items()}
            url = urlsplit(target)

            if method == "GET" and url.path == "/healthz":
                return Ticket(self._json(200, {"status": "ok"}))
            if method == "GET" and url.path == "/_fake/stats":
                key = parse_qs(url.query).get("key", [None])[0]
                return Ticket(self._json(200, self.stats(key)))
            if url.path != CHAT_PATH:
                return Ticket(self._json(404, {"detail": "Not Found"}))
            if method != "POST":
                return Ticket(self._json(405, {"detail": "Method Not Allowed"}))
            return self._chat(now, h, body)

    def finish(self, ticket: Ticket) -> Reply:
        with self._lock:
            if not ticket.done:
                self._complete(ticket, self.clock.monotonic())
            return ticket.reply

    def stats(self, api_key: str | None = None) -> dict:
        with self._lock:
            self._finalize_due(self.clock.monotonic())
            if api_key is not None:
                return self._stats_for(self._key_state(api_key))
            return {k: self._stats_for(s) for k, s in self._state.items()}

    # ── steps 1–6 ────────────────────────────────────────────────────────

    def _chat(self, now: float, h: dict[str, str], body: bytes) -> Ticket:
        # Step 1: authenticate and validate.
        auth = h.get("authorization", "")
        if not auth.startswith("Bearer ") or not auth[7:].strip():
            return Ticket(self._json(401, {"detail": "missing bearer token"},
                                     extra=[("WWW-Authenticate", "Bearer")]))
        api_key = auth[7:].strip()
        cfg = self.keys.get(api_key)
        if cfg is None:
            return Ticket(self._json(401, {"detail": "invalid api key"},
                                     extra=[("WWW-Authenticate", "Bearer")]))
        wall = self.clock.time()
        if (cfg.not_before is not None and wall < cfg.not_before) or \
           (cfg.not_after is not None and wall > cfg.not_after):
            return Ticket(self._json(401, {"detail": "api key expired"}))

        ks = self._key_state(api_key)
        ks.requests_seen += 1
        self._refill(ks, now)

        req, error = self._parse(body)
        if error:
            return Ticket(self._json(error[0], {"detail": error[1]}, ks=ks))
        idem_key = h.get("idempotency-key")
        if idem_key is not None and not _IDEMPOTENCY_KEY_RE.match(idem_key):
            return Ticket(self._json(400, {"detail": "invalid Idempotency-Key header"}, ks=ks))
        body_hash = hashlib.sha256(body).hexdigest()

        # Steps 2–3: idempotency conflict / replay.
        if idem_key is not None:
            entry = ks.idem.get(idem_key)
            if entry and entry.state == "completed" and now - entry.completed_at >= IDEMPOTENCY_TTL_S:
                del ks.idem[idem_key]
                entry = None
            if entry is not None:
                if entry.body_hash != body_hash:
                    return Ticket(self._json(422, {"detail": "idempotency key reused with a different payload"}, ks=ks))
                if entry.state == "in_progress":
                    return Ticket(self._json(409, {"detail": "request with this idempotency key is in progress"},
                                             ks=ks, extra=[("Retry-After", "1")]))
                entry.hits += 1
                stored = entry.reply
                headers = [(k, v) for k, v in stored.headers
                           if k.lower() not in ("x-request-id", "x-ratelimit-limit", "x-ratelimit-remaining")]
                headers += self._common_headers(ks) + [("Idempotent-Replayed", "true")]
                return Ticket(Reply(stored.status, headers, stored.body))

        # Step 4: rate limit.
        if ks.window_end is not None and now < ks.window_end:
            ks.window_end = min(ks.window_end + PENALTY_S, now + WINDOW_CAP_S)
            return Ticket(self._throttled(ks, math.ceil(ks.window_end - now)))

        forced = None
        if cfg.force_header and "x-chaos-force" in h:
            forced = parse_outcome(h["x-chaos-force"])
        next_outcome = forced or (parse_outcome(ks.script[0]) if ks.script else None)
        if next_outcome and next_outcome[0] == "throttle":
            if forced is None:
                ks.script.pop(0)
            ks.window_end = now + FORCED_THROTTLE_RETRY_AFTER
            return Ticket(self._throttled(ks, FORCED_THROTTLE_RETRY_AFTER))
        if ks.tokens < 1.0:
            retry_after = int((1.0 - ks.tokens) / REFILL_PER_SEC) + 1
            ks.window_end = now + retry_after
            return Ticket(self._throttled(ks, retry_after))
        ks.tokens -= 1.0
        ks.tokens_spent += 1

        # Step 5: failure roll.
        n = ks.n
        ks.n += 1
        if forced is not None:
            mode, delay = forced
        elif ks.script:
            mode, delay = parse_outcome(ks.script.pop(0))
        elif ks.script is not None:
            mode, delay = parse_outcome("ok")
        else:
            mode, delay = roll(api_key, n, PROFILES[cfg.profile])

        if mode == "503":
            return Ticket(self._json(503, {"detail": "upstream overloaded"}, ks=ks,
                                     extra=[("Retry-After", str(OVERLOAD_RETRY_AFTER))]))
        if mode == "502":
            return Ticket(Reply(502, [("Content-Type", "text/html"), ("Content-Length", str(len(HTML_502)))]
                                + self._common_headers(ks), HTML_502))

        # Step 6: do the work.
        ks.work_done += 1
        reply = self._json(200, self._completion(api_key, n, req), ks=ks)
        reply.drop = mode == "drop"
        ticket = Ticket(reply, delay=delay, completes_at=now + delay, api_key=api_key,
                        idempotency_key=idem_key, done=False)
        if idem_key is not None:
            ks.idem[idem_key] = _IdemEntry(body_hash=body_hash, state="in_progress")
        if delay <= 0:
            self._complete(ticket, now)
        else:
            self._pending.append(ticket)
        return ticket

    # ── helpers ──────────────────────────────────────────────────────────

    def _key_state(self, api_key: str) -> _KeyState:
        ks = self._state.get(api_key)
        if ks is None:
            ks = _KeyState(api_key=api_key, tokens=float(BUCKET_CAPACITY), last_refill=self.clock.monotonic())
            self._state[api_key] = ks
        return ks

    @staticmethod
    def _refill(ks: _KeyState, now: float) -> None:
        elapsed = max(0.0, now - ks.last_refill)  # a key created mid-request is stamped after `now`
        ks.tokens = min(float(BUCKET_CAPACITY), ks.tokens + elapsed * REFILL_PER_SEC)
        ks.last_refill = max(ks.last_refill, now)

    def _finalize_due(self, now: float) -> None:
        for t in [t for t in self._pending if t.completes_at <= now]:
            self._complete(t, t.completes_at)

    def _complete(self, ticket: Ticket, at: float) -> None:
        ticket.done = True
        if ticket in self._pending:
            self._pending.remove(ticket)
        if ticket.idempotency_key is None:
            return
        entry = self._state[ticket.api_key].idem.get(ticket.idempotency_key)
        if entry is not None and entry.state == "in_progress":
            entry.state = "completed"
            entry.reply = Reply(ticket.reply.status, list(ticket.reply.headers), ticket.reply.body)
            entry.completed_at = at

    def _throttled(self, ks: _KeyState, retry_after: int) -> Reply:
        ks.throttle_window_max_s = max(ks.throttle_window_max_s, retry_after)
        return self._json(429, {"detail": f"rate limit exceeded for key '{ks.api_key}'"}, ks=ks,
                          extra=[("Retry-After", str(retry_after))])

    @staticmethod
    def _parse(body: bytes) -> tuple[dict | None, tuple[int, str] | None]:
        try:
            req = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return None, (422, "request body is not valid JSON")
        if not isinstance(req, dict):
            return None, (422, "request body must be a JSON object")
        if not isinstance(req.get("model"), str) or not req["model"]:
            return None, (422, "field 'model' is required and must be a string")
        msgs = req.get("messages")
        if not isinstance(msgs, list) or not msgs:
            return None, (422, "field 'messages' must be a non-empty list")
        for i, m in enumerate(msgs):
            if not isinstance(m, dict) or m.get("role") not in _ROLES or not isinstance(m.get("content"), str):
                return None, (422, f"messages[{i}] must have a valid 'role' and string 'content'")
        if "temperature" in req and req["temperature"] is not None and not isinstance(req["temperature"], (int, float)):
            return None, (422, "field 'temperature' must be a number")
        if "max_tokens" in req and req["max_tokens"] is not None and not isinstance(req["max_tokens"], int):
            return None, (422, "field 'max_tokens' must be an integer")
        if req.get("stream") is True:
            return None, (400, "streaming not implemented yet")
        return req, None

    def _completion(self, api_key: str, n: int, req: dict) -> dict:
        user_msgs = [m["content"] for m in req["messages"] if m["role"] == "user"]
        question = normalise_question(user_msgs[-1]) if user_msgs else ""
        answer = self._answers.get(question, self._fallback)
        prompt_tokens = sum(len(m["content"].split()) for m in req["messages"])
        completion_tokens = len(answer.split())
        return {
            "id": "chatcmpl-" + hashlib.sha256(f"{api_key}|{n}".encode()).hexdigest()[:12],
            "object": "chat.completion",
            "created": int(self.clock.time()),
            "model": req["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": answer},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
                      "total_tokens": prompt_tokens + completion_tokens},
        }

    @staticmethod
    def _common_headers(ks: _KeyState | None) -> list[tuple[str, str]]:
        headers = [("X-Request-Id", uuid.uuid4().hex)]
        if ks is not None:
            headers += [("X-RateLimit-Limit", str(BUCKET_CAPACITY)),
                        ("X-RateLimit-Remaining", str(int(math.floor(ks.tokens))))]
        return headers

    def _json(self, status: int, payload: dict, *, ks: _KeyState | None = None,
              extra: list[tuple[str, str]] | None = None) -> Reply:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        headers = [("Content-Type", "application/json"), ("Content-Length", str(len(body)))]
        headers += self._common_headers(ks) + (extra or [])
        return Reply(status, headers, body)

    @staticmethod
    def _stats_for(ks: _KeyState) -> dict:
        return {
            "tokens_spent": ks.tokens_spent,
            "work_done": ks.work_done,
            "requests_seen": ks.requests_seen,
            "n": ks.n,
            "idempotency": {k: {"state": e.state, "hits": e.hits} for k, e in ks.idem.items()},
            "throttle_window_max_s": ks.throttle_window_max_s,
        }
