"""Task 3: calls to tax-model must time out, retry politely, and never do the same work twice."""
import pytest
from django.db import connection

from bot import usage
from bot.models import DailyUsage, Message
from tests.bot.conftest import run_concurrently

QUESTION = "What is reverse charge?"   # not in the local FAQ, so it goes to tax-model


def test_unknown_question_goes_to_tax_model(api, taxmodel):
    reply = api.ask(QUESTION)
    assert (reply["source"], reply["degraded"]) == ("upstream", False)
    assert reply["text"].startswith("Under reverse charge")
    assert taxmodel.stats()["work_done"] == 1


def test_503_is_retried_after_retry_after(api, taxmodel, virtual_clock):
    taxmodel.script("503", "503", "ok")
    reply = api.ask(QUESTION)
    assert reply["source"] == "upstream"
    assert len(virtual_clock.sleeps) == 2 and all(s >= 2 for s in virtual_clock.sleeps)


def test_502_html_is_retried(api, taxmodel):
    taxmodel.script("502", "ok")
    assert api.ask(QUESTION)["source"] == "upstream"


def test_429_waits_for_retry_after_without_extending_the_window(api, taxmodel, virtual_clock):
    taxmodel.script("throttle", "throttle", "ok")
    reply = api.ask(QUESTION)
    assert reply["source"] == "upstream"
    assert all(s >= 3 for s in virtual_clock.sleeps)
    assert taxmodel.stats()["throttle_window_max_s"] == 3, "a retry arrived before Retry-After"


def test_drop_off_is_replayed_not_redone(api, taxmodel):
    taxmodel.script("drop")
    assert api.ask(QUESTION)["source"] == "upstream"
    s = taxmodel.stats()
    assert s["work_done"] == 1 and s["tokens_spent"] == 1
    assert [e["hits"] for e in s["idempotency"].values()] == [1]


def test_slow_answer_within_read_timeout(api, taxmodel, settings):
    taxmodel.script(f"slow:{settings.TAXMODEL['READ_TIMEOUT'] - 0.5}")
    assert api.ask(QUESTION)["source"] == "upstream"
    assert taxmodel.stats()["requests_seen"] == 1


def test_timeout_then_retry_gets_the_same_answer(api, taxmodel, settings):
    taxmodel.script(f"slow:{settings.TAXMODEL['READ_TIMEOUT'] + 1}")
    assert api.ask(QUESTION)["source"] == "upstream"
    assert taxmodel.stats()["work_done"] == 1


def test_stall_gives_up_within_the_deadline(api, taxmodel, virtual_clock, settings):
    taxmodel.script("stall")
    reply = api.ask(QUESTION)
    assert (reply["source"], reply["degraded"]) == ("fallback", True)
    assert virtual_clock.monotonic() <= settings.TAXMODEL["DEADLINE_S"]
    assert taxmodel.stats()["work_done"] == 1, "a stalled request must not be started again"


def test_persistent_failure_stops_after_max_attempts(api, taxmodel, virtual_clock, settings):
    taxmodel.script(*["503"] * 20)
    reply = api.ask(QUESTION)
    assert reply["degraded"] is True
    assert taxmodel.stats()["requests_seen"] == settings.TAXMODEL["MAX_ATTEMPTS"]
    assert virtual_clock.monotonic() <= settings.TAXMODEL["DEADLINE_S"]


def test_client_errors_are_not_retried(api, taxmodel, settings, virtual_clock):
    taxmodel.engine.register_key(taxmodel.key, not_after=0.0)     # key expired: 401
    reply = api.ask(QUESTION)
    assert reply["degraded"] is True
    assert virtual_clock.sleeps == []
    assert usage.calls_today() == 1


def test_every_attempt_counts_against_the_daily_budget(api, taxmodel):
    taxmodel.script("503", "ok")
    api.ask(QUESTION)
    assert usage.calls_today() == 2


def test_spent_budget_skips_tax_model(api, taxmodel, settings):
    from django.utils import timezone
    DailyUsage.objects.create(day=timezone.localdate(), upstream_calls=settings.TAXMODEL["DAILY_CALL_BUDGET"])
    reply = api.ask(QUESTION)
    assert reply["degraded"] is True
    assert taxmodel.stats()["requests_seen"] == 0


def test_resending_a_message_returns_the_stored_reply(api, taxmodel):
    cid = api.new_conversation()
    first = api.send(cid, QUESTION, cmid="same-1")
    again = api.send(cid, QUESTION, cmid="same-1")
    assert (first.status_code, again.status_code) == (201, 200)
    assert first.json()["reply"]["id"] == again.json()["reply"]["id"]
    assert Message.objects.filter(conversation_id=cid).count() == 2
    assert taxmodel.stats()["work_done"] == 1


def test_history_is_sent_with_the_question(api, taxmodel):
    cid = api.new_conversation()
    api.send(cid, "hi", cmid="h1")
    api.send(cid, QUESTION, cmid="h2")
    assert api.send(cid, "What is place of supply?", cmid="h3").json()["reply"]["source"] == "upstream"
    assert taxmodel.stats()["work_done"] == 2


# ── races: these need real transactions and several DB connections ─────────────

@pytest.mark.django_db(transaction=True)
def test_double_submit_race_creates_one_message_and_one_call(taxmodel):
    from tests.bot.conftest import Api
    cid = Api().new_conversation()

    def submit(_):
        return Api().send(cid, QUESTION, cmid="dup-1").status_code

    statuses = run_concurrently(submit, 8)
    assert statuses.count(201) == 1, statuses
    assert set(statuses) <= {200, 201, 409}, statuses
    assert Message.objects.filter(conversation_id=cid, role="user").count() == 1
    assert Message.objects.filter(conversation_id=cid, role="assistant").count() == 1
    assert taxmodel.stats()["work_done"] == 1


@pytest.mark.django_db(transaction=True)
def test_usage_counter_does_not_lose_updates(settings):
    settings.TAXMODEL = {**settings.TAXMODEL, "DAILY_CALL_BUDGET": 10_000}

    def spend(_):
        return [usage.try_consume_upstream_call() for _ in range(5)]

    results = run_concurrently(spend, 20)
    assert all(all(r) for r in results)
    assert usage.calls_today() == 100


@pytest.mark.django_db(transaction=True)
def test_budget_is_never_exceeded_under_concurrency(settings):
    settings.TAXMODEL = {**settings.TAXMODEL, "DAILY_CALL_BUDGET": 10}
    granted = run_concurrently(lambda _: usage.try_consume_upstream_call(), 25)
    assert granted.count(True) == 10
    assert usage.calls_today() == 10
    assert connection.vendor == "postgresql", "race tests must run on Postgres"
