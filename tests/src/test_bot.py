"""Unit tests for src/bot.py."""

# ruff: noqa: S101, S105, S106, SLF001

from asyncio import sleep
from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage

# noinspection PyProtectedMember
from bot import TgBot, main
from tests.helpers import mocked
from tgbot.config import Config
from tgbot.misc.broadcaster import Broadcaster
from tgbot.misc.keyboards import KeyboardManager
from tgbot.misc.middlewares import AntiFloodMiddleware
from tgbot.misc.scheduler import Scheduler
from tgbot.misc.tmpl_render import TmplRender

__all__: tuple[str, ...] = ()


# noinspection PyProtectedMember
@pytest.fixture
def tg_bot() -> Iterator[TgBot]:
    """
    Provide a fresh TgBot instance for each test with mocked dependencies, using RedisStorage.

    :return: TgBot instance.
    """
    config: MagicMock = MagicMock(spec=Config)
    config.token = "mock_token"
    config.redis = MagicMock()  # Enable Redis to use RedisStorage
    config.admins = [123, 456]
    config.paths = MagicMock()
    config.webhook = None
    with patch(target="bot.Bot", return_value=MagicMock(spec=Bot)) as mock_bot:
        bot_instance: TgBot = TgBot(config=config)
        bot_instance._bot = mock_bot.return_value
        bot_instance._bot.default = DefaultBotProperties(
            parse_mode="HTML", allow_sending_without_reply=True, link_preview_is_disabled=True
        )
        bot_instance._bot.session = MagicMock()
        bot_instance._bot.session.close = AsyncMock()  # Only close remains asynchronous
        yield bot_instance
        Broadcaster._instance = None


def test_init(tg_bot: TgBot) -> None:
    """
    Tests initialization of TgBot with RedisStorage.

    :param tg_bot: Instance of TgBot to test.
    :return: None
    """
    assert isinstance(tg_bot._config, Config)
    assert isinstance(tg_bot._bot, Bot)
    assert isinstance(tg_bot._dp, Dispatcher)
    assert isinstance(tg_bot._broadcaster, Broadcaster)
    assert isinstance(tg_bot._tmpl, TmplRender)
    assert isinstance(tg_bot._kb, KeyboardManager)
    assert isinstance(tg_bot._scheduler, Scheduler)
    assert isinstance(tg_bot._dp.storage, RedisStorage)
    assert any(isinstance(middleware, AntiFloodMiddleware) for middleware in tg_bot._dp.update.outer_middleware)
    assert tg_bot._bot.default == DefaultBotProperties(
        parse_mode="HTML", allow_sending_without_reply=True, link_preview_is_disabled=True
    )


# noinspection PyUnresolvedReferences,PyPropertyAccess
@pytest.mark.asyncio
async def test_on_startup_polling(tg_bot: TgBot) -> None:
    """
    Tests the on_startup method in polling mode.

    :param tg_bot: Instance of TgBot to test.
    :return: None
    """
    tg_bot._broadcaster.broadcast = AsyncMock()
    tg_bot._scheduler.start = MagicMock()
    mock_bot_commands: MagicMock = MagicMock()
    mock_bot_commands.set_commands = AsyncMock()
    mocked(tg_bot._config).webhook = None
    with patch(target="bot.BotCommands", return_value=mock_bot_commands):
        await tg_bot._on_startup()
    tg_bot._broadcaster.broadcast.assert_called_once_with(
        users_ids=tg_bot._config.admins, msg="Bot was started", notify=False
    )
    tg_bot._scheduler.start.assert_called_once_with()
    mock_bot_commands.set_commands.assert_called_once()
    mocked(tg_bot._bot.set_webhook).assert_not_called()


