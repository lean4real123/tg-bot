"""PostgreSQL helpers for the bot."""

import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

DATABASE_URL = os.environ.get("DATABASE_URL", "")
MSK = ZoneInfo("Europe/Moscow")


def now_msk() -> datetime:
    return datetime.now(MSK).replace(tzinfo=None)


def get_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id         BIGINT PRIMARY KEY,
            username        TEXT,
            first_name      TEXT,
            sub_type        TEXT DEFAULT 'trial',
            sub_expires     TIMESTAMP,
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
        CREATE TABLE IF NOT EXISTS message_events (
            id                  SERIAL PRIMARY KEY,
            owner_id            BIGINT NOT NULL,
            connection_id       TEXT NOT NULL,
            chat_id             BIGINT NOT NULL,
            chat_name           TEXT,
            sender_id           BIGINT,
            sender_username     TEXT,
            sender_name         TEXT,
            message_id          BIGINT NOT NULL,
            message_type        TEXT NOT NULL,
            message_date        TIMESTAMP,
            is_deleted          BOOLEAN DEFAULT FALSE,
            deleted_at          TIMESTAMP,
            is_edited           BOOLEAN DEFAULT FALSE,
            edited_at           TIMESTAMP,
            UNIQUE(connection_id, chat_id, message_id)
        )
    """)

    c.execute("""
        ALTER TABLE message_events
        ADD COLUMN IF NOT EXISTS chat_name TEXT
    """)
    c.execute("""
        ALTER TABLE message_events
        ADD COLUMN IF NOT EXISTS sender_id BIGINT
    """)
    c.execute("""
        ALTER TABLE message_events
        ADD COLUMN IF NOT EXISTS sender_username TEXT
    """)
    c.execute("""
        ALTER TABLE message_events
        ADD COLUMN IF NOT EXISTS sender_name TEXT
    """)
    c.execute("""
        ALTER TABLE message_events
        ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE
    """)
    c.execute("""
        ALTER TABLE message_events
        ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP
    """)
    c.execute("""
        ALTER TABLE message_events
        ADD COLUMN IF NOT EXISTS is_edited BOOLEAN DEFAULT FALSE
    """)
    c.execute("""
        ALTER TABLE message_events
        ADD COLUMN IF NOT EXISTS edited_at TIMESTAMP
    """)

    conn.commit()
    conn.close()


# ── Пользователи ──────────────────────────────────────────

def save_user(user_id: int, username: str, first_name: str = ""):
    expires = now_msk() + timedelta(days=14)
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO users (user_id, username, first_name, sub_type, sub_expires)
        VALUES (%s, %s, %s, 'trial', %s)
        ON CONFLICT(user_id) DO UPDATE SET
            username = EXCLUDED.username,
            first_name = EXCLUDED.first_name
    """, (user_id, username or "", first_name or "", expires))
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
    if days > 0:
        expires = now_msk() + timedelta(days=days)
    else:
        expires = now_msk()
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE users SET sub_type = %s, sub_expires = %s WHERE user_id = %s
    """, (sub_type, expires, user_id))
    conn.commit()
    conn.close()


def add_days(user_id: int, days: int):
    """Добавить дни к текущей подписке"""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE users SET
            sub_expires = GREATEST(
                COALESCE(sub_expires, timezone('Europe/Moscow', NOW())),
                timezone('Europe/Moscow', NOW())
            ) + (%s || ' days')::INTERVAL
        WHERE user_id = %s AND sub_type != 'banned'
    """, (str(days), user_id))
    conn.commit()
    conn.close()


def is_sub_active(user_id: int) -> bool:
    user = get_user(user_id)
    if not user:
        return True  # новый пользователь — разрешаем
    if user["sub_type"] == "banned":
        return False
    if not user["sub_expires"]:
        return True
    expires = user["sub_expires"]
    if isinstance(expires, str):
        expires = datetime.strptime(expires[:19], "%Y-%m-%d %H:%M:%S")
    return now_msk() < expires


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


def save_message_event(
    owner_id: int,
    connection_id: str,
    chat_id: int,
    chat_name: str,
    sender_id: int | None,
    sender_username: str,
    sender_name: str,
    message_id: int,
    message_type: str,
    message_date: datetime | None,
):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO message_events (
            owner_id, connection_id, chat_id, chat_name,
            sender_id, sender_username, sender_name,
            message_id, message_type, message_date
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (connection_id, chat_id, message_id) DO UPDATE SET
            chat_name = EXCLUDED.chat_name,
            sender_id = EXCLUDED.sender_id,
            sender_username = EXCLUDED.sender_username,
            sender_name = EXCLUDED.sender_name,
            message_type = EXCLUDED.message_type,
            message_date = EXCLUDED.message_date
    """, (
        owner_id,
        connection_id,
        chat_id,
        chat_name,
        sender_id,
        sender_username or "",
        sender_name or "",
        message_id,
        message_type,
        message_date,
    ))
    conn.commit()
    conn.close()


def mark_message_event_deleted(connection_id: str, chat_id: int, message_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE message_events
        SET is_deleted = TRUE, deleted_at = NOW()
        WHERE connection_id = %s AND chat_id = %s AND message_id = %s
    """, (connection_id, chat_id, message_id))
    conn.commit()
    conn.close()


