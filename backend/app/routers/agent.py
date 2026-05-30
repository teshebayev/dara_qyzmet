"""Агент поддержки: отвечает по стоку/заявкам/расхождениям (ТЗ 9).

Инструменты — только чтение, всегда с фильтром по organization_id вызвавшего.
mock-режим: маршрутизация по ключевым словам (работает без LLM).
real-режим: tool-calling через OpenAI-совместимый LLM (vLLM).
"""
from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import Principal, get_principal
from ..models import Discrepancy, Order, Product, Stock
from ..schemas import AgentAsk, AgentReply

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])


# ---------- инструменты (читают только данные тенанта) ----------


def tool_get_stock(db: Session, org_id, query: str | None = None) -> list[dict]:
    stmt = (
        select(Product.name, Stock.quantity)
        .join(Stock, Stock.product_id == Product.id)
        .where(Stock.organization_id == org_id)
    )
    if query:
        stmt = stmt.where(Product.name.ilike(f"%{query}%"))
    return [{"name": n, "quantity": float(q)} for n, q in db.execute(stmt).all()]


def tool_get_orders(db: Session, org_id, status: str | None = None) -> list[dict]:
    stmt = select(Order).where(
        (Order.store_org_id == org_id) | (Order.supplier_org_id == org_id)
    )
    if status:
        stmt = stmt.where(Order.status == status)
    return [
        {"id": str(o.id), "status": o.status, "created_at": o.created_at.isoformat()}
        for o in db.scalars(stmt.order_by(Order.created_at.desc()).limit(20))
    ]


def tool_get_discrepancies(db: Session, org_id, dtype: str | None = None) -> list[dict]:
    rows = db.execute(
        select(Discrepancy.type, func.count()).group_by(Discrepancy.type)
    ).all()
    return [{"type": t, "count": c} for t, c in rows if (not dtype or t == dtype)]


def tool_find_product(db: Session, org_id, query: str) -> list[dict]:
    stmt = select(Product).where(
        Product.organization_id == org_id, Product.name.ilike(f"%{query}%")
    )
    return [{"name": p.name, "barcode": p.barcode} for p in db.scalars(stmt.limit(10))]


TOOLS_SPEC = [
    {
        "type": "function",
        "function": {
            "name": "get_stock",
            "description": "Остатки товаров на складе организации",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_orders",
            "description": "Заявки/поставки, опционально по статусу",
            "parameters": {
                "type": "object",
                "properties": {"status": {"type": "string"}},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_discrepancies",
            "description": "Сводка расхождений по типам",
            "parameters": {
                "type": "object",
                "properties": {"dtype": {"type": "string"}},
            },
        },
    },
]


def _dispatch(name: str, args: dict, db: Session, org_id) -> list[dict]:
    if name == "get_stock":
        return tool_get_stock(db, org_id, args.get("query"))
    if name == "get_orders":
        return tool_get_orders(db, org_id, args.get("status"))
    if name == "get_discrepancies":
        return tool_get_discrepancies(db, org_id, args.get("dtype"))
    if name == "find_product":
        return tool_find_product(db, org_id, args.get("query", ""))
    return []


def _mock_answer(message: str, db: Session, org_id) -> AgentReply:
    m = message.lower()
    if any(w in m for w in ("остат", "сток", "склад", "сколько")):
        data = tool_get_stock(db, org_id)
        if not data:
            return AgentReply(answer="На складе пока нет остатков.", used_tools=["get_stock"])
        lines = "; ".join(f"{d['name']} — {d['quantity']:g}" for d in data[:10])
        return AgentReply(answer=f"Текущие остатки: {lines}.", used_tools=["get_stock"])
    if any(w in m for w in ("расхожд", "недостач", "пересорт", "брак", "излиш")):
        data = tool_get_discrepancies(db, org_id)
        if not data:
            return AgentReply(answer="Расхождений не зафиксировано.", used_tools=["get_discrepancies"])
        lines = ", ".join(f"{d['type']}: {d['count']}" for d in data)
        return AgentReply(answer=f"Расхождения по типам: {lines}.", used_tools=["get_discrepancies"])
    if any(w in m for w in ("заявк", "поставк", "статус", "заказ")):
        data = tool_get_orders(db, org_id)
        lines = ", ".join(f"{d['id'][:8]}={d['status']}" for d in data[:10])
        return AgentReply(answer=f"Последние заявки: {lines or 'нет'}.", used_tools=["get_orders"])
    return AgentReply(
        answer="Могу подсказать по остаткам, заявкам и расхождениям. Спросите, например: «сколько молока на складе?»",
        used_tools=[],
    )


def _llm_answer(message: str, db: Session, org_id) -> AgentReply:
    """Реальный tool-calling через OpenAI-совместимый эндпоинт."""
    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    messages = [
        {"role": "system", "content": "Ты ассистент склада. Используй инструменты для точных данных. Отвечай кратко на русском."},
        {"role": "user", "content": message},
    ]
    used: list[str] = []
    with httpx.Client(timeout=settings.request_timeout) as client:
        for _ in range(4):  # ограничение итераций tool-calling
            resp = client.post(
                url,
                headers=headers,
                json={"model": settings.llm_model, "messages": messages, "tools": TOOLS_SPEC},
            )
            resp.raise_for_status()
            msg = resp.json()["choices"][0]["message"]
            calls = msg.get("tool_calls")
            if not calls:
                return AgentReply(answer=msg.get("content", ""), used_tools=used)
            messages.append(msg)
            for call in calls:
                name = call["function"]["name"]
                args = json.loads(call["function"].get("arguments") or "{}")
                used.append(name)
                result = _dispatch(name, args, db, org_id)
                messages.append(
                    {"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False)}
                )
    return AgentReply(answer="Не удалось получить ответ модели.", used_tools=used)


@router.post("/ask", response_model=AgentReply)
def ask(
    body: AgentAsk,
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> AgentReply:
    if settings.mock_vlm:
        return _mock_answer(body.message, db, p.org_id)
    try:
        return _llm_answer(body.message, db, p.org_id)
    except httpx.HTTPError:
        return _mock_answer(body.message, db, p.org_id)
