import logging
import shutil

from telegram import BotCommand, Update
from telegram.ext import Application

import config
import converter
import handlers


async def post_init(app: Application) -> None:
    # Remove leftovers from a previous crash, then make sure the folder exists.
    shutil.rmtree(config.TEMP_DIR, ignore_errors=True)
    config.TEMP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        await app.bot.set_my_commands([BotCommand("help", "راهنمای ربات")])
    except Exception:
        logging.getLogger("mp3bot").warning("could not set commands")
    logging.getLogger("mp3bot").info("started as @%s", app.bot.username)


async def post_shutdown(app: Application) -> None:
    await converter.close_client()


def main() -> None:
    logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not config.BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is missing. Put it in the .env file.")

    app = (
        Application.builder()
        .token(config.BOT_TOKEN)
        .concurrent_updates(True)
        .connection_pool_size(64)
        .pool_timeout(10)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )
    handlers.register(app)
    app.run_polling(allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY], drop_pending_updates=True)


if __name__ == "__main__":
    main()
