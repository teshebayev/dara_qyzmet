"""Рендер «Акта о расхождении» в PDF (server-side, с кириллицей) через PyMuPDF.

PyMuPDF (fitz) уже используется для нормализации накладных, поэтому без новых
зависимостей. Кириллический шрифт берём из app/assets (DejaVu), чтобы вывод не
зависел от системных шрифтов контейнера.

Используется HTTP-эндпоинтом `GET /acceptance/{id}/act.pdf`, который, в свою
очередь, дёргает Telegram-бот по нажатию кнопки «Скачать акт (PDF)».
"""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

_ASSETS = Path(__file__).resolve().parent.parent / "assets"
_FONT_REGULAR = _ASSETS / "DejaVuSans.ttf"
_FONT_BOLD = _ASSETS / "DejaVuSans-Bold.ttf"

_F = "dv"        # обычный
_FB = "dvb"      # жирный

# Объекты шрифтов для точного измерения ширины текста (обрезка по колонке).
_RF = fitz.Font(fontfile=str(_FONT_REGULAR))
_BF = fitz.Font(fontfile=str(_FONT_BOLD))

# Колонки таблицы: (заголовок, ключ строки, ширина в пунктах).
_COLS = [
    ("№", "n", 28),
    ("Наименование", "name", 230),
    ("По док.", "qty_doc", 60),
    ("Факт", "qty_fact", 60),
    ("Излишек", "surplus", 70),
    ("Недостача", "shortage", 70),
    ("Брак", "defect", 60),
    ("Пересорт", "regrade", 70),
]


def _num(x) -> str:
    """Аккуратное число: 5 вместо 5.0, иначе как есть."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x) if x not in (None, "") else "—"
    if f == 0:
        return "—"
    if f == int(f):
        return str(int(f))
    return f"{f:.3f}".rstrip("0").rstrip(".")


def _money(x) -> str:
    try:
        f = float(x or 0)
    except (TypeError, ValueError):
        f = 0.0
    return f"{f:,.0f} ₸".replace(",", " ")


def render_act_pdf(meta: dict, rows: list[dict], totals: dict) -> bytes:
    """Собирает PDF акта о расхождении (A4 альбомная).

    meta:   number, date, place, supplier, supplier_bin, receiver, receiver_bin,
            invoice_number
    rows:   список {n, name, qty_doc, qty_fact, surplus, shortage, defect, regrade}
    totals: {doc_sum, pay_sum}
    """
    doc = fitz.open()
    page = doc.new_page(width=842, height=595)  # A4 landscape (pt)
    page.insert_font(fontname=_F, fontfile=str(_FONT_REGULAR))
    page.insert_font(fontname=_FB, fontfile=str(_FONT_BOLD))

    margin = 36
    x0 = margin
    right = page.rect.width - margin
    y = margin

    # — Заголовок —
    page.insert_text((x0, y + 6), "АКТ О РАСХОЖДЕНИИ", fontname=_FB, fontsize=16)
    y += 24
    page.insert_text(
        (x0, y), f"№ {meta.get('number', '—')} от {meta.get('date', '—')}"
        f"   ·   {meta.get('place', 'г. Алматы')}",
        fontname=_F, fontsize=10, color=(0.33, 0.33, 0.33),
    )
    y += 22

    # — Реквизиты сторон —
    def _party(label, name, binv):
        b = f", БИН {binv}" if binv and binv != "—" else ""
        return f"{label}: {name or '—'}{b}"

    page.insert_text((x0, y), _party("Поставщик", meta.get("supplier"), meta.get("supplier_bin")),
                     fontname=_F, fontsize=10)
    y += 16
    page.insert_text((x0, y), _party("Получатель", meta.get("receiver"), meta.get("receiver_bin")),
                     fontname=_F, fontsize=10)
    y += 16
    page.insert_text((x0, y), f"Накладная: № {meta.get('invoice_number', '—')}",
                     fontname=_F, fontsize=10)
    y += 22

    # — Таблица —
    total_w = sum(w for _, _, w in _COLS)
    scale = min(1.0, (right - x0) / total_w)
    widths = [w * scale for _, _, w in _COLS]
    row_h = 22

    def draw_row(values, top, *, bold=False, fill=None):
        cx = x0
        if fill:
            page.draw_rect(fitz.Rect(x0, top, x0 + sum(widths), top + row_h),
                           color=None, fill=fill)
        for (col, w), val in zip([(c, wd) for (c, _, _), wd in zip(_COLS, widths)], values):
            page.draw_rect(fitz.Rect(cx, top, cx + w, top + row_h),
                           color=(0.2, 0.2, 0.2), width=0.5)
            text = str(val)
            fs = 9
            # обрезаем длинный текст точно по ширине колонки (по метрикам шрифта)
            fnt = _BF if bold else _RF
            avail = w - 8
            if fnt.text_length(text, fs) > avail:
                while text and fnt.text_length(text + "…", fs) > avail:
                    text = text[:-1]
                text += "…"
            page.insert_text((cx + 4, top + 15), text,
                             fontname=_FB if bold else _F, fontsize=fs)
            cx += w
        return top + row_h

    y = draw_row([c for c, _, _ in _COLS], y, bold=True, fill=(0.93, 0.93, 0.93))

    if not rows:
        page.draw_rect(fitz.Rect(x0, y, x0 + sum(widths), y + row_h),
                       color=(0.2, 0.2, 0.2), width=0.5)
        page.insert_text((x0 + 6, y + 15), "Расхождений не выявлено", fontname=_F, fontsize=9)
        y += row_h
    else:
        for r in rows:
            vals = []
            for _, key, _w in _COLS:
                if key == "n":
                    vals.append(r.get("n", ""))
                elif key == "name":
                    vals.append(r.get("name", ""))
                else:
                    vals.append(_num(r.get(key)))
            y = draw_row(vals, y)

    y += 18

    # — Итоги по деньгам —
    doc_sum = totals.get("doc_sum", 0)
    pay_sum = totals.get("pay_sum", 0)
    delta = float(pay_sum or 0) - float(doc_sum or 0)
    page.insert_text((x0, y), f"Сумма по документам: {_money(doc_sum)}", fontname=_F, fontsize=11)
    y += 18
    page.insert_text((x0, y), f"Сумма к оплате (с учётом расхождений): {_money(pay_sum)}",
                     fontname=_FB, fontsize=11)
    y += 18
    sign = "0 ₸" if abs(delta) < 0.005 else ("−" if delta < 0 else "+") + _money(abs(delta))
    page.insert_text((x0, y), f"Отклонение: {sign}", fontname=_FB, fontsize=11)
    y += 36

    # — Подписи —
    page.insert_text((x0, y), "Сдал: __________________________   ", fontname=_F, fontsize=10)
    page.insert_text((x0 + 360, y), "Принял: __________________________", fontname=_F, fontsize=10)

    return doc.tobytes()
