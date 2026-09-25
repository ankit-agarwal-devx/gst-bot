"""GST invoice calculation.

calculate(data) takes the raw request body and returns (result, errors).
"""
import datetime

from bot.gstin import validate_gstin
from bot.states import STATES
from bot.utils import calc_round_off, money, parse_date, r2, to_num

OLD_RATES = [0, 0.25, 3, 5, 12, 18, 28]
NEW_RATES = [0, 0.25, 3, 5, 18, 40]      # GST 2.0 (22 Sep 2025)
NEW_RATES_FROM = datetime.date(2025, 9, 22)


def _rates_for(d):
    if d > NEW_RATES_FROM:
        return NEW_RATES
    return OLD_RATES


def calculate(data):
    errors = []
    supplier = (data.get("supplier_gstin") or "").strip().upper()
    buyer = data.get("buyer_gstin")
    if buyer:
        buyer = buyer.strip().upper()
    pos = data.get("place_of_supply")
    sez = data.get("is_sez", False)

    if not validate_gstin(supplier):
        errors.append("supplier_gstin is not a valid GSTIN")
    if buyer and not validate_gstin(buyer):
        errors.append("buyer_gstin is not a valid GSTIN")
    if pos is not None and pos not in STATES:
        errors.append("place_of_supply is not a valid state code")

    inv_date = parse_date(data.get("invoice_date") or "")
    if inv_date is None:
        errors.append("invoice_date must be YYYY-MM-DD")

    raw_lines = data.get("lines") or []
    if not raw_lines:
        errors.append("at least one line is required")

    lines = []
    for i, l in enumerate(raw_lines):
        try:
            qty = to_num(l["quantity"])
        except Exception:
            errors.append("lines[%d].quantity is not a number" % i)
            continue
        try:
            price = to_num(l["unit_price"])
        except Exception:
            errors.append("lines[%d].unit_price is not a number" % i)
            continue
        try:
            rate = to_num(l["rate"])
        except Exception:
            errors.append("lines[%d].rate is not a number" % i)
            continue
        disc = to_num(l.get("discount", 0) or 0)
        if qty <= 0:
            errors.append("lines[%d].quantity must be positive" % i)
        if price < 0:
            errors.append("lines[%d].unit_price must not be negative" % i)
        if disc < 0 or disc > qty * price:
            errors.append("lines[%d].discount must be between 0 and quantity x unit_price" % i)
        if inv_date and rate not in _rates_for(inv_date):
            errors.append("lines[%d].rate %s is not a GST rate on %s" % (i, l["rate"], inv_date))
        lines.append((l.get("description", ""), qty, price, rate, disc, l["rate"]))

    if errors:
        return None, errors

    supplier_state = supplier[:2]
    if buyer:
        pos = buyer[:2]
    elif not pos:
        pos = supplier_state

    inter = False
    if sez:
        inter = True
    if pos != supplier_state:
        inter = True
    ut = STATES[pos][1]

    out_lines = []
    totals = {"taxable_value": 0.0, "cgst": 0.0, "sgst": 0.0, "utgst": 0.0, "igst": 0.0}
    for desc, qty, price, rate, disc, rate_str in lines:
        taxable = r2(qty * price - disc)
        cgst = sgst = utgst = igst = 0.0
        if inter:
            igst = r2(taxable * rate / 100)
        else:
            cgst = r2(taxable * rate / 2 / 100)
            if ut:
                utgst = r2(taxable * rate / 2 / 100)
            else:
                sgst = r2(taxable * rate / 2 / 100)
        out_lines.append({
            "description": desc,
            "rate": str(rate_str),
            "taxable_value": money(taxable),
            "cgst": money(cgst),
            "sgst": money(sgst),
            "utgst": money(utgst),
            "igst": money(igst),
        })
        _add_to_totals(totals, taxable, rate, inter, ut)

    tax = totals["cgst"] + totals["sgst"] + totals["utgst"] + totals["igst"]
    invoice_value = totals["taxable_value"] + tax
    round_off = calc_round_off(invoice_value)
    grand_total = invoice_value - round_off

    result = {
        "supply_type": "inter_state" if inter else "intra_state",
        "supplier_state": supplier_state,
        "place_of_supply": pos,
        "lines": out_lines,
        "totals": {
            "taxable_value": money(totals["taxable_value"]),
            "cgst": money(totals["cgst"]),
            "sgst": money(totals["sgst"]),
            "utgst": money(totals["utgst"]),
            "igst": money(totals["igst"]),
            "tax": money(tax),
            "invoice_value": money(invoice_value),
            "round_off": money(round_off),
            "grand_total": money(grand_total),
        },
    }
    return result, []


def _add_to_totals(totals, taxable, rate, inter, ut):
    # kept separate so the summary can be rebuilt without the line details (used by the old export)
    totals["taxable_value"] += taxable
    if inter:
        totals["igst"] += r2(taxable * rate / 100)
    else:
        totals["cgst"] += r2(taxable * rate / 2 / 100)
        if ut:
            totals["utgst"] += r2(taxable * rate / 2 / 100)
        else:
            totals["sgst"] += r2(taxable * rate / 2 / 100)
