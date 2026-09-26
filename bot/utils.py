import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
RUPEE = Decimal("1")

def r2(x):
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def money(x):
    return format(Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP), ".2f")


def calc_round_off(amount):
    """round off = difference between the invoice amount and the amount rounded to rupees"""
    amount = Decimal(str(amount))
    rounded = amount.quantize(RUPEE, rounding=ROUND_HALF_UP)
    return (rounded - amount).quantize(CENT, rounding=ROUND_HALF_UP)


def parse_date(s):
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def to_num(v):
    if isinstance(v, (bool, float)):
        raise InvalidOperation
    number = Decimal(str(v))
    if not number.is_finite():
        raise InvalidOperation
    return number