# noinspection PyUnresolvedReferences,PyPropertyAccess
@pytest.mark.asyncio
async def test_on_startup_webhook(tg_bot: TgBot) -> None:
    """
    Tests the on_startup method in webhook mode.

    :param tg_bot: Instance of TgBot to test.
    :return: None
    """
    tg_bot._broadcaster.broadcast = AsyncMock()
    tg_bot._scheduler.start = MagicMock()
    mock_bot_commands: MagicMock = MagicMock()
    mock_bot_commands.set_commands = AsyncMock()
    mocked(tg_bot._config).webhook = MagicMock(
        wh_host="https://example.com", wh_path="webhook_path", wh_token="mock_token"
    )
    with patch(target="bot.BotCommands", return_value=mock_bot_commands):
        await tg_bot._on_startup()
    tg_bot._broadcaster.broadcast.assert_called_once_with(
        users_ids=tg_bot._config.admins, msg="Bot was started", notify=False
    )
    tg_bot._scheduler.start.assert_called_once_with()
    mock_bot_commands.set_commands.assert_called_once()
    mocked(tg_bot._bot.set_webhook).assert_called_once_with(
        url="https://example.com/webhook_path",
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=False,
        secret_token="mock_token",
    )


# noinspection PyUnresolvedReferences,PyPropertyAccess
@pytest.mark.asyncio
async def test_on_shutdown_polling(tg_bot: TgBot) -> None:
    """
    Tests the on_shutdown method in polling mode.

    :param tg_bot: Instance of TgBot to test.
    :return: None
    """
    tg_bot._broadcaster.broadcast = AsyncMock()
    mocked(tg_bot._config).webhook = None
    with (
        patch.object(target=tg_bot._scheduler, attribute="shutdown") as mock_shutdown,
        patch.object(target=tg_bot._dp.storage, attribute="close") as mock_storage_close,
    ):
        await tg_bot._on_shutdown()
    mock_shutdown.assert_called_once_with()
    tg_bot._broadcaster.broadcast.assert_called_once_with(
        users_ids=tg_bot._config.admins, msg="Bot was stopped", notify=False
    )
    mocked(tg_bot._bot.delete_webhook).assert_not_called()
    mock_storage_close.assert_awaited_once_with()
    mocked(tg_bot._bot.session.close).assert_not_called()  # aiogram closes the session itself


# noinspection PyUnresolvedReferences,PyPropertyAccess
@pytest.mark.asyncio
async def test_on_shutdown_webhook(tg_bot: TgBot) -> None:
    """
    Tests the on_shutdown method in webhook mode.

    :param tg_bot: Instance of TgBot to test.
    :return: None
    """
    tg_bot._broadcaster.broadcast = AsyncMock()
    tg_bot._bot.delete_webhook = AsyncMock()
    mocked(tg_bot._config).webhook = MagicMock()
    with (
        patch.object(target=tg_bot._scheduler, attribute="shutdown") as mock_shutdown,
        patch.object(target=tg_bot._dp.storage, attribute="close") as mock_storage_close,
    ):
        await tg_bot._on_shutdown()
    mock_shutdown.assert_called_once_with()
    tg_bot._broadcaster.broadcast.assert_called_once_with(
        users_ids=tg_bot._config.admins, msg="Bot was stopped", notify=False
    )
    tg_bot._bot.delete_webhook.assert_called_once()
    mock_storage_close.assert_awaited_once_with()


# noinspection PyPropertyAccess
def test_run_polling(tg_bot: TgBot) -> None:
    """
    Tests the run method in polling mode.

    :param tg_bot: Instance of TgBot to test.
    :return: None
    """
    with (
        patch(target="bot.MainHandler"),
        patch(target="bot.run") as mock_run,
    ):
        mocked(tg_bot._config).webhook = None
        with patch.object(target=tg_bot._dp, attribute="start_polling", new=MagicMock()) as mock_polling:
            tg_bot.run()
        mock_polling.assert_called_once_with(tg_bot._bot, allowed_updates=["message", "callback_query"])
        mock_run.assert_called_once_with(main=mock_polling.return_value)
        assert tg_bot._on_startup in [handler.callback for handler in tg_bot._dp.startup.handlers]
        assert tg_bot._on_shutdown in [handler.callback for handler in tg_bot._dp.shutdown.handlers]


