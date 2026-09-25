"""Task 2: the invoice calculator must split and round GST exactly as the rules say."""
import pytest

KA = "29AABCG1234K1ZO"   # Karnataka
MH = "27AACCM5678P1ZN"   # Maharashtra
CH = "04AADCC4321L1ZY"   # Chandigarh: UT without a legislature
DL = "07AAECD8765Q1ZS"   # Delhi: has a legislature
AFTER = "2025-10-01"
BEFORE = "2025-09-21"


def invoice(lines, supplier=KA, date=AFTER, **extra):
    return {"supplier_gstin": supplier, "invoice_date": date, "lines": lines, **extra}


def line(qty="1", price="100", rate="18", discount=None, description="item"):
    d = {"description": description, "quantity": qty, "unit_price": price, "rate": rate}
    if discount is not None:
        d["discount"] = discount
    return d


def calc_ok(api, payload):
    r = api.calculate(payload)
    assert r.status_code == 200, r.content
    return r.json()


def test_intra_state_splits_into_cgst_and_sgst(api):
    out = calc_ok(api, invoice([line("3", "333.33", "18")], buyer_gstin=KA))
    assert out["supply_type"] == "intra_state"
    assert out["lines"][0] == {"description": "item", "rate": "18", "taxable_value": "999.99",
                               "cgst": "90.00", "sgst": "90.00", "utgst": "0.00", "igst": "0.00"}
    t = out["totals"]
    assert (t["tax"], t["invoice_value"], t["round_off"], t["grand_total"]) == ("180.00", "1179.99", "0.01", "1180.00")


def test_inter_state_is_igst(api):
    out = calc_ok(api, invoice([line("3", "333.33", "18")], buyer_gstin=MH))
    assert out["supply_type"] == "inter_state"
    assert out["place_of_supply"] == "27"
    assert (out["totals"]["igst"], out["totals"]["cgst"], out["totals"]["sgst"]) == ("180.00", "0.00", "0.00")
    assert out["totals"]["grand_total"] == "1180.00"


def test_each_half_is_rounded_separately(api):
    # 100.10 x 2.5% = 2.5025 -> 2.50 per half, so intra-state tax is 5.00 while IGST would be 5.01
    intra = calc_ok(api, invoice([line("1", "100.10", "5")]))
    inter = calc_ok(api, invoice([line("1", "100.10", "5")], buyer_gstin=MH))
    assert (intra["totals"]["cgst"], intra["totals"]["sgst"], intra["totals"]["tax"]) == ("2.50", "2.50", "5.00")
    assert inter["totals"]["igst"] == "5.01"


@pytest.mark.parametrize("price,igst", [
    ("10.10", "0.51"),   # 0.505 exactly
    ("2.50", "0.13"),    # 0.125 exactly
    ("20.10", "1.01"),   # 1.005 exactly
])
def test_half_paisa_rounds_up_not_to_even(api, price, igst):
    out = calc_ok(api, invoice([line("1", price, "5")], buyer_gstin=MH))
    assert out["totals"]["igst"] == igst


def test_large_invoice_is_exact_to_the_paisa(api):
    out = calc_ok(api, invoice([line("10", "45678901.01", "5")], buyer_gstin=MH))
    assert out["lines"][0]["taxable_value"] == "456789010.10"
    assert out["totals"]["igst"] == "22839450.51"


def test_tax_is_rounded_per_line_then_summed(api):
    lines = [line("1", "10.10", "5"), line("1", "10.10", "5"), line("1", "10.10", "5")]
    out = calc_ok(api, invoice(lines, buyer_gstin=MH))
    assert [ln["igst"] for ln in out["lines"]] == ["0.51"] * 3
    assert out["totals"]["igst"] == "1.53"   # not round(1.515) = 1.52


def test_discount_reduces_taxable_value(api):
    out = calc_ok(api, invoice([line("2", "500", "18", discount="100")], buyer_gstin=MH))
    assert out["lines"][0]["taxable_value"] == "900.00"
    assert out["totals"]["igst"] == "162.00"


