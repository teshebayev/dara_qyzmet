"""Telegram-бот приёмки товаров — фронт поверх бэкенда Dara Qyzmet.

Логика и запись в БД — на бэкенде; бот вызывает REST API. Для БРАКА и ИЗЛИШКА
количество определяется по фото через /products/recognize-image (VLM считает
единицы), и это количество подставляется в расхождение.

Запуск: BOT_TOKEN=... API_BASE_URL=http://api:8000/api/v1  python -m app.bot.main
"""
from __future__ import annotations

import io
import json
import logging
import os
from urllib.parse import quote

import httpx
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    Update,
    WebAppInfo,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

API_BASE = os.getenv("API_BASE_URL", "http://api:8000/api/v1")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
# Публичный HTTPS-URL для Telegram Mini App (камера). Пусто -> используем загрузку фото.
PUBLIC_URL = os.getenv("BOT_PUBLIC_URL", "").rstrip("/")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dara.bot")

# chat_id -> {token, user, step, order_id, invoice_id, acc_id, items,
#             disc_item, disc_type, disc_expected, disc_name, disc_count}
_sessions: dict[int, dict] = {}


def S(chat_id: int) -> dict:
    return _sessions.setdefault(chat_id, {})


async def api(method: str, path: str, token: str | None = None, **kw):
    headers = kw.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.request(method, API_BASE + path, headers=headers, **kw)
    if r.status_code >= 400:
        detail = r.text
        try:
            detail = r.json().get("detail", detail)
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(detail if isinstance(detail, str) else str(detail))
    return r.json() if r.content else None


async def api_bytes(path: str, token: str | None = None) -> tuple[bytes, str]:
    """GET бинарного ответа (напр. PDF). Возвращает (содержимое, content-type)."""
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=180.0) as client:
        r = await client.get(API_BASE + path, headers=headers)
    if r.status_code >= 400:
        detail = r.text
        try:
            detail = r.json().get("detail", detail)
        except Exception:  # noqa: BLE001
            pass
        raise RuntimeError(detail if isinstance(detail, str) else str(detail))
    return r.content, r.headers.get("content-type", "")


async def _download(msg) -> tuple[bytes, str]:
    if msg.photo:
        f = await msg.photo[-1].get_file()
        fname = "photo.jpg"
    elif msg.document:
        f = await msg.document.get_file()
        fname = msg.document.file_name or "file.bin"
    else:
        return b"", ""
    buf = io.BytesIO()
    await f.download_to_memory(buf)
    return buf.getvalue(), fname


# ───────────────────────── команды ─────────────────────────

async def cmd_start(update: Update, _ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Приёмка товаров Dara Qyzmet.\n\n"
        "/login — войти\n/orders — заявки к приёмке\n/logout — выйти"
    )


async def cmd_login(update: Update, _ctx):
    S(update.effective_chat.id)["step"] = "login_email"
    await update.message.reply_text("Введите email:")


async def cmd_logout(update: Update, _ctx):
    _sessions.pop(update.effective_chat.id, None)
    await update.message.reply_text("Вы вышли. /login — войти снова.")


async def cmd_orders(update: Update, _ctx):
    st = S(update.effective_chat.id)
    if not st.get("token"):
        return await update.message.reply_text("Сначала /login")
    try:
        orders = await api("GET", "/orders", token=st["token"])
    except Exception as e:  # noqa: BLE001
        return await update.message.reply_text(f"Ошибка: {e}")
    avail = [o for o in orders if o["status"] in ("shipped", "receiving")]
    if not avail:
        return await update.message.reply_text("Нет заявок, готовых к приёмке.")
    kb = [[InlineKeyboardButton(
        f"#{o['id'][:8].upper()} · {len(o['items'])} поз. · {o['status']}",
        callback_data=f"order:{o['id']}")] for o in avail]
    await update.message.reply_text("Выберите заявку для приёмки:",
                                    reply_markup=InlineKeyboardMarkup(kb))


# ───────────────────────── текст (логин / ручной ввод кол-ва) ─────────────────────────

