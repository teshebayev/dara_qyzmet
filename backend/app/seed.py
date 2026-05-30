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


# Дополнительные товары каталога (имя, штрихкод). Добавляются идемпотентно при
# каждом старте — попадают и в уже существующую БД (без пересоздания тома).
EXTRA_PRODUCTS = [
    ("bon aqua", "40822426"),
    ("C922 webcam", "6920377905316"),
    ("kiyoka влажные салфетки", "721688451723"),
    ("flovel care влажные салфетки", "0745114229908"),
    ("fantastic стикеры", "6946991801865"),
    ("black deli Think фломастер", "6921734941251"),
    ("blue deli Think фломастер", "6921734941268"),
    ("green deli Think фломастер", "6921734941299"),
    ("ручка", "6932784200106"),
    ("zara white jeans", "03991330710387"),
    ("dizzy energy drink", "4870204391510"),
    ("fusetea персик", "5449000189325"),
    ("snickers", "4607065001445"),
    ("coca-cola classic", "54491472"),
    ("fanta", "40822938"),
]


def _ensure_extra_products(db: Session, store: Organization) -> int:
    """Добавляет недостающие товары каталога магазину (по штрихкоду). Идемпотентно."""
    existing = set(
        db.scalars(select(Product.barcode).where(Product.organization_id == store.id))
    )
    added = 0
    for name, barcode in EXTRA_PRODUCTS:
        if barcode in existing:
            continue
        db.add(Product(
            organization_id=store.id, name=name, barcode=barcode,
            unit="шт", embedding=_emb(name),
        ))
        added += 1
    return added


def seed(db: Session) -> None:
    existing_store = db.scalar(
        select(Organization).where(Organization.org_type == "store")
    )
    if existing_store:
        # БД уже засеяна — только дополняем каталог недостающими товарами
        _ensure_extra_products(db, existing_store)
        db.commit()
        return

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

    # начальные остатки с ценой из каталога
    for i, pr in enumerate(products):
        price = catalog[i][2]
        db.add(Stock(
            organization_id=store.id, product_id=pr.id, quantity=5,
            avg_price=price, last_price=price,
        ))

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

    _ensure_extra_products(db, store)
    db.commit()
