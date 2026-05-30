"""Pydantic-схемы запросов/ответов API."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ---------- auth ----------


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    role: str
    full_name: str | None
    organization_id: uuid.UUID


# ---------- orders ----------


class OrderItemIn(BaseModel):
    product_id: uuid.UUID | None = None
    name: str
    qty_ordered: Decimal
    price: Decimal | None = None


class OrderCreate(BaseModel):
    supplier_org_id: uuid.UUID
    items: list[OrderItemIn]


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    qty_ordered: Decimal
    price: Decimal | None


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    store_org_id: uuid.UUID
    supplier_org_id: uuid.UUID
    status: str
    created_at: datetime
    items: list[OrderItemOut] = []


# ---------- invoice ----------


class InvoiceItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    barcode: str | None
    qty: Decimal
    unit: str
    price: Decimal
    line_total: Decimal
    confidence: float | None
    was_edited: bool


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    order_id: uuid.UUID
    supplier_name: str | None
    invoice_number: str | None
    invoice_date: date | None
    total_sum: Decimal | None
    ocr_status: str
    items: list[InvoiceItemOut] = []


class InvoiceHeadPatch(BaseModel):
    supplier_name: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    total_sum: Decimal | None = None


class InvoiceItemPatch(BaseModel):
    name: str | None = None
    barcode: str | None = None
    qty: Decimal | None = None
    price: Decimal | None = None


# ---------- discrepancies ----------

DiscType = Literal["shortage", "surplus", "misgrade", "defect"]


class DiscrepancyCreate(BaseModel):
    invoice_item_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    type: DiscType
    qty_actual: Decimal | None = None
    qty_defect: Decimal | None = None
    price_new: Decimal | None = None  # для пересорта (цена пришедшего товара)
    photo_url: str | None = None
    comment: str | None = None


class DiscrepancyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    type: str
    qty_expected: Decimal | None
    qty_actual: Decimal | None
    qty_defect: Decimal | None
    price: Decimal | None
    amount_delta: Decimal
    photo_url: str | None
    comment: str | None


class AcceptanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    order_id: uuid.UUID
    invoice_id: uuid.UUID
    status: str


class CorrectedSumOut(BaseModel):
    original_sum: Decimal
    corrected_sum: Decimal
    total_delta: Decimal
    discrepancies: list[DiscrepancyOut]


class ActOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    number: str
    original_sum: Decimal
    corrected_sum: Decimal
    total_delta: Decimal
    status: str


# ---------- products / stock ----------


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    sku: str | None
    barcode: str | None
    name: str
    unit: str


class ProductMatch(BaseModel):
    product: ProductOut
    score: float


class StockOut(BaseModel):
    product_id: uuid.UUID
    name: str
    quantity: Decimal


# ---------- agent ----------


class AgentAsk(BaseModel):
    message: str = Field(min_length=1)


class AgentReply(BaseModel):
    answer: str
    used_tools: list[str] = []