def mark_message_event_edited(connection_id: str, chat_id: int, message_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE message_events
        SET is_edited = TRUE, edited_at = NOW()
        WHERE connection_id = %s AND chat_id = %s AND message_id = %s
    """, (connection_id, chat_id, message_id))
    conn.commit()
    conn.close()


def get_deleted_sender_stats(owner_id: int | None, limit: int = 10):
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if owner_id is None:
        c.execute("""
            SELECT COALESCE(sender_name, 'Неизвестно') AS sender_name,
                   sender_username,
                   sender_id,
                   COUNT(*) AS deleted_count
            FROM message_events
            WHERE is_deleted = TRUE
            GROUP BY sender_name, sender_username, sender_id
            ORDER BY deleted_count DESC, sender_name ASC
            LIMIT %s
        """, (limit,))
    else:
        c.execute("""
            SELECT COALESCE(sender_name, 'Неизвестно') AS sender_name,
                   sender_username,
                   sender_id,
                   COUNT(*) AS deleted_count
            FROM message_events
            WHERE owner_id = %s AND is_deleted = TRUE
            GROUP BY sender_name, sender_username, sender_id
            ORDER BY deleted_count DESC, sender_name ASC
            LIMIT %s
        """, (owner_id, limit))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_monthly_photo_count(owner_id: int | None) -> int:
    conn = get_conn()
    c = conn.cursor()
    if owner_id is None:
        c.execute("""
            SELECT COUNT(*)
            FROM message_events
            WHERE message_type = 'photo'
              AND message_date >= (NOW() - INTERVAL '30 days')
        """)
    else:
        c.execute("""
            SELECT COUNT(*)
            FROM message_events
            WHERE owner_id = %s
              AND message_type = 'photo'
              AND message_date >= (NOW() - INTERVAL '30 days')
        """, (owner_id,))
    count = c.fetchone()[0]
    conn.close()
    return count


def get_activity_by_day(owner_id: int | None, days: int = 14):
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if owner_id is None:
        c.execute("""
            SELECT DATE(message_date) AS day, COUNT(*) AS count
            FROM message_events
            WHERE message_date >= (NOW() - (%s || ' days')::INTERVAL)
            GROUP BY DATE(message_date)
            ORDER BY day ASC
        """, (days,))
    else:
        c.execute("""
            SELECT DATE(message_date) AS day, COUNT(*) AS count
            FROM message_events
            WHERE owner_id = %s
              AND message_date >= (NOW() - (%s || ' days')::INTERVAL)
            GROUP BY DATE(message_date)
            ORDER BY day ASC
        """, (owner_id, days))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_heatmap_by_hour(owner_id: int | None):
    conn = get_conn()
    c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if owner_id is None:
        c.execute("""
            SELECT EXTRACT(DOW FROM message_date)::int AS dow,
                   EXTRACT(HOUR FROM message_date)::int AS hour,
                   COUNT(*) AS count
            FROM message_events
            GROUP BY 1, 2
            ORDER BY 1, 2
        """)
    else:
        c.execute("""
            SELECT EXTRACT(DOW FROM message_date)::int AS dow,
                   EXTRACT(HOUR FROM message_date)::int AS hour,
                   COUNT(*) AS count
            FROM message_events
            WHERE owner_id = %s
            GROUP BY 1, 2
            ORDER BY 1, 2
        """, (owner_id,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Кэш текстовых сообщений ───────────────────────────────

def cache_message(connection_id: str, chat_id: int, msg_id: int,
                  sender_name: str, text: str, date: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO message_cache (connection_id, chat_id, msg_id, sender_name, text, date)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT(connection_id, chat_id, msg_id) DO UPDATE SET
            text = EXCLUDED.text,
            sender_name = EXCLUDED.sender_name
    """, (connection_id, chat_id, msg_id, sender_name, text, date))
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
    return dict(row) if row else None


def update_cached_text(connection_id: str, chat_id: int, msg_id: int, new_text: str):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE message_cache SET text = %s
        WHERE connection_id = %s AND chat_id = %s AND msg_id = %s
    """, (new_text, connection_id, chat_id, msg_id))
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
        INSERT INTO media_cache (connection_id, chat_id, msg_id, sender_name, file_type, file_id, date)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT(connection_id, chat_id, msg_id) DO NOTHING
    """, (connection_id, chat_id, msg_id, sender_name, file_type, file_id, date))
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
    return dict(row) if row else None


def delete_cached_media(connection_id: str, chat_id: int, msg_id: int):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        DELETE FROM media_cache
        WHERE connection_id = %s AND chat_id = %s AND msg_id = %s
    """, (connection_id, chat_id, msg_id))
    conn.commit()
    conn.close()
