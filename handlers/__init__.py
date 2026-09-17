"""Сборка всех роутеров бота в один список для регистрации в bot.py."""
from aiogram import Router

from handlers.admin import router as admin_router
from handlers.captcha import router as captcha_router
from handlers.moderation import router as moderation_router


def get_routers() -> list[Router]:
    """
    Порядок важен:
    1) admin — команды администраторов обрабатываются в первую очередь;
    2) captcha — вступление новых участников и подтверждение капчи;
    3) moderation — общая проверка остальных сообщений (должна идти последней).
    """
    return [admin_router, captcha_router, moderation_router]
