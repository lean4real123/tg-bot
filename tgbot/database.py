"""PostgreSQL helpers for the bot."""

import base64
import hashlib
import logging
import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from cryptography.fernet import Fernet, InvalidToken

DATABASE_URL = os.environ.get("DATABASE_URL", "")
APP_MASTER_KEY = os.environ.get("APP_MASTER_KEY", "").strip()
MSK = ZoneInfo("Europe/Moscow")
ENCRYPTION_PREFIX = "enc:"
_FERNET = None


def now_msk() -> datetime:
    return datetime.now(MSK).replace(tzinfo=None)


def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def _get_fernet() -> Fernet:
    global _FERNET
    if _FERNET is None:
        if not APP_MASTER_KEY:
            raise RuntimeError("APP_MASTER_KEY is not set")
        digest = hashlib.sha256(APP_MASTER_KEY.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
        _FERNET = Fernet(key)
    return _FERNET


def encrypt_value(value):
    if value is None:
        return None
    text = str(value)
    if text.startswith(ENCRYPTION_PREFIX):
        return text
    token = _get_fernet().encrypt(text.encode("utf-8")).decode("ascii")
    return ENCRYPTION_PREFIX + token


def decrypt_value(value):
    if value is None:
        return None
    text = str(value)
    if not text.startswith(ENCRYPTION_PREFIX):
        return text
    token = text[len(ENCRYPTION_PREFIX):]
    try:
        return _get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        logging.error("Failed to decrypt cached value")
        return text


def init_db():
    if not APP_MASTER_KEY:
        raise RuntimeError("APP_MASTER_KEY is not set")
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id         BIGINT PRIMARY KEY,
            username        TEXT,
            first_name      TEXT,
            sub_type        TEXT DEFAULT 'trial',
            sub_expires     TIMESTAMP,
            sub_remaining_seconds INTEGER DEFAULT 0,
            created_at      TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS connections (
            connection_id   TEXT PRIMARY KEY,
            owner_id        BIGINT,
            is_enabled      INTEGER DEFAULT 1,
            connected_at    TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS message_cache (
            id              SERIAL PRIMARY KEY,
            connection_id   TEXT,
            chat_id         BIGINT,
            msg_id          BIGINT,
            sender_name     TEXT,
            text            TEXT,
            date            TEXT,
            created_at      TIMESTAMP DEFAULT NOW(),
            UNIQUE(connection_id, chat_id, msg_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS media_cache (
            id              SERIAL PRIMARY KEY,
            connection_id   TEXT,
            chat_id         BIGINT,
            msg_id          BIGINT,
            sender_name     TEXT,
            file_type       TEXT,
            file_id         TEXT,
            date            TEXT,
            created_at      TIMESTAMP DEFAULT NOW(),
            UNIQUE(connection_id, chat_id, msg_id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS referrals (
            id              SERIAL PRIMARY KEY,
            referrer_id     BIGINT,
            referred_id     BIGINT UNIQUE,
            created_at      TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id         BIGINT PRIMARY KEY,
            track_deleted   BOOLEAN DEFAULT TRUE,
            track_edited    BOOLEAN DEFAULT TRUE,
            support_mode    BOOLEAN DEFAULT FALSE,
            support_active  BOOLEAN DEFAULT FALSE,
            updated_at      TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("""
        ALTER TABLE user_settings
        ADD COLUMN IF NOT EXISTS support_mode BOOLEAN DEFAULT FALSE
    """)

    c.execute("""
        ALTER TABLE user_settings
        ADD COLUMN IF NOT EXISTS support_active BOOLEAN DEFAULT FALSE
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id                          SERIAL PRIMARY KEY,
            user_id                     BIGINT NOT NULL,
            invoice_payload             TEXT NOT NULL,
            total_amount                BIGINT NOT NULL,
            currency                    TEXT NOT NULL,
            telegram_payment_charge_id  TEXT UNIQUE NOT NULL,
            provider_payment_charge_id  TEXT,
            refunded                    BOOLEAN DEFAULT FALSE,
            created_at                  TIMESTAMP DEFAULT NOW(),
            refunded_at                 TIMESTAMP
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS support_message_links (
            admin_message_id    BIGINT PRIMARY KEY,
            user_id             BIGINT NOT NULL,
            created_at          TIMESTAMP DEFAULT NOW()
        )
    """)

    c.execute("""
        ALTER TABLE users
        ADD COLUMN IF NOT EXISTS sub_remaining_seconds INTEGER DEFAULT 0
    """)

    c.execute("""
        ALTER TABLE message_cache
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()
    """)
    c.execute("""
        ALTER TABLE media_cache
        ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()
    """)
    c.execute("""
        UPDATE message_cache
        SET created_at = COALESCE(created_at, to_timestamp(date, 'DD.MM.YYYY HH24:MI'), NOW())
    """)
    c.execute("""
        UPDATE media_cache
        SET created_at = COALESCE(created_at, to_timestamp(date, 'DD.MM.YYYY HH24:MI'), NOW())
    """)

    c.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users (username)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_sub_type ON users (sub_type)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_users_created_at ON users (created_at DESC)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_connections_owner_enabled ON connections (owner_id, is_enabled)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_connections_enabled ON connections (is_enabled)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals (referrer_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referred ON referrals (referred_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_user_settings_active ON user_settings (support_active)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments (user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_payments_charge_id ON payments (telegram_payment_charge_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_support_links_user_id ON support_message_links (user_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_message_cache_lookup ON message_cache (connection_id, chat_id, msg_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_media_cache_lookup ON media_cache (connection_id, chat_id, msg_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_message_cache_date ON message_cache (date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_media_cache_date ON media_cache (date)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_message_cache_created_at ON message_cache (created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_media_cache_created_at ON media_cache (created_at)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_support_links_created_at ON support_message_links (created_at)")

    c.execute("""
        UPDATE users
        SET sub_remaining_seconds = GREATEST(
                COALESCE(sub_remaining_seconds, 0),
                GREATEST(0, EXTRACT(EPOCH FROM (sub_expires - NOW()))::INT)
            ),
            sub_expires = NULL
        WHERE sub_expires IS NOT NULL
          AND NOT EXISTS (
              SELECT 1
              FROM connections c
              WHERE c.owner_id = users.user_id AND c.is_enabled = 1
          )
    """)

    c.execute("""
        SELECT id, sender_name, text
        FROM message_cache
        WHERE text IS NOT NULL AND text NOT LIKE %s
    """, (ENCRYPTION_PREFIX + "%",))
    rows = c.fetchall()
    for row_id, sender_name, text in rows:
        c.execute("""
            UPDATE message_cache
            SET sender_name = %s,
                text = %s
            WHERE id = %s
        """, (encrypt_value(sender_name), encrypt_value(text), row_id))

    c.execute("""
        SELECT id, sender_name, file_id
        FROM media_cache
        WHERE file_id IS NOT NULL AND file_id NOT LIKE %s
    """, (ENCRYPTION_PREFIX + "%",))
    rows = c.fetchall()
    for row_id, sender_name, file_id in rows:
        c.execute("""
            UPDATE media_cache
            SET sender_name = %s,
                file_id = %s
            WHERE id = %s
        """, (encrypt_value(sender_name), encrypt_value(file_id), row_id))

    conn.commit()
    conn.close()


# ── Пользователи ──────────────────────────────────────────

def save_user(user_id: int, username: str, first_name: str = ""):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO users (user_id, username, first_name, sub_type, sub_expires, sub_remaining_seconds)
        VALUES (%s, %s, %s, 'trial', NULL, %s)
        ON CONFLICT(user_id) DO UPDATE SET
            username = EXCLUDED.username,
            first_name = EXCLUDED.first_name
    """, (user_id, username or "", first_name or "", 14 * 24 * 60 * 60))
    conn.commit()
    conn.close()


def get_user(user_id: int):
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users():
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("SELECT * FROM users ORDER BY created_at DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_users_with_active_support():
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT u.user_id, u.username, u.first_name, us.updated_at
        FROM user_settings us
        LEFT JOIN users u ON u.user_id = us.user_id
        WHERE us.support_active = TRUE
        ORDER BY us.updated_at DESC
    """)
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def set_subscription(user_id: int, sub_type: str, days: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM connections WHERE owner_id = %s AND is_enabled = 1", (user_id,))
    active_connections = c.fetchone()[0]
    remaining_seconds = max(0, int(days * 24 * 60 * 60))
    if days <= 0:
        c.execute("""
            UPDATE users
            SET sub_type = %s,
                sub_expires = NULL,
                sub_remaining_seconds = 0
            WHERE user_id = %s
        """, (sub_type, user_id))
        conn.commit()
        conn.close()
        return
    if active_connections:
        expires = now_msk() + timedelta(seconds=remaining_seconds)
        remaining_seconds = 0
    else:
        expires = None
    c.execute("""
        UPDATE users
        SET sub_type = %s,
            sub_expires = %s,
            sub_remaining_seconds = sub_remaining_seconds + %s
        WHERE user_id = %s
    """, (sub_type, expires, remaining_seconds, user_id))
    conn.commit()
    conn.close()


def add_days(user_id: int, days: int):
    """Добавить дни к текущей подписке"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM connections WHERE owner_id = %s AND is_enabled = 1", (user_id,))
    active_connections = c.fetchone()[0]
    if active_connections:
        c.execute("""
            UPDATE users SET
                sub_expires = GREATEST(
                    COALESCE(sub_expires, timezone('Europe/Moscow', NOW())),
                    timezone('Europe/Moscow', NOW())
                ) + (%s || ' days')::INTERVAL
            WHERE user_id = %s AND sub_type != 'banned'
        """, (str(days), user_id))
    else:
        c.execute("""
            UPDATE users SET
                sub_remaining_seconds = COALESCE(sub_remaining_seconds, 0) + (%s * 86400)
            WHERE user_id = %s AND sub_type != 'banned'
        """, (days, user_id))
    conn.commit()
    conn.close()


def is_sub_active(user_id: int) -> bool:
    user = get_user(user_id)
    if not user:
        return True  # новый пользователь — разрешаем
    if user["sub_type"] == "banned":
        return False
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM connections WHERE owner_id = %s AND is_enabled = 1", (user_id,))
    active_connections = c.fetchone()[0]
    conn.close()
    if not active_connections:
        return False
    if not user["sub_expires"]:
        return False
    expires = user["sub_expires"]
    if isinstance(expires, str):
        expires = datetime.strptime(expires[:19], "%Y-%m-%d %H:%M:%S")
    return now_msk() < expires


def pause_subscription(user_id: int):
    user = get_user(user_id)
    if not user or user.get("sub_type") == "banned":
        return
    if not user.get("sub_expires"):
        return
    expires = user["sub_expires"]
    if isinstance(expires, str):
        expires = datetime.strptime(expires[:19], "%Y-%m-%d %H:%M:%S")
    remaining_seconds = max(0, int((expires - now_msk()).total_seconds()))
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET sub_remaining_seconds = %s,
            sub_expires = NULL
        WHERE user_id = %s
    """, (remaining_seconds, user_id))
    conn.commit()
    conn.close()


def resume_subscription(user_id: int):
    user = get_user(user_id)
    if not user or user.get("sub_type") == "banned":
        return
    remaining_seconds = int(user.get("sub_remaining_seconds") or 0)
    if remaining_seconds <= 0:
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE users
        SET sub_expires = %s,
            sub_remaining_seconds = 0
        WHERE user_id = %s
    """, (now_msk() + timedelta(seconds=remaining_seconds), user_id))
    conn.commit()
    conn.close()


def cleanup_temp_tables():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        DELETE FROM message_cache
        WHERE created_at < NOW() - INTERVAL '14 days'
    """)
    c.execute("""
        DELETE FROM media_cache
        WHERE created_at < NOW() - INTERVAL '14 days'
    """)
    c.execute("""
        DELETE FROM support_message_links
        WHERE created_at < NOW() - INTERVAL '7 days'
    """)
    conn.commit()
    conn.close()


def get_user_settings(user_id: int):
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        INSERT INTO user_settings (user_id)
        VALUES (%s)
        ON CONFLICT (user_id) DO NOTHING
    """, (user_id,))
    c.execute("""
        SELECT track_deleted, track_edited, support_mode
             , support_active
        FROM user_settings
        WHERE user_id = %s
    """, (user_id,))
    row = c.fetchone()
    conn.commit()
    conn.close()
    return dict(row) if row else {
        "track_deleted": True,
        "track_edited": True,
        "support_mode": False,
        "support_active": False,
    }


def save_user_settings(
    user_id: int,
    track_deleted: bool,
    track_edited: bool,
    support_mode: bool = False,
    support_active: bool = False,
):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO user_settings (
            user_id, track_deleted, track_edited, support_mode, support_active, updated_at
        )
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT (user_id) DO UPDATE SET
            track_deleted = EXCLUDED.track_deleted,
            track_edited = EXCLUDED.track_edited,
            support_mode = EXCLUDED.support_mode,
            support_active = EXCLUDED.support_active,
            updated_at = NOW()
    """, (user_id, track_deleted, track_edited, support_mode, support_active))
    conn.commit()
    conn.close()


def save_payment(
    user_id: int,
    invoice_payload: str,
    total_amount: int,
    currency: str,
    telegram_payment_charge_id: str,
    provider_payment_charge_id: str = "",
):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO payments (
            user_id, invoice_payload, total_amount, currency,
            telegram_payment_charge_id, provider_payment_charge_id
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (telegram_payment_charge_id) DO UPDATE SET
            user_id = EXCLUDED.user_id,
            invoice_payload = EXCLUDED.invoice_payload,
            total_amount = EXCLUDED.total_amount,
            currency = EXCLUDED.currency,
            provider_payment_charge_id = EXCLUDED.provider_payment_charge_id
    """, (
        user_id,
        invoice_payload,
        total_amount,
        currency,
        telegram_payment_charge_id,
        provider_payment_charge_id or "",
    ))
    conn.commit()
    conn.close()


def get_payment(telegram_payment_charge_id: str):
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT * FROM payments
        WHERE telegram_payment_charge_id = %s
    """, (telegram_payment_charge_id,))
    row = c.fetchone()
    conn.close()
    return dict(row) if row else None


def get_payments_by_user(user_id: int, limit: int = 10):
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT *
        FROM payments
        WHERE user_id = %s
        ORDER BY created_at DESC
        LIMIT %s
    """, (user_id, limit))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_payments_count_by_user(user_id: int) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT COUNT(*)
        FROM payments
        WHERE user_id = %s
    """, (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count


def mark_payment_refunded(telegram_payment_charge_id: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE payments
        SET refunded = TRUE, refunded_at = NOW()
        WHERE telegram_payment_charge_id = %s
    """, (telegram_payment_charge_id,))
    conn.commit()
    conn.close()


def save_support_message_link(admin_message_id: int, user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO support_message_links (admin_message_id, user_id)
        VALUES (%s, %s)
        ON CONFLICT (admin_message_id) DO UPDATE SET
            user_id = EXCLUDED.user_id
    """, (admin_message_id, user_id))
    conn.commit()
    conn.close()


def get_support_message_link(admin_message_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT user_id
        FROM support_message_links
        WHERE admin_message_id = %s
    """, (admin_message_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


# ── Бизнес-подключения ────────────────────────────────────

def save_connection(connection_id: str, owner_id: int, is_enabled: bool):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO connections (connection_id, owner_id, is_enabled)
        VALUES (%s, %s, %s)
        ON CONFLICT(connection_id) DO UPDATE SET
            is_enabled = EXCLUDED.is_enabled
    """, (connection_id, owner_id, int(is_enabled)))
    conn.commit()
    conn.close()


def get_owner_by_connection(connection_id: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT owner_id FROM connections WHERE connection_id = %s", (connection_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def get_connections_count() -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM connections WHERE is_enabled = 1")
    count = c.fetchone()[0]
    conn.close()
    return count


def get_connections_count_for_user(user_id: int) -> int:
    if not user_id:
        return 0
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM connections WHERE owner_id = %s AND is_enabled = 1", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count


def get_connected_owner_ids():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT DISTINCT owner_id FROM connections WHERE is_enabled = 1")
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]


def get_recent_connections(limit: int = 10):
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT c.connection_id, c.owner_id, c.is_enabled, c.connected_at,
               u.username, u.first_name, u.sub_type, u.sub_expires
        FROM connections c
        LEFT JOIN users u ON c.owner_id = u.user_id
        ORDER BY c.connected_at DESC
        LIMIT %s
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Реферальная система ───────────────────────────────────

def add_referral(referrer_id: int, referred_id: int) -> bool:
    """Добавить реферала. Возвращает True если новый."""
    conn = get_conn()
    c = conn.cursor()
    try:
        c.execute("""
            INSERT INTO referrals (referrer_id, referred_id)
            VALUES (%s, %s)
            ON CONFLICT(referred_id) DO NOTHING
        """, (referrer_id, referred_id))
        inserted = c.rowcount > 0
        conn.commit()
        return inserted
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def get_referral_count(user_id: int) -> int:
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = %s", (user_id,))
    count = c.fetchone()[0]
    conn.close()
    return count


def get_referral_leaderboard(limit: int = 20):
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT r.referrer_id,
               COUNT(*) AS referrals_count,
               u.username,
               u.first_name
        FROM referrals r
        LEFT JOIN users u ON u.user_id = r.referrer_id
        GROUP BY r.referrer_id, u.username, u.first_name
        ORDER BY referrals_count DESC, r.referrer_id DESC
        LIMIT %s
    """, (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_referrals_by_referrer(user_id: int):
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT r.referred_id, r.created_at, u.username, u.first_name
        FROM referrals r
        LEFT JOIN users u ON u.user_id = r.referred_id
        WHERE r.referrer_id = %s
        ORDER BY r.created_at DESC
    """, (user_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_referrer_for_user(user_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT referrer_id FROM referrals WHERE referred_id = %s", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


# ── Кэш текстовых сообщений ───────────────────────────────

def cache_message(connection_id: str, chat_id: int, msg_id: int,
                  sender_name: str, text: str, date: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO message_cache (connection_id, chat_id, msg_id, sender_name, text, date, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT(connection_id, chat_id, msg_id) DO UPDATE SET
            text = EXCLUDED.text,
            sender_name = EXCLUDED.sender_name,
            date = EXCLUDED.date
    """, (
        connection_id,
        chat_id,
        msg_id,
        encrypt_value(sender_name),
        encrypt_value(text),
        date,
    ))
    conn.commit()
    conn.close()


def get_cached_message(connection_id: str, chat_id: int, msg_id: int):
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT * FROM message_cache
        WHERE connection_id = %s AND chat_id = %s AND msg_id = %s
    """, (connection_id, chat_id, msg_id))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    result = dict(row)
    result["sender_name"] = decrypt_value(result.get("sender_name"))
    result["text"] = decrypt_value(result.get("text"))
    return result


def update_cached_text(connection_id: str, chat_id: int, msg_id: int, new_text: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE message_cache SET text = %s
        WHERE connection_id = %s AND chat_id = %s AND msg_id = %s
    """, (encrypt_value(new_text), connection_id, chat_id, msg_id))
    conn.commit()
    conn.close()


def delete_cached_message(connection_id: str, chat_id: int, msg_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        DELETE FROM message_cache
        WHERE connection_id = %s AND chat_id = %s AND msg_id = %s
    """, (connection_id, chat_id, msg_id))
    conn.commit()
    conn.close()


# ── Кэш медиа ─────────────────────────────────────────────

def cache_media(connection_id: str, chat_id: int, msg_id: int,
                sender_name: str, file_type: str, file_id: str, date: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO media_cache (connection_id, chat_id, msg_id, sender_name, file_type, file_id, date, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
        ON CONFLICT(connection_id, chat_id, msg_id) DO NOTHING
    """, (
        connection_id,
        chat_id,
        msg_id,
        encrypt_value(sender_name),
        file_type,
        encrypt_value(file_id),
        date,
    ))
    conn.commit()
    conn.close()


def get_cached_media(connection_id: str, chat_id: int, msg_id: int):
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    c.execute("""
        SELECT * FROM media_cache
        WHERE connection_id = %s AND chat_id = %s AND msg_id = %s
    """, (connection_id, chat_id, msg_id))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    result = dict(row)
    result["sender_name"] = decrypt_value(result.get("sender_name"))
    result["file_id"] = decrypt_value(result.get("file_id"))
    return result


def delete_cached_media(connection_id: str, chat_id: int, msg_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        DELETE FROM media_cache
        WHERE connection_id = %s AND chat_id = %s AND msg_id = %s
    """, (connection_id, chat_id, msg_id))
    conn.commit()
    conn.close()
