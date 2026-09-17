"""
Точка входа бота-модератора.
Инициализирует базу данных и список запрещённых слов, затем запускает polling.
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

import config
import database
from handlers import get_routers
from handlers.badwords import load_bad_words


def setup_logging() -> None:
    """Настраивает логирование в файл bot.log и в консоль."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(config.LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


async def main() -> None:
    setup_logging()
    logger = logging.getLogger(__name__)

    if not config.BOT_TOKEN or not config.GROUP_ID:
        raise RuntimeError("Не заданы BOT_TOKEN и/или GROUP_ID — проверьте .env")

    await database.init_db()
    load_bad_words()

    bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    for router in get_routers():
        dp.include_router(router)

    logger.info("Бот запущен")
    await bot.delete_webhook(drop_pending_updates=True)
    # allowed_updates обязательно должен включать chat_member — иначе капча не сработает
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "chat_member"])


if __name__ == "__main__":
    asyncio.run(main())
