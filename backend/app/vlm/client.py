"""Распознавание накладной через VLM (OpenAI-совместимый vLLM, Qwen2.5-VL).

Требуется поднятый vLLM с вижн-моделью (см. run_vllm.sh).
Паттерн вызова взят из исходного репозитория Dara-Vision.
"""
from __future__ import annotations

import base64
import json
import re

import httpx

from ..config import settings
from .domain import INVOICE_JSON_SCHEMA, Invoice

_SCHEMA_HINT = """Верни СТРОГО один JSON-объект без markdown и комментариев по схеме:
{
  "supplier": string|null, "supplier_bin": string|null, "buyer_bin": string|null,
  "invoice_number": string|null, "date": string|null,
  "items": [{"name": string|null, "article": string|null,
             "quantity": number|null, "unit_price": number|null, "total": number|null}],
  "grand_total": number|null
}"""

_PROMPT = (
    "Ты обрабатываешь накладную (товаросопроводительный документ) на русском или "
    "казахском языке. Извлеки данные строго из изображения, ничего не выдумывай. "
    "Числа — без пробелов-разделителей и без символа валюты. Если поле отсутствует — null.\n\n"
    + _SCHEMA_HINT
)


def _data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode()


def _parse_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise
        return json.loads(m.group(0))


_COUNT_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": ["string", "null"]},
        "count": {"type": ["integer", "null"]},
    },
    "required": ["count"],
}


def count_products(png: bytes) -> dict:
    """Сколько единиц товара на фото (VLM, guided JSON). Возвращает {name, count}."""
    content = [
        {"type": "text", "text":
            "На фото товары (обычно одного вида). Верни СТРОГО JSON: "
            "name — что за товар, count — сколько единиц видно на фото (целое число)."},
        {"type": "image_url", "image_url": {"url": _data_url(png)}},
    ]
    payload = {
        "model": settings.vlm_model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        "guided_json": _COUNT_SCHEMA,
    }
    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    with httpx.Client(timeout=settings.request_timeout) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
    return _parse_json(resp.json()["choices"][0]["message"]["content"])


def recognize(pages: list[bytes]) -> tuple[Invoice, str]:
    """Возвращает (Invoice, backend). Требует поднятого vLLM."""
    content: list[dict] = [{"type": "text", "text": _PROMPT}]
    for png in pages:
        content.append({"type": "image_url", "image_url": {"url": _data_url(png)}})

    payload = {
        "model": settings.vlm_model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        # vLLM: guided decoding гарантирует валидный JSON по схеме
        "guided_json": INVOICE_JSON_SCHEMA,
    }
    url = settings.openai_base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}

    with httpx.Client(timeout=settings.request_timeout) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    text = data["choices"][0]["message"]["content"]
    return Invoice.model_validate(_parse_json(text)), "vlm"
