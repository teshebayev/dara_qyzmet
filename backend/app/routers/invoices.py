"""Накладная: загрузка фото/PDF -> VLM -> редактирование -> подтверждение (ТЗ 6.3, 7)."""
from __future__ import annotations

import uuid
from datetime import date

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import Principal, get_principal, require_role
from ..models import Invoice, InvoiceItem, Order, Product
from ..schemas import (
    InvoiceCheckOut,
    InvoiceHeadPatch,
    InvoiceItemPatch,
    InvoiceOut,
)
from ..services.invoice_check import check_invoice
from ..services.recalc import line_total
from ..vlm.client import recognize
from ..vlm.pdf import normalize

router = APIRouter(prefix="/api/v1", tags=["invoices"])

MAX_BYTES = 25 * 1024 * 1024


def _match_product(db: Session, org_id: uuid.UUID, barcode: str | None):
    if not barcode:
        return None
    return db.query(Product).filter(
        Product.organization_id == org_id, Product.barcode == barcode
    ).first()


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


@router.post("/orders/{order_id}/invoice/upload", response_model=InvoiceOut)
async def upload_invoice(
    order_id: uuid.UUID,
    file: UploadFile = File(...),
    p: Principal = Depends(require_role("store")),
    db: Session = Depends(get_db),
) -> Invoice:
    order = db.get(Order, order_id)
    if not order or order.store_org_id != p.org_id:
        raise HTTPException(404, "Заявка не найдена")

    data = await file.read()
    if not data:
        raise HTTPException(400, "Пустой файл")
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Файл больше 25 МБ")

    try:
        pages = normalize(data, file.content_type or "", file.filename or "")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    try:
        parsed, backend = recognize(pages)
    except httpx.HTTPError as e:
        raise HTTPException(502, "Не удалось распознать накладную: модель (vLLM) недоступна") from e

    # создать/обновить накладную
    invoice = order.invoice or Invoice(order_id=order.id)
    invoice.supplier_name = parsed.supplier
    invoice.invoice_number = parsed.invoice_number
    invoice.invoice_date = _parse_date(parsed.date)
    invoice.total_sum = parsed.grand_total
    invoice.ocr_status = "done"
    invoice.raw_ocr_json = parsed.model_dump()
    invoice.source_file_url = f"upload://{file.filename}"
    invoice.items = []
    for li in parsed.items:
        qty = li.quantity or 0
        price = li.unit_price or 0
        prod = _match_product(db, p.org_id, li.article)
        invoice.items.append(
            InvoiceItem(
                product_id=prod.id if prod else None,
                name=li.name or "—",
                barcode=li.article,
                qty=qty,
                price=price,
                line_total=line_total(qty, price),
                # «уверенность» в mock задаём по полноте полей (демо подсветки)
                confidence=0.95 if (li.name and li.quantity and li.unit_price) else 0.65,
                was_edited=False,
            )
        )
    db.add(invoice)
    if order.status == "shipped":
        order.status = "receiving"
    db.commit()
    db.refresh(invoice)
    return invoice


@router.get("/invoices/{invoice_id}/check", response_model=InvoiceCheckOut)
def check_invoice_route(
    invoice_id: uuid.UUID,
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    """Проверка накладной на ошибки распознавания (арифметика строк и итога).

    Только читает и предлагает исправления — ничего не меняет (ТЗ: агент не
    подтверждает сам). Применение правок — через PATCH соответствующих позиций.
    """
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "Накладная не найдена")
    order = db.get(Order, invoice.order_id)
    if order.store_org_id != p.org_id and p.role != "admin":
        raise HTTPException(403, "Нет доступа")
    return check_invoice(invoice)


@router.get("/invoices/{invoice_id}", response_model=InvoiceOut)
def get_invoice(
    invoice_id: uuid.UUID,
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "Накладная не найдена")
    return invoice


@router.patch("/invoices/{invoice_id}", response_model=InvoiceOut)
def patch_invoice_head(
    invoice_id: uuid.UUID,
    body: InvoiceHeadPatch,
    p: Principal = Depends(require_role("store")),
    db: Session = Depends(get_db),
) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "Накладная не найдена")
    if invoice.ocr_status == "confirmed":
        raise HTTPException(409, "Накладная уже подтверждена")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(invoice, field, value)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.patch("/invoice-items/{item_id}", response_model=InvoiceOut)
def patch_invoice_item(
    item_id: uuid.UUID,
    body: InvoiceItemPatch,
    p: Principal = Depends(require_role("store")),
    db: Session = Depends(get_db),
) -> Invoice:
    item = db.get(InvoiceItem, item_id)
    if not item:
        raise HTTPException(404, "Позиция не найдена")
    if item.invoice.ocr_status == "confirmed":
        raise HTTPException(409, "Накладная уже подтверждена")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(item, field, value)
    item.line_total = line_total(item.qty, item.price)
    item.was_edited = True
    db.commit()
    db.refresh(item.invoice)
    return item.invoice


@router.delete("/invoice-items/{item_id}", response_model=InvoiceOut)
def delete_invoice_item(
    item_id: uuid.UUID,
    p: Principal = Depends(require_role("store")),
    db: Session = Depends(get_db),
) -> Invoice:
    item = db.get(InvoiceItem, item_id)
    if not item:
        raise HTTPException(404, "Позиция не найдена")
    invoice = item.invoice
    db.delete(item)
    db.commit()
    db.refresh(invoice)
    return invoice


@router.post("/invoices/{invoice_id}/confirm", response_model=InvoiceOut)
def confirm_invoice(
    invoice_id: uuid.UUID,
    p: Principal = Depends(require_role("store")),
    db: Session = Depends(get_db),
) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(404, "Накладная не найдена")
    invoice.ocr_status = "confirmed"
    db.commit()
    db.refresh(invoice)
    return invoice
