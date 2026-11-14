"""Unit tests for src/tgbot/services/profile.py."""

# ruff: noqa: SLF001

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Message, User
from pytest_mock import MockerFixture

from tests.helpers import mocked
from tgbot.config import Config
from tgbot.misc.keyboards import KeyboardManager
from tgbot.misc.tmpl_render import TmplRender
from tgbot.services.profile import ProfileService

__all__: tuple[str, ...] = ()


@pytest.fixture
def config(mocker: MockerFixture) -> Config:
    """
    Fixture for mocking Config.

    :param mocker: pytest-mock fixture for creating mock objects.
    :return: Mocked Config instance.
    """
    cfg: Config = mocker.Mock(spec=Config)
    cfg.paths.bot_logo = Path("path/to/logo.jpg")
    return cfg


@pytest.fixture
def tmpl(mocker: MockerFixture) -> TmplRender:
    """
    Fixture for mocking TmplRender.

    :param mocker: pytest-mock fixture for creating mock objects.
    :return: Mocked TmplRender instance.
    """
    tmpl: TmplRender = mocker.Mock(spec=TmplRender)
    tmpl.render = AsyncMock(return_value="rendered_text")
    return tmpl


@pytest.fixture
def kb(mocker: MockerFixture) -> KeyboardManager:
    """
    Fixture for mocking KeyboardManager.

    :param mocker: pytest-mock fixture for creating mock objects.
    :return: Mocked KeyboardManager instance.
    """
    kb: KeyboardManager = mocker.Mock(spec=KeyboardManager)
    return kb


@pytest.fixture
def profile_svc(config: Config, tmpl: TmplRender, kb: KeyboardManager) -> ProfileService:
    """
    Fixture for creating ProfileService instance with mocked dependencies.

    :param config: Mocked Config instance.
    :param tmpl: Mocked TmplRender instance.
    :param kb: Mocked KeyboardManager instance.
    :return: Mocked ProfileService instance.
    """
    svc: ProfileService = ProfileService(config=config, tmpl=tmpl, kb=kb)
    return svc


@pytest.fixture
def msg(mocker: MockerFixture) -> Message:
    """
    Fixture for mocking Message object.

    :param mocker: pytest-mock fixture for creating mock objects.
    :return: Mocked Message instance.
    """
    msg: Message = mocker.Mock(spec=Message)
    msg.answer = AsyncMock()
    msg.answer_photo = AsyncMock()
    msg.from_user = mocker.Mock(spec=User)
    msg.from_user.id = 999
    msg.from_user.first_name = "Test"
    msg.from_user.last_name = None
    msg.from_user.username = "testuser"
    msg.from_user.language_code = "en"
    return msg


# noinspection PyUnresolvedReferences
@pytest.mark.asyncio
async def test_start(profile_svc: ProfileService, msg: Message, tmpl: TmplRender) -> None:
    """
    Test start method.

    :param profile_svc: ProfileService instance with mocked dependencies.
    :param msg: Mocked Message instance.
    :param tmpl: Mocked TmplRender instance.
    :return: None
    """
    # Act
    await profile_svc.start(message=msg)
    # Assert
    mocked(tmpl.render).assert_called_once_with(tmpl=profile_svc._cmd_start, locale="en", data={"username": "Test"})
    mocked(msg.answer).assert_called_once_with(text="rendered_text")


# noinspection PyUnresolvedReferences
@pytest.mark.asyncio
async def test_help(profile_svc: ProfileService, msg: Message, tmpl: TmplRender) -> None:
    """
    Test help method.

    :param profile_svc: ProfileService instance with mocked dependencies.
    :param msg: Mocked Message instance.
    :param tmpl: Mocked TmplRender instance.
    :return: None
    """
    # Act
    await profile_svc.help(message=msg)
    # Assert
    mocked(tmpl.render).assert_called_once_with(tmpl=profile_svc._cmd_help, locale="en", data={"username": "Test"})
    mocked(msg.answer_photo).assert_called_once_with(photo=profile_svc._bot_logo, caption="rendered_text")


@pytest.mark.asyncio
async def test_start_without_user(profile_svc: ProfileService, msg: Message, tmpl: TmplRender) -> None:
    """
    Test start method for a message without a sender: the default locale and an empty name are used.

    :param profile_svc: ProfileService instance with mocked dependencies.
    :param msg: Mocked Message instance.
    :param tmpl: Mocked TmplRender instance.
    :return: None
    """
    mocked(msg).from_user = None
    await profile_svc.start(message=msg)
    mocked(tmpl.render).assert_called_once_with(tmpl=profile_svc._cmd_start, locale="en", data={"username": ""})


@pytest.mark.asyncio
async def test_help_without_user(profile_svc: ProfileService, msg: Message, tmpl: TmplRender) -> None:
    """
    Test help method for a message without a sender: the default locale and an empty name are used.

    :param profile_svc: ProfileService instance with mocked dependencies.
    :param msg: Mocked Message instance.
    :param tmpl: Mocked TmplRender instance.
    :return: None
    """
    mocked(msg).from_user = None
    await profile_svc.help(message=msg)
    mocked(tmpl.render).assert_called_once_with(tmpl=profile_svc._cmd_help, locale="en", data={"username": ""})
