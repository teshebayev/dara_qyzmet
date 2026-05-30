"""Структура распознанной накладной (вход VLM -> структурированный JSON)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class LineItem(BaseModel):
    name: str | None = Field(None, description="Название товара")
    article: str | None = Field(None, description="Артикул / штрихкод")
    quantity: float | None = Field(None, description="Количество")
    unit_price: float | None = Field(None, description="Цена за единицу")
    total: float | None = Field(None, description="Сумма по позиции")


class Invoice(BaseModel):
    supplier: str | None = None
    supplier_bin: str | None = None
    buyer_bin: str | None = None
    invoice_number: str | None = None
    date: str | None = None
    items: list[LineItem] = Field(default_factory=list)
    grand_total: float | None = None


class ValidationReport(BaseModel):
    buyer_bin_valid: bool | None = None
    supplier_bin_valid: bool | None = None
    total_reconciled: bool | None = None
    computed_total: float | None = None
    warnings: list[str] = Field(default_factory=list)


# JSON Schema для guided_json в vLLM (гарантирует структуру вывода)
INVOICE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "supplier": {"type": ["string", "null"]},
        "supplier_bin": {"type": ["string", "null"]},
        "buyer_bin": {"type": ["string", "null"]},
        "invoice_number": {"type": ["string", "null"]},
        "date": {"type": ["string", "null"]},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": ["string", "null"]},
                    "article": {"type": ["string", "null"]},
                    "quantity": {"type": ["number", "null"]},
                    "unit_price": {"type": ["number", "null"]},
                    "total": {"type": ["number", "null"]},
                },
            },
        },
        "grand_total": {"type": ["number", "null"]},
    },
    "required": ["supplier", "items", "grand_total"],
}
