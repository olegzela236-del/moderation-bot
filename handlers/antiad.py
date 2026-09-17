"""
Проверки антирекламы: ссылки, номера телефонов, рекламные ключевые слова
и @упоминания посторонних (не участников группы) пользователей.
"""
import re
from typing import Optional

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

from config import AD_KEYWORDS

_LINK_PATTERN = re.compile(r"(https?://|t\.me/)", re.IGNORECASE)
# Телефон: 8+ цифр подряд, допускаются пробелы/скобки/дефисы между ними
_PHONE_PATTERN = re.compile(r"(\+?\d[\d\-\s()]{6,}\d)")


def has_link(text: str) -> bool:
    """True, если в тексте есть http(s)-ссылка или ссылка вида t.me/..."""
    return bool(_LINK_PATTERN.search(text))


def has_phone_number(text: str) -> bool:
    """True, если в тексте похоже на номер телефона (8+ цифр подряд с разделителями)."""
    for match in _PHONE_PATTERN.findall(text):
        if len(re.sub(r"\D", "", match)) >= 8:
            return True
    return False


def has_ad_keyword(text: str) -> Optional[str]:
    """Возвращает найденное рекламное ключевое слово из конфига или None."""
    lowered = text.lower()
    for keyword in AD_KEYWORDS:
        if keyword.lower() in lowered:
            return keyword
    return None


async def has_foreign_mention(message: Message, bot: Bot) -> bool:
    """
    True, если сообщение содержит @упоминание пользователя,
    который не состоит в данной группе (частый признак рекламы/накрутки).

    Ограничение Bot API: для обычного текстового @username Telegram не
    передаёт user_id, поэтому пытаемся разрешить его через get_chat
    (best-effort). Если проверить не удалось — считаем упоминание подозрительным.
    """
    if not message.entities or not message.text:
        return False

    for entity in message.entities:
        target_id = None

        if entity.type == "text_mention" and entity.user:
            target_id = entity.user.id
        elif entity.type == "mention":
            username = message.text[entity.offset : entity.offset + entity.length]
            try:
                chat = await bot.get_chat(username)
                target_id = chat.id
            except TelegramBadRequest:
                return True  # не смогли разрешить username — считаем подозрительным

        if target_id is None:
            continue

        try:
            member = await bot.get_chat_member(message.chat.id, target_id)
            if member.status in ("left", "kicked"):
                return True
        except TelegramBadRequest:
            return True  # пользователь не найден в чате — считаем упоминание чужим

    return False
