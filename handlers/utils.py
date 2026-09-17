"""Вспомогательные функции, общие для нескольких обработчиков."""
import asyncio
import re
from datetime import timedelta
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

# Кэш админов чата, чтобы не дёргать Bot API на каждое сообщение.
# chat_id -> (set(user_id админов), время последнего обновления)
_admin_cache: dict[int, tuple[set, float]] = {}
_ADMIN_CACHE_TTL = 60  # секунд


async def is_admin(bot: Bot, chat_id: int, user_id: int) -> bool:
    """Проверяет, является ли пользователь админом/создателем чата (кэш на 60 секунд)."""
    loop = asyncio.get_event_loop()
    now = loop.time()

    cached = _admin_cache.get(chat_id)
    if cached is None or now - cached[1] > _ADMIN_CACHE_TTL:
        try:
            admins = await bot.get_chat_administrators(chat_id)
        except TelegramBadRequest:
            return False
        admin_ids = {admin.user.id for admin in admins}
        _admin_cache[chat_id] = (admin_ids, now)
        cached = _admin_cache[chat_id]

    return user_id in cached[0]


async def delete_after(bot: Bot, chat_id: int, message_id: int, delay: int) -> None:
    """Удаляет сообщение через `delay` секунд (используется для «тихих» уведомлений)."""
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except TelegramBadRequest:
        pass  # сообщение уже могло быть удалено вручную


def parse_duration(text: str) -> Optional[timedelta]:
    """Парсит длительность вида '30m', '2h', '1d', '45s' в timedelta. None — если формат не распознан."""
    match = re.fullmatch(r"(\d+)([smhd])", text.strip().lower())
    if not match:
        return None

    value, unit = int(match.group(1)), match.group(2)
    if unit == "s":
        return timedelta(seconds=value)
    if unit == "m":
        return timedelta(minutes=value)
    if unit == "h":
        return timedelta(hours=value)
    return timedelta(days=value)


async def resolve_target_user(message: Message, bot: Bot) -> Optional[tuple]:
    """
    Определяет пользователя, на которого направлена админ-команда:
    - через reply на его сообщение (самый надёжный способ);
    - через text_mention (Telegram передаёт объект User, если упоминание
      выбрано из подсказки со списком участников);
    - через обычный текстовый @username — в этом случае Bot API не отдаёт
      user_id напрямую, поэтому пробуем разрешить его через get_chat (best-effort).

    Возвращает (user_id, отображаемое_имя) или None, если определить не удалось.
    """
    if message.reply_to_message and message.reply_to_message.from_user:
        user = message.reply_to_message.from_user
        return user.id, user.full_name

    if message.entities and message.text:
        for entity in message.entities:
            if entity.type == "text_mention" and entity.user:
                return entity.user.id, entity.user.full_name

            if entity.type == "mention":
                username = message.text[entity.offset : entity.offset + entity.length]
                try:
                    chat = await bot.get_chat(username)
                except TelegramBadRequest:
                    continue
                name = " ".join(filter(None, [chat.first_name, chat.last_name])) or username
                return chat.id, name

    return None