async def on_text(update: Update, _ctx):
    st = S(update.effective_chat.id)
    step = st.get("step")
    text = (update.message.text or "").strip()
    if step == "login_email":
        st["email"] = text
        st["step"] = "login_pw"
        await update.message.reply_text("Введите пароль:")
    elif step == "login_pw":
        st["step"] = None
        try:
            tok = await api("POST", "/auth/login", json={"email": st["email"], "password": text})
            st["token"] = tok["access_token"]
            me = await api("GET", "/auth/me", token=st["token"])
            st["user"] = me
            await update.message.reply_text(
                f"✅ Вход выполнен: {me.get('full_name') or me['email']}.\n/orders — заявки")
        except Exception as e:  # noqa: BLE001
            await update.message.reply_text(f"Ошибка входа: {e}")
    elif step in ("disc_qty", "await_confirm"):
        try:
            qty = float(text.replace(",", "."))
        except ValueError:
            return await update.message.reply_text("Введите число.")
        await _post_and_reply(update.message, st, qty)
    else:
        await update.message.reply_text("Команды: /login, /orders")


# ───────────────────────── фото/файл (диспетчер) ─────────────────────────

async def on_file(update: Update, _ctx):
    st = S(update.effective_chat.id)
    if not st.get("token"):
        return await update.message.reply_text("Сначала /login")
    step = st.get("step")
    if step == "disc_photo":
        return await _on_disc_photo(update, st)
    if step == "await_invoice" and st.get("order_id"):
        return await _on_invoice(update, st)
    await update.message.reply_text("Сейчас фото не ожидается. /orders — выбрать заявку.")


async def _on_invoice(update: Update, st: dict):
    msg = update.message
    data, fname = await _download(msg)
    if not data:
        return
    if fname == "photo.jpg":
        fname = "invoice.jpg"
    await msg.reply_text("🔎 Распознаю накладную (ИИ)…")
    try:
        inv = await api("POST", f"/orders/{st['order_id']}/invoice/upload",
                        token=st["token"], files={"file": (fname, data)})
        acc = await api("POST", f"/orders/{st['order_id']}/acceptance", token=st["token"])
        st["invoice_id"], st["acc_id"], st["items"], st["step"] = inv["id"], acc["id"], inv["items"], None
        check = None
        try:
            check = await api("GET", f"/invoices/{inv['id']}/check", token=st["token"])
        except Exception:  # noqa: BLE001
            pass
        await msg.reply_text(_render_invoice(inv, check), reply_markup=_review_kb())
    except Exception as e:  # noqa: BLE001
        await msg.reply_text(f"Ошибка распознавания: {e}")


async def _on_disc_photo(update: Update, st: dict):
    """Фото брака/излишка -> распознавание товара и подсчёт количества (VLM)."""
    msg = update.message
    data, fname = await _download(msg)
    if not data:
        return
    await msg.reply_text("🔎 Определяю товар и количество по фото…")
    try:
        rec = await api("POST", "/products/recognize-image",
                        token=st["token"], files={"file": (fname, data)})
    except Exception as e:  # noqa: BLE001
        return await msg.reply_text(f"Ошибка распознавания: {e}")
    name = rec.get("recognized_name") or (
        rec["matches"][0]["name"] if rec.get("matches") else (st.get("disc_name") or "—"))
    count = rec.get("count")
    if count is None:
        st["disc_count"] = 0
        st["step"] = "await_confirm"
        return await msg.reply_text(
            f"Распознан товар: {name}. Количество определить не удалось — введите числом:")
    st["disc_count"] = count
    st["step"] = "await_confirm"
    await msg.reply_text(
        f"Распознано: {name}, количество ~{count} шт.\nПодтвердите или введите своё число.",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(f"✅ Подтвердить ({count})", callback_data="disc_confirm")]]))


# ───────────────────────── кнопки ─────────────────────────

