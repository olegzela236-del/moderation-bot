"""
Главный обработчик обычных сообщений группы.

Прогоняет каждое сообщение через проверки по очереди и останавливается
на первом совпадении:
  1) антиспам (флуд / дубли / много эмодзи) — технические ограничения,
     не связанные со счётчиком предупреждений;
  2) антиреклама (ссылки / чужие упоминания / телефоны / рекламные слова);
  3) запрещённые слова.
Пункты 2 и 3 идут через общую систему предупреждений (1 — варн, 2 — мут, 3 — бан).
"""
import asyncio
import logging
from datetime import datetime, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatPermissions, Message

import config
import database
from handlers import antiad, antispam, badwords, warnings
from handlers.utils import delete_after, is_admin

router = Router(name="moderation")
logger = logging.getLogger(__name__)


async def _safe_delete(message: Message) -> None:
    try:
        await message.delete()
    except TelegramBadRequest:
        pass  # сообщение уже могло быть удалено


async def _notify_silently(bot: Bot, chat_id: int, text: str) -> None:
    """Отправляет уведомление о нарушении и удаляет его через WARNING_MESSAGE_TTL секунд."""
    sent = await bot.send_message(chat_id, text)
    asyncio.create_task(delete_after(bot, chat_id, sent.message_id, config.WARNING_MESSAGE_TTL))


async def _punish_with_warning(bot: Bot, message: Message, reason: str) -> None:
    """Удаляет сообщение-нарушение и увеличивает счётчик предупреждений пользователя."""
    user = message.from_user
    chat_id = message.chat.id

    await _safe_delete(message)

    new_count = await database.add_warning(user.id, chat_id, reason)
    logger.info(
        "Нарушение: user_id=%s chat_id=%s reason=%s count=%s",
        user.id, chat_id, reason, new_count,
    )

    escalation_text = await warnings.apply_escalation(bot, chat_id, user.id, new_count)
    await _notify_silently(bot, chat_id, f"{user.full_name}: {escalation_text} Причина: {reason}")


@router.message(F.chat.id == config.GROUP_ID, F.text | F.caption)
async def moderate_message(message: Message, bot: Bot) -> None:
    user = message.from_user
    if user is None or user.is_bot:
        return

    # Бот не реагирует на сообщения администраторов группы
    if await is_admin(bot, message.chat.id, user.id):
        return

    text = message.text or message.caption or ""
    chat_id = message.chat.id

    # --- Антиспам (без системы предупреждений — это техническая защита) ---
    antispam.register_message(user.id, text)

    if antispam.is_flooding(user.id):
        await _safe_delete(message)
        until = datetime.utcnow() + timedelta(minutes=config.FLOOD_MUTE_MINUTES)
        try:
            await bot.restrict_chat_member(
                chat_id,
                user.id,
                permissions=ChatPermissions(can_send_messages=False),
                until_date=until,
            )
        except TelegramBadRequest:
            pass
        await _notify_silently(
            bot, chat_id, f"🔇 {user.full_name} замучен на {config.FLOOD_MUTE_MINUTES} мин. за флуд."
        )
        return

    if antispam.is_duplicate_spam(user.id, text):
        await _safe_delete(message)
        return

    if antispam.has_too_many_emoji(text):
        await _safe_delete(message)
        return

    # --- Антиреклама (идёт через систему предупреждений) ---
    if antiad.has_link(text):
        await _punish_with_warning(bot, message, "ссылка в сообщении")
        return

    if await antiad.has_foreign_mention(message, bot):
        await _punish_with_warning(bot, message, "упоминание постороннего пользователя")
        return

    if antiad.has_phone_number(text):
        await _punish_with_warning(bot, message, "номер телефона в сообщении")
        return

    keyword = antiad.has_ad_keyword(text)
    if keyword:
        await _punish_with_warning(bot, message, f"рекламное слово «{keyword}»")
        return

    # --- Запрещённые слова ---
    bad_word = badwords.contains_bad_word(text)
    if bad_word:
        await _punish_with_warning(bot, message, f"запрещённое слово «{bad_word}»")
        return
