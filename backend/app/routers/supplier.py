"""Сторона поставщика: получение акта и корректировка счёта (ТЗ 6.5)."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import Principal, get_principal, require_role
from ..models import Acceptance, DiscrepancyAct, Order
from ..schemas import ActOut

router = APIRouter(prefix="/api/v1", tags=["supplier"])


@router.get("/supplier/acts", response_model=list[ActOut])
def supplier_acts(
    p: Principal = Depends(require_role("distributor")),
    db: Session = Depends(get_db),
) -> list[DiscrepancyAct]:
    stmt = (
        select(DiscrepancyAct)
        .join(Acceptance, Acceptance.id == DiscrepancyAct.acceptance_id)
        .join(Order, Order.id == Acceptance.order_id)
        .where(Order.supplier_org_id == p.org_id)
        .order_by(DiscrepancyAct.created_at.desc())
    )
    return list(db.scalars(stmt))


@router.get("/acts/{act_id}", response_model=ActOut)
def get_act(
    act_id: uuid.UUID,
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> DiscrepancyAct:
    act = db.get(DiscrepancyAct, act_id)
    if not act:
        raise HTTPException(404, "Акт не найден")
    return act


@router.post("/acts/{act_id}/correct-invoice", response_model=ActOut)
def correct_invoice(
    act_id: uuid.UUID,
    p: Principal = Depends(require_role("distributor")),
    db: Session = Depends(get_db),
) -> DiscrepancyAct:
    act = db.get(DiscrepancyAct, act_id)
    if not act:
        raise HTTPException(404, "Акт не найден")
    acc = db.get(Acceptance, act.acceptance_id)
    order = db.get(Order, acc.order_id)
    if order.supplier_org_id != p.org_id:
        raise HTTPException(403, "Вы не поставщик по этой заявке")
    act.status = "corrected"
    order.status = "invoice_corrected"
    db.commit()
    db.refresh(act)
    return act