async def on_callback(update: Update, _ctx):
    q = update.callback_query
    await q.answer()
    st = S(q.message.chat.id)
    data = q.data
    if not st.get("token"):
        return await q.edit_message_text("Сначала /login")

    if data.startswith("order:"):
        st["order_id"] = data.split(":", 1)[1]
        st["invoice_id"] = st["acc_id"] = None
        st["step"] = "await_invoice"
        await q.edit_message_text("Отправьте фото или PDF накладной для распознавания.")

    elif data == "accept":
        await _do_accept(q, st)

    elif data == "discr":
        kb = [[InlineKeyboardButton(f"{i}. {it['name'][:32]}", callback_data=f"ditem:{it['id']}")]
              for i, it in enumerate(st.get("items", []), 1)]
        kb.append([InlineKeyboardButton("📄 Акт", callback_data="act"),
                   InlineKeyboardButton("✅ Подтвердить приёмку", callback_data="accept")])
        await q.edit_message_text("Позиция с расхождением:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("ditem:"):
        item_id = data.split(":", 1)[1]
        st["disc_item"] = item_id
        item = next((it for it in st.get("items", []) if it["id"] == item_id), None)
        st["disc_expected"] = float(item["qty"]) if item else 0.0
        st["disc_name"] = item["name"] if item else "—"
        kb = [[InlineKeyboardButton("Недостача", callback_data="dtype:shortage"),
               InlineKeyboardButton("Излишек", callback_data="dtype:surplus"),
               InlineKeyboardButton("Брак", callback_data="dtype:defect")]]
        await q.edit_message_text(f"«{st['disc_name']}». Тип расхождения:",
                                  reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("dtype:"):
        t = data.split(":", 1)[1]
        st["disc_type"] = t
        if t in ("defect", "surplus"):
            what = "бракованные" if t == "defect" else "излишковые"
            if PUBLIC_URL.startswith("https"):
                # Telegram Mini App с реалтайм-камерой
                url = (f"{PUBLIC_URL}/static/miniapp.html?api={PUBLIC_URL}/api/v1"
                       f"&token={st['token']}&type={t}&name={quote(st.get('disc_name') or '')}")
                st["step"] = "await_webapp"
                await q.edit_message_text(f"Откройте камеру и снимите {what} единицы товара 👇")
                await q.message.reply_text(
                    "Нажмите кнопку ниже:",
                    reply_markup=ReplyKeyboardMarkup(
                        [[KeyboardButton("📷 Открыть камеру", web_app=WebAppInfo(url=url))]],
                        resize_keyboard=True, one_time_keyboard=True))
            else:
                st["step"] = "disc_photo"
                await q.edit_message_text(
                    f"📷 Сфотографируйте {what} единицы товара и пришлите фото — "
                    "определю товар и количество автоматически.")
        else:  # shortage
            st["step"] = "disc_qty"
            await q.edit_message_text("Введите фактически принятое количество (числом):")

    elif data == "disc_confirm":
        await _post_and_reply(q.message, st, st.get("disc_count") or 0)

    elif data == "act":
        await _do_act(q, st)

    elif data.startswith("actpdf:"):
        await _send_act_pdf(q, st, data.split(":", 1)[1])


# ───────────────────────── запись расхождения ─────────────────────────

async def on_webapp_data(update: Update, _ctx):
    """Данные из Mini App (камера): {count, name} -> запись расхождения."""
    st = S(update.effective_chat.id)
    if not st.get("token") or not st.get("acc_id"):
        return
    try:
        payload = json.loads(update.message.web_app_data.data)
        qty = float(payload.get("count") or 0)
    except (ValueError, TypeError, AttributeError):
        return await update.message.reply_text("Не удалось прочитать данные камеры.")
    await update.message.reply_text("Принято с камеры.", reply_markup=ReplyKeyboardRemove())
    await _post_and_reply(update.message, st, qty)


async def _post_and_reply(message, st: dict, qty: float):
    t = st.get("disc_type")
    body = {"invoice_item_id": st["disc_item"], "type": t}
    if t == "defect":
        body["qty_defect"] = qty                       # кол-во брака (с фото)
        body["photo_url"] = "telegram"
    elif t == "surplus":
        body["qty_actual"] = (st.get("disc_expected") or 0) + qty  # ожидаемое + излишек
    else:  # shortage
        body["qty_actual"] = qty                       # фактически принято
    st["step"] = None
    try:
        res = await api("POST", f"/acceptance/{st['acc_id']}/discrepancies",
                        token=st["token"], json=body)
        await message.reply_text(
            f"Записано: {st.get('disc_name')} — {t}, {qty:g}.\n"
            f"По накладной: {res['original_sum']} → к оплате: {res['corrected_sum']}.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Ещё расхождение", callback_data="discr"),
                 InlineKeyboardButton("📄 Акт", callback_data="act")],
                [InlineKeyboardButton("✅ Подтвердить приёмку", callback_data="accept")],
            ]))
    except Exception as e:  # noqa: BLE001
        await message.reply_text(f"Ошибка: {e}")


