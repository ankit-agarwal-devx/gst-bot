import logging
import time

import httpx
from django.conf import settings

from bot import faq, usage
from bot.models import Conversation, Message  # noqa: F401  (Conversation used by views)

log = logging.getLogger("bot")

SYSTEM = "You are a GST assistant for Indian businesses. Answer briefly and precisely."
SORRY = "Sorry, something went wrong. Please try again later."

_http = None


def _client():
    global _http
    if _http is None:
        # timeout=None: tax-model is an LLM and answers can take a while, don't cut it off
        _http = httpx.Client(base_url=settings.TAXMODEL["BASE_URL"], timeout=None)
    return _http


def reset_state():
    global _http
    _http = None


def ask_taxmodel(messages):
    cfg = settings.TAXMODEL
    tries = 0
    while True:
        tries += 1
        if not usage.try_consume_upstream_call():
            raise Exception("daily budget used up")
        try:
            r = _client().post(
                "/v1/chat/completions",
                json={"model": cfg["MODEL"], "messages": messages, "temperature": 0},
                headers={"Authorization": "Bearer " + cfg["API_KEY"]},
            )
            if r.status_code == 200:
                return r.json()["choices"][0]["message"]["content"]
            log.warning("tax-model returned %s: %s", r.status_code, r.text[:200])
        except (httpx.HTTPError, ValueError, KeyError) as e:
            log.warning("tax-model call failed: %s", e)
        if tries >= 10:
            raise Exception("tax-model failed after %d tries" % tries)
        time.sleep(0.5)


def history(conversation, user_msg):
    msgs = [{"role": "system", "content": SYSTEM}]
    for m in conversation.messages.all()[: settings.TAXMODEL["HISTORY_TURNS"]]:
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

    user_msg = Message.objects.create(conversation=conversation, role="user", text=text,
                                      client_message_id=client_message_id)
    conversation.save()  # bump updated_at

    item = faq.match(text)
    if item:
        reply_text, source, degraded = item["answer"], "faq", False
    else:
        try:
            reply_text, source, degraded = ask_taxmodel(history(conversation, user_msg)), "upstream", False
        except Exception:
            log.exception("could not get an answer from tax-model")
            reply_text, source, degraded = SORRY, "fallback", True

    reply = Message.objects.create(conversation=conversation, role="assistant", text=reply_text,
                                   reply_to=user_msg, source=source, degraded=degraded)
    return user_msg, reply, True
