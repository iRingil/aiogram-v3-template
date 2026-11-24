"""Unit tests for src/tgbot/services/common.py."""

# ruff: noqa: S101, SLF001

from unittest.mock import AsyncMock, Mock, NonCallableMock

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import EditMessageText
from aiogram.types import CallbackQuery, InaccessibleMessage, InlineKeyboardMarkup, Message, User
from pytest_mock import MockerFixture

from tests.helpers import mocked
from tgbot.config import Config
from tgbot.misc.keyboards import KeyboardManager
from tgbot.misc.tmpl_render import TmplRender
from tgbot.services.common import BaseService

__all__: tuple[str, ...] = ()

_NOT_MODIFIED_ERROR: str = (
    "Bad Request: message is not modified: specified new message content and reply markup are exactly the same"
    " as a current content and reply markup of the message"
)


@pytest.fixture
def mock_config(mocker: MockerFixture) -> Config:
    """
    Fixture to provide a mocked Config object.

    :param mocker: Pytest mocker fixture.
    :return: Mocked Config object.
    """
    return mocker.Mock(spec=Config)


@pytest.fixture
def mock_tmpl(mocker: MockerFixture) -> TmplRender:
    """
    Fixture to provide a mocked TmplRender object.

    :param mocker: Pytest mocker fixture.
    :return: Mocked TmplRender object.
    """
    return mocker.Mock(spec=TmplRender)


@pytest.fixture
def mock_kb(mocker: MockerFixture) -> KeyboardManager:
    """
    Fixture to provide a mocked KeyboardManager object.

    :param mocker: Pytest mocker fixture.
    :return: Mocked KeyboardManager object.
    """
    return mocker.Mock(spec=KeyboardManager)


@pytest.fixture
def base_service(mock_config: Config, mock_tmpl: TmplRender, mock_kb: KeyboardManager) -> BaseService:
    """
    Fixture to provide an instance of BaseService with mocked dependencies.

    :param mock_config: Mocked Config object.
    :param mock_tmpl: Mocked TmplRender object.
    :param mock_kb: Mocked KeyboardManager object.
    :return: Instance of BaseService.
    """
    return BaseService(config=mock_config, tmpl=mock_tmpl, kb=mock_kb)


@pytest.fixture
def callback_query(mocker: MockerFixture) -> CallbackQuery:
    """
    Fixture to provide a mocked CallbackQuery object with a message attribute.

    :param mocker: Pytest mocker fixture.
    :return: Mocked CallbackQuery object.
    """
    call: Mock = mocker.Mock(spec=CallbackQuery)
    call.from_user = mocker.Mock(spec=User, language_code="en")
    call.message = mocker.Mock(spec=Message)
    return call


@pytest.fixture
def message(mocker: MockerFixture) -> Message:
    """
    Fixture to provide a mocked Message object.

    :param mocker: Pytest mocker fixture.
    :return: Mocked Message object.
    """
    msg: Mock = mocker.Mock(spec=Message)
    msg.from_user = mocker.Mock(spec=User, language_code="en")
    return msg


