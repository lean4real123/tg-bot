"""
Менеджер userbot сессий
Для каждого пользователя запускает отдельный Telethon клиент
"""

import asyncio
import os
from datetime import datetime

from telethon import TelegramClient, events
from telethon.tl.types import PeerUser
from telethon.errors import SessionPasswordNeededError

import database as db
from config import SESSIONS_DIR

# Словарь активных клиентов: {user_id: TelegramClient}
active_clients: dict[int, TelegramClient] = {}

# Callback для отправки уведомлений через бота: устанавливается из bot.py
notify_callback = None


def set_notify_callback(callback):
    global notify_callback
    notify_callback = callback


def get_session_path(user_id: int) -> str:
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    return os.path.join(SESSIONS_DIR, f"user_{user_id}")


async def get_sender_name(client: TelegramClient, sender_id: int) -> str:
    """Получить имя отправителя"""
    try:
        entity = await client.get_entity(sender_id)
        name = ""
        if hasattr(entity, "first_name") and entity.first_name:
            name += entity.first_name
        if hasattr(entity, "last_name") and entity.last_name:
            name += " " + entity.last_name
        if hasattr(entity, "username") and entity.username:
            name += f" (@{entity.username})"
        return name.strip() or str(sender_id)
    except Exception:
        return str(sender_id)


def make_handlers(owner_id: int, client: TelegramClient):
    """Создаём обработчики событий для конкретного пользователя"""

    @client.on(events.NewMessage)
    async def on_new_message(event):
        msg = event.message
        if not isinstance(msg.peer_id, PeerUser):
            return
        if not msg.text:
            return

        sender_name = await get_sender_name(client, msg.sender_id)
        date_str = msg.date.strftime("%d.%m.%Y %H:%M")

        db.cache_message(
            owner_id=owner_id,
            msg_id=msg.id,
            sender_id=msg.sender_id,
            sender_name=sender_name,
            text=msg.text,
            date=date_str,
        )

    @client.on(events.MessageEdited)
    async def on_message_edited(event):
        msg = event.message
        if not isinstance(msg.peer_id, PeerUser):
            return

        original = db.get_cached_message(owner_id, msg.id)
        new_text = msg.text or ""

        if original and original["text"] != new_text:
            report = (
                f"✏️ <b>Сообщение изменено</b>\n"
                f"👤 От: {original['sender_name']}\n"
                f"🕐 Дата: {original['date']}\n\n"
                f"<b>Было:</b>\n{original['text']}\n\n"
                f"<b>Стало:</b>\n{new_text}"
            )

            if notify_callback:
                await notify_callback(owner_id, report)

            db.update_cached_message_text(owner_id, msg.id, new_text)

    @client.on(events.MessageDeleted)
    async def on_message_deleted(event):
        for msg_id in event.deleted_ids:
            original = db.get_cached_message(owner_id, msg_id)
            if original:
                report = (
                    f"🗑️ <b>Сообщение удалено</b>\n"
                    f"👤 От: {original['sender_name']}\n"
                    f"🕐 Дата: {original['date']}\n\n"
                    f"<b>Текст:</b>\n{original['text']}"
                )

                if notify_callback:
                    await notify_callback(owner_id, report)

                db.delete_cached_message(owner_id, msg_id)


async def start_userbot(owner_id: int, api_id: int, api_hash: str) -> bool:
    """Запустить userbot для пользователя. Возвращает True если успешно."""
    if owner_id in active_clients:
        return True  # уже запущен

    session_path = get_session_path(owner_id)
    client = TelegramClient(session_path, api_id, api_hash)

    try:
        await client.connect()

        if not await client.is_user_authorized():
            return False  # нужна авторизация — обрабатывается в bot.py

        make_handlers(owner_id, client)
        active_clients[owner_id] = client
        db.set_active(owner_id, True)

        # Запускаем в фоне
        asyncio.create_task(client.run_until_disconnected())
        return True

    except Exception as e:
        print(f"[userbot] Ошибка запуска для {owner_id}: {e}")
        await client.disconnect()
        return False


async def stop_userbot(owner_id: int):
    """Остановить userbot пользователя"""
    client = active_clients.pop(owner_id, None)
    if client:
        await client.disconnect()
    db.set_active(owner_id, False)


async def send_code(owner_id: int, api_id: int, api_hash: str, phone: str) -> TelegramClient:
    """Отправить код подтверждения на номер телефона"""
    session_path = get_session_path(owner_id)
    client = TelegramClient(session_path, api_id, api_hash)
    await client.connect()
    await client.send_code_request(phone)
    # Временно сохраняем клиент для завершения авторизации
    active_clients[f"pending_{owner_id}"] = client
    return client


async def sign_in(owner_id: int, phone: str, code: str, password: str = None) -> bool:
    """Завершить авторизацию по коду"""
    client = active_clients.get(f"pending_{owner_id}")
    if not client:
        return False

    try:
        await client.sign_in(phone, code)
    except SessionPasswordNeededError:
        if password:
            await client.sign_in(password=password)
        else:
            return False  # нужен пароль 2FA
    except Exception as e:
        print(f"[userbot] Ошибка sign_in для {owner_id}: {e}")
        return False

    # Убираем из pending и запускаем нормально
    del active_clients[f"pending_{owner_id}"]

    user = db.get_user(owner_id)
    make_handlers(owner_id, client)
    active_clients[owner_id] = client
    db.set_active(owner_id, True)
    asyncio.create_task(client.run_until_disconnected())
    return True


async def restore_all_sessions():
    """При старте бота восстанавливаем все активные сессии"""
    users = db.get_all_active_users()
    for user in users:
        uid = user["user_id"]
        session_path = get_session_path(uid)

        if not os.path.exists(session_path + ".session"):
            db.set_active(uid, False)
            continue

        client = TelegramClient(session_path, user["api_id"], user["api_hash"])
        try:
            await client.connect()
            if await client.is_user_authorized():
                make_handlers(uid, client)
                active_clients[uid] = client
                asyncio.create_task(client.run_until_disconnected())
                print(f"[userbot] Восстановлена сессия для {uid}")
            else:
                db.set_active(uid, False)
                await client.disconnect()
        except Exception as e:
            print(f"[userbot] Не удалось восстановить сессию {uid}: {e}")
            db.set_active(uid, False)