async def _do_act(q, st):
    try:
        a = await api("POST", f"/acceptance/{st['acc_id']}/act", token=st["token"])
        st["act_number"] = a.get("number")
        await q.edit_message_text(
            f"📄 Акт {a['number']}: по накладной {a['original_sum']}, "
            f"к оплате {a['corrected_sum']}, разница {a['total_delta']}.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬇️ Скачать акт (PDF)", callback_data=f"actpdf:{st['acc_id']}")],
                [InlineKeyboardButton("✅ Подтвердить приёмку", callback_data="accept")],
            ]))
    except Exception as e:  # noqa: BLE001
        await q.edit_message_text(f"Ошибка: {e}")


async def _send_act_pdf(q, st, acc_id: str):
    """Скачивает акт о расхождении из API в PDF и отправляет документом."""
    # q.answer() уже вызван в on_callback — здесь только показываем «печатает документ…».
    await q.message.chat.send_action("upload_document")
    try:
        pdf, _ctype = await api_bytes(f"/acceptance/{acc_id}/act.pdf", token=st["token"])
    except Exception as e:  # noqa: BLE001
        return await q.message.reply_text(f"Не удалось сформировать PDF: {e}")
    num = st.get("act_number") or acc_id[:8].upper()
    doc = io.BytesIO(pdf)
    doc.name = f"akt-{num}.pdf"
    await q.message.reply_document(
        document=doc, filename=f"akt-{num}.pdf",
        caption=f"📄 Акт о расхождении {num}")


async def _do_accept(q, st):
    try:
        await api("POST", f"/acceptance/{st['acc_id']}/accept", token=st["token"])
        await q.edit_message_text(
            "✅ Приёмка подтверждена. Товары оприходованы в сток, заявка переведена в «Принято».")
        for k in ("order_id", "invoice_id", "acc_id", "items", "disc_item", "disc_type",
                  "disc_expected", "disc_name", "disc_count", "act_number", "step"):
            st.pop(k, None)
    except Exception as e:  # noqa: BLE001
        await q.edit_message_text(f"Ошибка: {e}")


def _render_invoice(inv: dict, check: dict | None) -> str:
    lines = [f"📄 {inv.get('supplier_name') or '—'} · № {inv.get('invoice_number') or '—'}", ""]
    for i, it in enumerate(inv["items"], 1):
        lines.append(f"{i}. {it['name']} — {it['qty']} × {it['price']} = {it['line_total']}")
    if check and not check.get("ok"):
        lines.append("\n⚠ " + check.get("summary", ""))
    return "\n".join(lines)


def _review_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Принять", callback_data="accept"),
        InlineKeyboardButton("⚠️ Расхождения", callback_data="discr"),
    ]])


def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не задан")
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("login", cmd_login))
    app.add_handler(CommandHandler("logout", cmd_logout))
    app.add_handler(CommandHandler("orders", cmd_orders))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, on_webapp_data))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.ALL, on_file))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    log.info("Бот запущен, API=%s", API_BASE)
    app.run_polling()


if __name__ == "__main__":
    main()
