"""Демо-данные для быстрого старта (логины см. ниже)."""
from __future__ import annotations

import hashlib
import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Counterparty, Order, OrderItem, Organization, Product, Stock, User
from .security import hash_password

DEMO_PASSWORD = "demo12345"
EMB_DIM = 32


def _emb(text: str) -> list[float]:
    h = hashlib.sha256(text.encode()).digest()
    v = [b / 255.0 for b in h[:EMB_DIM]]
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def seed(db: Session) -> None:
    if db.scalar(select(Organization).limit(1)):
        return  # уже засеяно

    store = Organization(name="Магазин «Береке»", org_type="store", bin="901130350123")
    dist = Organization(name="ТОО «Молпром»", org_type="distributor", bin="123456789012")
    db.add_all([store, dist])
    db.flush()

    db.add(Counterparty(store_org_id=store.id, supplier_org_id=dist.id))
    db.add_all(
        [
            User(
                organization_id=store.id,
                email="store@dara.kz",
                password_hash=hash_password(DEMO_PASSWORD),
                role="store",
                full_name="Мерей Касымова",
            ),
            User(
                organization_id=dist.id,
                email="dist@dara.kz",
                password_hash=hash_password(DEMO_PASSWORD),
                role="distributor",
                full_name="Алибек Сапаров",
            ),
        ]
    )

    catalog = [
        ("Молоко 3.2%, 1 л", "4870001112223", 430),
        ("Кефир 2.5%, 0.5 л", "4870001112230", 280),
        ("Сметана 20%, 400 г", "4870001112247", 560),
        ("Творог 9%, 200 г", "4870001112254", 340),
        ("Масло слив. 72.5%, 180 г", "4870001112261", 790),
    ]
    products = []
    for name, barcode, _price in catalog:
        pr = Product(
            organization_id=store.id,
            name=name,
            barcode=barcode,
            unit="шт",
            embedding=_emb(name),
        )
        products.append(pr)
        db.add(pr)
    db.flush()

    # начальные остатки
    for pr in products:
        db.add(Stock(organization_id=store.id, product_id=pr.id, quantity=5))

    # демо-заявка в статусе shipped (готова к приёмке)
    store_user = db.scalar(select(User).where(User.email == "store@dara.kz"))
    order = Order(
        store_org_id=store.id,
        supplier_org_id=dist.id,
        status="shipped",
        created_by=store_user.id,
    )
    order.items = [
        OrderItem(product_id=products[i].id, name=catalog[i][0], qty_ordered=qty, price=catalog[i][2])
        for i, qty in enumerate([20, 30, 15, 24, 12])
    ]
    db.add(order)
    db.commit()
