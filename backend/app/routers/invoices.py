"""Накладная: загрузка фото/PDF -> VLM -> редактирование -> подтверждение (ТЗ 6.3, 7)."""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import Principal, get_principal, require_role
from ..models import Counterparty, Invoice, InvoiceItem, Order, OrderItem, Organization, Product
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


def _norm_bin(value: str | None) -> str | None:
    """Оставляем только цифры; валидный БИН РК — ровно 12 цифр."""
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    return digits[:12] if len(digits) >= 12 else None


def _fill_invoice_from_parsed(
    invoice: Invoice, parsed, db: Session, org_id: uuid.UUID, filename: str
) -> None:
    """Шапка + позиции накладной из результата распознавания (общая логика
    для приёмки по заявке и для скана без заявки)."""
    invoice.supplier_name = parsed.supplier
    invoice.invoice_number = parsed.invoice_number
    invoice.invoice_date = _parse_date(parsed.date)
    invoice.total_sum = parsed.grand_total
    invoice.ocr_status = "done"
    invoice.raw_ocr_json = parsed.model_dump()
    invoice.source_file_url = f"upload://{filename}"
    invoice.items = []
    for li in parsed.items:
        qty = li.quantity or 0
        price = li.unit_price or 0
        prod = _match_product(db, org_id, li.article)
        invoice.items.append(
            InvoiceItem(
                product_id=prod.id if prod else None,
                name=li.name or "—",
                barcode=li.article,
                qty=qty,
                price=price,
                line_total=line_total(qty, price),
                # «уверенность» по полноте полей (для подсветки подозрительных строк)
                confidence=0.95 if (li.name and li.quantity and li.unit_price) else 0.65,
                was_edited=False,
            )
        )


def _resolve_or_create_supplier(
    db: Session, store_org_id: uuid.UUID, name: str | None, bin_raw: str | None
) -> Organization:
    """Найти поставщика по БИН/названию или создать нового, и привязать его
    к магазину (Counterparty). Нужен для приёмки накладной без заявки."""
    bin_ = _norm_bin(bin_raw)
    org: Organization | None = None
    if bin_:
        org = (
            db.query(Organization)
            .filter(Organization.bin == bin_, Organization.org_type == "distributor")
            .first()
        )
    if not org and name and name.strip():
        org = (
            db.query(Organization)
            .filter(
                Organization.org_type == "distributor",
                Organization.name.ilike(name.strip()),
            )
            .first()
        )
    if not org:
        org = Organization(
            name=(name or "Неизвестный поставщик").strip()[:200] or "Неизвестный поставщик",
            org_type="distributor",
            bin=bin_,
        )
        db.add(org)
        db.flush()  # нужен org.id для связи и заявки

    link = (
        db.query(Counterparty)
        .filter(
            Counterparty.store_org_id == store_org_id,
            Counterparty.supplier_org_id == org.id,
        )
        .first()
    )
    if not link:
        db.add(Counterparty(store_org_id=store_org_id, supplier_org_id=org.id))
    return org


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
    _fill_invoice_from_parsed(invoice, parsed, db, p.org_id, file.filename or "upload")
    db.add(invoice)
    if order.status == "shipped":
        order.status = "receiving"
    db.commit()
    db.refresh(invoice)
    return invoice


@router.post("/invoices/scan", response_model=InvoiceOut)
async def scan_invoice(
    file: UploadFile = File(...),
    p: Principal = Depends(require_role("store")),
    db: Session = Depends(get_db),
) -> Invoice:
    """Приёмка БЕЗ предварительной заявки: фото/PDF накладной → распознавание →
    система сама находит/создаёт поставщика и заявку, прикрепляет накладную.
    Дальше идёт обычный поток приёмки (проверка → расхождения → сток)."""
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

    supplier = _resolve_or_create_supplier(db, p.org_id, parsed.supplier, parsed.supplier_bin)

    # Товар физически на руках — заявку создаём сразу в статусе приёмки.
    order = Order(
        store_org_id=p.org_id,
        supplier_org_id=supplier.id,
        status="receiving",
        created_by=p.user_id,
    )
    # Позиции заявки повторяют распознанную накладную (заявка/ордер не пустые).
    for li in parsed.items:
        prod = _match_product(db, p.org_id, li.article)
        order.items.append(
            OrderItem(
                product_id=prod.id if prod else None,
                name=li.name or "—",
                qty_ordered=Decimal(str(li.quantity or 0)),
                price=Decimal(str(li.unit_price or 0)),
            )
        )
    db.add(order)
    db.flush()  # нужен order.id для накладной

    invoice = Invoice(order_id=order.id)
    _fill_invoice_from_parsed(invoice, parsed, db, p.org_id, file.filename or "scan")
    db.add(invoice)
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
