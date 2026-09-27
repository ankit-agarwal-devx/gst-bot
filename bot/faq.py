import json
import os
import unicodedata

_FAQ = None
_STOP_WORDS = {"a", "an", "and", "are", "can", "do", "for", "how", "i", "is", "it", "me", "my",
               "of", "on", "or", "the", "to", "what", "with", "you"}


def _load():
    global _FAQ
    if _FAQ is None:
        _FAQ = []
        with open(os.path.join(os.path.dirname(__file__), "faq.json")) as f:
            data = json.load(f)
            print(data)
        for item in data:
            keys = [clean(item["question"])]
            for a in item.get("aliases", item.get("alias", [])):
                keys.append(clean(a))
            _FAQ.append((keys, item))
    return _FAQ


def clean(q):
    q = unicodedata.normalize("NFKC", q).casefold()
    normalized = []
    for char in q:
        if char in "'\u2018\u2019":
            continue
        normalized.append(" " if unicodedata.category(char).startswith("P") else char)
    return " ".join("".join(normalized).split())


def match(q):
    """Returns the FAQ item (dict) for question q, or None."""
    q = clean(q)
    for keys, item in _load():
        for k in keys:
            if q == k:
                return item
    return None


def related_questions(q, limit=3):
    query_tokens = set(clean(q).split()) - _STOP_WORDS
    if not query_tokens:
        return []

    entries = _load()
    item_tokens = [
        set().union(*(set(key.split()) - _STOP_WORDS for key in keys))
        for keys, _ in entries
    ]
    frequencies = {}
    for tokens in item_tokens:
        for token in tokens:
            frequencies[token] = frequencies.get(token, 0) + 1

    ranked = []
    for (_, item), tokens in zip(entries, item_tokens):
        shared = query_tokens & tokens
        score = sum(2 if frequencies[token] == 1 else 1 for token in shared)
        if score >= 2:
            ranked.append((score, item["question"]))
    ranked.sort(key=lambda result: (-result[0], result[1]))
    return [question for _, question in ranked[:limit]]
