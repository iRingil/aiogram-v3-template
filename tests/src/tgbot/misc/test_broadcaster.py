"""
Unit tests for src/tgbot/misc/broadcaster.py.

Bot is an autospecced mock, so a wrong kwarg in broadcaster.py fails these tests. The singleton is
reset around every test, and asyncio.sleep is replaced with a recorder to keep the suite fast.
"""

# ruff: noqa: PLR2004, S101, SLF001

from asyncio import gather
from collections.abc import Iterator
from unittest.mock import MagicMock, create_autospec

import pytest
from aiogram import Bot
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.methods import SendMessage
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup

from tgbot.misc import broadcaster as broadcaster_module
from tgbot.misc.broadcaster import Broadcaster

__all__: tuple[str, ...] = ()


def _api_error() -> TelegramAPIError:
    """
    Builds a real TelegramAPIError, backed by a throwaway SendMessage method.

    :return: A TelegramAPIError instance.
    """
    return TelegramAPIError(method=SendMessage(chat_id=1, text="x"), message="bad")


def _retry_after(seconds: int) -> TelegramRetryAfter:
    """
    Builds a real TelegramRetryAfter (a flood limit), backed by a throwaway SendMessage method.

    :param seconds: The time Telegram asks to wait.
    :return: A TelegramRetryAfter instance.
    """
    return TelegramRetryAfter(method=SendMessage(chat_id=1, text="x"), message="flood", retry_after=seconds)


@pytest.fixture(autouse=True)
def _reset_singleton() -> Iterator[None]:
    """
    Resets the Broadcaster singleton before and after each test.

    :return: None
    """
    Broadcaster._instance = None
    yield
    Broadcaster._instance = None


