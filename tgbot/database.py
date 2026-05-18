"""
База данных на SQLite
"""

import sqlite3
from datetime import datetime, timedelta

DB_PATH = "spy.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id         INTEGER PRIMARY KEY,
            username        TEXT,
            first_name      TEXT,
            sub_type        TEXT DEFAULT 'trial',
            sub_expires     TEXT,
            created_at      TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS connections (
            connection_id   TEXT PRIMARY KEY,
            owner_id        INTEGER,
            is_enabled      INTEGER DEFAULT 1,
            connected_at    TEXT DEFAULT (datetime('now'))
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS message_cache (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            connection_id   TEXT,
            chat_id         INTEGER,
            msg_id          INTEGER,
            sender_name     TEXT,
            text            TEXT,
            date            TEXT,
            UNIQUE(connection_id, chat_id, msg_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS media_cache (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            connection_id   TEXT,
            chat_id         INTEGER,
            msg_id          INTEGER,
            sender_name     TEXT,
            file_type       TEXT,
            file_id         TEXT,
            date            TEXT,
            UNIQUE(connection_id, chat_id, msg_id)
        )
    """)

    conn.commit()
    conn.close()


# ── Пользователи ──────────────────────────────────────────

def save_user(user_id: int, username: str, first_name: str = ""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # При первом сохранении даём trial на 3 дня
    expires = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
    c.execute("""
        INSERT INTO users (user_id, username, first_name, sub_type, sub_expires)
        VALUES (?, ?, ?, 'trial', ?)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name
    """, (user_id, username or "", first_name or "", expires))
    conn.commit()
    conn.close()


def get_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM users ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_subscription(user_id: int, sub_type: str, days: int):
    """Установить подписку пользователю"""
    expires = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE users SET sub_type = ?, sub_expires = ? WHERE user_id = ?
    """, (sub_type, expires, user_id))
    conn.commit()
    conn.close()


def is_sub_active(user_id: int) -> bool:
    """Проверить активна ли подписка"""
    user = get_user(user_id)
    if not user:
        return False
    if user["sub_type"] == "banned":
        return False
    if not user["sub_expires"]:
        return True  # бессрочная
    try:
        expires = datetime.strptime(user["sub_expires"], "%Y-%m-%d %H:%M")
        return datetime.now() < expires
    except Exception:
        return False


# ── Бизнес-подключения ────────────────────────────────────

def save_connection(connection_id: str, owner_id: int, is_enabled: bool):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO connections (connection_id, owner_id, is_enabled)
        VALUES (?, ?, ?)
        ON CONFLICT(connection_id) DO UPDATE SET
            is_enabled = excluded.is_enabled
    """, (connection_id, owner_id, int(is_enabled)))
    conn.commit()
    conn.close()


def get_owner_by_connection(connection_id: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT owner_id FROM connections WHERE connection_id = ?", (connection_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def get_connections_count() -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM connections WHERE is_enabled = 1")
    count = c.fetchone()[0]
    conn.close()
    return count


def get_connections_count_for_user(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM connections WHERE owner_id = ? AND is_enabled = 1", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count


def get_recent_connections(limit: int = 10):
    """Последние подключения с инфо о пользователе"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT c.connection_id, c.owner_id, c.is_enabled, c.connected_at,
               u.username, u.first_name, u.sub_type, u.sub_expires
        FROM connections c
        LEFT JOIN users u ON c.owner_id = u.user_id
        ORDER BY c.connected_at DESC
        LIMIT ?
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Кэш текстовых сообщений ───────────────────────────────

def cache_message(connection_id: str, chat_id: int, msg_id: int,
                  sender_name: str, text: str, date: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO message_cache (connection_id, chat_id, msg_id, sender_name, text, date)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(connection_id, chat_id, msg_id) DO UPDATE SET
            text = excluded.text,
            sender_name = excluded.sender_name
    """, (connection_id, chat_id, msg_id, sender_name, text, date))
    conn.commit()
    conn.close()


def get_cached_message(connection_id: str, chat_id: int, msg_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT * FROM message_cache
        WHERE connection_id = ? AND chat_id = ? AND msg_id = ?
    """, (connection_id, chat_id, msg_id))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def update_cached_text(connection_id: str, chat_id: int, msg_id: int, new_text: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        UPDATE message_cache SET text = ?
        WHERE connection_id = ? AND chat_id = ? AND msg_id = ?
    """, (new_text, connection_id, chat_id, msg_id))
    conn.commit()
    conn.close()


def delete_cached_message(connection_id: str, chat_id: int, msg_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        DELETE FROM message_cache
        WHERE connection_id = ? AND chat_id = ? AND msg_id = ?
    """, (connection_id, chat_id, msg_id))
    conn.commit()
    conn.close()


# ── Кэш медиа ─────────────────────────────────────────────

def cache_media(connection_id: str, chat_id: int, msg_id: int,
                sender_name: str, file_type: str, file_id: str, date: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO media_cache (connection_id, chat_id, msg_id, sender_name, file_type, file_id, date)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(connection_id, chat_id, msg_id) DO NOTHING
    """, (connection_id, chat_id, msg_id, sender_name, file_type, file_id, date))
    conn.commit()
    conn.close()


def get_cached_media(connection_id: str, chat_id: int, msg_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT * FROM media_cache
        WHERE connection_id = ? AND chat_id = ? AND msg_id = ?
    """, (connection_id, chat_id, msg_id))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_cached_media(connection_id: str, chat_id: int, msg_id: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        DELETE FROM media_cache
        WHERE connection_id = ? AND chat_id = ? AND msg_id = ?
    """, (connection_id, chat_id, msg_id))
    conn.commit()
    conn.close()
