import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from app.handlers import routers

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")


async def main():

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не найден в файле .env"
        )

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )

    dp = Dispatcher()

    for router in routers:
        dp.include_router(router)

    print()
    print("=" * 50)
    print("        Family Budget AI")
    print("           Version 1.0 RC1")
    print("=" * 50)
    print("✅ Bot started")
    print("=" * 50)
    print()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())