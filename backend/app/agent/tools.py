"""Инструменты агентов. Все читают только данные тенанта (organization_id).

Паттерны запросов взяты из существующего routers/agent.py (get_stock и т.п.)
и расширены аналитикой и поиском по фото через Qdrant.

В этом каркасе функции принимают `db` (SQLAlchemy Session) и `org_id`.
При интеграции в dara_qyzmet импортируйте модели из ..models.
"""
from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select  # noqa: F401  (используется в функциях ниже)
from sqlalchemy.orm import Session  # noqa: F401
from ..models import Discrepancy, Order, OrderItem, Product, Stock  # noqa: F401


# ---------- Агент стока ----------

def tool_get_stock(db: Any, org_id: str, query: str | None = None) -> list[dict]:
    """Текущие остатки товаров на складе организации."""
    from sqlalchemy import select
    from ..models import Product, Stock

    stmt = (
        select(Product.name, Stock.quantity)
        .join(Stock, Stock.product_id == Product.id)
        .where(Stock.organization_id == org_id)
    )
    if query:
        stmt = stmt.where(Product.name.ilike(f"%{query}%"))
    return [{"name": n, "quantity": float(q)} for n, q in db.execute(stmt).all()]


def tool_low_stock(db: Any, org_id: str, threshold: float = 10.0) -> list[dict]:
    """Товары с остатком ниже порога (low-stock алерт)."""
    from sqlalchemy import select
    from ..models import Product, Stock

    stmt = (
        select(Product.name, Stock.quantity)
        .join(Stock, Stock.product_id == Product.id)
        .where(Stock.organization_id == org_id, Stock.quantity < threshold)
        .order_by(Stock.quantity.asc())
    )
    return [{"name": n, "quantity": float(q)} for n, q in db.execute(stmt).all()]


# ---------- Агент аналитики ----------

def tool_discrepancy_report(db: Any, org_id: str, dtype: str | None = None) -> list[dict]:
    """Сводка расхождений по типам (shortage|surplus|misgrade|defect)."""
    from sqlalchemy import func, select
    from ..models import Discrepancy

    rows = db.execute(
        select(Discrepancy.type, func.count(), func.coalesce(func.sum(Discrepancy.amount_delta), 0))
        .group_by(Discrepancy.type)
    ).all()
    out = [{"type": t, "count": c, "amount_delta": float(s)} for t, c, s in rows]
    return [r for r in out if (not dtype or r["type"] == dtype)]


def tool_top_products(db: Any, org_id: str, limit: int = 5) -> list[dict]:
    """Топ товаров по объёму заказов (простой тренд продаж)."""
    from sqlalchemy import func, select
    from ..models import Order, OrderItem

    stmt = (
        select(OrderItem.name, func.sum(OrderItem.qty_ordered).label("total"))
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.store_org_id == org_id)
        .group_by(OrderItem.name)
        .order_by(func.sum(OrderItem.qty_ordered).desc())
        .limit(limit)
    )
    return [{"name": n, "qty": float(t)} for n, t in db.execute(stmt).all()]


# ---------- Агент товаров (Qdrant) ----------

def tool_search_product_by_photo(org_id: str, image_b64: str, limit: int = 5) -> list[dict]:
    """Поиск товара в каталоге тенанта по фото через Qdrant (CLIP-эмбеддинг)."""
    import base64

    from ..catalog import search_by_image

    return search_by_image(base64.b64decode(image_b64), org_id, limit=limit)


def tool_match_invoice_item(org_id: str, name: str, limit: int = 3) -> list[dict]:
    """Сопоставить позицию накладной (текст) с каталогом тенанта через Qdrant."""
    from ..catalog import search_by_text

    return search_by_text(name, org_id, limit=limit)


# ---------- Аналитика: исход/качество/статус/траты ----------

