"""Валидация: контрольный разряд БИН/ИИН (РК) и арифметика итога."""
from __future__ import annotations

from .domain import Invoice, ValidationReport

_W1 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
_W2 = [3, 4, 5, 6, 7, 8, 9, 10, 11, 1, 2]


def is_valid_bin(value: str | None) -> bool | None:
    """Проверка 12-значного БИН/ИИН РК по контрольному разряду.

    Возвращает None, если поле пустое (нечего проверять).
    """
    if not value:
        return None
    digits = [c for c in value if c.isdigit()]
    if len(digits) != 12:
        return False
    d = [int(c) for c in digits]
    control = sum(d[i] * _W1[i] for i in range(11)) % 11
    if control == 10:
        control = sum(d[i] * _W2[i] for i in range(11)) % 11
        if control == 10:
            return False
    return control == d[11]


def reconcile_total(inv: Invoice, tol: float = 0.5) -> tuple[bool | None, float | None]:
    """Σ(кол-во × цена) против заявленного итога. Дешёвая проверка качества OCR."""
    parts: list[float] = []
    for it in inv.items:
        if it.total is not None:
            parts.append(it.total)
        elif it.quantity is not None and it.unit_price is not None:
            parts.append(it.quantity * it.unit_price)
    if not parts:
        return None, None
    computed = round(sum(parts), 2)
    if inv.grand_total is None:
        return None, computed
    return abs(computed - inv.grand_total) <= tol, computed


def validate(inv: Invoice) -> ValidationReport:
    warnings: list[str] = []
    buyer_ok = is_valid_bin(inv.buyer_bin)
    supplier_ok = is_valid_bin(inv.supplier_bin)
    reconciled, computed = reconcile_total(inv)

    if buyer_ok is False:
        warnings.append("БИН пользователя не проходит контрольную проверку")
    if supplier_ok is False:
        warnings.append("БИН поставщика не проходит контрольную проверку")
    if reconciled is False:
        warnings.append(
            f"Итог не сходится: распознано {inv.grand_total}, расчётно {computed}"
        )
    if not inv.items:
        warnings.append("Не распознано ни одной товарной позиции")

    return ValidationReport(
        buyer_bin_valid=buyer_ok,
        supplier_bin_valid=supplier_ok,
        total_reconciled=reconciled,
        computed_total=computed,
        warnings=warnings,
    )
