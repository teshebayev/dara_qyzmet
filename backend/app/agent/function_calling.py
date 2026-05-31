"""LLM-агент по паттерну ReAct (Reason + Act).

Каждый шаг — JSON по строгой схеме (guided_json + Pydantic, tool_schemas.ReactStep):
сначала thought (рассуждение), затем либо действие-инструмент (action + action_input),
либо финал (action="final_answer" + текст ответа). Цикл:

    Thought -> Action(tool, input) -> Observation(результат) -> ... -> Final Answer

«Рассуждение вслух» перед действием улучшает выбор инструмента на слабой модели,
а guided_json делает каждый шаг машинно-надёжным. Финальный ответ пишет сама модель
(ветка final_answer) — никаких шаблонов.

Память: история диалога подаётся в контекст. session_id (= conversation_id)
группирует трейсы беседы в Langfuse. Запись (создание заявки) модели не доверяется —
есть только propose_order_draft (read-only), заявку создаёт пользователь подтверждением.
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
from .tool_schemas import (
    TOOL_ARG_MODELS,
    coerce_args,
    react_action_schema,
    react_step_schema,
    tool_signature,
)


@dataclass
class Ctx:
    db: Any
    org_id: str
    user_id: str
    image_b64: str | None = None


# ----------------------- адаптеры инструментов (ctx, **args) -----------------------

def _stock(ctx, query=None):            return T.tool_get_stock(ctx.db, ctx.org_id, query)
def _low_stock(ctx, threshold=10.0):    return T.tool_reorder_suggestions(ctx.db, ctx.org_id, threshold)
def _discrepancies(ctx, type=None, **_):
    # Всегда отдаём полную разбивку по типам — слабая модель часто сужает type
    # до отсутствующего значения (shortage при наличии только defect) и получает
    # пусто, после чего отвечает «расхождений нет». Фильтрацию по типу пусть делает
    # сама по этим данным.
    return T.tool_discrepancy_report(ctx.db, ctx.org_id, None)
def _supplier_quality(ctx):             return T.tool_supplier_quality(ctx.db, ctx.org_id)
def _top_products(ctx, limit=5):        return T.tool_top_products(ctx.db, ctx.org_id, limit)
def _find_product(ctx, query=None):     return T.tool_find_product(ctx.db, ctx.org_id, query or "", limit=5)


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

# Назначение каждого инструмента (что он делает и когда его звать). Аргументы
# подставляются автоматически из Pydantic-моделей (tool_signature) — единый источник.
TOOL_DESCRIPTIONS = {
    "get_stock": "текущие остатки товара на складе; query — название товара (можно без него — вернёт весь сток)",
    "low_stock": "товары на исходе / что нужно дозаказать, с предлагаемым поставщиком",
    "discrepancy_report": "расхождения приёмки (недостача/излишек/пересорт/брак): сводка по типам и список позиций",
    "supplier_quality": "рейтинг поставщиков по браку и недостачам",
    "delivery_status": "статусы заявок магазина; supplier — поставщик, status — статус",
    "spend": "сумма расходов по подтверждённым накладным; supplier и даты YYYY-MM-DD необязательны",
    "top_products": "самые заказываемые товары; limit — сколько вернуть",
    "find_product": "найти конкретный товар в каталоге по названию; query — название",
    "search_product_by_photo": "найти товар по приложенному к сообщению фото",
    "propose_order_draft": "предложить черновик заявки на поставку; items = список товаров с количеством, supplier — поставщик",
}


def _tools_doc() -> str:
    """Спецификация инструментов для LLM: имя(аргументы) — описание.
    Модель сама выбирает инструмент по описаниям и генерирует action_input."""
    lines = []
    for name in TOOL_ARG_MODELS:
        sig = tool_signature(name)
        lines.append(f"- {name}({sig}) — {TOOL_DESCRIPTIONS.get(name, '')}")
    return "\n".join(lines)


_SYSTEM = (
    "Ты — ассистент склада магазина. Сегодня {today}. Работаешь по циклу ReAct.\n"
    "На КАЖДОМ шаге возвращай ОДИН JSON-объект:\n"
    "1) thought — рассуждение: что нужно узнать и каким инструментом;\n"
    "2) затем либо действие-инструмент: action = имя инструмента, action_input = его аргументы "
    "(строго по сигнатуре инструмента);\n"
    '   либо финал: action = "final_answer", final_answer = ответ пользователю на русском.\n'
    "После каждого действия ты получишь Observation (результат инструмента) и продолжишь.\n\n"
    "Доступные инструменты:\n{tools}\n\n"
    "Выбирай инструмент по его описанию и сути запроса. Числа бери ТОЛЬКО из Observation, "
    "не выдумывай. Как только данных достаточно — верни final_answer (кратко, по делу). "
    "propose_order_draft вызывай сразу (без проверки остатков); это лишь предложение — "
    "заявку создаёт пользователь подтверждением."
)


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        return json.loads(m.group(0)) if m else {"action": "final_answer", "final_answer": ""}


def _history_msgs(history):
    out = []
    for h in (history or []):
        if h.get("role") in ("user", "assistant") and h.get("content"):
            out.append({"role": h["role"], "content": h["content"]})
    return out


def run(message: str, settings: Any, ctx: Ctx, history: list | None = None,
        session_id: str = "", user_id: str = "", max_steps: int = 6) -> dict:
    """ReAct: на каждом шаге модель рассуждает (thought) и либо вызывает инструмент
    (action+input), либо завершает (final_answer). Результаты инструментов
    возвращаются как Observation, пока модель не сформулирует финальный ответ."""
    today = datetime.now().date().isoformat()
    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    image_note = " (К сообщению приложено фото товара — используй search_product_by_photo.)" if ctx.image_b64 else ""

    messages: list[dict] = [{"role": "system", "content": _SYSTEM.format(today=today, tools=_tools_doc())}]
    messages += _history_msgs(history)
    messages.append({"role": "user", "content": message + image_note})

    used: list[str] = []
    data: dict = {}
    answer = ""

    trace_kw = {"input": {"message": message}, "metadata": {"org_id": ctx.org_id}}
    if session_id:
        trace_kw["session_id"] = session_id
    if user_id:
        trace_kw["user_id"] = user_id

    with obs.trace(name="agent", **trace_kw) as tr, \
         httpx.Client(timeout=getattr(settings, "request_timeout", 60.0)) as client:

        def _chat(msgs, schema=None, temperature=0.0):
            payload = {"model": settings.llm_model, "messages": msgs, "temperature": temperature}
            if schema:
                # response_format — этот vLLM реально форсит схему (guided_json игнорит)
                payload["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": "react_step", "schema": schema},
                }
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()

        def _exec(name: str, args: dict) -> dict:
            """Выполнить инструмент. Никогда не бросает — ошибка возвращается как результат."""
            fn = TOOL_FUNCS.get(name)
            try:
                result = fn(ctx, **args) if fn else {"error": f"неизвестный инструмент {name}"}
            except Exception as e:  # noqa: BLE001
                result = {"error": str(e)}
            if name == "propose_order_draft" and isinstance(result, dict) and result.get("draft"):
                data["draft"] = result["draft"]
            with obs.span(tr, name=f"tool.{name}", input=args) as ts:
                obs.update(ts, output=result)
            return result

        schema_full = react_step_schema()
        schema_action = react_action_schema()
        seen: set = set()  # повторные одинаковые вызовы -> данных достаточно, к финалу

        # Цикл ReAct: thought -> action -> observation -> ... -> final_answer.
        # Пока не выполнен ни один инструмент — запрещаем final_answer (схема без
        # него), иначе слабая модель сразу выдумывает ответ, не собрав данные.
        for _ in range(max_steps):
            schema = schema_full if used else schema_action
            with obs.generation(tr, name="vllm.react", model=settings.llm_model, input=messages) as gen:
                body = _chat(messages, schema=schema)
                content = body["choices"][0]["message"].get("content") or ""
                u = body.get("usage") or {}
                obs.update(gen, output=content, usage={
                    "input": u.get("prompt_tokens"), "output": u.get("completion_tokens"),
                    "total": u.get("total_tokens")})

            raw = _parse_json(content)
            action = raw.get("action")
            final_text = raw.get("final_answer", "")

            if action == "final_answer" or action not in TOOL_FUNCS:
                answer = (final_text or "").strip()
                if answer:
                    break
                # модель не дала текст — просим завершить на следующем витке
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content":
                    "Сформулируй final_answer для пользователя по уже собранным данным."})
                continue

            args = coerce_args(action, raw.get("action_input") or {})  # типизация по модели тула
            key = action + ":" + json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
            if key in seen:
                break  # тот же вызов повторно — данных достаточно, идём к финалу
            seen.add(key)

            result = _exec(action, args)
            used.append(action)
            messages.append({"role": "assistant", "content": content})  # Thought + Action
            messages.append({"role": "user", "content":
                f"Observation ({action}): " + json.dumps(result, ensure_ascii=False, default=str)
                + "\nЕсли этого достаточно для ответа (даже если результат пуст) — верни final_answer, не повторяй тот же вызов."})

        # Подстраховка для фото: если модель не вызвала поиск по фото — делаем сами.
        if ctx.image_b64 and "search_product_by_photo" not in used:
            result = _exec("search_product_by_photo", {})
            used.append("search_product_by_photo")
            messages.append({"role": "user", "content":
                "Observation (search_product_by_photo): " + json.dumps(result, ensure_ascii=False, default=str)
                + "\nСформулируй final_answer."})
            answer = ""

        # Финальный ответ, если цикл не дал текста (исчерпан лимит шагов / фото-фолбэк).
        if not answer:
            with obs.generation(tr, name="vllm.final", model=settings.llm_model, input=messages) as gen:
                body = _chat(messages + [{"role": "user", "content":
                    "Дай ответ пользователю по собранным данным, обычным текстом."}], temperature=0.3)
                answer = (body["choices"][0]["message"].get("content") or "").strip()
                u = body.get("usage") or {}
                obs.update(gen, output=answer, usage={
                    "input": u.get("prompt_tokens"), "output": u.get("completion_tokens"),
                    "total": u.get("total_tokens")})

        answer = answer or "Готово."
        obs.update(tr, output={"answer": answer, "used_tools": used})
        return {"answer": answer, "used_tools": used, "data": data}
