"""
Простая капча для новых участников: кнопка «Я не бот».
Если не нажать за CAPTCHA_TIMEOUT_SECONDS — пользователя кикают.
"""
import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    ChatMemberUpdated,
    ChatPermissions,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import config

router = Router(name="captcha")
logger = logging.getLogger(__name__)

# user_id -> отложенная задача кика (отменяется, если капча пройдена вовремя)
_pending_kicks: dict = {}


def _captcha_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(text="✅ Я не бот", callback_data=f"captcha:{user_id}")
        ]]
    )


@router.chat_member(F.chat.id == config.GROUP_ID)
async def on_user_joined(event: ChatMemberUpdated, bot: Bot) -> None:
    """Срабатывает при вступлении нового участника в группу."""
    old_status = event.old_chat_member.status
    new_status = event.new_chat_member.status
    user = event.new_chat_member.user

    if user.is_bot or old_status not in ("left", "kicked") or new_status != "member":
        return

    chat_id = event.chat.id

    # Пока капча не пройдена — запрещаем писать в чат
    try:
        await bot.restrict_chat_member(
            chat_id, user.id, permissions=ChatPermissions(can_send_messages=False)
        )
    except TelegramBadRequest:
        pass  # например, пользователю уже выданы права — не критично

    sent = await bot.send_message(
        chat_id,
        f"👋 {user.full_name}, добро пожаловать! Нажмите кнопку в течение "
        f"{config.CAPTCHA_TIMEOUT_SECONDS} секунд, чтобы подтвердить, что вы не бот.",
        reply_markup=_captcha_keyboard(user.id),
    )

    task = asyncio.create_task(_kick_if_not_confirmed(bot, chat_id, user.id, sent.message_id))
    _pending_kicks[user.id] = task


async def _kick_if_not_confirmed(bot: Bot, chat_id: int, user_id: int, captcha_message_id: int) -> None:
    await asyncio.sleep(config.CAPTCHA_TIMEOUT_SECONDS)

    # Если мы дошли сюда — задача не была отменена, значит капча не пройдена
    try:
        await bot.ban_chat_member(chat_id, user_id)
        await bot.unban_chat_member(chat_id, user_id)  # разбан сразу же — это "кик", а не бан навсегда
        logger.info("Пользователь %s кикнут — капча не пройдена", user_id)
    except TelegramBadRequest:
        pass
    finally:
        try:
            await bot.delete_message(chat_id, captcha_message_id)
        except TelegramBadRequest:
            pass
        _pending_kicks.pop(user_id, None)


@router.callback_query(F.data.startswith("captcha:"))
async def on_captcha_confirmed(callback: CallbackQuery, bot: Bot) -> None:
    expected_user_id = int(callback.data.split(":")[1])

    if callback.from_user.id != expected_user_id:
        await callback.answer("Эта кнопка не для вас.", show_alert=True)
        return

    task = _pending_kicks.pop(expected_user_id, None)
    if task:
        task.cancel()

    try:
        await bot.restrict_chat_member(
            callback.message.chat.id,
            expected_user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_other_messages=True,
            ),
        )
    except TelegramBadRequest:
        pass

    await callback.answer("Спасибо! Доступ открыт.")
    try:
        await callback.message.delete()
    except TelegramBadRequest:
        pass