@pytest.mark.asyncio
async def test_any_delete(
    base_service: BaseService, mock_tmpl: TmplRender, message: Message, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Test the any_delete method to ensure it deletes unsupported user content correctly.

    :param base_service: Instance of BaseService.
    :param mock_tmpl: Mocked TmplRender object.
    :param message: Mocked Message object.
    :param monkeypatch: Pytest monkeypatch fixture for patching module attributes.
    """
    # Arrange
    reply_msg: Mock = Mock(spec=Message)
    message.reply = AsyncMock(return_value=reply_msg)
    reply_msg.delete = AsyncMock()
    message.delete = AsyncMock()
    mock_tmpl.render = AsyncMock(return_value="Unsupported text")
    sleep_mock: AsyncMock = AsyncMock()
    monkeypatch.setattr(target="tgbot.services.common.sleep", name=sleep_mock)
    # Act
    await base_service.any_delete(message=message)
    # Assert
    mock_tmpl.render.assert_called_once_with(tmpl=base_service._msg_unsupported, locale="en")
    message.reply.assert_called_once_with(text="Unsupported text")
    reply_msg.delete.assert_called_once()
    message.delete.assert_called_once()
    sleep_mock.assert_called_once_with(delay=3)


@pytest.mark.asyncio
async def test_edit_or_send_callback_success(base_service: BaseService, callback_query: CallbackQuery) -> None:
    """
    Test the _edit_or_send_callback method when editing succeeds.

    :param base_service: Instance of BaseService.
    :param callback_query: Mocked CallbackQuery object.
    """
    # Arrange
    origin: NonCallableMock = mocked(callback_query.message)
    origin.edit_text = AsyncMock(return_value=Mock(spec=Message))
    callback_query.answer = AsyncMock()
    reply_markup: InlineKeyboardMarkup = InlineKeyboardMarkup(inline_keyboard=[])
    text: str = "Edited text"
    # Act
    result: Message = await base_service._edit_or_send_callback(
        call=callback_query, text=text, reply_markup=reply_markup
    )
    # Assert
    origin.edit_text.assert_called_once_with(text=text, reply_markup=reply_markup)
    callback_query.answer.assert_called_once_with()
    assert result == origin.edit_text.return_value


@pytest.mark.asyncio
async def test_edit_or_send_callback_failure(
    base_service: BaseService, mock_tmpl: TmplRender, callback_query: CallbackQuery
) -> None:
    """
    Test the _edit_or_send_callback method when editing fails due to TelegramBadRequest.

    :param base_service: Instance of BaseService.
    :param mock_tmpl: Mocked TmplRender object.
    :param callback_query: Mocked CallbackQuery object.
    """
    # Arrange
    origin: NonCallableMock = mocked(callback_query.message)
    origin.edit_text = AsyncMock(side_effect=TelegramBadRequest(method=EditMessageText(text="Test"), message="Too old"))
    origin.answer = AsyncMock(return_value=Mock(spec=Message))
    callback_query.answer = AsyncMock()
    mock_tmpl.render = AsyncMock(return_value="Expired action text")
    reply_markup: InlineKeyboardMarkup = InlineKeyboardMarkup(inline_keyboard=[])
    text: str = "New text"
    # Act
    result: Message = await base_service._edit_or_send_callback(
        call=callback_query, text=text, reply_markup=reply_markup
    )
    # Assert
    origin.edit_text.assert_called_once_with(text=text, reply_markup=reply_markup)
    mock_tmpl.render.assert_called_once_with(tmpl=base_service._msg_expired_action, locale="en")
    callback_query.answer.assert_called_once_with(text="Expired action text", show_alert=True)
    origin.answer.assert_called_once_with(text=text, reply_markup=reply_markup)
    assert result == origin.answer.return_value


# noinspection PyUnresolvedReferences
@pytest.mark.asyncio
async def test_edit_or_send_callback_same_content(
    base_service: BaseService, callback_query: CallbackQuery, mocker: MockerFixture
) -> None:
    """
    Test the _edit_or_send_callback method when editing fails due to same content.

    :param base_service: Instance of BaseService.
    :param callback_query: Mocked CallbackQuery object.
    :param mocker: Pytest mocker fixture.
    """
    # Arrange
    origin: NonCallableMock = mocked(callback_query.message)
    mocker.patch.object(
        target=origin,
        attribute="edit_text",
        side_effect=TelegramBadRequest(method=EditMessageText(text="Test"), message=_NOT_MODIFIED_ERROR),
    )
    callback_query.answer = AsyncMock()
    reply_markup: InlineKeyboardMarkup = InlineKeyboardMarkup(inline_keyboard=[])
    text: str = "Same text"
    # Act
    result: Message = await base_service._edit_or_send_callback(
        call=callback_query, text=text, reply_markup=reply_markup
    )
    # Assert
    origin.edit_text.assert_called_once_with(text=text, reply_markup=reply_markup)
    callback_query.answer.assert_called_once_with()
    origin.answer.assert_not_called()
    assert result == origin


@pytest.mark.asyncio
async def test_edit_or_send_msg_success(base_service: BaseService, message: Message) -> None:
    """
    Test the _edit_or_send_msg method when editing succeeds.

    :param base_service: Instance of BaseService.
    :param message: Mocked Message object.
    """
    # Arrange
    bot: AsyncMock = AsyncMock()
    bot.edit_message_text = AsyncMock(return_value=Mock(spec=Message))
    message.chat = Mock(id=12345)
    message.message_id = 67890
    reply_markup: InlineKeyboardMarkup = InlineKeyboardMarkup(inline_keyboard=[])
    text: str = "Edited text"
    # Act
    result: Message | None = await base_service._edit_or_send_msg(
        bot=bot, chat_id=message.chat.id, msg_id=message.message_id, text=text, reply_markup=reply_markup
    )
    # Assert
    bot.edit_message_text.assert_called_once_with(
        chat_id=message.chat.id, message_id=message.message_id, text=text, reply_markup=reply_markup
    )
    bot.send_message.assert_not_called()
    assert result == bot.edit_message_text.return_value


@pytest.mark.asyncio
async def test_edit_or_send_msg_failure(base_service: BaseService, message: Message) -> None:
    """
    Test the _edit_or_send_msg method when editing fails due to TelegramBadRequest.

    :param base_service: Instance of BaseService.
    :param message: Mocked Message object.
    """
    # Arrange
    bot: AsyncMock = AsyncMock()
    bot.edit_message_text = AsyncMock(
        side_effect=TelegramBadRequest(method=EditMessageText(text="Test"), message="Too old")
    )
    bot.send_message = AsyncMock(return_value=Mock(spec=Message))
    message.chat = Mock(id=12345)
    message.message_id = 67890
    reply_markup: InlineKeyboardMarkup = InlineKeyboardMarkup(inline_keyboard=[])
    text: str = "New text"
    # Act
    result: Message | None = await base_service._edit_or_send_msg(
        bot=bot, chat_id=message.chat.id, msg_id=message.message_id, text=text, reply_markup=reply_markup
    )
    # Assert
    bot.edit_message_text.assert_called_once_with(
        chat_id=message.chat.id, message_id=message.message_id, text=text, reply_markup=reply_markup
    )
    bot.send_message.assert_called_once_with(chat_id=message.chat.id, text=text, reply_markup=reply_markup)
    assert result == bot.send_message.return_value


@pytest.mark.asyncio
async def test_edit_or_send_msg_no_message(base_service: BaseService) -> None:
    """
    Test the _edit_or_send_msg method when Telegram answers an edit with True instead of the message.

    :param base_service: Instance of BaseService.
    """
    bot: AsyncMock = AsyncMock()
    bot.edit_message_text = AsyncMock(return_value=True)
    with pytest.raises(expected_exception=TypeError, match="returned no message"):
        await base_service._edit_or_send_msg(bot=bot, chat_id=12345, msg_id=67890, text="Text")
    bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_edit_or_send_callback_not_a_message(base_service: BaseService, callback_query: CallbackQuery) -> None:
    """
    Test the _edit_or_send_callback method when Telegram answers an edit with True: the origin is returned.

    :param base_service: Instance of BaseService.
    :param callback_query: Mocked CallbackQuery object.
    """
    origin: NonCallableMock = mocked(callback_query.message)
    origin.edit_text = AsyncMock(return_value=True)
    callback_query.answer = AsyncMock()
    result: Message = await base_service._edit_or_send_callback(call=callback_query, text="Text")
    callback_query.answer.assert_called_once_with()
    assert result == origin


@pytest.mark.asyncio
async def test_edit_or_send_callback_inaccessible(
    base_service: BaseService, mock_tmpl: TmplRender, callback_query: CallbackQuery
) -> None:
    """
    Test the _edit_or_send_callback method when the origin message is no longer accessible.

    :param base_service: Instance of BaseService.
    :param mock_tmpl: Mocked TmplRender object.
    :param callback_query: Mocked CallbackQuery object.
    """
    origin: Mock = Mock(spec=InaccessibleMessage)
    origin.answer = AsyncMock(return_value=Mock(spec=Message))
    mocked(callback_query).message = origin
    callback_query.answer = AsyncMock()
    mock_tmpl.render = AsyncMock(return_value="Expired action text")
    result: Message = await base_service._edit_or_send_callback(call=callback_query, text="Text")
    callback_query.answer.assert_called_once_with(text="Expired action text", show_alert=True)
    origin.answer.assert_called_once_with(text="Text", reply_markup=None)
    assert result == origin.answer.return_value


@pytest.mark.asyncio
async def test_edit_or_send_callback_without_message(
    base_service: BaseService, mock_tmpl: TmplRender, callback_query: CallbackQuery
) -> None:
    """
    Test the _edit_or_send_callback method when the callback has no message: the bot sends a new one.

    :param base_service: Instance of BaseService.
    :param mock_tmpl: Mocked TmplRender object.
    :param callback_query: Mocked CallbackQuery object.
    """
    bot: Mock = Mock(spec=Bot)
    bot.send_message = AsyncMock(return_value=Mock(spec=Message))
    call: NonCallableMock = mocked(callback_query)
    call.message = None
    call.bot = bot
    call.from_user.id = 12345
    call.answer = AsyncMock()
    mock_tmpl.render = AsyncMock(return_value="Expired action text")
    result: Message = await base_service._edit_or_send_callback(call=callback_query, text="Text")
    bot.send_message.assert_called_once_with(chat_id=12345, text="Text", reply_markup=None)
    assert result == bot.send_message.return_value


def test_bot_of_unbound_event(base_service: BaseService, message: Message) -> None:
    """
    Test the _bot_of method with an event that is not bound to a bot.

    :param base_service: Instance of BaseService.
    :param message: Mocked Message object.
    """
    mocked(message).bot = None
    with pytest.raises(expected_exception=RuntimeError, match="not bound to a bot"):
        base_service._bot_of(event=message)


@pytest.mark.parametrize(("language_code", "expected"), [("ru", "ru"), ("pt-br", "pt"), (None, "en"), ("", "en")])
def test_locale(base_service: BaseService, language_code: str | None, expected: str) -> None:
    """
    Test the _locale method: the language reported by Telegram cut to two characters, or the default locale.

    :param base_service: Instance of BaseService.
    :param language_code: Language code reported by Telegram.
    :param expected: Expected locale.
    """
    assert base_service._locale(user=Mock(spec=User, language_code=language_code)) == expected
    assert base_service._locale(user=None) == "en"


@pytest.mark.asyncio
async def test_edit_or_send_msg_not_modified(base_service: BaseService) -> None:
    """
    Test that _edit_or_send_msg sends no duplicate when the new content is the same as the current one.

    :param base_service: Instance of BaseService.
    """
    bot: AsyncMock = AsyncMock()
    bot.edit_message_text = AsyncMock(
        side_effect=TelegramBadRequest(method=EditMessageText(text="Test"), message=_NOT_MODIFIED_ERROR)
    )
    result: Message | None = await base_service._edit_or_send_msg(bot=bot, chat_id=12345, msg_id=67890, text="Text")
    assert result is None
    bot.send_message.assert_not_called()
