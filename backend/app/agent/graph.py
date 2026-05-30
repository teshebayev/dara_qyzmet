"""Сборка графа LangGraph: supervisor -> agent (LLM) / order -> ответ.

Весь интеллект — в LLM-агенте (agent/function_calling.py): модель сама выбирает
инструменты и свободно формулирует ответ. Детерминированный узел остаётся только
для записи: создание заявки из ПОДТВЕРЖДЁННОГО черновика (LLM не пишет в БД).

Маршрутизация: confirm_draft -> order; иначе -> agent (включая запросы с фото).
"""
from __future__ import annotations

from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from . import function_calling as fc
from .state import AgentState
from .tools import tool_create_order_draft


def _g(x) -> str:
    return f"{float(x or 0):g}"


def build_graph(get_db: Callable[[], Any], settings: Any):
    """Собирает и компилирует граф. get_db() -> SQLAlchemy Session."""

    def supervisor_node(state: AgentState) -> dict:
        return {"route": "order" if state.confirm_draft else "agent"}

    def agent_node(state: AgentState) -> dict:
        ctx = fc.Ctx(db=get_db(), org_id=state.org_id,
                     user_id=state.user_id, image_b64=state.image_b64)
        return fc.run(state.message, settings, ctx, history=state.history,
                      session_id=state.conversation_id, user_id=state.user_id)

    def order_node(state: AgentState) -> dict:
        # создание заявки из подтверждённого черновика (детерминировано, без LLM)
        db = get_db()
        d = state.confirm_draft or {}
        res = tool_create_order_draft(db, state.org_id, state.user_id,
                                      d.get("supplier_org_id"), d.get("items", []))
        if not res:
            return {"answer": "Не удалось создать черновик: не указан поставщик или позиции."}
        lines = ", ".join(f"{i['name']} {_g(i['qty_ordered'])} шт" for i in res["items"])
        return {
            "answer": (f"Черновик заявки создан (№ {res['order_id'][:8]}, статус «новая»): {lines}. "
                       "Проверьте его во вкладке «Заявки» и отправьте поставщику."),
            "used_tools": ["create_order_draft"],
            "data": {"created_order": res},
        }

    g = StateGraph(AgentState)
    g.add_node("supervisor", supervisor_node)
    g.add_node("agent", agent_node)
    g.add_node("order", order_node)
    g.add_edge(START, "supervisor")
    g.add_conditional_edges("supervisor", lambda s: s.route,
                            {"agent": "agent", "order": "order"})
    g.add_edge("agent", END)
    g.add_edge("order", END)
    return g.compile()
