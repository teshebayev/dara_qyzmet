"""Модель данных (см. ТЗ, раздел 5). Денежные значения — Numeric(14,2)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Organization(Base):
    __tablename__ = "organization"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200))
    org_type: Mapped[str] = mapped_column(String(16))  # store | distributor
    bin: Mapped[str | None] = mapped_column(String(12), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class User(Base):
    __tablename__ = "app_user"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organization.id"))
    email: Mapped[str] = mapped_column(String(160), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16))  # store | distributor | admin
    full_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    organization: Mapped[Organization] = relationship()


class Counterparty(Base):
    __tablename__ = "counterparty"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    store_org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organization.id"))
    supplier_org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organization.id"))


class Product(Base):
    __tablename__ = "product"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organization.id"))
    sku: Mapped[str | None] = mapped_column(String(64), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    unit: Mapped[str] = mapped_column(String(16), default="шт")
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # эмбеддинг изображения для поиска по фото (в MVP — JSON-вектор, kNN в Python;
    # в проде заменить на pgvector, см. ТЗ 5.2 / 8)
    embedding: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Stock(Base):
    __tablename__ = "stock"
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organization.id"), primary_key=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("product.id"), primary_key=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    store_org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organization.id"))
    supplier_org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organization.id"))
    status: Mapped[str] = mapped_column(String(24), default="new")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    items: Mapped[list["OrderItem"]] = relationship(
        cascade="all, delete-orphan", back_populates="order"
    )
    invoice: Mapped["Invoice | None"] = relationship(
        cascade="all, delete-orphan", back_populates="order", uselist=False
    )


class OrderItem(Base):
    __tablename__ = "order_item"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255))
    qty_ordered: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)

    order: Mapped[Order] = relationship(back_populates="items")


class Invoice(Base):
    __tablename__ = "invoice"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"), unique=True)
    supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    invoice_date: Mapped[date | None] = mapped_column(nullable=True)
    total_sum: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    source_file_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ocr_status: Mapped[str] = mapped_column(String(16), default="pending")
    raw_ocr_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    order: Mapped[Order] = relationship(back_populates="invoice")
    items: Mapped[list["InvoiceItem"]] = relationship(
        cascade="all, delete-orphan", back_populates="invoice"
    )


class InvoiceItem(Base):
    __tablename__ = "invoice_item"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoice.id"))
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255))
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    unit: Mapped[str] = mapped_column(String(16), default="шт")
    price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    was_edited: Mapped[bool] = mapped_column(default=False)

    invoice: Mapped[Invoice] = relationship(back_populates="items")


class Acceptance(Base):
    __tablename__ = "acceptance"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"))
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoice.id"))
    status: Mapped[str] = mapped_column(String(16), default="in_progress")
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id"), nullable=True
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    discrepancies: Mapped[list["Discrepancy"]] = relationship(
        cascade="all, delete-orphan", back_populates="acceptance"
    )
    act: Mapped["DiscrepancyAct | None"] = relationship(
        cascade="all, delete-orphan", back_populates="acceptance", uselist=False
    )


class Discrepancy(Base):
    __tablename__ = "discrepancy"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    acceptance_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("acceptance.id"))
    invoice_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("invoice_item.id"), nullable=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product.id"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(16))  # shortage|surplus|misgrade|defect
    qty_expected: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    qty_actual: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    qty_defect: Mapped[Decimal | None] = mapped_column(Numeric(14, 3), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    price_new: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    amount_delta: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    photo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    comment: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    acceptance: Mapped[Acceptance] = relationship(back_populates="discrepancies")


class DiscrepancyAct(Base):
    __tablename__ = "discrepancy_act"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    acceptance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("acceptance.id"), unique=True
    )
    number: Mapped[str] = mapped_column(String(32))
    original_sum: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    corrected_sum: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    total_delta: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(24), default="created")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    acceptance: Mapped[Acceptance] = relationship(back_populates="act")


class AgentConversation(Base):
    __tablename__ = "agent_conversation"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("app_user.id"))
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AgentMessage(Base):
    __tablename__ = "agent_message"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=_uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_conversation.id")
    )
    role: Mapped[str] = mapped_column(String(16))  # user|assistant|tool
    content: Mapped[str | None] = mapped_column(String, nullable=True)
    tool_calls: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