def tool_reorder_suggestions(db: Any, org_id: str, threshold: float = 10.0) -> list[dict]:
    """Товары на исходе + предлагаемый поставщик.

    Поставщик определяется по последней заявке, где заказывали этот товар;
    если такой нет, берём единственного контрагента (если он один).
    """
    from sqlalchemy import select
    from ..models import Counterparty, Order, OrderItem, Organization, Product, Stock

    low = db.execute(
        select(Product.id, Product.name, Stock.quantity)
        .join(Stock, Stock.product_id == Product.id)
        .where(Stock.organization_id == org_id, Stock.quantity < threshold)
        .order_by(Stock.quantity.asc())
    ).all()

    cps = db.execute(
        select(Organization.id, Organization.name)
        .join(Counterparty, Counterparty.supplier_org_id == Organization.id)
        .where(Counterparty.store_org_id == org_id)
    ).all()
    default_sup = (
        {"supplier_org_id": str(cps[0][0]), "supplier_name": cps[0][1]}
        if len(cps) == 1 else None
    )

    out: list[dict] = []
    for pid, name, qty in low:
        row = db.execute(
            select(Organization.id, Organization.name)
            .join(Order, Order.supplier_org_id == Organization.id)
            .join(OrderItem, OrderItem.order_id == Order.id)
            .where(Order.store_org_id == org_id, OrderItem.product_id == pid)
            .order_by(Order.created_at.desc())
            .limit(1)
        ).first()
        sup = {"supplier_org_id": str(row[0]), "supplier_name": row[1]} if row else default_sup
        out.append({
            "product_id": str(pid),
            "name": name,
            "quantity": float(qty),
            "supplier_org_id": (sup or {}).get("supplier_org_id"),
            "supplier_name": (sup or {}).get("supplier_name"),
        })
    return out


def tool_supplier_quality(db: Any, org_id: str) -> list[dict]:
    """Рейтинг поставщиков по расхождениям (Discrepancy -> Acceptance -> Order)."""
    from sqlalchemy import func, select
    from ..models import Acceptance, Discrepancy, Order, Organization

    rows = db.execute(
        select(
            Organization.id, Organization.name, Discrepancy.type,
            func.count(), func.coalesce(func.sum(Discrepancy.amount_delta), 0),
        )
        .join(Acceptance, Acceptance.id == Discrepancy.acceptance_id)
        .join(Order, Order.id == Acceptance.order_id)
        .join(Organization, Organization.id == Order.supplier_org_id)
        .where(Order.store_org_id == org_id)
        .group_by(Organization.id, Organization.name, Discrepancy.type)
    ).all()

    agg: dict[str, dict] = {}
    for sid, name, dtype, cnt, delta in rows:
        e = agg.setdefault(str(sid), {
            "supplier_org_id": str(sid), "supplier_name": name,
            "total": 0, "amount_delta": 0.0, "by_type": {},
        })
        e["total"] += cnt
        e["amount_delta"] += float(delta)
        e["by_type"][dtype] = cnt
    return sorted(agg.values(), key=lambda x: (-x["total"], x["amount_delta"]))


def tool_delivery_status(
    db: Any, org_id: str, supplier_org_id: str | None = None, status: str | None = None
) -> list[dict]:
    """Заявки магазина по поставщику и/или статусу."""
    from sqlalchemy import select
    from ..models import Order

    stmt = select(Order).where(Order.store_org_id == org_id)
    if supplier_org_id:
        stmt = stmt.where(Order.supplier_org_id == supplier_org_id)
    if status:
        stmt = stmt.where(Order.status == status)
    stmt = stmt.order_by(Order.created_at.desc()).limit(20)
    return [
        {
            "order_id": str(o.id),
            "status": o.status,
            "supplier_org_id": str(o.supplier_org_id),
            "created_at": o.created_at.isoformat(),
            "items": len(o.items),
        }
        for o in db.scalars(stmt)
    ]


