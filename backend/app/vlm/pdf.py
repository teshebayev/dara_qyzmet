"""Нормализация входа: PDF или фото -> список PNG-страниц (bytes)."""
from __future__ import annotations

import io

import fitz  # PyMuPDF
from PIL import Image

MAX_PAGES = 5          # для MVP приёмки этого достаточно
RENDER_DPI = 200       # компромисс скорость/читаемость мелкого шрифта
MAX_SIDE = 2200        # ограничение длинной стороны, чтобы не раздувать токены


def _downscale(img: Image.Image) -> Image.Image:
    w, h = img.size
    longest = max(w, h)
    if longest <= MAX_SIDE:
        return img
    scale = MAX_SIDE / longest
    return img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)


def _to_png(img: Image.Image) -> bytes:
    img = _downscale(img.convert("RGB"))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def normalize(data: bytes, content_type: str, filename: str = "") -> list[bytes]:
    """Возвращает страницы как PNG. Поддержка PDF и распространённых изображений."""
    name = filename.lower()
    is_pdf = content_type == "application/pdf" or name.endswith(".pdf")

    if is_pdf:
        pages: list[bytes] = []
        with fitz.open(stream=data, filetype="pdf") as doc:
            mat = fitz.Matrix(RENDER_DPI / 72, RENDER_DPI / 72)
            for page in doc[:MAX_PAGES]:
                pix = page.get_pixmap(matrix=mat)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                pages.append(_to_png(img))
        if not pages:
            raise ValueError("PDF не содержит страниц")
        return pages

    # одиночное изображение
    try:
        img = Image.open(io.BytesIO(data))
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Не удалось прочитать изображение: {e}") from e
    return [_to_png(img)]
