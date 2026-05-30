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


class ShipItem(BaseModel):
    item_id: uuid.UUID
    product_id: uuid.UUID | None = None  # привязка к каталогу (даёт штрихкод/артикул)
    price: Decimal | None = None         # цена от поставщика (необязательно)


class ShipIn(BaseModel):
    items: list[ShipItem] = []


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


# ---------- приходный ордер (печатная форма, Приложение 25) ----------


class OrgBrief(BaseModel):
    name: str
    bin: str | None = None


class ReceiptItem(BaseModel):
    name: str
    barcode: str | None = None
    unit: str = "шт"
    qty: Decimal
    price: Decimal
    total: Decimal


class OrderReceiptOut(BaseModel):
    number: str
    date: date | None
    receiver: OrgBrief
    supplier: OrgBrief
    items: list[ReceiptItem] = []
    total_sum: Decimal


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


class CheckSuggestion(BaseModel):
    field: Literal["price", "qty", "total_sum"]
    value: Decimal
    label: str


class InvoiceItemCheck(BaseModel):
    invoice_item_id: uuid.UUID
    name: str
    qty: Decimal
    price: Decimal
    line_total: Decimal
    ocr_line_total: Decimal | None
    ok: bool
    issues: list[str] = []
    message: str | None = None
    suggestions: list[CheckSuggestion] = []


class InvoiceTotalCheck(BaseModel):
    declared: Decimal | None
    computed: Decimal
    ok: bool
    suggestion: CheckSuggestion | None = None


class InvoiceCheckOut(BaseModel):
    ok: bool
    summary: str
    total: InvoiceTotalCheck
    items: list[InvoiceItemCheck] = []


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
    created_at: datetime


# ---------- products / stock ----------


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    barcode: str | None
    name: str
    unit: str


class ProductMatch(BaseModel):
    product: ProductOut
    score: float


class RecognizeMatch(BaseModel):
    product_id: uuid.UUID | None = None
    name: str
    barcode: str | None = None
    score: float


class RecognizeOut(BaseModel):
    matches: list[RecognizeMatch] = []
    recognized_name: str | None = None   # что распознал VLM
    count: int | None = None             # сколько единиц на фото (VLM)


class StockOut(BaseModel):
    product_id: uuid.UUID
    name: str
    barcode: str | None = None
    quantity: Decimal
    price: Decimal = Decimal("0")        # средневзвешенная себестоимость
    last_price: Decimal | None = None    # последняя цена прихода


# ---------- agent ----------


class OrderDraftItem(BaseModel):
    product_id: uuid.UUID | None = None
    name: str
    qty: Decimal
    price: Decimal | None = None


class OrderDraft(BaseModel):
    """Черновик заявки, предложенный агентом. Создаётся только после подтверждения."""
    supplier_org_id: uuid.UUID | None = None
    supplier_name: str | None = None
    items: list[OrderDraftItem] = []


class AgentAsk(BaseModel):
    message: str = Field(min_length=1)
    image_b64: str | None = None  # фото для поиска товара по каталогу (product-агент)
    # Шаг подтверждения: фронт переотправляет просмотренный черновик -> агент создаёт заявку.
    confirm_draft: OrderDraft | None = None
    # Память диалога: id текущего разговора (None -> создаётся новый).
    conversation_id: uuid.UUID | None = None


class AgentReply(BaseModel):
    answer: str
    used_tools: list[str] = []
    # Структурированная выдача: data["draft"] (предложение) или data["created_order"] (после создания).
    data: dict = {}
    conversation_id: uuid.UUID | None = None


class AgentMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    role: str
    content: str | None
    created_at: datetime
