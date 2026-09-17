"""
Общая логика наказания в зависимости от количества предупреждений.
Используется и автоматическими фильтрами, и командой /warn, чтобы
эскалация (мут на 2-м, бан на 3-м) была одинаковой в обоих случаях.
"""
from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.types import ChatPermissions

import config


async def apply_escalation(bot: Bot, chat_id: int, user_id: int, new_count: int) -> str:
    """
    Применяет наказание, соответствующее новому количеству предупреждений,
    и возвращает текст уведомления для чата:
      1-е нарушение -> просто предупреждение
      2-е нарушение -> мут на MUTE_ON_SECOND_WARN_HOURS
      3-е и далее   -> бан
    """
    if new_count <= 1:
        return f"⚠️ предупреждение ({new_count}/3)."

    if new_count == 2:
        until = datetime.utcnow() + timedelta(hours=config.MUTE_ON_SECOND_WARN_HOURS)
        await bot.restrict_chat_member(
            chat_id,
            user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until,
        )
        return f"🔇 мут на {config.MUTE_ON_SECOND_WARN_HOURS} ч. (2/3 предупреждения)."

    await bot.ban_chat_member(chat_id, user_id)
    return "⛔ бан (3/3 предупреждения)."
