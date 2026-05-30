"""Каталог, сток, распознавание товара по штрихкоду/фото (ТЗ 6.6, 8)."""
from __future__ import annotations

import hashlib
import math
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import Principal, get_principal
from ..models import Counterparty, Organization, Product, Stock
from ..schemas import ProductMatch, ProductOut, StockOut

router = APIRouter(prefix="/api/v1", tags=["catalog"])

EMB_DIM = 32


def pseudo_embedding(data: bytes) -> list[float]:
    """Заглушка эмбеддинга (детерминированная). В проде — мультимодальный энкодер
    (CLIP-подобный) + pgvector. Здесь — хэш-вектор для демонстрации kNN-пути."""
    h = hashlib.sha256(data).digest()
    vec = [(b / 255.0) for b in h[:EMB_DIM]]
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


@router.get("/products", response_model=list[ProductOut])
def find_products(
    barcode: str | None = Query(None),
    q: str | None = Query(None),
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[Product]:
    stmt = select(Product).where(Product.organization_id == p.org_id)
    if barcode:
        stmt = stmt.where(Product.barcode == barcode)
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q}%"))
    return list(db.scalars(stmt.limit(20)))


@router.post("/products/recognize-image", response_model=list[ProductMatch])
async def recognize_by_image(
    file: UploadFile = File(...),
    top: int = Query(3, ge=1, le=10),
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[ProductMatch]:
    """Фото товара без штрихкода -> ближайшие товары каталога (kNN по эмбеддингу)."""
    data = await file.read()
    if not data:
        raise HTTPException(400, "Пустой файл")
    query_vec = pseudo_embedding(data)
    products = list(
        db.scalars(
            select(Product).where(
                Product.organization_id == p.org_id, Product.embedding.isnot(None)
            )
        )
    )
    scored = [
        ProductMatch(product=ProductOut.model_validate(pr), score=round(cosine(query_vec, pr.embedding), 4))
        for pr in products
    ]
    scored.sort(key=lambda m: m.score, reverse=True)
    return scored[:top]


@router.get("/stock", response_model=list[StockOut])
def stock(
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[StockOut]:
    rows = db.execute(
        select(Stock, Product.name)
        .join(Product, Product.id == Stock.product_id)
        .where(Stock.organization_id == p.org_id)
    ).all()
    return [
        StockOut(product_id=s.product_id, name=name, quantity=s.quantity)
        for s, name in rows
    ]


@router.get("/suppliers", response_model=list[dict])
def suppliers(
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Поставщики, связанные с магазином (для создания заявки)."""
    stmt = (
        select(Organization)
        .join(Counterparty, Counterparty.supplier_org_id == Organization.id)
        .where(Counterparty.store_org_id == p.org_id)
    )
    return [{"id": str(o.id), "name": o.name} for o in db.scalars(stmt)]
