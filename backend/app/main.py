"""Dara Kyzmet — FastAPI-приложение (точка входа)."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import models  # noqa: F401  (регистрация таблиц)
from .config import settings
from .db import Base, SessionLocal, engine
from .routers import (
    acceptance,
    agent,
    auth,
    invoices,
    orders,
    products,
    supplier,
)
from .seed import seed

_STATIC = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    if settings.seed_demo:
        db = SessionLocal()
        try:
            seed(db)
        finally:
            db.close()
    if settings.index_catalog_on_start:
        # Best-effort: индексация каталога в Qdrant для поиска товара (агент).
        # Недоступность Qdrant/модели не должна мешать старту приложения.
        from .catalog import index_catalog

        db = SessionLocal()
        try:
            index_catalog(db)
        finally:
            db.close()
    yield


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth, orders, invoices, acceptance, supplier, products, agent):
    app.include_router(r.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": settings.vlm_model}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(_STATIC / "index.html")


# статика UI
app.mount("/static", StaticFiles(directory=_STATIC), name="static")
