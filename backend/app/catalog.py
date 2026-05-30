"""Поиск товара по каталогу через Qdrant (CLIP-эмбеддинги, ONNX/CPU).

Текст и изображение кодируются в общее 512-мерное пространство CLIP
(`Qdrant/clip-ViT-B-32-*` через fastembed), поэтому фото-запрос матчится
с проиндексированными названиями товаров без отдельных картинок в каталоге.

Изоляция тенантов: каждая точка хранит `org_id` в payload, поиск всегда
фильтруется по нему. Все функции устойчивы к недоступности Qdrant — при
ошибке соединения возвращают пустой результат (агент не падает, см. ТЗ 9).

Ленивые синглтоны (клиент и эмбеддеры) — чтобы не тормозить старт и не тянуть
модель, пока она реально не понадобилась.
"""
from __future__ import annotations

import io
import logging
import uuid
from functools import lru_cache
from typing import Any

from .config import settings

# Фото товара хранятся отдельными точками: id = uuid5(NS, "<product_id>:<slot>"),
# slot 0..4. Это позволяет до 5 ракурсов на товар; поиск дедуплицируется по product_id.
_PHOTO_NS = uuid.uuid5(uuid.NAMESPACE_DNS, "dara.product.photo")


def _photo_point_id(product_id, slot: int) -> str:
    return str(uuid.uuid5(_PHOTO_NS, f"{product_id}:{slot}"))

log = logging.getLogger("dara.catalog")

# Имена векторов в коллекции (мульти-вектор не нужен — текст и фото в одном
# пространстве, поэтому одна именованная конфигурация на коллекцию).


@lru_cache(maxsize=1)
def _client():
    from qdrant_client import QdrantClient

    return QdrantClient(url=settings.qdrant_url, timeout=10.0)


@lru_cache(maxsize=1)
def _text_embedder():
    from fastembed import TextEmbedding

    return TextEmbedding(model_name=settings.embed_text_model)


@lru_cache(maxsize=1)
def _image_embedder():
    from fastembed import ImageEmbedding

    return ImageEmbedding(model_name=settings.embed_image_model)


def _embed_text(text: str) -> list[float]:
    return list(next(iter(_text_embedder().embed([text]))))


def _embed_image(image_bytes: bytes) -> list[float]:
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    return list(next(iter(_image_embedder().embed([img]))))


def ensure_collection() -> None:
    """Создаёт коллекцию (idempotent). Бросает при недоступности Qdrant."""
    from qdrant_client.models import Distance, VectorParams

    client = _client()
    if client.collection_exists(settings.qdrant_collection):
        return
    client.create_collection(
        collection_name=settings.qdrant_collection,
        vectors_config=VectorParams(size=settings.embed_dim, distance=Distance.COSINE),
    )


def index_catalog(db: Any) -> int:
    """Индексирует все товары (по названию) в Qdrant. Возвращает число точек.

    Best-effort: при недоступности Qdrant/модели логирует и возвращает 0.
    Вызывается из lifespan после seed; точку идентифицируем по product_id,
    поэтому повторный вызов перезаписывает (upsert), а не дублирует.
    """
    try:
        from qdrant_client.models import PointStruct
        from sqlalchemy import select

        from .models import Product

        ensure_collection()
        client = _client()
        rows = list(db.execute(select(Product)).scalars())
        if not rows:
            return 0
        points = [
            PointStruct(
                id=str(p.id),
                vector=_embed_text(p.name),
                payload={
                    "product_id": str(p.id),
                    "org_id": str(p.organization_id),
                    "name": p.name,
                    "barcode": p.barcode,
                },
            )
            for p in rows
        ]
        client.upsert(collection_name=settings.qdrant_collection, points=points)
        log.info("Каталог проиндексирован в Qdrant: %d товаров", len(points))
        return len(points)
    except Exception as e:  # noqa: BLE001 — индексация не должна валить старт
        log.warning("Индексация каталога в Qdrant пропущена: %s", e)
        return 0


def _photo_filter(product_id):
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    return Filter(must=[
        FieldCondition(key="product_id", match=MatchValue(value=str(product_id))),
        FieldCondition(key="has_image", match=MatchValue(value=True)),
    ])


