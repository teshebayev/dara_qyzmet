"""Приёмка, расхождения (недостача/излишек/пересорт/брак), акт (ТЗ 6.4)."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import Principal, get_principal, require_role
from ..models import (
    Acceptance,
    Discrepancy,
    DiscrepancyAct,
    Invoice,
    InvoiceItem,
    Order,
    Organization,
    Product,
    Stock,
)
from ..schemas import (
    AcceptanceOut,
    ActOut,
    CorrectedSumOut,
    DiscrepancyCreate,
    ScanSessionIn,
    ScanSessionOut,
)
from ..services.recalc import recompute
from ..services.act_pdf import render_act_pdf

router = APIRouter(prefix="/api/v1", tags=["acceptance"])


def _order_for_store(order_id: uuid.UUID, p: Principal, db: Session) -> Order:
    order = db.get(Order, order_id)
    if not order or order.store_org_id != p.org_id:
        raise HTTPException(404, "Заявка не найдена")
    return order


def _resolve_product_id(db: Session, org_id: uuid.UUID, it: InvoiceItem) -> uuid.UUID:
    """Находит товар в каталоге по штрихкоду/названию, иначе создаёт — чтобы
    приёмка всегда оприходовалась в сток (распознанные позиции часто без product_id)."""
    if it.product_id:
        return it.product_id
    prod = None
    if it.barcode:
        prod = (
            db.query(Product)
            .filter(Product.organization_id == org_id, Product.barcode == it.barcode)
            .first()
        )
    if not prod:
        prod = (
            db.query(Product)
            .filter(Product.organization_id == org_id, Product.name == it.name)
            .first()
        )
    if not prod:
        prod = Product(organization_id=org_id, name=it.name, barcode=it.barcode, unit=it.unit or "шт")
        db.add(prod)
        db.flush()
    it.product_id = prod.id
    return prod.id


def _add_to_stock(db: Session, org_id: uuid.UUID, invoice: Invoice) -> None:
    """Принятые позиции попадают в сток магазина (товар создаётся при необходимости).

    Цена фиксируется как средневзвешенная себестоимость; если цена прихода неизвестна
    (0), цену не трогаем, чтобы не обнулять стоимость остатка."""
    for it in invoice.items:
        pid = _resolve_product_id(db, org_id, it)
        q = Decimal(str(it.qty or 0))
        price = Decimal(str(it.price or 0))
        row = db.get(Stock, (org_id, pid))
        if row:
            old_q = Decimal(str(row.quantity or 0))
            new_q = old_q + q
            if price > 0 and new_q > 0:
                old_avg = Decimal(str(row.avg_price or 0))
                row.avg_price = ((old_q * old_avg + q * price) / new_q).quantize(Decimal("0.01"))
                row.last_price = price
            row.quantity = new_q
        else:
            db.add(Stock(
                organization_id=org_id, product_id=pid, quantity=q,
                avg_price=price if price > 0 else Decimal("0"),
                last_price=price if price > 0 else None,
            ))


@router.post("/orders/{order_id}/scan-session", response_model=ScanSessionOut)
def scan_session(
    order_id: uuid.UUID,
    body: ScanSessionIn,
    p: Principal = Depends(require_role("store")),
    db: Session = Depends(get_db),
) -> ScanSessionOut:
    """Приёмка из мобильного терминала (сканы вместо OCR-накладной).

    Если накладной нет — создаём её из позиций заявки, открываем приёмку,
    из непустых сканов формируем расхождения, принятое количество (qty_actual)
    оприходуем в сток. Один вызов = завершённая приёмка.
    """
    order = _order_for_store(order_id, p, db)

    invoice = order.invoice
    if invoice is None:
        invoice = Invoice(order_id=order.id, ocr_status="confirmed")
        total = Decimal("0")
        invoice.items = []
        for it in order.items:
            qty = Decimal(str(it.qty_ordered or 0))
            price = Decimal(str(it.price or 0))
            invoice.items.append(InvoiceItem(
                product_id=it.product_id, name=it.name, qty=qty, price=price,
                line_total=(qty * price).quantize(Decimal("0.01")),
            ))
            total += qty * price
        invoice.total_sum = total.quantize(Decimal("0.01"))
        db.add(invoice)
        db.flush()

    acc = Acceptance(order_id=order.id, invoice_id=invoice.id, status="in_progress")
    db.add(acc)
    db.flush()

    by_pid = {str(i.product_id): i for i in invoice.items if i.product_id}
    count = 0
    for r in body.records:
        item = by_pid.get(str(r.product_id)) if r.product_id else None
        # принятое количество оприходуем в сток (правим qty позиции накладной)
        if item is not None and r.qty_actual is not None:
            item.qty = Decimal(str(r.qty_actual))
        if r.status == "ok":
            continue
        price = item.price if item else Decimal("0")
        qty_expected = item.qty if item else (Decimal(str(r.qty_ordered or 0)))
        disc = Discrepancy(
            acceptance_id=acc.id,
            invoice_item_id=item.id if item else None,
            product_id=r.product_id,
            type=r.status,
            price=price,
            qty_expected=qty_expected,
        )
        if r.status in ("shortage", "surplus"):
            disc.qty_actual = r.qty_actual
        if r.status == "defect":
            disc.qty_defect = r.qty_discrepancy if r.qty_discrepancy is not None else (
                Decimal(str(qty_expected or 0)) - Decimal(str(r.qty_actual or 0)))
            disc.photo_url = "scan-session"
        db.add(disc)
        count += 1

    db.flush()
    if count:
        recompute(acc, invoice)

    _add_to_stock(db, p.org_id, invoice)  # принятые qty -> сток
    acc.status = "accepted"
    acc.accepted_by = p.user_id
    acc.accepted_at = datetime.utcnow()
    order.status = "accepted"
    db.commit()
    db.refresh(acc)
    return ScanSessionOut(
        order_id=order.id, acceptance_id=acc.id, status=order.status,
        discrepancies=count, accepted=True,
    )


@router.post("/orders/{order_id}/acceptance", response_model=AcceptanceOut)
def start_acceptance(
    order_id: uuid.UUID,
    p: Principal = Depends(require_role("store")),
    db: Session = Depends(get_db),
) -> Acceptance:
    order = _order_for_store(order_id, p, db)
    if not order.invoice:
        raise HTTPException(400, "Сначала загрузите и распознайте накладную")
    if order.status == "shipped":
        order.status = "receiving"
    acc = Acceptance(order_id=order.id, invoice_id=order.invoice.id, status="in_progress")
    db.add(acc)
    db.commit()
    db.refresh(acc)
    return acc


def _get_acceptance(acc_id: uuid.UUID, p: Principal, db: Session) -> Acceptance:
    acc = db.get(Acceptance, acc_id)
    if not acc:
        raise HTTPException(404, "Приёмка не найдена")
    order = db.get(Order, acc.order_id)
    if order.store_org_id != p.org_id:
        raise HTTPException(403, "Нет доступа")
    return acc


@router.post("/acceptance/{acc_id}/accept", response_model=AcceptanceOut)
def accept(
    acc_id: uuid.UUID,
    p: Principal = Depends(require_role("store")),
    db: Session = Depends(get_db),
) -> Acceptance:
    """Принять без расхождений: списать в сток, статус заявки -> accepted."""
    acc = _get_acceptance(acc_id, p, db)
    invoice = db.get(Invoice, acc.invoice_id)
    _add_to_stock(db, p.org_id, invoice)
    acc.status = "accepted"
    acc.accepted_by = p.user_id
    acc.accepted_at = datetime.utcnow()
    order = db.get(Order, acc.order_id)
    order.status = "accepted"
    db.commit()
    db.refresh(acc)
    return acc


@router.post("/acceptance/{acc_id}/discrepancies", response_model=CorrectedSumOut)
def add_discrepancy(
    acc_id: uuid.UUID,
    body: DiscrepancyCreate,
    p: Principal = Depends(require_role("store")),
    db: Session = Depends(get_db),
) -> CorrectedSumOut:
    acc = _get_acceptance(acc_id, p, db)
    invoice = db.get(Invoice, acc.invoice_id)

    if body.type == "defect" and not body.photo_url:
        raise HTTPException(400, "Для брака обязательно фото (photo_url)")

    item = db.get(InvoiceItem, body.invoice_item_id) if body.invoice_item_id else None
    price = item.price if item else Decimal("0")
    qty_expected = item.qty if item else None

    disc = Discrepancy(
        acceptance_id=acc.id,
        invoice_item_id=body.invoice_item_id,
        product_id=body.product_id or (item.product_id if item else None),
        type=body.type,
        qty_expected=qty_expected,
        qty_actual=body.qty_actual,
        qty_defect=body.qty_defect,
        price=price,
        price_new=body.price_new,
        photo_url=body.photo_url,
        comment=body.comment,
    )
    db.add(disc)
    acc.status = "discrepancy"
    db.flush()

    res = recompute(acc, invoice)
    db.commit()
    db.refresh(acc)
    return CorrectedSumOut(discrepancies=acc.discrepancies, **res)


@router.get("/acceptance/{acc_id}/discrepancies", response_model=CorrectedSumOut)
def list_discrepancies(
    acc_id: uuid.UUID,
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> CorrectedSumOut:
    acc = db.get(Acceptance, acc_id)
    if not acc:
        raise HTTPException(404, "Приёмка не найдена")
    invoice = db.get(Invoice, acc.invoice_id)
    res = recompute(acc, invoice)
    return CorrectedSumOut(discrepancies=acc.discrepancies, **res)


@router.delete("/discrepancies/{disc_id}", response_model=CorrectedSumOut)
def delete_discrepancy(
    disc_id: uuid.UUID,
    p: Principal = Depends(require_role("store")),
    db: Session = Depends(get_db),
) -> CorrectedSumOut:
    disc = db.get(Discrepancy, disc_id)
    if not disc:
        raise HTTPException(404, "Запись не найдена")
    acc = db.get(Acceptance, disc.acceptance_id)
    db.delete(disc)
    db.flush()
    invoice = db.get(Invoice, acc.invoice_id)
    res = recompute(acc, invoice)
    db.commit()
    db.refresh(acc)
    return CorrectedSumOut(discrepancies=acc.discrepancies, **res)


def _act_rows(acc: Acceptance, db: Session) -> list[dict]:
    """Строки расхождений для печатной формы (разбивка излишек/недостача/брак/пересорт)."""
    rows: list[dict] = []
    for i, d in enumerate(acc.discrepancies, 1):
        item = db.get(InvoiceItem, d.invoice_item_id) if d.invoice_item_id else None
        doc = Decimal(str(d.qty_expected if d.qty_expected is not None
                          else (item.qty if item else 0)))
        actual = Decimal(str(d.qty_actual)) if d.qty_actual is not None else None
        defect = Decimal(str(d.qty_defect)) if d.qty_defect is not None else Decimal("0")
        row = {
            "n": i,
            "name": item.name if item else "—",
            "qty_doc": doc,
            "qty_fact": actual if actual is not None else (doc - defect),
            "surplus": Decimal("0"), "shortage": Decimal("0"),
            "defect": Decimal("0"), "regrade": Decimal("0"),
        }
        if d.type == "shortage" and actual is not None:
            row["shortage"] = max(Decimal("0"), doc - actual)
        elif d.type == "surplus" and actual is not None:
            row["surplus"] = max(Decimal("0"), actual - doc)
        elif d.type == "defect":
            row["defect"] = defect
        elif d.type == "misgrade" and actual is not None:
            row["regrade"] = actual
        rows.append(row)
    return rows


@router.get("/acceptance/{acc_id}/act.pdf")
def get_act_pdf(
    acc_id: uuid.UUID,
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> Response:
    """Акт о расхождении в PDF (для скачивания из веба и Telegram-бота)."""
    acc = _get_acceptance(acc_id, p, db)
    invoice = db.get(Invoice, acc.invoice_id)
    order = db.get(Order, acc.order_id)
    sums = recompute(acc, invoice)

    supplier = db.get(Organization, order.supplier_org_id) if order else None
    receiver = db.get(Organization, order.store_org_id) if order else None
    act = acc.act
    meta = {
        "number": act.number if act else f"ACT-{str(acc.id)[:8].upper()}",
        "date": datetime.utcnow().strftime("%d.%m.%Y"),
        "place": "г. Алматы",
        "supplier": supplier.name if supplier else (invoice.supplier_name if invoice else "—"),
        "supplier_bin": supplier.bin if supplier else None,
        "receiver": receiver.name if receiver else "—",
        "receiver_bin": receiver.bin if receiver else None,
        "invoice_number": (invoice.invoice_number if invoice else None) or "—",
    }
    totals = {"doc_sum": sums["original_sum"], "pay_sum": sums["corrected_sum"]}

    pdf = render_act_pdf(meta, _act_rows(acc, db), totals)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="akt-{meta["number"]}.pdf"'},
    )


@router.post("/acceptance/{acc_id}/act", response_model=ActOut)
def create_act(
    acc_id: uuid.UUID,
    p: Principal = Depends(require_role("store")),
    db: Session = Depends(get_db),
) -> DiscrepancyAct:
    acc = _get_acceptance(acc_id, p, db)
    if not acc.discrepancies:
        raise HTTPException(400, "Нет расхождений для акта")
    invoice = db.get(Invoice, acc.invoice_id)
    res = recompute(acc, invoice)

    if acc.act:
        act = acc.act
        act.original_sum = res["original_sum"]
        act.corrected_sum = res["corrected_sum"]
        act.total_delta = res["total_delta"]
    else:
        act = DiscrepancyAct(
            acceptance_id=acc.id,
            number=f"ACT-{str(acc.id)[:8].upper()}",
            status="created",
            **res,
        )
        db.add(act)
    order = db.get(Order, acc.order_id)
    order.status = "act_created"
    db.commit()
    db.refresh(act)
    return act
