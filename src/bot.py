"""Main program module."""

import sys
from asyncio import run
from typing import TYPE_CHECKING, ClassVar

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode, UpdateType
from aiogram.fsm.storage.base import DefaultKeyBuilder
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp.web import run_app
from aiohttp.web_app import Application

from tgbot.config import Config, logger
from tgbot.db.pg_client import PostgresClient
from tgbot.db.schema import Schema
from tgbot.handlers.main import MainHandler
from tgbot.misc.bot_commands import BotCommands
from tgbot.misc.broadcaster import Broadcaster
from tgbot.misc.keyboards import KeyboardManager
from tgbot.misc.log_setup import LoggingManager
from tgbot.misc.middlewares import AntiFloodMiddleware, UserSyncMiddleware
from tgbot.misc.scheduler import Scheduler
from tgbot.misc.tmpl_render import TmplRender
from tgbot.storage.redis_client import RedisClient
from tgbot.storage.synced_users import SyncedUsers

if TYPE_CHECKING:
    from redis.asyncio import Redis

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
            token=self._config.token.get_secret_value(),
            default=DefaultBotProperties(
                parse_mode=ParseMode.HTML, allow_sending_without_reply=True, link_preview_is_disabled=True
            ),
        )
        # One Redis client for the FSM storage, the anti-flood windows and the stores; the storage closes it on
        # shutdown
        redis: Redis = RedisClient(credentials=self._config.redis).redis
        self._dp: Dispatcher = Dispatcher(
            storage=RedisStorage(redis=redis, key_builder=DefaultKeyBuilder(prefix="tgbot_fsm"))
        )
        self._dp.update.outer_middleware(AntiFloodMiddleware(redis=redis))
        self._db: PostgresClient = PostgresClient(credentials=self._config.postgres)
        self._synced: SyncedUsers = SyncedUsers(redis=redis)
        # After the anti-flood middleware, so the updates it drops don't reach the database
        self._dp.update.outer_middleware(UserSyncMiddleware(client=self._db, synced=self._synced))
        self._broadcaster: Broadcaster = Broadcaster(bot=self._bot)
        self._tmpl: TmplRender = TmplRender(paths=self._config.paths)
        self._kb: KeyboardManager = KeyboardManager(tmpl=self._tmpl)
        self._scheduler: Scheduler = Scheduler(config=self._config, broadcaster=self._broadcaster, tmpl=self._tmpl)

    async def _on_startup(self) -> None:
        """
        The functions that runs when the bot starts.

        :return: None
        """
        await self._db.connect()
        await Schema(client=self._db).create()
        bot_commands: BotCommands = BotCommands(bot=self._bot, tmpl_render=self._tmpl, admin_ids=self._config.admins)
        await bot_commands.set_commands()
        self._scheduler.start()
        if (webhook := self._config.webhook) is not None:
            await self._bot.set_webhook(
                # str(HttpUrl) ends with "/" when the URL has no path
                url=f"{str(webhook.wh_host).rstrip('/')}/{webhook.wh_path}",
                allowed_updates=self._ALLOWED_UPDATES,
                drop_pending_updates=False,
                secret_token=webhook.wh_token.get_secret_value(),
            )

    async def _on_shutdown(self) -> None:
        """
        The functions that runs when the bot is stopped.

        Stops the scheduler first, waiting for a running job to finish (Scheduler.shutdown waits by
        default), before closing the database and the FSM storage a job might still be using. The database and the
        storage are closed even if a step before fails; the error still goes on to main(). The bot session is left
        to aiogram, which closes it after this hook: closing it here would cut the long-polling
        request that is still waiting for updates.

        :return: None
        """
        try:
            self._scheduler.shutdown()
            if self._config.webhook:
                await self._bot.delete_webhook()
        finally:
            try:
                await self._db.close()
            finally:
                await self._dp.storage.close()

    def run(self) -> None:
        """
        Runs the bot.

        :return: None
        """
        MainHandler(config=self._config, dp=self._dp, tmpl=self._tmpl, kb=self._kb, db=self._db, synced=self._synced)
        self._dp.startup.register(callback=self._on_startup)
        self._dp.shutdown.register(callback=self._on_shutdown)
        if (webhook := self._config.webhook) is not None:
            app: Application = Application()
            # aiohttp runs the shutdown hooks in the order they were added: the dispatcher's (_on_shutdown, which
            # calls delete_webhook) must come before the request handler's, which closes the bot session.
            # The other way round delete_webhook opens a new session that nobody closes ("Unclosed client session")
            setup_application(app, self._dp)
            SimpleRequestHandler(
                dispatcher=self._dp, bot=self._bot, secret_token=webhook.wh_token.get_secret_value()
            ).register(app, path=f"/{webhook.wh_path}")
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

    An unhandled error ends the process with exit code 1, so systemd and the shell see the failure.

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
        sys.exit(1)
    finally:
        logger.info("Bot stopped!")


if __name__ == "__main__":
    main()
