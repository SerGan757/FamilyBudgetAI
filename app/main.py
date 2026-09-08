import asyncio
import logging
import os
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from app.handlers import routers
from app.database.db import engine
from app.database.init_db import init_db
from app.workers.temporary_message_worker import run_temporary_message_worker

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

async def health(request):
    return web.Response(text="OK")


async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.environ.get("PORT", 10000))

    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    print(f"Web server started on port {port}")
    return runner

async def main():

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    if not BOT_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не найден в файле .env"
        )

    await init_db()
    web_runner = await start_web_server()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
        ),
    )

    dp = Dispatcher()

    for router in routers:
        dp.include_router(router)

    worker_stop = asyncio.Event()
    worker_task = asyncio.create_task(
        run_temporary_message_worker(bot, worker_stop),
        name="temporary-message-worker",
    )

    print()
    print("=" * 50)
    print("        Family Budget AI")
    print("           Version 1.0 RC1")
    print("=" * 50)
    print("Bot started")
    print("=" * 50)
    print()
    print(">>> START POLLING <<<")
    try:
        await dp.start_polling(bot, close_bot_session=False)
    finally:
        worker_stop.set()
        await worker_task
        await bot.session.close()
        await web_runner.cleanup()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