def _photo_slots(product_id) -> set[int]:
    """Занятые слоты фото (0..4) для товара."""
    try:
        pts, _ = _client().scroll(
            collection_name=settings.qdrant_collection,
            scroll_filter=_photo_filter(product_id),
            limit=16, with_payload=True,
        )
        return {int(p.payload["slot"]) for p in pts
                if p.payload and p.payload.get("slot") is not None}
    except Exception:  # noqa: BLE001
        return set()


def count_product_images(product_id) -> int:
    return len(_photo_slots(product_id))


def add_product_image(product_id, org_id, name, barcode, image_bytes: bytes,
                      max_photos: int = 5) -> dict:
    """Добавить ещё одно ФОТО товара (до max_photos) — image-эмбеддинг CLIP в Qdrant.

    Возвращает {ok, count, limit}. Несколько ракурсов = несколько точек с одним
    product_id; поиск дедуплицируется по товару (берётся лучший матч).
    """
    try:
        from qdrant_client.models import PointStruct

        ensure_collection()
        slots = _photo_slots(product_id)
        if len(slots) >= max_photos:
            return {"ok": False, "count": len(slots), "limit": True}
        slot = next(s for s in range(max_photos) if s not in slots)
        vec = _embed_image(image_bytes)
        _client().upsert(
            collection_name=settings.qdrant_collection,
            points=[PointStruct(
                id=_photo_point_id(product_id, slot),
                vector=vec,
                payload={"product_id": str(product_id), "org_id": str(org_id),
                         "name": name, "barcode": barcode, "has_image": True, "slot": slot},
            )],
        )
        return {"ok": True, "count": len(slots) + 1, "limit": False}
    except Exception as e:  # noqa: BLE001
        log.warning("Индексация фото товара пропущена: %s", e)
        return {"ok": False, "count": 0, "limit": False, "error": str(e)}


def clear_product_images(product_id) -> bool:
    """Удалить все фото-точки товара (имя-текстовая точка остаётся)."""
    try:
        from qdrant_client.models import FilterSelector

        _client().delete(
            collection_name=settings.qdrant_collection,
            points_selector=FilterSelector(filter=_photo_filter(product_id)),
        )
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("Очистка фото товара не удалась: %s", e)
        return False


def _org_filter(org_id: str):
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    return Filter(
        must=[FieldCondition(key="org_id", match=MatchValue(value=str(org_id)))]
    )


def _search(vector: list[float], org_id: str, limit: int) -> list[dict]:
    try:
        # берём с запасом (у товара может быть несколько фото-точек) и дедуплицируем
        hits = _client().query_points(
            collection_name=settings.qdrant_collection,
            query=vector,
            query_filter=_org_filter(org_id),
            limit=max(limit * 4, 12),
            with_payload=True,
        ).points
    except Exception as e:  # noqa: BLE001 — поиск не должен валить агента
        log.warning("Поиск в Qdrant недоступен: %s", e)
        return []
    out: list[dict] = []
    seen: set = set()
    for h in hits:
        payload = h.payload or {}
        pid = payload.get("product_id")
        if pid in seen:  # один товар — один лучший матч (точки отсортированы по score)
            continue
        seen.add(pid)
        out.append({
            "product_id": pid,
            "name": payload.get("name", "?"),
            "barcode": payload.get("barcode"),
            "score": round(float(h.score), 3),
        })
        if len(out) >= limit:
            break
    return out


def search_by_text(name: str, org_id: str, limit: int = 3) -> list[dict]:
    """Сопоставить позицию накладной (текст) с каталогом тенанта."""
    if not name:
        return []
    try:
        vector = _embed_text(name)
    except Exception as e:  # noqa: BLE001
        log.warning("Эмбеддинг текста недоступен: %s", e)
        return []
    return _search(vector, org_id, limit)


def search_by_image(image_bytes: bytes, org_id: str, limit: int = 5) -> list[dict]:
    """Найти товар каталога тенанта по фото (CLIP image->text)."""
    if not image_bytes:
        return []
    try:
        vector = _embed_image(image_bytes)
    except Exception as e:  # noqa: BLE001
        log.warning("Эмбеддинг изображения недоступен: %s", e)
        return []
    return _search(vector, org_id, limit)
