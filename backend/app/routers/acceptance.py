"""Приёмка, расхождения (недостача/излишек/пересорт/брак), акт (ТЗ 6.4)."""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
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
    Stock,
)
from ..schemas import (
    AcceptanceOut,
    ActOut,
    CorrectedSumOut,
    DiscrepancyCreate,
)
from ..services.recalc import recompute

router = APIRouter(prefix="/api/v1", tags=["acceptance"])


def _order_for_store(order_id: uuid.UUID, p: Principal, db: Session) -> Order:
    order = db.get(Order, order_id)
    if not order or order.store_org_id != p.org_id:
        raise HTTPException(404, "Заявка не найдена")
    return order


def _add_to_stock(db: Session, org_id: uuid.UUID, invoice: Invoice) -> None:
    """Принятые позиции попадают в сток магазина."""
    for it in invoice.items:
        if not it.product_id:
            continue
        row = db.get(Stock, (org_id, it.product_id))
        if row:
            row.quantity = Decimal(str(row.quantity)) + Decimal(str(it.qty))
        else:
            db.add(Stock(organization_id=org_id, product_id=it.product_id, quantity=it.qty))


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
