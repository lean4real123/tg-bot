"""
Telegram Spy Bot — Business API
"""

import urllib.request
import json
import time
import logging
import sys
import os
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.dirname(__file__))
import database as db
from config import BOT_TOKEN, ADMIN_ID, PORT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Цены в Telegram Stars
PRICE_WEEKLY = 45
PRICE_MONTHLY = 100
PRICE_YEARLY = 550

ALLOWED_UPDATES = [
    "message",
    "callback_query",
    "business_connection",
    "business_message",
    "edited_business_message",
    "deleted_business_messages",
    "pre_checkout_query",
]

user_settings: dict = {}
BOT_USERNAME = ""


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health", "/healthz"):
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        return


def start_health_server():
    server = HTTPServer(("0.0.0.0", PORT), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logging.info(f"Healthcheck server started on port {PORT}")


def get_settings(user_id: int) -> dict:
    if user_id not in user_settings:
        user_settings[user_id] = {"track_deleted": True, "track_edited": True}
    return user_settings[user_id]


def api(method, **params):
    url = f"{BASE}/{method}"
    data = json.dumps(params).encode()
    req = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        logging.error(f"API error {method}: {e}")
        return {"ok": False}


def send(chat_id, text, keyboard=None):
    params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        params["reply_markup"] = keyboard
    api("sendMessage", **params)


def send_invoice(chat_id: int, title: str, description: str, payload: str, amount: int):
    api("sendInvoice",
        chat_id=chat_id,
        title=title,
        description=description,
        payload=payload,
        currency="XTR",
        prices=[{"label": title, "amount": amount}]
    )


def send_file(chat_id, file_id, file_type, caption=""):
    method_map = {
        "voice": "sendVoice",
        "video_note": "sendVideoNote",
        "audio": "sendAudio",
        "photo": "sendPhoto",
        "video": "sendVideo",
        "document": "sendDocument",
        "sticker": "sendSticker",
    }
    method = method_map.get(file_type, "sendDocument")
    if file_type in ("video_note", "sticker"):
        api(method, **{"chat_id": chat_id, file_type: file_id})
        if caption:
            send(chat_id, caption)
    else:
        params = {"chat_id": chat_id, file_type: file_id}
        if caption:
            params["caption"] = caption
            params["parse_mode"] = "HTML"
        api(method, **params)


def get_ref_link(user_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=ref_{user_id}"


def send_expired_message(user_id: int):
    ref_link = get_ref_link(user_id)
    ref_count = db.get_referral_count(user_id)
    send(user_id,
        "⏰ <b>Ваша подписка истекла</b>\n\n"
        "Для продолжения выберите вариант:\n\n"
        f"👥 <b>Пригласи друга</b> — получи +3 дня бесплатно\n"
        f"Приглашено: {ref_count} чел.\n\n"
        "💳 <b>Или купи подписку за Telegram Stars:</b>",
        keyboard={
            "inline_keyboard": [
                [{"text": f"⭐ 7 дней — {PRICE_WEEKLY} Stars", "callback_data": "buy_weekly"}],
                [{"text": f"⭐ 30 дней — {PRICE_MONTHLY} Stars", "callback_data": "buy_monthly"}],
                [{"text": f"⭐ 365 дней — {PRICE_YEARLY} Stars", "callback_data": "buy_yearly"}],
                [{"text": "👥 Пригласить друга", "url": ref_link}],
            ]
        }
    )


def main_keyboard():
    return {
        "keyboard": [
            [{"text": "📊 Статус"}, {"text": "⚙️ Настройки"}],
            [{"text": "📖 Инструкция"}, {"text": "🔒 Приватность"}],
            [{"text": "💳 Купить подписку"}, {"text": "👥 Пригласить друга"}],
        ],
        "resize_keyboard": True
    }


def settings_keyboard(user_id: int):
    s = get_settings(user_id)
    del_icon = "✅" if s["track_deleted"] else "❌"
    edit_icon = "✅" if s["track_edited"] else "❌"
    return {
        "keyboard": [
            [{"text": f"{del_icon} Удалённые сообщения"}],
            [{"text": f"{edit_icon} Изменённые сообщения"}],
            [{"text": "◀️ Назад"}],
        ],
        "resize_keyboard": True
    }


def get_user_link(user: dict) -> str:
    if not user:
        return "Неизвестный"
    name = (user.get("first_name") or "")
    if user.get("last_name"):
        name += " " + user["last_name"]
    name = name.strip() or "Неизвестный"
    username = user.get("username")
    uid = user.get("id")
    if username:
        return f'<a href="https://t.me/{username}">{name} (@{username})</a>'
    elif uid:
        return f'<a href="tg://user?id={uid}">{name}</a>'
    return name


def get_chat_link(chat: dict) -> str:
    name = (chat.get("first_name") or "")
    if chat.get("last_name"):
        name += " " + chat["last_name"]
    name = name.strip() or "Неизвестный"
    username = chat.get("username")
    cid = chat.get("id")
    if username:
        return f'<a href="https://t.me/{username}">{name} (@{username})</a>'
    elif cid:
        return f'<a href="tg://user?id={cid}">{name}</a>'
    return name


def handle_update(update: dict):
    logging.info(f"UPDATE: {list(update.keys())}")

    # ── Успешная оплата ────────────────────────────────────
    if "message" in update and update["message"].get("successful_payment"):
        msg = update["message"]
        user_id = msg["from"]["id"]
        payload = msg["successful_payment"].get("invoice_payload", "")
        if payload == "weekly":
            db.set_subscription(user_id, "weekly", 7)
            send(user_id, "✅ <b>Оплата прошла!</b>\nПодписка на <b>7 дней</b> активирована.", keyboard=main_keyboard())
        elif payload == "monthly":
            db.set_subscription(user_id, "monthly", 30)
            send(user_id, "✅ <b>Оплата прошла!</b>\nПодписка на <b>30 дней</b> активирована.", keyboard=main_keyboard())
        elif payload == "yearly":
            db.set_subscription(user_id, "yearly", 365)
            send(user_id, "✅ <b>Оплата прошла!</b>\nПодписка на <b>365 дней</b> активирована.", keyboard=main_keyboard())
        return

    # ── Обычное сообщение боту ─────────────────────────────
    if "message" in update:
        msg = update["message"]
        text = msg.get("text", "")
        user = msg.get("from", {})
        chat_id = msg["chat"]["id"]
        user_id = user.get("id")

        db.save_user(user_id, user.get("username", ""), user.get("first_name", ""))
        s = get_settings(user_id)

        # Реферальная ссылка
        if text.startswith("/start ref_"):
            referrer_str = text.replace("/start ref_", "").strip()
            if referrer_str.isdigit():
                referrer_id = int(referrer_str)
                if referrer_id != user_id:
                    is_new = db.add_referral(referrer_id, user_id)
                    if is_new:
                        db.add_days(referrer_id, 3)
                        try:
                            send(referrer_id, "🎉 <b>Друг зарегистрировался по вашей ссылке!</b>\n+3 дня добавлено к подписке.")
                        except Exception:
                            pass

        if text.startswith("/start"):
            send(chat_id,
                "👁 <b>Dialog Spy Bot</b>\n\n"
                "Узнавай что скрывают — видь удалённые и изменённые сообщения в своих чатах.\n\n"
                "🔍 <b>Что умеет бот:</b>\n"
                "• Удалённые сообщения, фото, видео, голосовые и кружочки\n"
                "• Что было написано до редактирования\n"
                "• Работает в реальном времени\n\n"
                "🔒 Бот видит только твои чаты — никто другой не имеет доступа\n\n"
                "🎁 <b>14 дней бесплатно</b> при первом подключении!\n\n"
                "Нажми <b>📖 Инструкция</b> чтобы подключить.",
                keyboard=main_keyboard()
            )

        elif text in ("📊 Статус", "Статус"):
            is_connected = db.get_connections_count_for_user(user_id) or db.get_connections_count_for_user(chat_id)
            status = "🟢 Подключён" if is_connected else "🔴 Не подключён"
            sub_active = db.is_sub_active(user_id)
            user_data = db.get_user(user_id)
            sub_type = user_data.get("sub_type", "trial") if user_data else "trial"
            sub_expires = str(user_data.get("sub_expires", ""))[:10] if user_data else "—"
            del_icon = "✅" if s["track_deleted"] else "❌"
            edit_icon = "✅" if s["track_edited"] else "❌"
            send(chat_id,
                f"📊 <b>Статус</b>\n\n"
                f"Подключение: {status}\n"
                f"Подписка: {'✅ Активна' if sub_active else '❌ Истекла'} ({sub_type})\n"
                f"До: {sub_expires}\n"
                f"Удалённые: {del_icon}\n"
                f"Изменённые: {edit_icon}\n\n"
                + ("" if is_connected else "Добавь бота в <b>Автоматизация чатов</b>"),
                keyboard=main_keyboard()
            )

        elif text in ("⚙️ Настройки", "Настройки"):
            send(chat_id, "⚙️ <b>Настройки</b>\n\nВыбери что отслеживать:", keyboard=settings_keyboard(user_id))

        elif "Удалённые сообщения" in text:
            s["track_deleted"] = not s["track_deleted"]
            send(chat_id, f"Удалённые сообщения: {'✅' if s['track_deleted'] else '❌'}", keyboard=settings_keyboard(user_id))

        elif "Изменённые сообщения" in text:
            s["track_edited"] = not s["track_edited"]
            send(chat_id, f"Изменённые сообщения: {'✅' if s['track_edited'] else '❌'}", keyboard=settings_keyboard(user_id))

        elif text == "◀️ Назад":
            send(chat_id, "Главное меню:", keyboard=main_keyboard())

        elif text in ("💳 Купить подписку",):
            send(chat_id,
                f"💳 <b>Купить подписку</b>\n\n"
                f"⭐ 7 дней — {PRICE_WEEKLY} Telegram Stars\n"
                f"⭐ 30 дней — {PRICE_MONTHLY} Telegram Stars\n"
                f"⭐ 365 дней — {PRICE_YEARLY} Telegram Stars\n\n"
                "Оплата через Telegram Stars — мгновенно и безопасно.",
                keyboard={
                    "inline_keyboard": [
                        [{"text": f"⭐ 7 дней — {PRICE_WEEKLY} Stars", "callback_data": "buy_weekly"}],
                        [{"text": f"⭐ 30 дней — {PRICE_MONTHLY} Stars", "callback_data": "buy_monthly"}],
                        [{"text": f"⭐ 365 дней — {PRICE_YEARLY} Stars", "callback_data": "buy_yearly"}],
                    ]
                }
            )

        elif text in ("👥 Пригласить друга",):
            ref_link = get_ref_link(user_id)
            ref_count = db.get_referral_count(user_id)
            share_url = f"https://t.me/share/url?url={ref_link}&text=Попробуй%20этого%20бота!"
            send(chat_id,
                f"👥 <b>Пригласи друга — получи +3 дня</b>\n\n"
                f"За каждого друга который зарегистрируется по твоей ссылке — "
                f"ты получаешь <b>+3 дня</b> автоматически.\n\n"
                f"Твоя ссылка:\n<code>{ref_link}</code>\n\n"
                f"Приглашено друзей: <b>{ref_count}</b>",
                keyboard={"inline_keyboard": [[{"text": "📤 Поделиться", "url": share_url}]]}
            )

        elif text in ("🔒 Приватность",):
            send(chat_id,
                "🔒 <b>Приватность и безопасность</b>\n\n"
                "✅ Бот видит только твои чаты\n"
                "✅ Уведомления приходят только тебе\n"
                "✅ Работает через официальный API Telegram\n"
                "✅ Отключить можно в любой момент:\n"
                "Профиль → Изм. → Автоматизация чатов → удали бота",
                keyboard=main_keyboard()
            )

        elif text in ("📖 Инструкция",):
            send(chat_id,
                "⚙️ <b>Как подключить:</b>\n\n"
                "<b>Способ 1 — Новая версия Telegram:</b>\n"
                "1️⃣ Открой профиль → <b>Изм.</b>\n"
                "2️⃣ Прокрути вниз → <b>Автоматизация чатов</b>\n"
                f"3️⃣ Введи <code>@{BOT_USERNAME}</code> → <b>Добавить</b>\n\n"
                "<b>Способ 2 — Telegram Premium:</b>\n"
                "1️⃣ Настройки → <b>Telegram для бизнеса</b>\n"
                "2️⃣ <b>Чат-боты</b>\n"
                f"3️⃣ Введи <code>@{BOT_USERNAME}</code> → <b>Добавить</b>\n\n"
                "⚠️ <i>Если раздел не появляется — обнови Telegram</i>",
                keyboard=main_keyboard()
            )

        elif text == "/admin" and user_id == ADMIN_ID:
            users = db.get_all_users()
            connections = db.get_connections_count()
            trial = sum(1 for u in users if u["sub_type"] == "trial")
            paid = sum(1 for u in users if u["sub_type"] in ("monthly", "yearly"))
            banned = sum(1 for u in users if u["sub_type"] == "banned")
            recent = db.get_recent_connections(5)
            recent_text = ""
            for r in recent:
                name = r.get("first_name") or r.get("username") or str(r["owner_id"])
                uname = f"@{r['username']}" if r.get("username") else f"id:{r['owner_id']}"
                icon = "🟢" if r["is_enabled"] else "🔴"
                sub = r.get("sub_type", "?")
                date = str(r.get("connected_at") or "")[:16]
                recent_text += f"\n{icon} {name} ({uname}) · {sub} · {date}"
            send(chat_id,
                f"👑 <b>Админ панель</b>\n\n"
                f"👥 Пользователей: {len(users)}\n"
                f"🔗 Подключений: {connections}\n\n"
                f"🆓 Trial: {trial} | 💳 Платных: {paid} | 🚫 Бан: {banned}\n\n"
                f"🕐 <b>Последние подключения:</b>{recent_text or ' нет'}\n\n"
                f"<b>Команды:</b>\n"
                f"/sub @user monthly|yearly|trial\n"
                f"/ban @user | /unban @user\n"
                f"/users"
            )

        elif text.startswith("/sub ") and user_id == ADMIN_ID:
            parts = text.split()
            if len(parts) >= 3:
                try:
                    target = parts[1].lstrip("@")
                    sub_type = parts[2]
                    days = {"trial": 14, "monthly": 30, "yearly": 365}.get(sub_type, 30)
                    if target.isdigit():
                        target_id = int(target)
                    else:
                        found = next((u for u in db.get_all_users() if (u.get("username") or "").lower() == target.lower()), None)
                        if not found:
                            send(chat_id, f"❌ @{target} не найден.")
                            return
                        target_id = found["user_id"]
                    db.set_subscription(target_id, sub_type, days)
                    send(chat_id, f"✅ {sub_type} выдан {target_id} на {days} дней.")
                except Exception as e:
                    send(chat_id, f"❌ {e}")

        elif text.startswith("/ban ") and user_id == ADMIN_ID:
            parts = text.split()
            if len(parts) >= 2:
                try:
                    target = parts[1].lstrip("@")
                    if target.isdigit():
                        target_id = int(target)
                    else:
                        found = next((u for u in db.get_all_users() if (u.get("username") or "").lower() == target.lower()), None)
                        if not found:
                            send(chat_id, f"❌ @{target} не найден.")
                            return
                        target_id = found["user_id"]
                    db.set_subscription(target_id, "banned", 0)
                    send(chat_id, f"🚫 {target_id} забанен.")
                    try:
                        send(target_id, "🚫 Ваш доступ заблокирован.")
                    except Exception:
                        pass
                except Exception as e:
                    send(chat_id, f"❌ {e}")

        elif text.startswith("/unban ") and user_id == ADMIN_ID:
            parts = text.split()
            if len(parts) >= 2:
                try:
                    target = parts[1].lstrip("@")
                    if target.isdigit():
                        target_id = int(target)
                    else:
                        found = next((u for u in db.get_all_users() if (u.get("username") or "").lower() == target.lower()), None)
                        if not found:
                            send(chat_id, f"❌ @{target} не найден.")
                            return
                        target_id = found["user_id"]
                    db.set_subscription(target_id, "trial", 14)
                    send(chat_id, f"✅ {target_id} разбанен, trial 14 дней.")
                    try:
                        send(target_id, "✅ Ваш доступ восстановлен.")
                    except Exception:
                        pass
                except Exception as e:
                    send(chat_id, f"❌ {e}")

        elif text == "/users" and user_id == ADMIN_ID:
            users = db.get_all_users()
            if not users:
                send(chat_id, "Нет пользователей.")
                return
            text_out = "👥 <b>Пользователи:</b>\n\n"
            for u in users[:20]:
                uid = u["user_id"]
                name = u.get("first_name") or u.get("username") or str(uid)
                if u.get("username"):
                    link = f'<a href="https://t.me/{u["username"]}">@{u["username"]}</a>'
                else:
                    link = f'<a href="tg://user?id={uid}">{name}</a>'
                sub = u.get("sub_type", "?")
                exp = str(u.get("sub_expires") or "")[:10]
                sub_icon = "✅" if db.is_sub_active(uid) else "❌"
                # 🔗 = подключён, ➖ = отключён
                conn_count = db.get_connections_count_for_user(uid)
                conn_icon = "🔗" if conn_count else "➖"
                text_out += f"{sub_icon}{conn_icon} {link} (id:{uid})\n    {sub} до {exp}\n\n"
            send(chat_id, text_out)

    # ── Callback кнопки ────────────────────────────────────
    elif "callback_query" in update:
        cq = update["callback_query"]
        user_id = cq["from"]["id"]
        data = cq.get("data", "")
        api("answerCallbackQuery", callback_query_id=cq["id"])

        if data == "buy_weekly":
            send_invoice(user_id, "Подписка 7 дней", "Dialog Spy Bot — 7 дней доступа", "weekly", PRICE_WEEKLY)
        elif data == "buy_monthly":
            send_invoice(user_id, "Подписка 30 дней", "Dialog Spy Bot — 30 дней доступа", "monthly", PRICE_MONTHLY)
        elif data == "buy_yearly":
            send_invoice(user_id, "Подписка 365 дней", "Dialog Spy Bot — 365 дней доступа", "yearly", PRICE_YEARLY)

    # ── Pre-checkout ───────────────────────────────────────
    elif "pre_checkout_query" in update:
        pcq = update["pre_checkout_query"]
        api("answerPreCheckoutQuery", pre_checkout_query_id=pcq["id"], ok=True)

    # ── Подключение бизнес-аккаунта ───────────────────────
    elif "business_connection" in update:
        bc = update["business_connection"]
        owner_id = bc["user_chat_id"]
        is_enabled = bc.get("is_enabled", False)
        db.save_connection(bc["id"], owner_id, is_enabled)
        if is_enabled:
            send(owner_id, "✅ <b>Бот подключён!</b>\n\nБуду присылать уведомления об удалённых и изменённых сообщениях.", keyboard=main_keyboard())
        else:
            send(owner_id, "❌ Бот отключён.", keyboard=main_keyboard())

    # ── Новое сообщение из бизнес-чата ────────────────────
    elif "business_message" in update:
        msg = update["business_message"]
        conn_id = msg.get("business_connection_id", "")
        sender = msg.get("from", {})
        owner_id = db.get_owner_by_connection(conn_id) or ADMIN_ID

        if sender.get("id") == owner_id or msg["chat"]["id"] == owner_id:
            return

        date_str = datetime.fromtimestamp(msg["date"]).strftime("%d.%m.%Y %H:%M")
        sender_link = get_user_link(sender)

        if msg.get("text"):
            db.cache_message(conn_id, msg["chat"]["id"], msg["message_id"], sender_link, msg["text"], date_str)
        elif msg.get("voice"):
            db.cache_media(conn_id, msg["chat"]["id"], msg["message_id"], sender_link, "voice", msg["voice"]["file_id"], date_str)
        elif msg.get("video_note"):
            db.cache_media(conn_id, msg["chat"]["id"], msg["message_id"], sender_link, "video_note", msg["video_note"]["file_id"], date_str)
        elif msg.get("audio"):
            db.cache_media(conn_id, msg["chat"]["id"], msg["message_id"], sender_link, "audio", msg["audio"]["file_id"], date_str)
        elif msg.get("photo"):
            db.cache_media(conn_id, msg["chat"]["id"], msg["message_id"], sender_link, "photo", msg["photo"][-1]["file_id"], date_str)
        elif msg.get("video"):
            db.cache_media(conn_id, msg["chat"]["id"], msg["message_id"], sender_link, "video", msg["video"]["file_id"], date_str)
        elif msg.get("document"):
            db.cache_media(conn_id, msg["chat"]["id"], msg["message_id"], sender_link, "document", msg["document"]["file_id"], date_str)
        elif msg.get("sticker"):
            db.cache_media(conn_id, msg["chat"]["id"], msg["message_id"], sender_link, "sticker", msg["sticker"]["file_id"], date_str)

    # ── Изменённое сообщение ───────────────────────────────
    elif "edited_business_message" in update:
        msg = update["edited_business_message"]
        conn_id = msg.get("business_connection_id", "")
        new_text = msg.get("text", "")
        owner_id = db.get_owner_by_connection(conn_id) or ADMIN_ID

        if not db.is_sub_active(owner_id):
            send_expired_message(owner_id)
            return

        s = get_settings(owner_id)
        if not s["track_edited"]:
            return

        original = db.get_cached_message(conn_id, msg["chat"]["id"], msg["message_id"])
        if original and original["text"] != new_text:
            send(owner_id,
                f"✏️ <b>Сообщение изменено</b>\n"
                f"👤 {get_chat_link(msg['chat'])}\n"
                f"🕐 {original['date']}\n\n"
                f"<b>Было:</b>\n{original['text']}\n\n"
                f"<b>Стало:</b>\n{new_text}"
            )
            db.update_cached_text(conn_id, msg["chat"]["id"], msg["message_id"], new_text)

    # ── Удалённые сообщения ────────────────────────────────
    elif "deleted_business_messages" in update:
        event = update["deleted_business_messages"]
        conn_id = event.get("business_connection_id", "")
        owner_id = db.get_owner_by_connection(conn_id) or ADMIN_ID

        if not db.is_sub_active(owner_id):
            send_expired_message(owner_id)
            return

        s = get_settings(owner_id)
        if not s["track_deleted"]:
            return

        chat_link = get_chat_link(event["chat"])

        for msg_id in event["message_ids"]:
            original = db.get_cached_message(conn_id, event["chat"]["id"], msg_id)
            if original:
                send(owner_id,
                    f"🗑️ <b>Сообщение удалено</b>\n"
                    f"👤 {chat_link}\n"
                    f"🕐 {original['date']}\n\n"
                    f"<b>Текст:</b>\n{original['text']}"
                )
                db.delete_cached_message(conn_id, event["chat"]["id"], msg_id)
                continue

            media = db.get_cached_media(conn_id, event["chat"]["id"], msg_id)
            if media:
                caption = f"🗑️ <b>Удалено</b> · {media['file_type']}\n👤 {chat_link}\n🕐 {media['date']}"
                send_file(owner_id, media["file_id"], media["file_type"], caption)
                db.delete_cached_media(conn_id, event["chat"]["id"], msg_id)


def main():
    global BOT_USERNAME
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not set")
    if not os.getenv("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is not set")

    db.init_db()
    start_health_server()

    api("deleteWebhook", drop_pending_updates=False)

    me = api("getMe")
    BOT_USERNAME = me.get("result", {}).get("username", "DialogDelBot")

    print("=" * 40)
    print(f"Бот @{BOT_USERNAME} запущен!")
    print("=" * 40)

    offset = 0
    while True:
        try:
            result = api("getUpdates", offset=offset, timeout=50, allowed_updates=ALLOWED_UPDATES)
            if not result.get("ok"):
                time.sleep(5)
                continue

            for update in result.get("result", []):
                offset = update["update_id"] + 1
                try:
                    handle_update(update)
                except Exception as e:
                    logging.error(f"Ошибка: {e}")

        except KeyboardInterrupt:
            break
        except Exception as e:
            logging.error(f"Polling error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
