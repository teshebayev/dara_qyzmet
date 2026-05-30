"""Агент поддержки (ТЗ 9). Логика — в пакете `app.agent` (LangGraph).

Реальный режим: function-calling на guided_json — LLM сам выбирает и вызывает
инструменты. Память диалога хранится в БД (AgentConversation/AgentMessage): на
каждый запрос подгружаем историю разговора в контекст и сохраняем новые реплики.
Все инструменты фильтруют данные по organization_id вызвавшего (изоляция тенантов).
"""
from __future__ import annotations

import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..agent.graph import build_graph
from ..agent.state import AgentState
from ..config import settings
from ..db import get_db
from ..deps import Principal, get_principal
from ..models import AgentConversation, AgentMessage
from ..schemas import AgentAsk, AgentMessageOut, AgentReply

router = APIRouter(prefix="/api/v1/agent", tags=["agent"])

_HISTORY_LIMIT = 20  # сколько последних реплик подаём в контекст


def _get_conversation(body: AgentAsk, p: Principal, db: Session) -> AgentConversation:
    if body.conversation_id:
        conv = db.get(AgentConversation, body.conversation_id)
        if conv and conv.user_id == p.user_id:
            return conv
    conv = AgentConversation(user_id=p.user_id, title=(body.message or "")[:120])
    db.add(conv)
    db.flush()
    return conv


def _load_history(conv_id: uuid.UUID, db: Session) -> list[dict]:
    rows = list(db.scalars(
        select(AgentMessage)
        .where(AgentMessage.conversation_id == conv_id)
        .order_by(AgentMessage.created_at.desc())
        .limit(_HISTORY_LIMIT)
    ))
    rows.reverse()
    return [{"role": m.role, "content": m.content}
            for m in rows if m.content and m.role in ("user", "assistant")]


@router.post("/ask", response_model=AgentReply)
def ask(
    body: AgentAsk,
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> AgentReply:
    conv = _get_conversation(body, p, db)
    history = _load_history(conv.id, db)

    # Граф строим на запрос: get_db замыкается на сессию ИМЕННО этого запроса.
    graph = build_graph(get_db=lambda: db, settings=settings)
    confirm_draft = body.confirm_draft.model_dump(mode="json") if body.confirm_draft else None
    state = AgentState(
        message=body.message,
        org_id=str(p.org_id),
        user_id=str(p.user_id),
        image_b64=body.image_b64,
        confirm_draft=confirm_draft,
        conversation_id=str(conv.id),
        history=history,
    )
    try:
        result = graph.invoke(state)
    except httpx.HTTPStatusError as e:
        body_text = ""
        try:
            body_text = (e.response.text or "")[:400]
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(
            502,
            f"Модель вернула ошибку {e.response.status_code}. "
            "Возможно, неверное имя модели или модель недоступна. "
            f"Ответ модели: {body_text}",
        ) from e
    except httpx.HTTPError as e:
        raise HTTPException(
            503,
            f"Не удалось обратиться к модели ({type(e).__name__}): {e}. "
            "Проверьте, что vLLM запущен и доступен по OPENAI_BASE_URL.",
        ) from e
    except Exception as e:  # noqa: BLE001 — диагностика прочих сбоев агента
        raise HTTPException(502, f"Ошибка агента: {type(e).__name__}: {e}") from e

    answer = result.get("answer", "")
    # сохраняем реплики в память диалога
    db.add(AgentMessage(conversation_id=conv.id, role="user", content=body.message))
    db.add(AgentMessage(conversation_id=conv.id, role="assistant", content=answer))
    db.commit()

    return AgentReply(
        answer=answer,
        used_tools=result.get("used_tools", []),
        data=result.get("data", {}),
        conversation_id=conv.id,
    )


@router.get("/messages", response_model=list[AgentMessageOut])
def messages(
    conversation_id: uuid.UUID,
    p: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> list[AgentMessage]:
    """История разговора (для восстановления переписки в UI)."""
    conv = db.get(AgentConversation, conversation_id)
    if not conv or conv.user_id != p.user_id:
        raise HTTPException(404, "Разговор не найден")
    rows = db.scalars(
        select(AgentMessage)
        .where(AgentMessage.conversation_id == conv.id)
        .order_by(AgentMessage.created_at.asc())
    )
    return [m for m in rows if m.role in ("user", "assistant")]
