"""
Работа с базой данных SQLite: хранение счётчика предупреждений
и журнала нарушений (для команды /stats).

Используется aiosqlite, чтобы не блокировать event loop aiogram
операциями чтения/записи на диск.
"""
from datetime import datetime, timedelta

import aiosqlite

from config import DB_PATH, WARN_RESET_HOURS


async def init_db() -> None:
    """Создаёт таблицы, если их ещё нет. Вызывается один раз при старте бота."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS warnings (
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                last_violation_at TEXT NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS violations_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        await db.commit()


async def get_warning_count(user_id: int, chat_id: int) -> int:
    """Текущее число предупреждений с учётом автосброса через WARN_RESET_HOURS."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT count, last_violation_at FROM warnings WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id),
        )
        row = await cursor.fetchone()

    if row is None:
        return 0

    count, last_violation_at = row
    last_dt = datetime.fromisoformat(last_violation_at)
    if datetime.utcnow() - last_dt > timedelta(hours=WARN_RESET_HOURS):
        # Прошло больше 24 часов с последнего нарушения — счётчик считается сброшенным
        return 0
    return count


async def _upsert_count(user_id: int, chat_id: int, new_count: int, timestamp: str) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO warnings (user_id, chat_id, count, last_violation_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, chat_id) DO UPDATE SET
                count = excluded.count,
                last_violation_at = excluded.last_violation_at
            """,
            (user_id, chat_id, new_count, timestamp),
        )
        await db.commit()


async def add_warning(user_id: int, chat_id: int, reason: str) -> int:
    """
    Увеличивает счётчик предупреждений на 1 (с учётом автосброса через 24 часа)
    и добавляет запись в журнал нарушений. Возвращает новое количество.
    """
    now = datetime.utcnow().isoformat()
    new_count = await get_warning_count(user_id, chat_id) + 1

    await _upsert_count(user_id, chat_id, new_count, now)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO violations_log (user_id, chat_id, reason, created_at) VALUES (?, ?, ?, ?)",
            (user_id, chat_id, reason, now),
        )
        await db.commit()

    return new_count


async def reset_warnings(user_id: int, chat_id: int) -> None:
    """Полностью обнуляет счётчик предупреждений пользователя."""
    await _upsert_count(user_id, chat_id, 0, datetime.utcnow().isoformat())


async def remove_one_warning(user_id: int, chat_id: int) -> int:
    """Снимает одно предупреждение (не уходя ниже нуля). Возвращает новое количество."""
    new_count = max(0, await get_warning_count(user_id, chat_id) - 1)
    await _upsert_count(user_id, chat_id, new_count, datetime.utcnow().isoformat())
    return new_count


async def get_stats(chat_id: int, limit: int = 10):
    """Возвращает (общее число нарушений, список [(user_id, count), ...] топ-нарушителей)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM violations_log WHERE chat_id = ?", (chat_id,)
        )
        (total,) = await cursor.fetchone()

        cursor = await db.execute(
            """
            SELECT user_id, COUNT(*) as cnt
            FROM violations_log
            WHERE chat_id = ?
            GROUP BY user_id
            ORDER BY cnt DESC
            LIMIT ?
            """,
            (chat_id, limit),
        )
        top_users = await cursor.fetchall()

    return total, top_users