def tool_spend(
    db: Any, org_id: str, supplier_org_id: str | None = None,
    date_from: str | None = None, date_to: str | None = None,
) -> dict:
    """Сумма по ПОДТВЕРЖДЁННЫМ накладным магазина за период (Invoice -> Order)."""
    from datetime import date as _date

    from sqlalchemy import func, select
    from ..models import Invoice, Order

    stmt = (
        select(func.coalesce(func.sum(Invoice.total_sum), 0), func.count())
        .join(Order, Order.id == Invoice.order_id)
        .where(Order.store_org_id == org_id, Invoice.ocr_status == "confirmed")
    )
    if supplier_org_id:
        stmt = stmt.where(Order.supplier_org_id == supplier_org_id)
    if date_from:
        stmt = stmt.where(Invoice.invoice_date >= _date.fromisoformat(date_from))
    if date_to:
        stmt = stmt.where(Invoice.invoice_date <= _date.fromisoformat(date_to))
    total, cnt = db.execute(stmt).one()
    return {"total": float(total or 0), "invoices": int(cnt)}


# ---------- Агент создания заявки (черновик на поставку) ----------

def tool_find_supplier(db: Any, org_id: str, query: str | None = None) -> list[dict]:
    """Поставщики, с которыми работает магазин (через Counterparty)."""
    from sqlalchemy import select
    from ..models import Counterparty, Organization

    stmt = (
        select(Organization)
        .join(Counterparty, Counterparty.supplier_org_id == Organization.id)
        .where(Counterparty.store_org_id == org_id)
    )
    if query:
        stmt = stmt.where(Organization.name.ilike(f"%{query}%"))
    return [
        {"supplier_org_id": str(o.id), "name": o.name, "bin": o.bin}
        for o in db.scalars(stmt)
    ]


def tool_find_product(db: Any, org_id: str, query: str, limit: int = 1) -> list[dict]:
    """Товар в собственном каталоге магазина по названию (ilike).

    Если точное вхождение не найдено, пробуем по основе слова (отбрасываем
    падежное окончание) — «сметану» -> «сметан» -> «Сметана 20%».
    """
    from sqlalchemy import select
    from ..models import Product

    if not query:
        return []

    def _run(pattern: str) -> list[dict]:
        stmt = (
            select(Product)
            .where(Product.organization_id == org_id, Product.name.ilike(pattern))
            .limit(limit)
        )
        return [
            {"product_id": str(p.id), "name": p.name, "barcode": p.barcode}
            for p in db.scalars(stmt)
        ]

    rows = _run(f"%{query}%")
    if not rows and len(query) >= 5:
        rows = _run(f"%{query[:-2]}%")  # грубый стемминг под русские окончания
    return rows


def tool_get_previous_orders(
    db: Any, org_id: str, supplier_org_id: str | None = None, limit: int = 5
) -> list[dict]:
    """Недавние заявки магазина (для подсказки количеств «как обычно»)."""
    from sqlalchemy import select
    from ..models import Order

    stmt = select(Order).where(Order.store_org_id == org_id)
    if supplier_org_id:
        stmt = stmt.where(Order.supplier_org_id == supplier_org_id)
    stmt = stmt.order_by(Order.created_at.desc()).limit(limit)
    out: list[dict] = []
    for o in db.scalars(stmt):
        out.append(
            {
                "order_id": str(o.id),
                "status": o.status,
                "items": [
                    {
                        "name": i.name,
                        "product_id": str(i.product_id) if i.product_id else None,
                        "qty_ordered": float(i.qty_ordered),
                        "price": float(i.price) if i.price is not None else None,
                    }
                    for i in o.items
                ],
            }
        )
    return out


