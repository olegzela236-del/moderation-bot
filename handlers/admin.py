"""
Команды для администраторов чата: /warn /mute /ban /unwarn /stats.
Доступны только пользователям со статусом admin/creator в группе.
"""
import logging
from datetime import datetime

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import ChatPermissions, Message

import database
from handlers import warnings
from handlers.utils import is_admin, parse_duration, resolve_target_user

router = Router(name="admin")
logger = logging.getLogger(__name__)


async def _check_admin(message: Message, bot: Bot) -> bool:
    if message.from_user is None or not await is_admin(bot, message.chat.id, message.from_user.id):
        await message.reply("Команда доступна только администраторам.")
        return False
    return True


async def _get_target(message: Message, bot: Bot):
    target = await resolve_target_user(message, bot)
    if target is None:
        await message.reply(
            "Не удалось определить пользователя. Ответьте (reply) на его сообщение "
            "или укажите через @упоминание из списка подсказок."
        )
    return target


@router.message(Command("warn"))
async def cmd_warn(message: Message, bot: Bot) -> None:
    if not await _check_admin(message, bot):
        return

    target = await _get_target(message, bot)
    if target is None:
        return

    user_id, name = target
    count = await database.add_warning(user_id, message.chat.id, "ручное предупреждение от админа")
    escalation_text = await warnings.apply_escalation(bot, message.chat.id, user_id, count)
    await message.reply(f"{name}: {escalation_text}")


@router.message(Command("unwarn"))
async def cmd_unwarn(message: Message, bot: Bot) -> None:
    if not await _check_admin(message, bot):
        return

    target = await _get_target(message, bot)
    if target is None:
        return

    user_id, name = target
    count = await database.remove_one_warning(user_id, message.chat.id)
    await message.reply(f"✅ Снято предупреждение у {name}. Осталось: {count}.")


@router.message(Command("mute"))
async def cmd_mute(message: Message, bot: Bot) -> None:
    if not await _check_admin(message, bot):
        return

    target = await _get_target(message, bot)
    if target is None:
        return

    # Ищем в аргументах команды длительность вида 30m/2h/1d (первый токен, начинающийся с цифры)
    args = message.text.split()[1:] if message.text else []
    duration_str = next((a for a in args if a[:1].isdigit()), None)
    duration = parse_duration(duration_str) if duration_str else None
    if duration is None:
        await message.reply("Укажите длительность, например: /mute @user 30m")
        return

    user_id, name = target
    until = datetime.utcnow() + duration
    await bot.restrict_chat_member(
        message.chat.id,
        user_id,
        permissions=ChatPermissions(can_send_messages=False),
        until_date=until,
    )
    await message.reply(f"🔇 {name} замучен до {until.strftime('%Y-%m-%d %H:%M UTC')}.")


@router.message(Command("ban"))
async def cmd_ban(message: Message, bot: Bot) -> None:
    if not await _check_admin(message, bot):
        return

    target = await _get_target(message, bot)
    if target is None:
        return

    user_id, name = target
    await bot.ban_chat_member(message.chat.id, user_id)
    await message.reply(f"⛔ {name} забанен.")


@router.message(Command("stats"))
async def cmd_stats(message: Message, bot: Bot) -> None:
    if not await _check_admin(message, bot):
        return

    total, top_users = await database.get_stats(message.chat.id)
    if total == 0:
        await message.reply("Нарушений пока не зафиксировано.")
        return

    lines = [f"📊 Всего нарушений: {total}", "", "Топ нарушителей (user_id: количество):"]
    for user_id, count in top_users:
        lines.append(f"• {user_id}: {count}")

    await message.reply("\n".join(lines))
