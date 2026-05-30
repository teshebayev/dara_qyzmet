"""Детерминированный пересчёт сумм при расхождениях (ТЗ 5.3).

Все деньги — Decimal, округление до 2 знаков (банковское — ROUND_HALF_EVEN).
"""
from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal

from ..models import Acceptance, Discrepancy, Invoice

Q = Decimal("0.01")


def money(x) -> Decimal:
    return Decimal(str(x or 0)).quantize(Q, rounding=ROUND_HALF_EVEN)


def line_total(qty, price) -> Decimal:
    return money(Decimal(str(qty or 0)) * Decimal(str(price or 0)))


def compute_delta(d: Discrepancy) -> Decimal:
    """Влияние одной записи расхождения на сумму счёта (+/-)."""
    price = Decimal(str(d.price or 0))
    exp = Decimal(str(d.qty_expected or 0))
    act = Decimal(str(d.qty_actual or 0))
    if d.type == "shortage":            # недостача
        return money(-(exp - act) * price)
    if d.type == "surplus":             # излишек (принят)
        return money((act - exp) * price)
    if d.type == "defect":              # брак
        defect = Decimal(str(d.qty_defect or 0))
        return money(-defect * price)
    if d.type == "misgrade":            # пересорт: снять заявленное, принять факт
        price_new = Decimal(str(d.price_new or 0))
        return money(-(exp * price) + (act * price_new))
    return Decimal("0.00")


def invoice_original_sum(invoice: Invoice) -> Decimal:
    """Сумма по накладной: заявленный итог либо Σ по позициям."""
    if invoice.total_sum is not None:
        return money(invoice.total_sum)
    return money(sum((line_total(i.qty, i.price) for i in invoice.items), Decimal(0)))


def recompute(acceptance: Acceptance, invoice: Invoice) -> dict:
    """Возвращает {original_sum, corrected_sum, total_delta} и проставляет deltas."""
    original = invoice_original_sum(invoice)
    total_delta = Decimal("0.00")
    for d in acceptance.discrepancies:
        d.amount_delta = compute_delta(d)
        total_delta += d.amount_delta
    total_delta = money(total_delta)
    return {
        "original_sum": original,
        "corrected_sum": money(original + total_delta),
        "total_delta": total_delta,
    }
