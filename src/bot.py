"""Main program module."""

from asyncio import run

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp.web import run_app
from aiohttp.web_app import Application

from tgbot.config import Config, logger
from tgbot.handlers.main import MainHandler
from tgbot.misc.bot_commands import BotCommands
from tgbot.misc.broadcaster import Broadcaster
from tgbot.misc.keyboards import KeyboardManager
from tgbot.misc.scheduler import Scheduler
from tgbot.misc.tmpl_render import TmplRender

__all__: tuple[str, ...] = ()


class TgBot:
    """The main class that executes the application logic."""

    def __init__(self) -> None:
        """Initialization necessary parameters."""
        self._config: Config = Config()
        self._bot: Bot = Bot(
            token=self._config.token,
            default=DefaultBotProperties(
                parse_mode=ParseMode.HTML, allow_sending_without_reply=True, link_preview_is_disabled=True
            ),
        )
        storage: MemoryStorage | RedisStorage = (
            RedisStorage(redis=self._config.redis, key_builder=DefaultKeyBuilder(prefix="tgbot_fsm"))
            if self._config.redis
            else MemoryStorage()
        )
        self._dp: Dispatcher = Dispatcher(storage=storage)
        self._broadcaster: Broadcaster = Broadcaster(bot=self._bot)
        self._tmpl: TmplRender = TmplRender(paths=self._config.paths)
        self._kb: KeyboardManager = KeyboardManager(tmpl=self._tmpl)
        self._scheduler: Scheduler = Scheduler(config=self._config, broadcaster=self._broadcaster, tmpl=self._tmpl)

    async def _on_startup(self) -> None:
        """
        The functions that runs when the bot starts.

        :return: None
        """
        bot_commands: BotCommands = BotCommands(bot=self._bot, tmpl_render=self._tmpl, admin_ids=self._config.admins)
        await bot_commands.set_commands()
        await self._scheduler.schedule()
        if self._config.webhook:
            await self._bot.set_webhook(
                url=f"{self._config.webhook.wh_host}/{self._config.webhook.wh_path}",
                drop_pending_updates=False,
                secret_token=self._config.webhook.wh_token,
            )
        await self._broadcaster.broadcast(users_ids=self._config.admins, msg="Bot was started", notify=False)

    async def _on_shutdown(self) -> None:
        """
        The functions that runs when the bot is stopped.

        :return: None
        """
        if self._config.webhook:
            await self._bot.delete_webhook()
        await self._broadcaster.broadcast(users_ids=self._config.admins, msg="Bot was stopped", notify=False)
        await self._bot.session.close()

    def run(self) -> None:
        """
        Runs the bot.

        :return: None
        """
        MainHandler(config=self._config, dp=self._dp, tmpl=self._tmpl, kb=self._kb)
        self._dp.startup.register(callback=self._on_startup)
        self._dp.shutdown.register(callback=self._on_shutdown)
        if self._config.webhook:
            app: Application = Application()
            SimpleRequestHandler(
                dispatcher=self._dp, bot=self._bot, secret_token=self._config.webhook.wh_token
            ).register(app, path=f"/{self._config.webhook.wh_path}")
            setup_application(app, self._dp)
            run_app(app=app, host=self._config.webhook.app_host, port=self._config.webhook.app_port)
        else:
            # The aiogram start_polling accepts untyped **kwargs
            run(main=self._dp.start_polling(self._bot))  # pyright: ignore[reportUnknownMemberType]


def main() -> None:
    """
    Runs the application and logs its start, stop and unhandled errors.

    :return: None
    """
    logger.info("Starting bot")
    tg_bot: TgBot = TgBot()
    try:
        tg_bot.run()
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as exc:  # noqa: BLE001 - the last resort: logs whatever stopped the bot
        logger.critical(f"Unhandled error: {exc!r}")
    finally:
        logger.info("Bot stopped!")


if __name__ == "__main__":
    main()
