"""Main program module."""

from asyncio import run
from typing import ClassVar

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, UpdateType
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
from tgbot.misc.log_setup import LoggingManager
from tgbot.misc.middlewares import AntiFloodMiddleware
from tgbot.misc.scheduler import Scheduler
from tgbot.misc.tmpl_render import TmplRender

__all__: tuple[str, ...] = ()


class TgBot:
    """
    The main class that executes the application logic.

    :cvar _ALLOWED_UPDATES: Update types Telegram is allowed to send, in both webhook and polling
        mode, so nothing the bot doesn't act on ever reaches it. Extend it with the update types the
        handlers of a new feature need.
    """

    _ALLOWED_UPDATES: ClassVar[list[str]] = [UpdateType.MESSAGE, UpdateType.CALLBACK_QUERY]

    def __init__(self, config: Config) -> None:
        """
        Initialization necessary parameters.

        :param config: Config object with configuration settings.
        """
        self._config: Config = config
        self._bot: Bot = Bot(
            token=self._config.token,
            default=DefaultBotProperties(
                parse_mode=ParseMode.HTML, allow_sending_without_reply=True, link_preview_is_disabled=True
            ),
        )
        redis = self._config.redis
        storage: MemoryStorage | RedisStorage = (
            RedisStorage(redis=redis, key_builder=DefaultKeyBuilder(prefix="tgbot_fsm"))
            if redis is not None
            else MemoryStorage()
        )
        self._dp: Dispatcher = Dispatcher(storage=storage)
        self._dp.update.outer_middleware(AntiFloodMiddleware())
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
        self._scheduler.start()
        if (webhook := self._config.webhook) is not None:
            await self._bot.set_webhook(
                url=f"{webhook.wh_host}/{webhook.wh_path}",
                allowed_updates=self._ALLOWED_UPDATES,
                drop_pending_updates=False,
                secret_token=webhook.wh_token,
            )
        await self._broadcaster.broadcast(users_ids=self._config.admins, msg="Bot was started", notify=False)

    async def _on_shutdown(self) -> None:
        """
        The functions that runs when the bot is stopped.

        Stops the scheduler first, waiting for a running job to finish (Scheduler.shutdown waits by
        default), before closing the FSM storage a job might still be using. The bot session is left
        to aiogram, which closes it after this hook: closing it here would cut the long-polling
        request that is still waiting for updates.

        :return: None
        """
        self._scheduler.shutdown()
        if self._config.webhook:
            await self._bot.delete_webhook()
        await self._broadcaster.broadcast(users_ids=self._config.admins, msg="Bot was stopped", notify=False)
        await self._dp.storage.close()

    def run(self) -> None:
        """
        Runs the bot.

        :return: None
        """
        MainHandler(config=self._config, dp=self._dp, tmpl=self._tmpl, kb=self._kb)
        self._dp.startup.register(callback=self._on_startup)
        self._dp.shutdown.register(callback=self._on_shutdown)
        if (webhook := self._config.webhook) is not None:
            app: Application = Application()
            SimpleRequestHandler(dispatcher=self._dp, bot=self._bot, secret_token=webhook.wh_token).register(
                app, path=f"/{webhook.wh_path}"
            )
            setup_application(app, self._dp)
            run_app(app=app, host=webhook.app_host, port=webhook.app_port)
        else:
            # The aiogram start_polling accepts untyped **kwargs
            polling = self._dp.start_polling(  # pyright: ignore[reportUnknownMemberType]
                self._bot, allowed_updates=self._ALLOWED_UPDATES
            )
            run(main=polling)


def main() -> None:
    """
    Reads the config, sets up logging, then runs the bot and logs its start, stop and unhandled errors.

    :return: None
    """
    config: Config = Config()
    LoggingManager(debug=config.debug, log_dir=config.log_dir, project_name="tgbot")
    logger.info("Starting bot")
    tg_bot: TgBot = TgBot(config=config)
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
