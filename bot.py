import asyncio
import logging
import argparse

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums.parse_mode import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiohttp import web

from config import config, Config
from handlers import register_handlers
from webhook_handlers import handle_payment_webhook


def setup_logging(*, log_to_file: bool) -> None:
    handlers = None
    if log_to_file:
        handlers = [logging.FileHandler("logs.log", encoding="utf-8")]

    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        handlers=handlers,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )

    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("aiogram.event").setLevel(logging.WARNING)


async def main(*, log_to_file: bool) -> None:
    setup_logging(log_to_file=log_to_file)

    bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    register_handlers(dp, bot)

    # Setting up a web server for webhooks
    app = web.Application()
    app.router.add_post("/webhook", handle_payment_webhook,)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, Config.web_server_host, Config.web_server_port)

    # Launching the server in the background
    await site.start()
    logging.info(f"The web server is running on {Config.web_server_host}:{Config.web_server_port}")

    logging.info("Starting bot polling...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logging.error("Error while polling: %s", e)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--log-to-file",
        action="store_true",
        help="Write all logs to logs.log instead of stdout",
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(log_to_file=args.log_to_file))
    except KeyboardInterrupt:
        logging.info("Bot stopped by keyboard interrupt (Ctrl+C)")
