"""
Telegram Spy - отслеживает удалённые и изменённые сообщения в личных чатах
Пересылает оригиналы в твои "Избранное" (Saved Messages)

Установка:
    pip install telethon

Настройка:
    1. Зайди на https://my.telegram.org
    2. Войди своим номером телефона
    3. Перейди в "API development tools"
    4. Создай приложение (название любое)
    5. Скопируй api_id и api_hash сюда ниже
"""

from telethon import TelegramClient, events
from telethon.tl.types import PeerUser
from datetime import datetime
import asyncio

# ========================
# НАСТРОЙКИ — заполни здесь
# ========================
API_ID = 0          # вставь свой api_id (число)
API_HASH = ""       # вставь свой api_hash (строка)
SESSION_NAME = "spy_session"  # имя файла сессии, можно не менять
# ========================

# Кэш сообщений: {message_id: {text, sender, date}}
message_cache = {}

client = TelegramClient(SESSION_NAME, API_ID, API_HASH)


async def get_sender_name(user_id):
    """Получить имя отправителя по ID"""
    try:
        entity = await client.get_entity(user_id)
        name = ""
        if hasattr(entity, "first_name") and entity.first_name:
            name += entity.first_name
        if hasattr(entity, "last_name") and entity.last_name:
            name += " " + entity.last_name
        if hasattr(entity, "username") and entity.username:
            name += f" (@{entity.username})"
        return name.strip() or str(user_id)
    except Exception:
        return str(user_id)


@client.on(events.NewMessage)
async def on_new_message(event):
    """Сохраняем все входящие сообщения в кэш"""
    msg = event.message

    # Только личные чаты (PeerUser)
    if not isinstance(msg.peer_id, PeerUser):
        return

    if msg.text:
        message_cache[msg.id] = {
            "text": msg.text,
            "sender_id": msg.sender_id,
            "date": msg.date,
            "chat_id": msg.peer_id.user_id,
        }


@client.on(events.MessageEdited)
async def on_message_edited(event):
    """Отслеживаем изменённые сообщения"""
    msg = event.message

    # Только личные чаты
    if not isinstance(msg.peer_id, PeerUser):
        return

    original = message_cache.get(msg.id)
    new_text = msg.text or ""

    if original and original["text"] != new_text:
        sender_name = await get_sender_name(original["sender_id"])
        original_date = original["date"].strftime("%d.%m.%Y %H:%M")

        report = (
            f"✏️ **Сообщение изменено**\n"
            f"👤 От: {sender_name}\n"
            f"🕐 Дата: {original_date}\n\n"
            f"**Было:**\n{original['text']}\n\n"
            f"**Стало:**\n{new_text}"
        )

        await client.send_message("me", report)

        # Обновляем кэш
        message_cache[msg.id]["text"] = new_text


@client.on(events.MessageDeleted)
async def on_message_deleted(event):
    """Отслеживаем удалённые сообщения"""
    for msg_id in event.deleted_ids:
        original = message_cache.get(msg_id)

        if original:
            sender_name = await get_sender_name(original["sender_id"])
            original_date = original["date"].strftime("%d.%m.%Y %H:%M")

            report = (
                f"🗑️ **Сообщение удалено**\n"
                f"👤 От: {sender_name}\n"
                f"🕐 Дата: {original_date}\n\n"
                f"**Текст:**\n{original['text']}"
            )

            await client.send_message("me", report)

            # Удаляем из кэша
            del message_cache[msg_id]


async def main():
    print("=" * 40)
    print("Telegram Spy запущен")
    print("Удалённые и изменённые сообщения")
    print("будут приходить в Избранное (Saved Messages)")
    print("Для остановки нажми Ctrl+C")
    print("=" * 40)

    await client.start()
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
