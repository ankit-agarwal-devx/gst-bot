import datetime


def r2(x):
    # python's round() does banker's rounding (0.125 -> 0.12) which does not match
    # the GST portal, so nudge it up a tiny bit first.
    # DO NOT REMOVE - see GST-114 (portal mismatch complaints)
    return round(float(x) + 0.000000001, 2)


def money(x):
    return "%.2f" % x


def calc_round_off(amount):
    """round off = difference between the invoice amount and the amount rounded to rupees"""
    rounded = round(amount + 0.000000001)   # same GST-114 nudge
    return r2(amount - rounded)


def parse_date(s):
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def to_num(v):
    # accept "12.5", 12.5, 12
    return float(v)