@pytest.fixture(autouse=True, name="sleep_calls")
def sleep_calls_fixture(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """
    Replaces the broadcaster's sleep with a no-op that records each requested delay.

    :param monkeypatch: pytest fixture used to patch the sleep function.
    :return: The list every requested delay is appended to.
    """
    delays: list[float] = []

    async def _instant_sleep(delay: float) -> None:
        """
        Records the delay instead of waiting it out.

        :param delay: The rate-limit delay.
        :return: None
        """
        delays.append(delay)

    monkeypatch.setattr(target=broadcaster_module, name="sleep", value=_instant_sleep)
    return delays


@pytest.fixture(name="bot")
def bot_fixture() -> MagicMock:
    """
    An autospecced aiogram Bot, its send methods are AsyncMocks checked against the real signatures.

    :return: The mocked Bot instance.
    """
    return create_autospec(spec=Bot, instance=True)


@pytest.fixture(name="broadcaster")
def broadcaster_fixture(bot: MagicMock) -> Broadcaster:
    """
    A fresh Broadcaster backed by the mocked bot.

    :param bot: The mocked Bot fixture.
    :return: The Broadcaster instance under test.
    """
    return Broadcaster(bot=bot)


def test_singleton_keeps_the_first_bot(bot: MagicMock) -> None:
    """
    Test that a second construction returns the same instance, still bound to the first bot.

    :param bot: The mocked Bot fixture.
    :return: None
    """
    first: Broadcaster = Broadcaster(bot=bot)
    second: Broadcaster = Broadcaster(bot=create_autospec(spec=Bot, instance=True))
    assert first is second
    assert second._bot is bot


async def test_send_text(broadcaster: Broadcaster, bot: MagicMock) -> None:
    """
    Test that a text message is sent via send_message and its ID is returned.

    :param broadcaster: The Broadcaster fixture.
    :param bot: The mocked Bot fixture.
    :return: None
    """
    bot.send_message.return_value = MagicMock(message_id=111)
    assert await broadcaster.send_content(user_id=42, msg="hello") == 111
    bot.send_message.assert_awaited_once_with(
        chat_id=42, text="hello", disable_notification=False, reply_markup=None, reply_to_message_id=None
    )


async def test_send_text_options(broadcaster: Broadcaster, bot: MagicMock) -> None:
    """
    Test that the text is truncated to 4096 chars and notify, markup and reply ID are passed through.

    :param broadcaster: The Broadcaster fixture.
    :param bot: The mocked Bot fixture.
    :return: None
    """
    bot.send_message.return_value = MagicMock(message_id=1)
    markup: InlineKeyboardMarkup = InlineKeyboardMarkup(inline_keyboard=[])
    await broadcaster.send_content(user_id=42, msg="x" * 5000, notify=False, reply_markup=markup, reply_to_message_id=7)
    bot.send_message.assert_awaited_once_with(
        chat_id=42, text="x" * 4096, disable_notification=True, reply_markup=markup, reply_to_message_id=7
    )


@pytest.mark.parametrize("msg", [None, ""])
async def test_send_empty_text(broadcaster: Broadcaster, bot: MagicMock, msg: str | None) -> None:
    """
    Test that an empty text message is not sent.

    :param broadcaster: The Broadcaster fixture.
    :param bot: The mocked Bot fixture.
    :param msg: The empty message value.
    :return: None
    """
    assert await broadcaster.send_content(user_id=42, msg=msg) is None
    bot.send_message.assert_not_awaited()


async def test_send_raises_telegram_error(broadcaster: Broadcaster, bot: MagicMock) -> None:
    """
    Test that send_content lets a Telegram API error propagate to the caller.

    :param broadcaster: The Broadcaster fixture.
    :param bot: The mocked Bot fixture.
    :return: None
    """
    bot.send_message.side_effect = _api_error()
    with pytest.raises(expected_exception=TelegramAPIError):
        await broadcaster.send_content(user_id=42, msg="hi")


async def test_send_chat_action(broadcaster: Broadcaster, bot: MagicMock) -> None:
    """
    Test that a chat action sends the typing indicator and returns None.

    :param broadcaster: The Broadcaster fixture.
    :param bot: The mocked Bot fixture.
    :return: None
    """
    assert await broadcaster.send_content(user_id=42, content_type="chat_action") is None
    bot.send_chat_action.assert_awaited_once_with(chat_id=42, action=ChatAction.TYPING)


async def test_send_photo(broadcaster: Broadcaster, bot: MagicMock) -> None:
    """
    Test that a photo is sent with msg as its caption and its ID is returned.

    :param broadcaster: The Broadcaster fixture.
    :param bot: The mocked Bot fixture.
    :return: None
    """
    bot.send_photo.return_value = MagicMock(message_id=222)
    result: int | None = await broadcaster.send_content(
        user_id=42, msg="a chart", content_type="photo", photo=b"png-bytes"
    )
    assert result == 222
    sent_photo: BufferedInputFile = bot.send_photo.call_args.kwargs["photo"]
    assert sent_photo.data == b"png-bytes"
    assert sent_photo.filename == "photo.png"
    assert bot.send_photo.call_args.kwargs["caption"] == "a chart"
    assert bot.send_photo.call_args.kwargs["chat_id"] == 42


@pytest.mark.parametrize("photo", [None, b""])
async def test_send_empty_photo(broadcaster: Broadcaster, bot: MagicMock, photo: bytes | None) -> None:
    """
    Test that an empty photo is not sent.

    :param broadcaster: The Broadcaster fixture.
    :param bot: The mocked Bot fixture.
    :param photo: The empty photo value.
    :return: None
    """
    assert await broadcaster.send_content(user_id=42, content_type="photo", photo=photo) is None
    bot.send_photo.assert_not_awaited()


async def test_send_rate_limit(broadcaster: Broadcaster, bot: MagicMock, sleep_calls: list[float]) -> None:
    """
    Test that a single call sleeps once for the rate-limit delay.

    :param broadcaster: The Broadcaster fixture.
    :param bot: The mocked Bot fixture.
    :param sleep_calls: Fixture recording every requested delay.
    :return: None
    """
    bot.send_message.return_value = MagicMock(message_id=1)
    await broadcaster.send_content(user_id=42, msg="hi")
    assert sleep_calls == [1.0 / Broadcaster._max_msgs_per_sec]


async def test_send_retries_after_flood_limit(
    broadcaster: Broadcaster, bot: MagicMock, sleep_calls: list[float]
) -> None:
    """
    Test that a flood limit is waited out for the time Telegram asks, and the same message is sent again.

    :param broadcaster: The Broadcaster fixture.
    :param bot: The mocked Bot fixture.
    :param sleep_calls: Fixture recording every requested delay.
    :return: None
    """
    bot.send_message.side_effect = [_retry_after(seconds=7), MagicMock(message_id=5)]
    assert await broadcaster.send_content(user_id=42, msg="hi") == 5
    assert [call.kwargs["chat_id"] for call in bot.send_message.await_args_list] == [42, 42]
    assert sleep_calls == [7, 1.0 / Broadcaster._max_msgs_per_sec]


async def test_send_gives_up_after_the_last_attempt(
    broadcaster: Broadcaster, bot: MagicMock, sleep_calls: list[float]
) -> None:
    """
    Test that a flood limit on every attempt is raised after the last one, with no delay before raising.

    :param broadcaster: The Broadcaster fixture.
    :param bot: The mocked Bot fixture.
    :param sleep_calls: Fixture recording every requested delay.
    :return: None
    """
    attempts: int = Broadcaster._max_attempts
    bot.send_message.side_effect = [_retry_after(seconds=3) for _ in range(attempts)]
    with pytest.raises(expected_exception=TelegramRetryAfter):
        await broadcaster.send_content(user_id=42, msg="hi")
    assert bot.send_message.await_count == attempts
    assert sleep_calls == [3] * (attempts - 1)


async def test_send_concurrent(broadcaster: Broadcaster, bot: MagicMock, sleep_calls: list[float]) -> None:
    """
    Test that concurrent calls are serialized by the lock and each gets its own message ID.

    :param broadcaster: The Broadcaster fixture.
    :param bot: The mocked Bot fixture.
    :param sleep_calls: Fixture recording every requested delay.
    :return: None
    """
    bot.send_message.side_effect = [MagicMock(message_id=101), MagicMock(message_id=202)]
    first, second = await gather(
        broadcaster.send_content(user_id=1, msg="first"), broadcaster.send_content(user_id=2, msg="second")
    )
    assert {first, second} == {101, 202}
    assert len(sleep_calls) == 2


async def test_broadcast_forwards_options(broadcaster: Broadcaster, bot: MagicMock) -> None:
    """
    Test that broadcast sends to every user with all options passed through.

    :param broadcaster: The Broadcaster fixture.
    :param bot: The mocked Bot fixture.
    :return: None
    """
    bot.send_photo.return_value = MagicMock(message_id=1)
    markup: InlineKeyboardMarkup = InlineKeyboardMarkup(inline_keyboard=[])
    await broadcaster.broadcast(
        users_ids=[1, 2],
        msg="caption",
        content_type="photo",
        notify=False,
        reply_markup=markup,
        reply_to_message_id=9,
        photo=b"png-bytes",
    )
    assert [call.kwargs["chat_id"] for call in bot.send_photo.await_args_list] == [1, 2]
    for call in bot.send_photo.await_args_list:
        assert call.kwargs["caption"] == "caption"
        assert call.kwargs["disable_notification"] is True
        assert call.kwargs["reply_markup"] is markup
        assert call.kwargs["reply_to_message_id"] == 9
        assert call.kwargs["photo"].data == b"png-bytes"


async def test_broadcast_telegram_error(broadcaster: Broadcaster, bot: MagicMock) -> None:
    """
    Test that a Telegram error for one user does not skip the rest.

    :param broadcaster: The Broadcaster fixture.
    :param bot: The mocked Bot fixture.
    :return: None
    """
    bot.send_message.side_effect = [MagicMock(message_id=1), _api_error(), MagicMock(message_id=3)]
    await broadcaster.broadcast(users_ids=[1, 2, 3], msg="hi")
    assert bot.send_message.await_count == 3


async def test_broadcast_other_error(broadcaster: Broadcaster, bot: MagicMock) -> None:
    """
    Test that any other exception stops the broadcast and goes to the caller.

    :param broadcaster: The Broadcaster fixture.
    :param bot: The mocked Bot fixture.
    :return: None
    """
    bot.send_message.side_effect = [MagicMock(message_id=1), RuntimeError("boom"), MagicMock(message_id=3)]
    with pytest.raises(expected_exception=RuntimeError, match="boom"):
        await broadcaster.broadcast(users_ids=[1, 2, 3], msg="hi")
    assert bot.send_message.await_count == 2