def test_ut_without_legislature_charges_utgst(api):
    out = calc_ok(api, invoice([line("1", "1000", "18")], supplier=CH, buyer_gstin=CH))
    t = out["totals"]
    assert (t["cgst"], t["utgst"], t["sgst"], t["igst"]) == ("90.00", "90.00", "0.00", "0.00")


def test_delhi_charges_sgst_not_utgst(api):
    out = calc_ok(api, invoice([line("1", "1000", "18")], supplier=DL, buyer_gstin=DL))
    assert (out["totals"]["sgst"], out["totals"]["utgst"]) == ("90.00", "0.00")


def test_sez_supply_is_always_igst(api):
    out = calc_ok(api, invoice([line("1", "1000", "18")], buyer_gstin=KA, sez=True))
    assert out["supply_type"] == "inter_state"
    assert out["totals"]["igst"] == "180.00"


def test_place_of_supply_overrides_buyer_state(api):
    out = calc_ok(api, invoice([line("1", "1000", "18")], buyer_gstin=MH, place_of_supply="29"))
    assert out["supply_type"] == "intra_state" and out["place_of_supply"] == "29"


def test_no_buyer_means_local_sale(api):
    out = calc_ok(api, invoice([line("1", "1000", "5")]))
    assert out["supply_type"] == "intra_state" and out["place_of_supply"] == "29"


@pytest.mark.parametrize("price,round_off,grand", [
    ("1000.34", "-0.34", "1000.00"),
    ("1000.50", "0.50", "1001.00"),
    ("1000.49", "-0.49", "1000.00"),
])
def test_grand_total_rounds_half_up_to_the_rupee(api, price, round_off, grand):
    out = calc_ok(api, invoice([line("1", price, "0")]))
    assert (out["totals"]["round_off"], out["totals"]["grand_total"]) == (round_off, grand)


@pytest.mark.parametrize("rate,date,ok", [
    ("12", BEFORE, True), ("28", BEFORE, True), ("40", BEFORE, False),
    ("12", AFTER, False), ("28", AFTER, False), ("40", AFTER, True),
    ("18", BEFORE, True), ("18", AFTER, True), ("0.25", AFTER, True), ("7", AFTER, False),
])
def test_allowed_rates_depend_on_invoice_date(api, rate, date, ok):
    r = api.calculate(invoice([line("1", "100", rate)], date=date))
    assert (r.status_code == 200) is ok, r.content


def test_rate_change_takes_effect_on_22_september_2025(api):
    assert api.calculate(invoice([line("1", "100", "12")], date="2025-09-22")).status_code == 400
    assert api.calculate(invoice([line("1", "100", "40")], date="2025-09-22")).status_code == 200


@pytest.mark.parametrize("payload,error", [
    (invoice([line()], supplier="29AABCG1234K1ZP"), "supplier_gstin"),     # wrong check character
    (invoice([line()], supplier="25AABCG1234K1ZO"), "supplier_gstin"),     # retired state code
    (invoice([line()], buyer_gstin="27AACCM5678P1ZX"), "buyer_gstin"),
    (invoice([line()], place_of_supply="99"), "place_of_supply"),
    (invoice([]), "at least one line"),
    (invoice([line(qty="0")]), "quantity"),
    (invoice([line(price="-1")]), "unit_price"),
    (invoice([line(discount="101")]), "discount"),
    (invoice([{"quantity": 1.5, "unit_price": "10", "rate": "5"}]), "quantity"),   # JSON float
    (invoice([line(qty="abc")]), "quantity"),
    (invoice([line(qty="NaN")]), "quantity"),
    (invoice([line()], date="2025-13-01"), "invoice_date"),
    (invoice([line()], sez="yes"), "sez"),
])
def test_validation_errors(api, payload, error):
    r = api.calculate(payload)
    assert r.status_code == 400, r.content
    assert any(error in e for e in r.json()["errors"]), r.json()


def test_lowercase_gstin_is_accepted(api):
    out = calc_ok(api, invoice([line()], supplier=KA.lower(), buyer_gstin=MH.lower()))
    assert out["supply_type"] == "inter_state"
