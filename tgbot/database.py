"""
База данных на SQLite
Хранит пользователей и кэш сообщений из бизнес-чатов
"""

import sqlite3

DB_PATH = "spy.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Пользователи бота (те кто написал /start)
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            created_at  TEXT DEFAULT (datetime('now'))
        )
    """)

    # Бизнес-подключения: business_connection_id -> user_id владельца
    c.execute("""
        CREATE TABLE IF NOT EXISTS connections (
            connection_id   TEXT PRIMARY KEY,
            owner_id        INTEGER,   -- user_id кто подключил бота
            is_enabled      INTEGER DEFAULT 1,
            connected_at    TEXT DEFAULT (datetime('now'))
        )
    """)

    # Кэш сообщений из бизнес-чатов
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

    conn.commit()
    conn.close()


# ── Пользователи ──────────────────────────────────────────

def save_user(user_id: int, username: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO users (user_id, username)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET username = excluded.username
    """, (user_id, username or ""))
    conn.commit()
    conn.close()


def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM users")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


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


def get_owner_by_connection(connection_id: str) -> int | None:
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


# ── Кэш сообщений ─────────────────────────────────────────

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
