"""Опциональная трассировка через Langfuse (SDK v2, self-hosted или cloud).

Включается, если заданы LANGFUSE_PUBLIC_KEY и LANGFUSE_SECRET_KEY (+ LANGFUSE_HOST).
Без ключей — полный no-op. Любая ошибка трассировки проглатывается: наблюдаемость
не должна ломать запрос.
"""
from __future__ import annotations

import functools
import os
from contextlib import contextmanager

_ENABLED = bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))


def enabled() -> bool:
    return _ENABLED


@functools.lru_cache(maxsize=1)
def _client():
    if not _ENABLED:
        return None
    try:
        from langfuse import Langfuse  # ленивый импорт — только если включено
        return Langfuse()  # читает LANGFUSE_PUBLIC_KEY/SECRET_KEY/HOST из окружения
    except Exception:  # noqa: BLE001
        return None


@contextmanager
def trace(name: str, **kw):
    """Корневой трейс запроса. Выдаёт объект трейса (или None) и флашит на выходе."""
    c = _client()
    if c is None:
        yield None
        return
    t = None
    try:
        t = c.trace(name=name, **kw)
    except Exception:  # noqa: BLE001
        t = None
    try:
        yield t
    finally:
        try:
            c.flush()
        except Exception:  # noqa: BLE001
            pass


@contextmanager
def _child(parent, kind: str, name: str, **kw):
    if parent is None:
        yield None
        return
    o = None
    try:
        o = getattr(parent, kind)(name=name, **kw)  # parent.generation(...) / parent.span(...)
    except Exception:  # noqa: BLE001
        o = None
    try:
        yield o
    finally:
        if o is not None:
            try:
                o.end()
            except Exception:  # noqa: BLE001
                pass


def generation(parent, name: str, **kw):
    """LLM-вызов внутри трейса (вход/выход/модель/токены)."""
    return _child(parent, "generation", name, **kw)


def span(parent, name: str, **kw):
    """Произвольный спан внутри трейса (например, вызов инструмента)."""
    return _child(parent, "span", name, **kw)


def update(obj, **kw) -> None:
    if obj is None:
        return
    try:
        obj.update(**kw)
    except Exception:  # noqa: BLE001
        pass
