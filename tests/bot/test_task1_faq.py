"""Task 1: the bot must recognise its own FAQ however the question is typed.

tax-model is unreachable in these tests: a question the FAQ misses gets a fallback, never an answer.
"""
import pytest

WHAT_IS_GST = "GST (Goods and Services Tax) is a destination-based indirect tax"


@pytest.mark.parametrize("question", [
    "What is GST?",
    "what is gst",
    "WHAT IS GST",
    "  What   is\tGST?  ",
    "What is GST???",
    "What is GST ?",
    "What’s GST?",
    "what's gst",
    "Whats GST",
    "ｗｈａｔ ｉｓ ＧＳＴ？",
])
def test_faq_matches_any_casing_spacing_or_punctuation(api, unreachable_taxmodel, question):
    reply = api.ask(question)
    assert reply["source"] == "faq"
    assert reply["text"].startswith(WHAT_IS_GST)
    assert unreachable_taxmodel == [], "FAQ answers must not call tax-model"


@pytest.mark.parametrize("question,expected_start", [
    ("hi", "Hello!"),
    ("E-way bill meaning", "An e-way bill"),
    ("e way bill meaning", "An e-way bill"),
    ("CGST vs SGST vs IGST", "Within one state"),
    ("cgst, sgst, igst", "Within one state"),
])
def test_faq_aliases(api, unreachable_taxmodel, question, expected_start):
    reply = api.ask(question)
    assert reply["source"] == "faq"
    assert reply["text"].startswith(expected_start)


@pytest.mark.parametrize("question", [
    "What is GSTIN?",           # must not match "What is GST?" by prefix
    "What is GST on gold?",     # must not match by substring
    "gst",
])
def test_faq_never_matches_partially(api, unreachable_taxmodel, question):
    reply = api.ask(question)
    assert not (reply["source"] == "faq" and reply["text"].startswith(WHAT_IS_GST))


def test_what_is_gstin_gets_the_gstin_answer(api, unreachable_taxmodel):
    reply = api.ask("what is GSTIN")
    assert reply["source"] == "faq" and reply["text"].startswith("A GSTIN is")


def test_conversation_history_is_returned_in_order(api, unreachable_taxmodel):
    cid = api.new_conversation()
    api.send(cid, "hi", cmid="a1")
    api.send(cid, "What is GST?", cmid="a2")
    r = api.http.get(f"/api/conversations/{cid}/messages")
    msgs = r.json()["messages"]
    assert [(m["role"], m["client_message_id"]) for m in msgs] == [
        ("user", "a1"), ("assistant", None), ("user", "a2"), ("assistant", None)]


@pytest.mark.parametrize("body,error", [
    ({"text": "hi"}, "client_message_id"),
    ({"client_message_id": "has space", "text": "hi"}, "client_message_id"),
    ({"client_message_id": "x1", "text": "   "}, "text"),
    ({"client_message_id": "x1", "text": "a" * 2001}, "at most 2000"),
])
def test_message_validation(api, body, error):
    cid = api.new_conversation()
    r = api.http.post(f"/api/conversations/{cid}/messages", body, content_type="application/json")
    assert r.status_code == 400
    assert any(error in e for e in r.json()["errors"])


def test_unknown_conversation_is_404(api):
    assert api.send(999_999, "hi").status_code == 404
