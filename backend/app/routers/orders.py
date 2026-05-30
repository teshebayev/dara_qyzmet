"""Заявки/потребности и жизненный цикл статусов (ТЗ 3)."""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..deps import Principal, get_principal, require_role
from ..models import Order, OrderItem, Organization, Product
from ..schemas import (
    OrderCreate,
    OrderOut,
    OrderReceiptOut,
    OrgBrief,
    ProductOut,
    ReceiptItem,
    ShipIn,
)

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])

# Разрешённые переходы статусов
TRANSITIONS = {
    "new": {"shipped", "cancelled"},
    "shipped": {"receiving", "cancelled"},
    "receiving": {"accepted", "discrepancy"},
    "discrepancy": {"act_created"},
    "act_created": {"invoice_corrected"},
    "invoice_corrected": {"closed"},
}


def assert_transition(current: str, target: str) -> None:
    if target not in TRANSITIONS.get(current, set()):
        raise HTTPException(409, f"Недопустимый переход: {current} -> {target}")


def visible_orders_filter(p: Principal):
    """Магазин видит свои заявки, поставщик — адресованные ему."""
    return or_(Order.store_org_id == p.org_id, Order.supplier_org_id == p.org_id)


@router.post("", response_model=OrderOut, status_code=201)
def create_order(
    body: OrderCreate,
    p: Principal = Depends(require_role("store")),
    db: Session = Depends(get_db),
) -> Order:
    supplier = db.get(Organization, body.supplier_org_id)
    if not supplier or supplier.org_type != "distributor":
        raise HTTPException(400, "Поставщик не найден")
    order = Order(
        store_org_id=p.org_id,
        supplier_org_id=body.supplier_org_id,
        status="new",
        created_by=p.user_id,
    )
    order.items = [
        OrderItem(
            product_id=i.product_id,
            name=i.name,
            qty_ordered=i.qty_ordered,
            price=i.price,
        )
        for i in body.items
    ]
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


@router.get("", response_model=list[OrderOut])
def list_orders(
    status: str | None = None,
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[Order]:
    stmt = (
        select(Order)
        .where(visible_orders_filter(p))
        .options(selectinload(Order.items))
        .order_by(Order.created_at.desc())
    )
    if status:
        stmt = stmt.where(Order.status == status)
    return list(db.scalars(stmt))


def get_order_or_404(order_id: uuid.UUID, p: Principal, db: Session) -> Order:
    order = db.get(Order, order_id)
    if not order or p.org_id not in (order.store_org_id, order.supplier_org_id):
        raise HTTPException(404, "Заявка не найдена")
    return order


@router.get("/{order_id}", response_model=OrderOut)
def get_order(
    order_id: uuid.UUID,
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> Order:
    return get_order_or_404(order_id, p, db)


@router.get("/{order_id}/receipt", response_model=OrderReceiptOut)
def order_receipt(
    order_id: uuid.UUID,
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> OrderReceiptOut:
    """Данные для печати приходного ордера запасов (шапка + номенклатура)."""
    order = get_order_or_404(order_id, p, db)
    store = db.get(Organization, order.store_org_id)
    supplier = db.get(Organization, order.supplier_org_id)

    items: list[ReceiptItem] = []
    total = Decimal("0")
    for it in order.items:
        prod = db.get(Product, it.product_id) if it.product_id else None
        qty = Decimal(str(it.qty_ordered or 0))
        price = Decimal(str(it.price or 0))
        line = (qty * price).quantize(Decimal("0.01"))
        total += line
        items.append(
            ReceiptItem(
                name=it.name,
                barcode=prod.barcode if prod else None,
                unit=(prod.unit if prod else None) or "шт",
                qty=qty,
                price=price,
                total=line,
            )
        )

    return OrderReceiptOut(
        number="#" + str(order.id)[:8].upper(),
        date=order.created_at.date() if order.created_at else None,
        receiver=OrgBrief(name=store.name, bin=store.bin),
        supplier=OrgBrief(name=supplier.name, bin=supplier.bin),
        items=items,
        total_sum=total.quantize(Decimal("0.01")),
    )


@router.get("/{order_id}/catalog", response_model=list[ProductOut])
def order_catalog(
    order_id: uuid.UUID,
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[Product]:
    """Каталог товаров магазина-заказчика — чтобы поставщик при отгрузке привязывал
    позиции к товарам (и подтягивал штрихкод/артикул)."""
    order = get_order_or_404(order_id, p, db)
    return list(
        db.scalars(select(Product).where(Product.organization_id == order.store_org_id))
    )


@router.post("/{order_id}/ship", response_model=OrderOut)
def ship_order(
    order_id: uuid.UUID,
    body: ShipIn | None = None,
    p: Principal = Depends(require_role("distributor")),
    db: Session = Depends(get_db),
) -> Order:
    order = get_order_or_404(order_id, p, db)
    if order.supplier_org_id != p.org_id:
        raise HTTPException(403, "Вы не поставщик по этой заявке")
    assert_transition(order.status, "shipped")

    # поставщик может проставить цену и привязать товар к каталогу (штрихкод/артикул)
    if body and body.items:
        by_id = {it.id: it for it in order.items}
        for upd in body.items:
            it = by_id.get(upd.item_id)
            if not it:
                continue
            if upd.product_id is not None:
                it.product_id = upd.product_id
            if upd.price is not None:
                it.price = upd.price

    order.status = "shipped"
    db.commit()
    db.refresh(order)
    return order


@router.post("/{order_id}/cancel", response_model=OrderOut)
def cancel_order(
    order_id: uuid.UUID,
    p: Principal = Depends(require_role("store")),
    db: Session = Depends(get_db),
) -> Order:
    order = get_order_or_404(order_id, p, db)
    assert_transition(order.status, "cancelled")
    order.status = "cancelled"
    db.commit()
    db.refresh(order)
    return order
