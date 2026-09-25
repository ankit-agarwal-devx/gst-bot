"""Task 4: when tax-model keeps failing, stop calling it for a while and still help the user."""
import pytest

from bot import chat
from tests.bot.conftest import run_concurrently, yielding

try:
    from bot.breaker import CLOSED, HALF_OPEN, OPEN, CircuitBreaker
except ImportError:  # task 4 not started: these tests fail, the rest of the suite still runs
    CLOSED = HALF_OPEN = OPEN = CircuitBreaker = None


@pytest.fixture(autouse=True)
def _breaker_exists():
    if CircuitBreaker is None:
        pytest.fail("bot/breaker.py does not define CircuitBreaker, CLOSED, OPEN and HALF_OPEN yet", pytrace=False)
    if not hasattr(chat, "breaker"):
        pytest.fail("bot.chat has no module-level `breaker` (a CircuitBreaker) yet", pytrace=False)

QUESTION = "What is reverse charge?"


@pytest.fixture
def threshold(settings):
    return settings.BREAKER["FAILURE_THRESHOLD"]


@pytest.fixture
def open_seconds(settings):
    return settings.BREAKER["OPEN_SECONDS"]


def fail_calls(api, taxmodel, n):
    """n user questions whose tax-model calls fail on every attempt; afterwards tax-model is healthy again."""
    taxmodel.script(*["503"] * 1_000)
    for _ in range(n):
        assert api.ask(QUESTION)["degraded"] is True
    taxmodel.script()
    taxmodel.engine.reset_rate_limit(taxmodel.key)


def test_breaker_opens_after_threshold_failed_calls(api, taxmodel, virtual_clock, threshold):
    fail_calls(api, taxmodel, threshold)
    assert chat.breaker.state == OPEN
    seen, t = taxmodel.stats()["requests_seen"], virtual_clock.monotonic()
    reply = api.ask(QUESTION)
    assert (reply["source"], reply["degraded"]) == ("fallback", True)
    assert taxmodel.stats()["requests_seen"] == seen, "an open breaker must not call tax-model"
    assert virtual_clock.monotonic() == t, "an open breaker must answer without waiting"


def test_fewer_failures_do_not_open_the_breaker(api, taxmodel, threshold):
    fail_calls(api, taxmodel, threshold - 1)
    assert chat.breaker.state == CLOSED
    assert api.ask(QUESTION)["source"] == "upstream"


def test_success_resets_the_failure_count(api, taxmodel, threshold):
    fail_calls(api, taxmodel, threshold - 1)
    assert api.ask(QUESTION)["source"] == "upstream"
    fail_calls(api, taxmodel, threshold - 1)
    assert chat.breaker.state == CLOSED


def test_half_open_trial_success_closes_the_breaker(api, taxmodel, virtual_clock, threshold, open_seconds):
    fail_calls(api, taxmodel, threshold)
    virtual_clock.advance(open_seconds + 0.01)  # just past the boundary: clock arithmetic is floating point
    assert api.ask(QUESTION)["source"] == "upstream"
    assert chat.breaker.state == CLOSED


def test_half_open_trial_failure_reopens_the_breaker(api, taxmodel, virtual_clock, threshold, open_seconds):
    fail_calls(api, taxmodel, threshold)
    virtual_clock.advance(open_seconds + 0.01)  # just past the boundary: clock arithmetic is floating point
    fail_calls(api, taxmodel, 1)
    assert chat.breaker.state == OPEN
    seen = taxmodel.stats()["requests_seen"]
    assert api.ask(QUESTION)["degraded"] is True
    assert taxmodel.stats()["requests_seen"] == seen


def test_breaker_stays_open_for_open_seconds(api, taxmodel, virtual_clock, threshold, open_seconds):
    fail_calls(api, taxmodel, threshold)
    virtual_clock.advance(open_seconds - 0.1)
    seen = taxmodel.stats()["requests_seen"]
    api.ask(QUESTION)
    assert taxmodel.stats()["requests_seen"] == seen


def test_spent_budget_does_not_trip_the_breaker(api, taxmodel, settings, threshold):
    from django.utils import timezone

    from bot.models import DailyUsage
    DailyUsage.objects.create(day=timezone.localdate(), upstream_calls=settings.TAXMODEL["DAILY_CALL_BUDGET"])
    for _ in range(threshold + 1):
        assert api.ask(QUESTION)["degraded"] is True
    assert chat.breaker.failures == 0, "our own budget is not a tax-model failure"
    assert chat.breaker.state == CLOSED


def test_faq_still_works_while_the_breaker_is_open(api, taxmodel, threshold):
    fail_calls(api, taxmodel, threshold)
    reply = api.ask("What is GST?")
    assert (reply["source"], reply["degraded"]) == ("faq", False)


def test_fallback_suggests_related_faq_questions(api, taxmodel, threshold):
    fail_calls(api, taxmodel, threshold)
    reply = api.ask("Do I need an e-way bill for goods worth Rs 60,000?")
    assert "busy" in reply["text"]
    assert "- What is an e-way bill?" in reply["text"]


def test_fallback_without_related_questions(api, taxmodel, threshold):
    fail_calls(api, taxmodel, threshold)
    reply = api.ask("Zzz qqq?")
    assert reply["text"].endswith("Please try again in a minute.")


def test_degraded_replies_are_not_sent_as_history(api, taxmodel, virtual_clock, settings):
    cid = api.new_conversation()
    taxmodel.script(*["503"] * settings.TAXMODEL["MAX_ATTEMPTS"])
    api.send(cid, QUESTION, cmid="d1")
    history = chat.history(chat.Message.objects.get(client_message_id="d1").conversation,
                           chat.Message.objects.get(client_message_id="d1"))
    assert all("busy" not in m["content"] for m in history)


# ── the breaker is shared by every request thread ──────────────────────────────

def test_concurrent_failures_are_all_counted():
    b = yielding(CircuitBreaker)(failure_threshold=1_000, open_seconds=30)
    run_concurrently(lambda _: [b.record_failure() for _ in range(25)], 8)
    assert b.failures == 200, "failures were lost: the counter is not updated atomically"


def test_half_open_admits_exactly_one_trial(virtual_clock):
    for _ in range(20):  # the race window is small: give it many chances to show
        b = yielding(CircuitBreaker)(failure_threshold=1, open_seconds=30)
        b.record_failure()
        virtual_clock.advance(30)
        allowed = run_concurrently(lambda _: b.allow(), 8)
        assert allowed.count(True) == 1, f"{allowed.count(True)} callers got the half-open trial"
        assert b.state == HALF_OPEN
