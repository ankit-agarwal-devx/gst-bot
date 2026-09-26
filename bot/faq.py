import json
import os
import unicodedata

_FAQ = None


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
