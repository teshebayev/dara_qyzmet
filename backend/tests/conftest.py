"""Общие хелперы для unit-тестов.

Тесты намеренно не требуют ни GPU/vLLM, ни Postgres, ни сети: проверяется
чистая бизнес-логика (пересчёт сумм, валидация, проверка накладной, auth).
Доменные объекты подменяются лёгкими заглушками через ``types.SimpleNamespace``.
"""
from __future__ import annotations

from types import SimpleNamespace


def discrepancy(**kw) -> SimpleNamespace:
    """Заглушка ``Discrepancy`` — только поля, читаемые в recalc.compute_delta."""
    kw.setdefault("amount_delta", None)
    kw.setdefault("qty_expected", None)
    kw.setdefault("qty_actual", None)
    kw.setdefault("qty_defect", None)
    kw.setdefault("price", None)
    kw.setdefault("price_new", None)
    return SimpleNamespace(**kw)


def invoice_item(**kw) -> SimpleNamespace:
    """Заглушка ``InvoiceItem`` для recalc / invoice_check."""
    kw.setdefault("confidence", None)
    return SimpleNamespace(**kw)


def invoice(items, total_sum=None, raw_ocr_json=None) -> SimpleNamespace:
    return SimpleNamespace(items=items, total_sum=total_sum, raw_ocr_json=raw_ocr_json)


def acceptance(discrepancies) -> SimpleNamespace:
    return SimpleNamespace(discrepancies=discrepancies)