# noinspection PyPropertyAccess
@pytest.mark.asyncio
async def test_run_webhook(tg_bot: TgBot) -> None:
    """
    Tests the run method in webhook mode.

    :param tg_bot: Instance of TgBot to test.
    :return: None
    """
    with (
        patch(target="bot.MainHandler"),
        patch(target="bot.run_app") as mock_run_app,
        patch(target="bot.Application") as mock_app,
        patch(target="bot.SimpleRequestHandler") as mock_handler,
        patch(target="bot.setup_application") as mock_setup,
    ):
        mocked(tg_bot._config).webhook = MagicMock(
            wh_path="webhook_path", wh_token="mock_token", app_host="localhost", app_port=8080
        )
        tg_bot.run()
        await sleep(delay=0.1)
        mock_handler.assert_called_once_with(dispatcher=tg_bot._dp, bot=tg_bot._bot, secret_token="mock_token")
        mock_setup.assert_called_once_with(mock_app.return_value, tg_bot._dp)
        mock_run_app.assert_called_once_with(app=mock_app.return_value, host="localhost", port=8080)
        assert tg_bot._on_startup in [handler.callback for handler in tg_bot._dp.startup.handlers]
        assert tg_bot._on_shutdown in [handler.callback for handler in tg_bot._dp.shutdown.handlers]


@pytest.mark.asyncio
async def test_main() -> None:
    """
    Tests the main function.

    :return: None
    """
    with (
        patch(target="bot.Config") as mock_config,
        patch(target="bot.LoggingManager") as mock_logging,
        patch(target="bot.TgBot") as mock_tg_bot,
        patch(target="bot.logger", new_callable=MagicMock) as mock_logger,
    ):
        mock_bot_instance: MagicMock = mock_tg_bot.return_value
        mock_bot_instance.run = MagicMock()
        main()
        config: MagicMock = mock_config.return_value
        mock_logging.assert_called_once_with(debug=config.debug, log_dir=config.log_dir, project_name="tgbot")
        mock_logger.info.assert_any_call("Starting bot")
        mock_tg_bot.assert_called_once_with(config=config)
        mock_bot_instance.run.assert_called_once()
        mock_logger.info.assert_any_call("Bot stopped!")


@pytest.mark.asyncio
async def test_main_with_exception() -> None:
    """
    Tests the main function when an exception occurs.

    :return: None
    """
    with (
        patch(target="bot.Config"),
        patch(target="bot.LoggingManager"),
        patch(target="bot.TgBot") as mock_tg_bot,
        patch(target="bot.logger", new_callable=MagicMock) as mock_logger,
    ):
        mock_bot_instance: MagicMock = mock_tg_bot.return_value
        mock_bot_instance.run = MagicMock(side_effect=Exception("Test error"))
        main()
        mock_logger.info.assert_any_call("Starting bot")
        mock_tg_bot.assert_called_once()
        mock_bot_instance.run.assert_called_once()
        mock_logger.critical.assert_called_once_with("Unhandled error: Exception('Test error')")
        mock_logger.info.assert_any_call("Bot stopped!")


@pytest.mark.asyncio
async def test_main_with_keyboard_interrupt() -> None:
    """
    Tests the main function when a KeyboardInterrupt occurs.

    :return: None
    """
    with (
        patch(target="bot.Config"),
        patch(target="bot.LoggingManager"),
        patch(target="bot.TgBot") as mock_tg_bot,
        patch(target="bot.logger", new_callable=MagicMock) as mock_logger,
    ):
        mock_bot_instance: MagicMock = mock_tg_bot.return_value
        mock_bot_instance.run = MagicMock(side_effect=KeyboardInterrupt)
        main()
        mock_logger.info.assert_any_call("Starting bot")
        mock_tg_bot.assert_called_once()
        mock_bot_instance.run.assert_called_once()
        mock_logger.critical.assert_not_called()
        mock_logger.info.assert_any_call("Bot stopped!")


@pytest.mark.asyncio
async def test_main_with_system_exit() -> None:
    """
    Tests the main function when a SystemExit occurs.

    :return: None
    """
    with (
        patch(target="bot.Config"),
        patch(target="bot.LoggingManager"),
        patch(target="bot.TgBot") as mock_tg_bot,
        patch(target="bot.logger", new_callable=MagicMock) as mock_logger,
    ):
        mock_bot_instance: MagicMock = mock_tg_bot.return_value
        mock_bot_instance.run = MagicMock(side_effect=SystemExit)
        main()
        mock_logger.info.assert_any_call("Starting bot")
        mock_tg_bot.assert_called_once()
        mock_bot_instance.run.assert_called_once()
        mock_logger.critical.assert_not_called()
        mock_logger.info.assert_any_call("Bot stopped!")
