"""Тесты детерминированного пересчёта сумм (services/recalc.py)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.recalc import (
    compute_delta,
    invoice_original_sum,
    line_total,
    money,
    recompute,
)
from tests.conftest import acceptance, discrepancy, invoice, invoice_item


# --- money / line_total -------------------------------------------------------

def test_money_rounds_half_even():
    # ROUND_HALF_EVEN: .5 округляется к ближайшему чётному
    assert money("2.345") == Decimal("2.34")
    assert money("2.355") == Decimal("2.36")
    assert money(None) == Decimal("0.00")


def test_money_always_two_places():
    assert str(money(10)) == "10.00"


def test_line_total():
    assert line_total(3, "10.50") == Decimal("31.50")
    assert line_total(None, 5) == Decimal("0.00")
    assert line_total("2.5", "4") == Decimal("10.00")


# --- compute_delta по типам расхождений --------------------------------------

def test_delta_shortage_is_negative():
    d = discrepancy(type="shortage", qty_expected=10, qty_actual=7, price="100")
    assert compute_delta(d) == Decimal("-300.00")


def test_delta_surplus_is_positive():
    d = discrepancy(type="surplus", qty_expected=5, qty_actual=8, price="50")
    assert compute_delta(d) == Decimal("150.00")


def test_delta_defect_is_negative():
    d = discrepancy(type="defect", qty_defect=2, price="120")
    assert compute_delta(d) == Decimal("-240.00")


def test_delta_misgrade_swaps_price():
    # сняли заявленное (10 × 100), приняли факт (10 × 80)
    d = discrepancy(
        type="misgrade", qty_expected=10, qty_actual=10, price="100", price_new="80"
    )
    assert compute_delta(d) == Decimal("-200.00")


def test_delta_misgrade_different_quantities():
    d = discrepancy(
        type="misgrade", qty_expected=10, qty_actual=12, price="100", price_new="90"
    )
    # -(10*100) + (12*90) = -1000 + 1080
    assert compute_delta(d) == Decimal("80.00")


def test_delta_unknown_type_is_zero():
    d = discrepancy(type="unknown", qty_expected=10, qty_actual=1, price="100")
    assert compute_delta(d) == Decimal("0.00")


def test_delta_shortage_no_actual_loss_when_full():
    d = discrepancy(type="shortage", qty_expected=5, qty_actual=5, price="100")
    assert compute_delta(d) == Decimal("0.00")


# --- invoice_original_sum -----------------------------------------------------

def test_invoice_original_sum_by_lines():
    inv = invoice([
        invoice_item(qty=2, price="100.00"),
        invoice_item(qty="1.5", price="10.00"),
    ])
    assert invoice_original_sum(inv) == Decimal("215.00")


def test_invoice_original_sum_empty():
    assert invoice_original_sum(invoice([])) == Decimal("0.00")


# --- recompute (полный сценарий) ---------------------------------------------

def test_recompute_no_discrepancies():
    inv = invoice([invoice_item(qty=10, price="100")])
    acc = acceptance([])
    res = recompute(acc, inv)
    assert res == {
        "original_sum": Decimal("1000.00"),
        "corrected_sum": Decimal("1000.00"),
        "total_delta": Decimal("0.00"),
    }


def test_recompute_applies_and_persists_deltas():
    inv = invoice([invoice_item(qty=10, price="100")])
    d1 = discrepancy(type="shortage", qty_expected=10, qty_actual=8, price="100")
    d2 = discrepancy(type="defect", qty_defect=1, price="100")
    acc = acceptance([d1, d2])

    res = recompute(acc, inv)

    # deltas проставлены на самих записях
    assert d1.amount_delta == Decimal("-200.00")
    assert d2.amount_delta == Decimal("-100.00")
    assert res["original_sum"] == Decimal("1000.00")
    assert res["total_delta"] == Decimal("-300.00")
    assert res["corrected_sum"] == Decimal("700.00")


def test_recompute_surplus_increases_sum():
    inv = invoice([invoice_item(qty=5, price="200")])
    acc = acceptance([
        discrepancy(type="surplus", qty_expected=5, qty_actual=7, price="200"),
    ])
    res = recompute(acc, inv)
    assert res["corrected_sum"] == Decimal("1400.00")
    assert res["total_delta"] == Decimal("400.00")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
