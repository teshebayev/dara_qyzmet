"""LLM-агент: модель сама выбирает инструмент, получает результат и СВОБОДНО
формулирует ответ.

Надёжность на слабой модели:
* выбор инструмента — через guided_json (узкая схема решения) -> без «мусорных» вызовов;
* финальный ответ — обычная генерация по данным инструментов (живой текст, не шаблон).

Память: история диалога подаётся в контекст. session_id (= conversation_id)
группирует трейсы беседы в Langfuse. Запись (создание заявки) модели не доверяется —
есть только propose_order_draft, заявку создаёт пользователь подтверждением.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx

from . import tools as T
from .. import observability as obs


@dataclass
class Ctx:
    db: Any
    org_id: str
    user_id: str
    image_b64: str | None = None


# ----------------------- адаптеры инструментов (ctx, **args) -----------------------

def _stock(ctx, query=None):            return T.tool_get_stock(ctx.db, ctx.org_id, query)
def _low_stock(ctx, threshold=10.0):    return T.tool_reorder_suggestions(ctx.db, ctx.org_id, threshold)
def _discrepancies(ctx, type=None):     return T.tool_discrepancy_report(ctx.db, ctx.org_id, type)
def _supplier_quality(ctx):             return T.tool_supplier_quality(ctx.db, ctx.org_id)
def _top_products(ctx, limit=5):        return T.tool_top_products(ctx.db, ctx.org_id, limit)
def _find_product(ctx, query):          return T.tool_find_product(ctx.db, ctx.org_id, query, limit=5)


def _delivery_status(ctx, supplier=None, status=None):
    sup = T.resolve_supplier(ctx.db, ctx.org_id, supplier or "", supplier)
    return T.tool_delivery_status(ctx.db, ctx.org_id, sup["supplier_org_id"] if sup else None, status)


def _spend(ctx, supplier=None, date_from=None, date_to=None):
    sup = T.resolve_supplier(ctx.db, ctx.org_id, supplier or "", supplier)
    return T.tool_spend(ctx.db, ctx.org_id, sup["supplier_org_id"] if sup else None, date_from, date_to)


def _search_by_photo(ctx):
    if not ctx.image_b64:
        return {"error": "К запросу не приложено изображение."}
    return T.tool_search_product_by_photo(ctx.org_id, ctx.image_b64)


def _propose_order_draft(ctx, items=None, supplier=None):
    sup = T.resolve_supplier(ctx.db, ctx.org_id, supplier or "", supplier)
    if not sup:
        return {"ok": False, "reason": "Не нашёл поставщика. Уточните, у кого заказать."}
    draft, missing = T.build_order_draft(ctx.db, ctx.org_id, items or [], sup)
    return {"ok": True, "draft": draft, "missing": missing}


TOOL_FUNCS = {
    "get_stock": _stock,
    "low_stock": _low_stock,
    "discrepancy_report": _discrepancies,
    "supplier_quality": _supplier_quality,
    "delivery_status": _delivery_status,
    "spend": _spend,
    "top_products": _top_products,
    "find_product": _find_product,
    "search_product_by_photo": _search_by_photo,
    "propose_order_draft": _propose_order_draft,
}

# Краткое описание инструментов для промпта (имя + назначение + параметры).
_TOOLS_DOC = "\n".join([
    "- get_stock(query?): остатки товаров на складе",
    "- low_stock(): что на исходе + предлагаемый поставщик для дозаказа",
    "- discrepancy_report(type?): сводка расхождений по типам",
    "- supplier_quality(): рейтинг поставщиков по браку/недостачам",
    "- delivery_status(supplier?, status?): статус заявок по поставщику",
    "- spend(supplier?, date_from?, date_to?): сумма по подтверждённым накладным за период (YYYY-MM-DD)",
    "- top_products(limit?): топ товаров по заказам",
    "- find_product(query): найти товар в каталоге по названию",
    "- search_product_by_photo(): найти товар по приложенному фото",
    "- propose_order_draft(items, supplier?): ПРЕДЛОЖИТЬ черновик заявки (items=[{name, qty}]); "
    "заявку создаёт пользователь, не ты",
])

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["tool", "final"]},
        "tool": {"type": ["string", "null"]},
        "args": {"type": "object"},
    },
    "required": ["action"],
}

_DECIDE_SYSTEM = (
    "Ты — ассистент склада магазина. Сегодня {today}. Решай по шагам, какой инструмент "
    "вызвать, чтобы ответить на запрос. Инструменты:\n{tools}\n\n"
    "Верни СТРОГО один JSON:\n"
    '- вызвать инструмент: {{"action":"tool","tool":"<имя>","args":{{...}}}}\n'
    '- если данных уже достаточно: {{"action":"final"}}\n'
    "Не выдумывай числа — бери их только из инструментов. Для заказа используй propose_order_draft."
)

_ANSWER_SYSTEM = (
    "Ты — ассистент склада магазина. Сегодня {today}. Ответь пользователю кратко, "
    "дружелюбно и по делу на русском, опираясь ТОЛЬКО на данные инструментов ниже. "
    "Если данных нет или они пустые — честно скажи об этом. Не выдумывай числа. "
    "Если предложен черновик заявки — перечисли позиции и спроси, создать ли черновик."
)


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group(0)) if m else {"action": "final"}


def _history_msgs(history):
    out = []
    for h in (history or []):
        if h.get("role") in ("user", "assistant") and h.get("content"):
            out.append({"role": h["role"], "content": h["content"]})
    return out


def run(message: str, settings: Any, ctx: Ctx, history: list | None = None,
        session_id: str = "", user_id: str = "", max_steps: int = 4) -> dict:
    """LLM выбирает инструменты (guided_json) и затем свободно формулирует ответ."""
    today = datetime.now().date().isoformat()
    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    image_note = " (К сообщению приложено фото товара — используй search_product_by_photo.)" if ctx.image_b64 else ""

    decide_msgs = [{"role": "system", "content": _DECIDE_SYSTEM.format(today=today, tools=_TOOLS_DOC)}]
    decide_msgs += _history_msgs(history)
    decide_msgs.append({"role": "user", "content": message + image_note})

    used: list[str] = []
    data: dict = {}
    tool_results: list[tuple] = []

    trace_kw = {"input": {"message": message}, "metadata": {"org_id": ctx.org_id}}
    if session_id:
        trace_kw["session_id"] = session_id
    if user_id:
        trace_kw["user_id"] = user_id

    with obs.trace(name="agent", **trace_kw) as tr, \
         httpx.Client(timeout=getattr(settings, "request_timeout", 60.0)) as client:

        def _chat(messages, guided=None, temperature=0.0):
            payload = {"model": settings.llm_model, "messages": messages, "temperature": temperature}
            if guided:
                payload["guided_json"] = guided
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

        # 1) Цикл выбора инструментов (guided_json)
        for _ in range(max_steps):
            with obs.generation(tr, name="vllm.decide", model=settings.llm_model, input=decide_msgs) as gen:
                body = _chat(decide_msgs, guided=DECISION_SCHEMA)
                content = body["choices"][0]["message"].get("content") or ""
                u = body.get("usage") or {}
                obs.update(gen, output=content, usage={
                    "input": u.get("prompt_tokens"), "output": u.get("completion_tokens"),
                    "total": u.get("total_tokens")})
            d = _parse_json(content)
            tool = d.get("tool")
            if d.get("action") != "tool" or not tool:
                break
            args = d.get("args") or {}
            used.append(tool)
            fn = TOOL_FUNCS.get(tool)
            try:
                result = fn(ctx, **args) if fn else {"error": f"неизвестный инструмент {tool}"}
            except Exception as e:  # noqa: BLE001
                result = {"error": str(e)}
            if tool == "propose_order_draft" and isinstance(result, dict) and result.get("draft"):
                data["draft"] = result["draft"]
            with obs.span(tr, name=f"tool.{tool}", input=args) as ts:
                obs.update(ts, output=result)
            tool_results.append((tool, result))
            decide_msgs.append({"role": "assistant", "content": content})
            decide_msgs.append({"role": "user", "content":
                f"Результат {tool}: " + json.dumps(result, ensure_ascii=False, default=str)
                + '\nЕсли данных достаточно — верни {"action":"final"}, иначе вызови ещё инструмент.'})

        # подстраховка для фото: если модель не вызвала поиск по фото — делаем сами
        if ctx.image_b64 and "search_product_by_photo" not in used:
            res = _search_by_photo(ctx)
            used.append("search_product_by_photo")
            tool_results.append(("search_product_by_photo", res))

        # 2) Свободный финальный ответ (обычная генерация по данным инструментов)
        ans_msgs = [{"role": "system", "content": _ANSWER_SYSTEM.format(today=today)}]
        ans_msgs += _history_msgs(history)
        ans_msgs.append({"role": "user", "content": message})
        for name, result in tool_results:
            ans_msgs.append({"role": "user", "content":
                f"Данные инструмента {name}: " + json.dumps(result, ensure_ascii=False, default=str)})
        ans_msgs.append({"role": "user", "content": "Сформулируй ответ пользователю."})

        with obs.generation(tr, name="vllm.answer", model=settings.llm_model, input=ans_msgs) as gen:
            body = _chat(ans_msgs, temperature=0.3)
            answer = body["choices"][0]["message"].get("content") or ""
            u = body.get("usage") or {}
            obs.update(gen, output=answer, usage={
                "input": u.get("prompt_tokens"), "output": u.get("completion_tokens"),
                "total": u.get("total_tokens")})

        answer = answer.strip() or "Готово."
        obs.update(tr, output={"answer": answer, "used_tools": used})
        return {"answer": answer, "used_tools": used, "data": data}
