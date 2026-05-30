"""Распознавание накладной через VLM (OpenAI-совместимый vLLM, Qwen2.5-VL).

mock_vlm=true -> детерминированная заглушка (без GPU/модели), чтобы поднять
весь проект одной командой. На GPU-машине: mock_vlm=false + vLLM с Qwen2.5-VL.
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


def _mock_invoice() -> Invoice:
    """Реалистичная заглушка распознавания (одно поле с низкой уверенностью)."""
    return Invoice(
        supplier="ТОО «Молпром»",
        supplier_bin="123456789012",
        invoice_number="10482",
        date="2026-05-30",
        items=[
            LineItemFactory("Молоко 3.2%, 1 л", "4870001112223", 20, 430),
            LineItemFactory("Кефир 2.5%, 0.5 л", None, 30, 280),
            LineItemFactory("Сметана 20%, 400 г", "4870001112247", 15, 560),
            LineItemFactory("Творог 9%, 200 г", None, 24, 340),
            LineItemFactory("Масло слив. 72.5%, 180 г", "4870001112261", 12, 790),
        ],
        grand_total=20 * 430 + 30 * 280 + 15 * 560 + 24 * 340 + 12 * 790,
    )


def LineItemFactory(name, article, qty, price):  # noqa: N802
    from .domain import LineItem

    return LineItem(
        name=name, article=article, quantity=qty, unit_price=price, total=qty * price
    )


def recognize(pages: list[bytes]) -> tuple[Invoice, str]:
    """Возвращает (Invoice, backend)."""
    if settings.mock_vlm:
        return _mock_invoice(), "mock"

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
