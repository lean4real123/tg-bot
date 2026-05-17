"""
Telegram Spy Bot — чистый HTTP polling без aiogram
"""

import urllib.request
import urllib.parse
import json
import time
import logging
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
import database as db
from config import BOT_TOKEN, ADMIN_ID

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

ALLOWED_UPDATES = [
    "message",
    "business_connection",
    "business_message",
    "edited_business_message",
    "deleted_business_messages",
]


def api(method, **params):
    url = f"{BASE}/{method}"
    data = json.dumps(params).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        logging.error(f"API error {method}: {e}")
        return {"ok": False}


def send(chat_id, text):
    api("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML")


def get_user_name(user: dict) -> str:
    if not user:
        return "Неизвестный"
    name = user.get("first_name", "")
    if user.get("last_name"):
        name += " " + user["last_name"]
    return name.strip() or "Неизвестный"


def get_user_link(user: dict) -> str:
    """Кликабельная ссылка на профиль пользователя"""
    if not user:
        return "Неизвестный"
    name = get_user_name(user)
    user_id = user.get("id")
    if user_id:
        return f'<a href="tg://user?id={user_id}">{name}</a>'
    return name


def get_chat_link(chat: dict) -> str:
    """Кликабельная ссылка на чат/собеседника"""
    name = chat.get("first_name", "")
    if chat.get("last_name"):
        name += " " + chat["last_name"]
    name = name.strip() or "Неизвестный"
    chat_id = chat.get("id")
    if chat_id:
        return f'<a href="tg://user?id={chat_id}">{name}</a>'
    return name


