"""Состояние графа агента (LangGraph).

supervisor (VLM-классификация интента) выбирает ОДИН узел: stock / analytics /
product / order / fallback. Узлы детерминированы и берут слоты из `nlu`.
"""
from __future__ import annotations

from operator import add
from typing import Annotated, Literal

from pydantic import BaseModel, Field

AgentName = Literal["agent", "order"]


class AgentState(BaseModel):
    # --- вход ---
    message: str = ""
    org_id: str = ""                       # тенант: фильтр данных, обязателен
    user_id: str = ""                      # автор заявки (для create_order_draft)
    image_b64: str | None = None           # для поиска товара по фото
    confirm_draft: dict | None = None      # просмотренный черновик -> создать заявку
    conversation_id: str = ""              # id беседы (= session_id для трассировки)
    history: list[dict] = Field(default_factory=list)  # предыдущие реплики (память диалога)

    # --- маршрутизация ---
    route: AgentName = "agent"

    # --- результат ---
    used_tools: Annotated[list[str], add] = Field(default_factory=list)
    answer: str = ""
    data: dict = Field(default_factory=dict)
