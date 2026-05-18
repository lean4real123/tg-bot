"""
Telegram Spy Bot — Business API
"""

import urllib.request
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

# Настройки пользователей в памяти: {user_id: {track_deleted, track_edited}}
user_settings: dict = {}


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


def send_file(chat_id, file_id, file_type, caption=""):
    """Пересылаем голосовое/кружочек/фото"""
    method_map = {
        "voice": "sendVoice",
        "video_note": "sendVideoNote",
        "audio": "sendAudio",
        "photo": "sendPhoto",
        "video": "sendVideo",
        "document": "sendDocument",
    }
    method = method_map.get(file_type, "sendDocument")
    params = {"chat_id": chat_id, file_type: file_id}
    if caption:
        params["caption"] = caption
        params["parse_mode"] = "HTML"
    api(method, **params)


def main_keyboard():
    return {
        "keyboard": [
            [{"text": "📊 Статус"}, {"text": "⚙️ Настройки"}],
            [{"text": "📖 Инструкция"}, {"text": "🔒 Приватность"}],
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
    uid = user.get("id")
    username = user.get("username")
    if username:
        # Если есть username — ссылка через @username (всегда работает)
        return f'<a href="https://t.me/{username}">{name} (@{username})</a>'
    elif uid:
        # Если нет username — ссылка через tg://user?id=
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

    # ── Обычное сообщение боту ─────────────────────────────
    if "message" in update:
        msg = update["message"]
        text = msg.get("text", "")
        user = msg.get("from", {})
        chat_id = msg["chat"]["id"]
        user_id = user.get("id")

        db.save_user(user_id, user.get("username", ""), user.get("first_name", ""))
        s = get_settings(user_id)

        if text == "/start":
            send(chat_id,
                "👁 <b>Dialog Spy Bot</b>\n\n"
                "Узнавай что скрывают — видь удалённые и изменённые сообщения в своих чатах.\n\n"
                "🔍 <b>Что умеет бот:</b>\n"
                "• Показывает удалённые сообщения, фото, видео, голосовые и кружочки\n"
                "• Показывает что было написано до редактирования\n"
                "• Работает в реальном времени\n\n"
                "🔒 <b>Безопасно:</b> бот видит только твои чаты — никто другой не имеет доступа к твоей переписке\n\n"
                "Нажми <b>📖 Инструкция</b> чтобы подключить за 1 минуту.",
                keyboard=main_keyboard()
            )

        elif text in ("📊 Статус", "Статус"):
            is_connected = db.get_connections_count_for_user(user_id)
            status = "🟢 Подключён" if is_connected else "🔴 Не подключён"
            del_icon = "✅" if s["track_deleted"] else "❌"
            edit_icon = "✅" if s["track_edited"] else "❌"
            send(chat_id,
                f"📊 <b>Статус</b>\n\n"
                f"Подключение: {status}\n"
                f"Удалённые: {del_icon}\n"
                f"Изменённые: {edit_icon}\n\n"
                + ("" if is_connected else "Добавь бота в <b>Автоматизация чатов</b>"),
                keyboard=main_keyboard()
            )

        elif text in ("⚙️ Настройки", "Настройки"):
            send(chat_id,
                "⚙️ <b>Настройки</b>\n\nВыбери что отслеживать:",
                keyboard=settings_keyboard(user_id)
            )

        elif "Удалённые сообщения" in text:
            s["track_deleted"] = not s["track_deleted"]
            icon = "✅" if s["track_deleted"] else "❌"
            send(chat_id,
                f"Удалённые сообщения: {icon}",
                keyboard=settings_keyboard(user_id)
            )

        elif "Изменённые сообщения" in text:
            s["track_edited"] = not s["track_edited"]
            icon = "✅" if s["track_edited"] else "❌"
            send(chat_id,
                f"Изменённые сообщения: {icon}",
                keyboard=settings_keyboard(user_id)
            )

        elif text == "◀️ Назад":
            send(chat_id, "Главное меню:", keyboard=main_keyboard())

        elif text in ("🔒 Приватность", "Приватность"):
            send(chat_id,
                "🔒 <b>Приватность и безопасность</b>\n\n"
                "Мы понимаем что вопрос доверия важен. Вот как всё устроено:\n\n"
                "✅ <b>Только твои данные</b>\n"
                "Бот видит исключительно твои личные чаты — те, в которых ты сам участвуешь. "
                "Никакой другой пользователь не имеет доступа к твоей переписке.\n\n"
                "✅ <b>Уведомления только тебе</b>\n"
                "Все уведомления об удалённых и изменённых сообщениях приходят только тебе в этот чат.\n\n"
                "✅ <b>Официальный API Telegram</b>\n"
                "Бот работает через официальную функцию Telegram «Автоматизация чатов» — "
                "это стандартный инструмент для бизнес-аккаунтов.\n\n"
                "✅ <b>Ты контролируешь доступ</b>\n"
                "В любой момент можешь отключить бота: "
                "Профиль → Изм. → Автоматизация чатов → удали бота.\n\n"
                "❓ Есть вопросы? Напиши нам.",
                keyboard=main_keyboard()
            )

        elif text in ("📖 Инструкция", "Инструкция"):
            send(chat_id,
                "⚙️ <b>Как подключить бота:</b>\n\n"
                "<b>Способ 1 — Новая версия Telegram (рекомендуется):</b>\n"
                "1️⃣ Открой свой профиль\n"
                "2️⃣ Нажми <b>Изм.</b> (карандаш)\n"
                "3️⃣ Прокрути вниз → <b>Автоматизация чатов</b>\n"
                "4️⃣ Введи <code>@DialogDelete123Bot</code> → <b>Добавить</b>\n\n"
                "<b>Способ 2 — Telegram Premium (старая версия):</b>\n"
                "1️⃣ Настройки Telegram\n"
                "2️⃣ <b>Telegram для бизнеса</b>\n"
                "3️⃣ <b>Чат-боты</b>\n"
                "4️⃣ Введи <code>@DialogDelete123Bot</code> → <b>Добавить</b>\n\n"
                "✅ После подключения уведомления будут приходить сюда.\n\n"
                "⚠️ <i>Если раздел не появляется — обнови Telegram до последней версии</i>",
                keyboard=main_keyboard()
            )

        elif text == "/admin" and user_id == ADMIN_ID:
            users = db.get_all_users()
            connections = db.get_connections_count()
            active = sum(1 for u in users if db.is_sub_active(u["user_id"]))
            trial = sum(1 for u in users if u["sub_type"] == "trial")
            paid = sum(1 for u in users if u["sub_type"] in ("monthly", "yearly"))
            banned = sum(1 for u in users if u["sub_type"] == "banned")

            # Последние 5 подключений
            recent = db.get_recent_connections(5)
            recent_text = ""
            for r in recent:
                name = r.get("first_name") or r.get("username") or str(r["owner_id"])
                uname = f"@{r['username']}" if r.get("username") else f"id:{r['owner_id']}"
                status = "🟢" if r["is_enabled"] else "🔴"
                sub = r.get("sub_type", "?")
                date = (r.get("connected_at") or "")[:16]
                recent_text += f"\n{status} {name} ({uname}) · {sub} · {date}"

            send(chat_id,
                f"👑 <b>Админ панель</b>\n\n"
                f"👥 Всего пользователей: {len(users)}\n"
                f"🔗 Активных подключений: {connections}\n\n"
                f"📊 <b>Подписки:</b>\n"
                f"🆓 Trial: {trial}\n"
                f"💳 Платных: {paid}\n"
                f"🚫 Забанено: {banned}\n\n"
                f"🕐 <b>Последние подключения:</b>"
                f"{recent_text or ' нет данных'}\n\n"
                f"<b>Команды:</b>\n"
                f"/sub [id] [monthly/yearly/trial] — выдать подписку\n"
                f"/ban [id] — забанить\n"
                f"/users — список всех пользователей"
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
                        all_users = db.get_all_users()
                        found = next((u for u in all_users if (u.get("username") or "").lower() == target.lower()), None)
                        if not found:
                            send(chat_id, f"❌ Пользователь @{target} не найден.")
                            return
                        target_id = found["user_id"]
                    db.set_subscription(target_id, sub_type, days)
                    send(chat_id, f"✅ Подписка <b>{sub_type}</b> выдана {target_id} на {days} дней.")
                except Exception as e:
                    send(chat_id, f"❌ Ошибка: {e}\nФормат: /sub [id или @username] [monthly/yearly/trial]")
            else:
                send(chat_id, "Формат: /sub [id или @username] [monthly/yearly/trial]")

        elif text.startswith("/ban ") and user_id == ADMIN_ID:
            parts = text.split()
            if len(parts) >= 2:
                try:
                    target = parts[1].lstrip("@")
                    if target.isdigit():
                        target_id = int(target)
                    else:
                        all_users = db.get_all_users()
                        found = next((u for u in all_users if (u.get("username") or "").lower() == target.lower()), None)
                        if not found:
                            send(chat_id, f"❌ Пользователь @{target} не найден.")
                            return
                        target_id = found["user_id"]
                    db.set_subscription(target_id, "banned", 0)
                    send(chat_id, f"🚫 Пользователь {target_id} забанен.")
                except Exception as e:
                    send(chat_id, f"❌ Ошибка: {e}")

        elif text == "/users" and user_id == ADMIN_ID:
            users = db.get_all_users()
            if not users:
                send(chat_id, "Нет пользователей.")
                return
            text_out = "👥 <b>Все пользователи:</b>\n\n"
            for u in users[:20]:
                name = u.get("first_name") or u.get("username") or str(u["user_id"])
                uid = u["user_id"]
                if u.get("username"):
                    uname_link = f'<a href="https://t.me/{u["username"]}">@{u["username"]}</a>'
                else:
                    uname_link = f'<a href="tg://user?id={uid}">{name}</a>'
                sub = u.get("sub_type", "?")
                expires = (u.get("sub_expires") or "")[:10]
                active_icon = "✅" if db.is_sub_active(uid) else "❌"
                connected = "🔗" if db.get_connections_count_for_user(uid) else "  "
                text_out += f"{active_icon}{connected} {uname_link} (id:{uid})\n    {sub} до {expires}\n\n"
            send(chat_id, text_out)

    # ── Подключение бизнес-аккаунта ───────────────────────
    elif "business_connection" in update:
        bc = update["business_connection"]
        logging.info(f"[BUSINESS_CONNECTION] {bc}")
        owner_id = bc["user_chat_id"]
        is_enabled = bc.get("is_enabled", False)
        db.save_connection(bc["id"], owner_id, is_enabled)

        if is_enabled:
            send(owner_id,
                "✅ <b>Бот подключён!</b>\n\nБуду присылать уведомления об удалённых и изменённых сообщениях.",
                keyboard=main_keyboard()
            )
        else:
            send(owner_id, "❌ Бот отключён.", keyboard=main_keyboard())

    # ── Новое сообщение из бизнес-чата — кэшируем ─────────
    elif "business_message" in update:
        msg = update["business_message"]
        conn_id = msg.get("business_connection_id", "")
        sender = msg.get("from", {})
        owner_id = db.get_owner_by_connection(conn_id) or ADMIN_ID

        # Кэшируем только входящие сообщения (от собеседника, не от владельца)
        # chat.id == собеседник, sender.id == кто написал
        # Если отправитель — сам владелец, пропускаем
        if sender.get("id") == owner_id:
            return

        # Также пропускаем если чат — это сам владелец (исходящие)
        if msg["chat"]["id"] == owner_id:
            return

        date_str = datetime.fromtimestamp(msg["date"]).strftime("%d.%m.%Y %H:%M")
        sender_link = get_user_link(sender)

        # Текст
        if msg.get("text"):
            db.cache_message(conn_id, msg["chat"]["id"], msg["message_id"],
                             sender_link, msg["text"], date_str)

        # Голосовое
        elif msg.get("voice"):
            db.cache_media(conn_id, msg["chat"]["id"], msg["message_id"],
                          sender_link, "voice", msg["voice"]["file_id"], date_str)

        # Кружочек
        elif msg.get("video_note"):
            db.cache_media(conn_id, msg["chat"]["id"], msg["message_id"],
                          sender_link, "video_note", msg["video_note"]["file_id"], date_str)

        # Аудио
        elif msg.get("audio"):
            db.cache_media(conn_id, msg["chat"]["id"], msg["message_id"],
                          sender_link, "audio", msg["audio"]["file_id"], date_str)

        # Фото
        elif msg.get("photo"):
            # Берём самое большое фото
            file_id = msg["photo"][-1]["file_id"]
            db.cache_media(conn_id, msg["chat"]["id"], msg["message_id"],
                          sender_link, "photo", file_id, date_str)

        # Видео
        elif msg.get("video"):
            db.cache_media(conn_id, msg["chat"]["id"], msg["message_id"],
                          sender_link, "video", msg["video"]["file_id"], date_str)

        # Документ/файл
        elif msg.get("document"):
            db.cache_media(conn_id, msg["chat"]["id"], msg["message_id"],
                          sender_link, "document", msg["document"]["file_id"], date_str)

        # Стикер
        elif msg.get("sticker"):
            db.cache_media(conn_id, msg["chat"]["id"], msg["message_id"],
                          sender_link, "sticker", msg["sticker"]["file_id"], date_str)

    # ── Изменённое сообщение ───────────────────────────────
    elif "edited_business_message" in update:
        msg = update["edited_business_message"]
        conn_id = msg.get("business_connection_id", "")
        new_text = msg.get("text", "")

        owner_id = db.get_owner_by_connection(conn_id) or ADMIN_ID
        s = get_settings(owner_id)
        if not s["track_edited"]:
            return

        original = db.get_cached_message(conn_id, msg["chat"]["id"], msg["message_id"])
        if original and original["text"] != new_text:
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
        conn_id = event.get("business_connection_id", "")
        owner_id = db.get_owner_by_connection(conn_id) or ADMIN_ID

        s = get_settings(owner_id)
        if not s["track_deleted"]:
            return

        chat_link = get_chat_link(event["chat"])

        for msg_id in event["message_ids"]:
            # Проверяем текстовый кэш
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

            # Проверяем медиа кэш
            media = db.get_cached_media(conn_id, event["chat"]["id"], msg_id)
            if media:
                caption = (
                    f"🗑️ <b>Удалено</b> · {media['file_type']}\n"
                    f"👤 {chat_link}\n"
                    f"🕐 {media['date']}"
                )
                send_file(owner_id, media["file_id"], media["file_type"], caption)
                db.delete_cached_media(conn_id, event["chat"]["id"], msg_id)


def main():
    db.init_db()
    print("=" * 40)
    print("Бот запущен!")
    print("=" * 40)

    offset = 0
    while True:
        try:
            result = api("getUpdates", offset=offset, timeout=0,
                         allowed_updates=ALLOWED_UPDATES)
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