def handle_update(update: dict):
    logging.info(f"UPDATE type: {list(update.keys())}")

    # ── Обычное сообщение боту ─────────────────────────────
    if "message" in update:
        msg = update["message"]
        text = msg.get("text", "")
        user = msg.get("from", {})
        chat_id = msg["chat"]["id"]

        db.save_user(user.get("id"), user.get("username", ""))

        if text == "/start":
            me_url = f"https://t.me/{user.get('username', '')}"
            send(chat_id,
                "👁 <b>Telegram Spy Bot</b>\n\n"
                "Отслеживаю удалённые и изменённые сообщения в твоих личных чатах.\n\n"
                "<b>Как подключить:</b>\n"
                "1️⃣ Открой свой профиль в Telegram\n"
                "2️⃣ Нажми кнопку <b>Изм.</b> (редактировать)\n"
                "3️⃣ Прокрути вниз до раздела <b>Автоматизация чатов</b>\n"
                "4️⃣ В поле поиска введи <b>@DialogDelete123Bot</b>\n"
                "5️⃣ Нажми <b>Добавить</b>\n\n"
                "✅ Готово! Бот начнёт присылать уведомления сюда."
            )
        elif text in ("📊 Статус", "Статус"):
            connections = db.get_connections_count()
            send(chat_id,
                f"📊 <b>Статус</b>\n\n"
                f"Активных подключений: {connections}\n\n"
                f"Если 0 — добавь бота в <b>Автоматизация чатов</b>."
            )
        elif text in ("📖 Инструкция", "Инструкция"):
            send(chat_id,
                "⚙️ <b>Инструкция по подключению:</b>\n\n"
                "1️⃣ Открой свой профиль в Telegram\n"
                "2️⃣ Нажми кнопку <b>Изм.</b> (карандаш в правом углу)\n"
                "3️⃣ Прокрути вниз — найди раздел <b>Автоматизация чатов</b>\n"
                "4️⃣ Нажми на поле и введи: <code>@DialogDelete123Bot</code>\n"
                "5️⃣ Выбери бота из списка и нажми <b>Добавить</b>\n\n"
                "✅ После подключения все удалённые и изменённые сообщения "
                "из твоих личных чатов будут приходить сюда.\n\n"
                "⚠️ <i>Требуется актуальная версия Telegram</i>"
            )
        elif text == "/admin" and user.get("id") == ADMIN_ID:
            users = db.get_all_users()
            connections = db.get_connections_count()
            send(chat_id,
                f"👑 <b>Админ</b>\n\n"
                f"Пользователей: {len(users)}\n"
                f"Подключений: {connections}"
            )

    # ── Подключение бизнес-аккаунта ───────────────────────
    elif "business_connection" in update:
        bc = update["business_connection"]
        logging.info(f"[BUSINESS_CONNECTION] {bc}")
        owner_id = bc["user_chat_id"]
        is_enabled = bc.get("is_enabled", False)

        db.save_connection(bc["id"], owner_id, is_enabled)

        if is_enabled:
            send(owner_id,
                "✅ <b>Бот подключён!</b>\n\n"
                "Буду присылать удалённые и изменённые сообщения из твоих личных чатов."
            )
        else:
            send(owner_id, "❌ Бот отключён от автоматизации чатов.")

    # ── Новое сообщение из бизнес-чата ────────────────────
    elif "business_message" in update:
        msg = update["business_message"]
        logging.info(f"[BUSINESS_MESSAGE] chat={msg['chat']['id']} id={msg['message_id']}")

        text = msg.get("text")
        if not text:
            return

        conn_id = msg.get("business_connection_id", "")
        sender_name = get_user_link(msg.get("from"))
        date_str = datetime.fromtimestamp(msg["date"]).strftime("%d.%m.%Y %H:%M")

        db.cache_message(conn_id, msg["chat"]["id"], msg["message_id"],
                         sender_name, text, date_str)

    # ── Изменённое сообщение ───────────────────────────────
    elif "edited_business_message" in update:
        msg = update["edited_business_message"]
        logging.info(f"[EDITED_BUSINESS_MESSAGE] chat={msg['chat']['id']} id={msg['message_id']}")

        conn_id = msg.get("business_connection_id", "")
        new_text = msg.get("text", "")

        original = db.get_cached_message(conn_id, msg["chat"]["id"], msg["message_id"])
        if original and original["text"] != new_text:
            owner_id = db.get_owner_by_connection(conn_id)
            if not owner_id:
                owner_id = ADMIN_ID
            if owner_id:
                chat_link = get_chat_link(msg["chat"])
                send(owner_id,
                    f"✏️ <b>Сообщение изменено</b>\n"
                    f"👤 {chat_link}\n"
                    f"🕐 {original['date']}\n\n"
                    f"<b>Было:</b>\n{original['text']}\n\n"
                    f"<b>Стало:</b>\n{new_text}"
                )
            db.update_cached_text(conn_id, msg["chat"]["id"], msg["message_id"], new_text)

    # ── Удалённые сообщения ────────────────────────────────
    elif "deleted_business_messages" in update:
        event = update["deleted_business_messages"]
        logging.info(f"[DELETED_BUSINESS_MESSAGES] chat={event['chat']['id']} ids={event['message_ids']}")

        conn_id = event.get("business_connection_id", "")
        owner_id = db.get_owner_by_connection(conn_id)

        # Если owner не найден в БД — используем ADMIN_ID как fallback
        if not owner_id:
            logging.warning(f"owner_id not found for conn={conn_id}, fallback to ADMIN_ID={ADMIN_ID}")
            owner_id = ADMIN_ID

        if not owner_id:
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


def main():
    db.init_db()
    print("=" * 40)
    print("Бот запущен!")
    print("Подключение: Профиль → Изм. → Автоматизация чатов")
    print("=" * 40)

    offset = 0

    while True:
        try:
            result = api("getUpdates",
                offset=offset,
                timeout=0,
                allowed_updates=ALLOWED_UPDATES
            )

            if not result.get("ok"):
                time.sleep(5)
                continue

            updates = result.get("result", [])
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    handle_update(update)
                except Exception as e:
                    logging.error(f"Ошибка обработки update: {e}")

        except KeyboardInterrupt:
            print("\nБот остановлен.")
            break
        except Exception as e:
            logging.error(f"Polling error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
