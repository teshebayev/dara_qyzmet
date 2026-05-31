"""Каталог, сток, распознавание товара по штрихкоду/фото (ТЗ 6.6, 8)."""
from __future__ import annotations

import uuid

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import catalog
from ..db import get_db
from ..deps import Principal, get_principal
from ..models import Counterparty, Organization, Product, Stock
from ..schemas import ProductOut, RecognizeMatch, RecognizeOut, StockOut
from ..vlm import client as vlm
from ..vlm.pdf import normalize

router = APIRouter(prefix="/api/v1", tags=["catalog"])


@router.get("/products", response_model=list[ProductOut])
def find_products(
    barcode: str | None = Query(None),
    q: str | None = Query(None),
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[Product]:
    # Магазин видит свой каталог; поставщик — каталог обслуживаемых магазинов
    # (товары принадлежат организации-магазину).
    if p.role == "distributor":
        store_ids = select(Counterparty.store_org_id).where(
            Counterparty.supplier_org_id == p.org_id
        )
        stmt = select(Product).where(Product.organization_id.in_(store_ids))
    else:
        stmt = select(Product).where(Product.organization_id == p.org_id)
    if barcode:
        stmt = stmt.where(Product.barcode == barcode)
    if q:
        stmt = stmt.where(Product.name.ilike(f"%{q}%"))
    return list(db.scalars(stmt.limit(50)))


MAX_PRODUCT_PHOTOS = 5


@router.post("/products/{product_id}/photo")
async def upload_product_photo(
    product_id: uuid.UUID,
    file: UploadFile = File(...),
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    """Добавить фото товара (до 5 ракурсов) и проиндексировать image-эмбеддинг в Qdrant."""
    prod = db.get(Product, product_id)
    if not prod or prod.organization_id != p.org_id:
        raise HTTPException(404, "Товар не найден")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Пустой файл")
    png = normalize(data, file.content_type or "", file.filename or "")[0]
    res = catalog.add_product_image(
        prod.id, prod.organization_id, prod.name, prod.barcode, png,
        max_photos=MAX_PRODUCT_PHOTOS,
    )
    if res.get("limit"):
        raise HTTPException(409, f"Достигнут лимит {MAX_PRODUCT_PHOTOS} фото — удалите лишние")
    if not res.get("ok"):
        raise HTTPException(502, "Не удалось проиндексировать фото (Qdrant/эмбеддер недоступны)")
    if not prod.image_url:
        prod.image_url = f"indexed://{file.filename}"
        db.commit()
    return {"ok": True, "photos": res["count"], "max": MAX_PRODUCT_PHOTOS}


@router.get("/products/{product_id}/photos")
def product_photos_count(
    product_id: uuid.UUID,
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    prod = db.get(Product, product_id)
    if not prod or prod.organization_id != p.org_id:
        raise HTTPException(404, "Товар не найден")
    return {"photos": catalog.count_product_images(prod.id), "max": MAX_PRODUCT_PHOTOS}


@router.delete("/products/{product_id}/photos")
def clear_product_photos(
    product_id: uuid.UUID,
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> dict:
    prod = db.get(Product, product_id)
    if not prod or prod.organization_id != p.org_id:
        raise HTTPException(404, "Товар не найден")
    catalog.clear_product_images(prod.id)
    prod.image_url = None
    db.commit()
    return {"ok": True, "photos": 0}


@router.post("/products/recognize-image", response_model=RecognizeOut)
async def recognize_by_image(
    file: UploadFile = File(...),
    top: int = Query(3, ge=1, le=10),
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> RecognizeOut:
    """Фото товара -> ближайшие товары каталога (Qdrant/CLIP) + подсчёт единиц (VLM)."""
    data = await file.read()
    if not data:
        raise HTTPException(400, "Пустой файл")
    matches = catalog.search_by_image(data, str(p.org_id), limit=top)

    recognized_name = None
    count = None
    try:  # подсчёт через VLM — best-effort (нужен vLLM)
        png = normalize(data, file.content_type or "", file.filename or "")[0]
        c = vlm.count_products(png)
        if isinstance(c, dict):
            recognized_name = c.get("name")
            count = c.get("count")
    except Exception:  # noqa: BLE001 — подсчёт не критичен, фото всё равно принимаем
        pass

    return RecognizeOut(
        matches=[RecognizeMatch(**m) for m in matches],
        recognized_name=recognized_name,
        count=count,
    )


@router.get("/stock", response_model=list[StockOut])
def stock(
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[StockOut]:
    rows = db.execute(
        select(Stock, Product.name, Product.barcode)
        .join(Product, Product.id == Stock.product_id)
        .where(Stock.organization_id == p.org_id)
    ).all()
    return [
        StockOut(
            product_id=s.product_id, name=name, barcode=barcode,
            quantity=s.quantity, price=s.avg_price, last_price=s.last_price,
        )
        for s, name, barcode in rows
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
