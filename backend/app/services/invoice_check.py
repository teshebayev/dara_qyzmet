"""Проверка распознанной накладной на арифметические ошибки OCR/VLM.

Узкое место: при загрузке `InvoiceItem.line_total` уже считается как qty×price
(см. routers/invoices.py), поэтому «qty×price = line_total» по сохранённым данным
тривиально верно. Реальные расхождения видны при сравнении с ИСХОДНЫМИ числами
распознавания (`invoice.raw_ocr_json`): построчный `total` и `grand_total`.

Что делает:
* построчно сверяет qty×price с распознанной суммой строки;
* сверяет Σ(qty×price) с распознанным итогом (total_sum);
* помечает подозрительные строки и объясняет человеку, что не так;
* предлагает исправления (цена/кол-во/итог), но НИЧЕГО не меняет сам.
"""
from __future__ import annotations

from decimal import Decimal

from .recalc import money

# Допуск: абсолютный минимум + доля от суммы (OCR-округления не считаем ошибкой).
_ABS_TOL = Decimal("1.0")
_REL_TOL = Decimal("0.01")


def _tol(value: Decimal) -> Decimal:
    return max(_ABS_TOL, (abs(value) * _REL_TOL).quantize(Decimal("0.01")))


def _qty(x) -> Decimal:
    return Decimal(str(x or 0))


def _raw_items_by_name(raw: dict | None) -> dict[str, dict]:
    if not raw:
        return {}
    out: dict[str, dict] = {}
    for ri in raw.get("items", []):
        name = (ri.get("name") or "").strip().lower()
        if name:
            out.setdefault(name, ri)
    return out


def _check_item(item, raw_item: dict | None) -> dict:
    qty = _qty(item.qty)
    price = _qty(item.price)
    computed = money(qty * price)
    ocr_total = None
    if raw_item is not None and raw_item.get("total") is not None:
        ocr_total = money(raw_item["total"])

    issues: list[str] = []
    suggestions: list[dict] = []
    message: str | None = None

    if qty <= 0:
        issues.append("Нулевое или отрицательное количество")
    if price <= 0:
        issues.append("Нулевая или отрицательная цена")

    if ocr_total is not None and abs(computed - ocr_total) > _tol(ocr_total):
        issues.append(
            f"qty×price = {computed:g}, но в накладной сумма строки = {ocr_total:g}"
        )
        message = (
            f"Строка не сходится: {qty:g} × {price:g} = {computed:g}, "
            f"а в документе указано {ocr_total:g}. "
            "Скорее всего, цена или количество распознаны неверно."
        )
        if qty > 0:
            suggestions.append({
                "field": "price",
                "value": money(ocr_total / qty),
                "label": f"Цена → {money(ocr_total / qty):g} (при кол-ве {qty:g})",
            })
        if price > 0:
            qty_fix = (ocr_total / price).quantize(Decimal("0.001"))
            suggestions.append({
                "field": "qty",
                "value": qty_fix,
                "label": f"Кол-во → {qty_fix:g} (при цене {price:g})",
            })

    # сигнал низкой уверенности распознавания (даже если арифметика сошлась)
    if item.confidence is not None and item.confidence < 0.8 and not issues:
        issues.append("Низкая уверенность распознавания — проверьте строку")

    return {
        "invoice_item_id": item.id,
        "name": item.name,
        "qty": money(qty),
        "price": money(price),
        "line_total": money(item.line_total),
        "ocr_line_total": ocr_total,
        "ok": not issues,
        "issues": issues,
        "message": message,
        "suggestions": suggestions,
    }


def check_invoice(invoice) -> dict:
    """Строит отчёт проверки накладной (без изменения данных)."""
    raw_by_name = _raw_items_by_name(invoice.raw_ocr_json)
    raw_list = (invoice.raw_ocr_json or {}).get("items", [])

    item_reports: list[dict] = []
    for idx, item in enumerate(invoice.items):
        raw = raw_by_name.get((item.name or "").strip().lower())
        if raw is None and idx < len(raw_list):  # фолбэк: по позиции
            raw = raw_list[idx]
        item_reports.append(_check_item(item, raw))

    computed_total = money(sum((money(_qty(i.qty) * _qty(i.price)) for i in invoice.items), Decimal(0)))
    declared = money(invoice.total_sum) if invoice.total_sum is not None else None
    total_ok = declared is None or abs(computed_total - declared) <= _tol(declared)
    total_suggestion = None
    if not total_ok:
        total_suggestion = {
            "field": "total_sum",
            "value": computed_total,
            "label": f"Итог → {computed_total:g} (сумма строк)",
        }

    bad_items = [r for r in item_reports if not r["ok"]]
    ok = total_ok and not bad_items

    if ok:
        summary = "Накладная сходится: ошибок не найдено."
    else:
        parts = []
        if bad_items:
            parts.append(f"подозрительных строк: {len(bad_items)}")
        if not total_ok:
            parts.append(
                f"итог не сходится (распознано {declared:g}, сумма строк {computed_total:g})"
            )
        summary = "Найдены расхождения: " + "; ".join(parts) + "."

    return {
        "ok": ok,
        "summary": summary,
        "total": {
            "declared": declared,
            "computed": computed_total,
            "ok": total_ok,
            "suggestion": total_suggestion,
        },
        "items": item_reports,
    }
