import re

from bot.states import STATES

CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GSTIN_REGEX = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"


def validate_gstin(g):
    """True if g is a valid GSTIN. Used by the calculator and (old) invoice import."""
    if not g:
        return False
    g = g.upper()
    if not re.match(GSTIN_REGEX, g):
        return False
    if g[:2] not in STATES:
        return False
    return get_check_char(g[:14]) == g[14]


def get_check_char(s):
    # GSTN check digit: weights alternate 2,1,2,1... over the first 14 chars,
    # each product is split into quotient + remainder mod 36
    factor = 2
    total = 0
    for c in s:
        v = CHARS.index(c) * factor
        total = total + (v // 36) + (v % 36)
        factor = 1 if factor == 2 else 2
    return CHARS[(36 - (total % 36)) % 36]
