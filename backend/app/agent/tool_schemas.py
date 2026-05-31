"""Pydantic-схемы аргументов инструментов агента.

На каждый инструмент — своя модель аргументов. Из них собирается единая
discriminated-union JSON-schema «решения», которую отдаём в vLLM `guided_json`,
чтобы модель ЖЁСТКО (на уровне грамматики генерации) возвращала только валидные
имена и типы аргументов конкретного инструмента. Эти же модели валидируют ответ
на стороне кода — двойная страховка против «выдуманных» аргументов слабой LLM.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class _Args(BaseModel):
    # extra="forbid" -> в JSON-schema additionalProperties:false:
    # модель не сможет дописать лишние ключи.
    model_config = ConfigDict(extra="forbid")


class GetStockArgs(_Args):
    query: Optional[str] = Field(None, description="Фильтр по названию товара")


class LowStockArgs(_Args):
    threshold: float = Field(10.0, description="Порог остатка для алерта")


class DiscrepancyReportArgs(_Args):
    pass  # без аргументов — инструмент всегда отдаёт полную разбивку по типам


class SupplierQualityArgs(_Args):
    pass


class DeliveryStatusArgs(_Args):
    supplier: Optional[str] = Field(None, description="Название поставщика")
    status: Optional[str] = Field(None, description="Статус заявки")


class SpendArgs(_Args):
    supplier: Optional[str] = Field(None, description="Название поставщика")
    date_from: Optional[str] = Field(None, description="Дата с, YYYY-MM-DD")
    date_to: Optional[str] = Field(None, description="Дата по, YYYY-MM-DD")


class TopProductsArgs(_Args):
    limit: int = Field(5, ge=1, le=50, description="Сколько позиций вернуть")


class FindProductArgs(_Args):
    query: Optional[str] = Field(None, description="Название товара для поиска")


class SearchByPhotoArgs(_Args):
    pass


class OrderDraftItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., description="Название товара")
    qty: Optional[float] = Field(None, description="Количество")


class ProposeOrderDraftArgs(_Args):
    items: list[OrderDraftItem] = Field(default_factory=list, description="Позиции заявки")
    supplier: Optional[str] = Field(None, description="Поставщик")


# имя инструмента -> модель его аргументов (единый источник правды)
TOOL_ARG_MODELS: dict[str, type[_Args]] = {
    "get_stock": GetStockArgs,
    "low_stock": LowStockArgs,
    "discrepancy_report": DiscrepancyReportArgs,
    "supplier_quality": SupplierQualityArgs,
    "delivery_status": DeliveryStatusArgs,
    "spend": SpendArgs,
    "top_products": TopProductsArgs,
    "find_product": FindProductArgs,
    "search_product_by_photo": SearchByPhotoArgs,
    "propose_order_draft": ProposeOrderDraftArgs,
}


def _const_to_enum(node):
    """Некоторые парсеры надёжнее работают с enum, чем с const — конвертируем."""
    if isinstance(node, dict):
        if "const" in node and "enum" not in node:
            node["enum"] = [node.pop("const")]
        for v in node.values():
            _const_to_enum(v)
    elif isinstance(node, list):
        for v in node:
            _const_to_enum(v)
    return node


def tool_parameters_schema(tool: str) -> dict:
    """JSON-schema аргументов инструмента (поле `parameters` в OpenAI tools-спеке).
    Берётся прямо из Pydantic-модели — единый источник правды по аргументам."""
    model = TOOL_ARG_MODELS[tool]
    return _const_to_enum(model.model_json_schema())


# ── ReAct: шаг = thought -> (action + action_input | final_answer) ─────────────
# Плоская схема (НЕ anyOf): action — строгий enum, поэтому constrained-decoding
# надёжно форсит выбор инструмента. thought идёт первым полем — модель сначала
# рассуждает, потом действует (приём ReAct, поднимает точность на слабой модели).
# action_input — свободный объект, который валидируется по модели тула (coerce_args).

ACTION_NAMES = list(TOOL_ARG_MODELS)


def react_step_schema(allow_final: bool = True) -> dict:
    """JSON-schema одного шага ReAct для response_format.
    allow_final=False -> без final_answer (заставляет вызвать инструмент на 1-м шаге)."""
    actions = ACTION_NAMES + (["final_answer"] if allow_final else [])
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "thought": {"type": "string", "description": "рассуждение: что нужно и каким инструментом"},
            "action": {"type": "string", "enum": actions},
            "action_input": {"type": "object", "description": "аргументы инструмента (для action != final_answer)"},
            "final_answer": {"type": "string", "description": "ответ пользователю (только для action=final_answer)"},
        },
        "required": ["thought", "action"],
    }


def react_action_schema() -> dict:
    """Шаг без final_answer — модель обязана выбрать инструмент."""
    return react_step_schema(allow_final=False)


_PY_TYPE = {"string": "str", "number": "float", "integer": "int", "boolean": "bool", "array": "list"}


def tool_signature(tool: str) -> str:
    """Сигнатура аргументов тула для описания в промпте, напр. "query?: str".
    Берётся прямо из Pydantic-модели (имя, тип, обязательность) — единый источник."""
    model = TOOL_ARG_MODELS[tool]
    props = model.model_json_schema().get("properties", {})
    parts = []
    for name, field in model.model_fields.items():
        schema = props.get(name, {})
        t = schema.get("type")
        if not t and "anyOf" in schema:
            t = next((o.get("type") for o in schema["anyOf"] if o.get("type") not in (None, "null")), None)
        opt = "" if field.is_required() else "?"
        parts.append(f"{name}{opt}: {_PY_TYPE.get(t, t or 'any')}")
    return ", ".join(parts)


# синонимы имён аргументов: слабая модель часто называет их по-своему
ARG_ALIASES = {
    "name": "query", "q": "query", "search": "query", "product": "query", "item": "query",
    "supplier_name": "supplier", "vendor": "supplier",
    "n": "limit", "count": "limit", "top": "limit", "k": "limit",
    "from": "date_from", "to": "date_to", "since": "date_from", "until": "date_to",
}


def coerce_args(tool: str, raw) -> dict:
    """Привести произвольные args от LLM к строго валидному виду по модели тула:
    1) переименовать синонимы; 2) отбросить чужие ключи; 3) провалидировать
    pydantic-моделью (с дефолтами). Никогда не бросает — на выходе всегда
    словарь, пригодный для вызова адаптера инструмента."""
    model = TOOL_ARG_MODELS.get(tool)
    if model is None:
        return {}
    data = dict(raw) if isinstance(raw, dict) else {}
    for src, dst in ARG_ALIASES.items():
        if src in data and dst not in data:
            data[dst] = data.pop(src)
    allowed = set(model.model_fields)
    data = {k: v for k, v in data.items() if k in allowed}
    try:
        return model.model_validate(data).model_dump()
    except Exception:  # noqa: BLE001 — типы не сошлись: спасаем поля по одному
        clean = {}
        for k, v in data.items():
            try:
                model.model_validate({k: v})
                clean[k] = v
            except Exception:  # noqa: BLE001
                pass
        try:
            return model.model_validate(clean).model_dump()
        except Exception:  # noqa: BLE001
            return model().model_dump()
