import json
import os

_FAQ = None


def _load():
    global _FAQ
    if _FAQ is None:
        _FAQ = []
        with open(os.path.join(os.path.dirname(__file__), "faq.json")) as f:
            data = json.load(f)
        for item in data:
            keys = [clean(item["question"])]
            for a in item.get("alias", []):
                keys.append(clean(a))
            _FAQ.append((keys, item))
    return _FAQ


def clean(q):
    return q.lower().strip().rstrip("?")


def match(q):
    """Returns the FAQ item (dict) for question q, or None."""
    q = clean(q)
    for keys, item in _load():
        for k in keys:
            if q.startswith(k):
                return item
    return None
