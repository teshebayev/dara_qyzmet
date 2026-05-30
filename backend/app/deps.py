"""Зависимости FastAPI: текущий пользователь, проверка роли, контекст тенанта."""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .db import get_db
from .models import User
from .security import decode_token


@dataclass
class Principal:
    user_id: uuid.UUID
    role: str
    org_id: uuid.UUID


def get_principal(authorization: str = Header(default="")) -> Principal:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Нет токена авторизации")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_token(token)
    except jwt.PyJWTError as e:
        raise HTTPException(401, f"Невалидный токен: {e}") from e
    return Principal(
        user_id=uuid.UUID(payload["sub"]),
        role=payload["role"],
        org_id=uuid.UUID(payload["org"]),
    )


def require_role(*roles: str):
    def _guard(p: Principal = Depends(get_principal)) -> Principal:
        if p.role not in roles and p.role != "admin":
            raise HTTPException(403, f"Требуется роль: {', '.join(roles)}")
        return p

    return _guard


def get_current_user(
    p: Principal = Depends(get_principal), db: Session = Depends(get_db)
) -> User:
    user = db.get(User, p.user_id)
    if not user:
        raise HTTPException(401, "Пользователь не найден")
    return user