def tool_create_order_draft(
    db: Any, org_id: str, user_id: str, supplier_org_id: str | None, items: list[dict]
) -> dict:
    """Создать ЧЕРНОВИК заявки (статус new). Вызывается только после подтверждения."""
    import uuid as _uuid
    from decimal import Decimal

    from ..models import Order, OrderItem

    if not supplier_org_id or not items:
        return {}
    order = Order(
        store_org_id=_uuid.UUID(str(org_id)),
        supplier_org_id=_uuid.UUID(str(supplier_org_id)),
        status="new",
        created_by=_uuid.UUID(str(user_id)),
    )
    order.items = [
        OrderItem(
            product_id=_uuid.UUID(str(it["product_id"])) if it.get("product_id") else None,
            name=it.get("name") or "—",
            qty_ordered=Decimal(str(it.get("qty") or 0)),
            price=Decimal(str(it["price"])) if it.get("price") is not None else None,
        )
        for it in items
    ]
    db.add(order)
    db.commit()
    db.refresh(order)
    return {
        "order_id": str(order.id),
        "status": order.status,
        "supplier_org_id": str(order.supplier_org_id),
        "items": [
            {"name": i.name, "qty_ordered": float(i.qty_ordered)} for i in order.items
        ],
    }


# ---------- Общие хелперы (используются и узлами, и function-calling) ----------

def resolve_supplier(db: Any, org_id: str, message: str, hint: str | None) -> dict | None:
    """Определить поставщика по подсказке или по тексту среди контрагентов."""
    suppliers = tool_find_supplier(db, org_id, hint) if hint else []
    if hint and suppliers:
        return suppliers[0]
    suppliers = suppliers or tool_find_supplier(db, org_id)
    if not suppliers:
        return None
    m = (message or "").lower()
    match = next(
        (s for s in suppliers
         if any(t in m for t in re.findall(r"\w{4,}", s["name"].lower()))),
        None,
    )
    if match:
        return match
    return suppliers[0] if len(suppliers) == 1 else None


def build_order_draft(db: Any, org_id: str, raw_items: list[dict], supplier: dict) -> tuple[dict, list]:
    """Собрать черновик заявки из списка [{name, qty?}] (БЕЗ записи в БД).

    Количество без явного значения берётся из последних заявок («как обычно»),
    иначе 1. Возвращает (draft, missing) — missing = названия не из каталога.
    """
    prev = tool_get_previous_orders(db, org_id, supplier["supplier_org_id"])
    prev_by_name: dict[str, dict] = {}
    for o in prev:
        for it in o["items"]:
            prev_by_name.setdefault(it["name"].lower(), it)

    # модель может прислать items как список строк, объект или мусор — нормализуем
    if isinstance(raw_items, (str, dict)):
        raw_items = [raw_items]
    items: list[dict] = []
    missing: list[str] = []
    for ri in (raw_items or []):
        if isinstance(ri, str):
            name, qty = ri.strip(), None
        elif isinstance(ri, dict):
            name, qty = ri.get("name"), ri.get("qty")
        else:
            continue
        # пропускаем пустые/мусорные имена (без букв/цифр)
        if not name or not re.search(r"\w", str(name)):
            continue
        name = str(name).strip()
        try:
            qty = float(qty) if qty not in (None, "") else None
        except (TypeError, ValueError):
            qty = None
        matches = tool_find_product(db, org_id, name)
        if matches:
            m = matches[0]
            prev_it = prev_by_name.get(m["name"].lower())
            q = qty or (prev_it["qty_ordered"] if prev_it else None) or 1
            price = prev_it["price"] if prev_it else None
            items.append({"product_id": m["product_id"], "name": m["name"], "qty": q, "price": price})
        else:
            items.append({"product_id": None, "name": name, "qty": qty or 1, "price": None})
            missing.append(name)

    draft = {
        "supplier_org_id": supplier["supplier_org_id"],
        "supplier_name": supplier["name"],
        "items": items,
    }
    return draft, missing


# Инструменты вызываются либо детерминированными узлами (mock, agent/graph.py),
# детерминированными узлами графа по интенту от NLU (agent/nlu.py, agent/graph.py).
