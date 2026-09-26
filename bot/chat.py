import logging
import time
import hashlib
import json

import httpx
from django.conf import settings
from django.db import IntegrityError, transaction

from bot import faq, usage
from bot.models import Conversation, Message  # noqa: F401  (Conversation used by views)

log = logging.getLogger("bot")

SYSTEM = "You are a GST assistant for Indian businesses. Answer briefly and precisely."
SORRY = "Sorry, something went wrong. Please try again later."

_http = None


def _client():
    global _http
    if _http is None:
        cfg = settings.TAXMODEL
        timeout = httpx.Timeout(cfg["READ_TIMEOUT"], connect=cfg["CONNECT_TIMEOUT"])
        _http = httpx.Client(base_url=cfg["BASE_URL"], timeout=timeout)
    return _http


def reset_state():
    global _http
    _http = None


def ask_taxmodel(messages, idempotency_key=None):
    cfg = settings.TAXMODEL
    if idempotency_key is None:
        payload = json.dumps(messages, sort_keys=True, separators=(",", ":")).encode()
        idempotency_key = hashlib.sha256(payload).hexdigest()

    deadline = time.monotonic() + cfg["DEADLINE_S"]
    max_attempts = cfg["MAX_ATTEMPTS"]
    for attempt in range(max_attempts):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if not usage.try_consume_upstream_call():
            raise Exception("daily budget used up")

        timeout = httpx.Timeout(
            min(cfg["READ_TIMEOUT"], remaining),
            connect=min(cfg["CONNECT_TIMEOUT"], remaining),
        )
        response = None
        try:
            response = _client().post(
                "/v1/chat/completions",
                json={"model": cfg["MODEL"], "messages": messages, "temperature": 0},
                headers={
                    "Authorization": "Bearer " + cfg["API_KEY"],
                    "Idempotency-Key": idempotency_key,
                },
                timeout=timeout,
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            if response.status_code not in (409, 429, 502, 503):
                raise Exception("tax-model returned non-retryable status %s" % response.status_code)
            log.warning("tax-model returned %s: %s", response.status_code, response.text[:200])
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as e:
            log.warning("tax-model call failed: %s", e)

        if attempt + 1 >= max_attempts:
            break
        retry_after = response.headers.get("Retry-After") if response is not None else None
        try:
            delay = float(retry_after) if retry_after is not None else None
        except ValueError:
            delay = None
        if delay is None:
            delay = min(cfg["BACKOFF_BASE_S"] * (2 ** attempt), cfg["BACKOFF_CAP_S"])
        remaining = deadline - time.monotonic()
        if delay >= remaining:
            break
        time.sleep(delay)

    raise Exception("tax-model failed within the retry and deadline limits")


def history(conversation, user_msg):
    msgs = [{"role": "system", "content": SYSTEM}]
    previous = conversation.messages.exclude(pk=user_msg.pk).order_by("-created_at", "-pk")[
        : settings.TAXMODEL["HISTORY_TURNS"]
    ]
    for m in reversed(previous):
        msgs.append({"role": m.role, "content": m.text})
    msgs.append({"role": "user", "content": user_msg.text})
    return msgs


def post_message(conversation, client_message_id, text):
    """Returns (user_msg, reply, created)"""
    existing = Message.objects.filter(conversation=conversation, client_message_id=client_message_id,
                                      role="user").first()
    if existing:
        reply = Message.objects.filter(reply_to=existing).first()
        if reply:
            return existing, reply, False

    try:
        with transaction.atomic():
            user_msg = Message.objects.create(conversation=conversation, role="user", text=text,
                                              client_message_id=client_message_id)
    except IntegrityError:
        user_msg = Message.objects.get(conversation=conversation, client_message_id=client_message_id,
                                       role="user")
        reply = Message.objects.filter(reply_to=user_msg).first()
        return user_msg, reply, False
    conversation.save()  # bump updated_at

    item = faq.match(text)
    if item:
        reply_text, source, degraded = item["answer"], "faq", False
    else:
        try:
            reply_text, source, degraded = ask_taxmodel(
                history(conversation, user_msg), idempotency_key="msg-%d" % user_msg.pk
            ), "upstream", False
        except Exception:
            log.exception("could not get an answer from tax-model")
            reply_text, source, degraded = SORRY, "fallback", True

    reply = Message.objects.create(conversation=conversation, role="assistant", text=reply_text,
                                   reply_to=user_msg, source=source, degraded=degraded)
    return user_msg, reply, True
