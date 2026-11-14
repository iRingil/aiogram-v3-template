"""Unit tests for src/tgbot/handlers/profile.py."""

from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from pytest_mock import MockerFixture

from tests.helpers import mocked
from tgbot.handlers.profile import ProfileHandler
from tgbot.services.profile import ProfileService

__all__: tuple[str, ...] = ()


@pytest.fixture
def profile_svc(mocker: MockerFixture) -> ProfileService:
    """
    Fixture for mocking ProfileService.

    :param mocker: pytest-mock fixture for creating mock objects.
    :return: Mocked ProfileService instance.
    """
    svc: ProfileService = mocker.Mock(spec=ProfileService)
    svc.start = AsyncMock()
    svc.help = AsyncMock()
    return svc


@pytest.fixture
def profile_hdlr(profile_svc: ProfileService) -> ProfileHandler:
    """
    Fixture for creating ProfileHandler instance with mocked service.

    :param profile_svc: Mocked ProfileService instance.
    :return: ProfileHandler instance.
    """
    hdlr: ProfileHandler = ProfileHandler(service=profile_svc)
    return hdlr


@pytest.fixture
def msg(mocker: MockerFixture) -> Message:
    """
    Fixture for mocking Message object.

    :param mocker: pytest-mock fixture for creating mock objects.
    :return: Mocked Message instance.
    """
    msg: Message = mocker.Mock(spec=Message)
    msg.delete = AsyncMock()
    return msg


@pytest.fixture
def fsm_context(mocker: MockerFixture) -> FSMContext:
    """
    Fixture for mocking FSMContext.

    :param mocker: pytest-mock fixture for creating mock objects.
    :return: Mocked FSMContext instance.
    """
    context: FSMContext = mocker.Mock(spec=FSMContext)
    context.clear = AsyncMock()
    return context


# noinspection PyUnresolvedReferences
@pytest.mark.asyncio
async def test_cmd_start(
    profile_hdlr: ProfileHandler, msg: Message, fsm_context: FSMContext, profile_svc: ProfileService
) -> None:
    """
    Test cmd_start handler.

    :param profile_hdlr: ProfileHandler instance with mocked service.
    :param msg: Mocked Message instance.
    :param fsm_context: Mocked FSMContext instance.
    :param profile_svc: Mocked ProfileService instance.
    :return: None
    """
    # Act
    await profile_hdlr.cmd_start(message=msg, state=fsm_context)
    # Assert
    mocked(fsm_context.clear).assert_called_once()
    mocked(msg.delete).assert_called_once()
    mocked(profile_svc.start).assert_called_once_with(message=msg)


# noinspection PyUnresolvedReferences
@pytest.mark.asyncio
async def test_cmd_help(profile_hdlr: ProfileHandler, msg: Message, profile_svc: ProfileService) -> None:
    """
    Test cmd_help handler.

    :param profile_hdlr: ProfileHandler instance with mocked service.
    :param msg: Mocked Message instance.
    :param profile_svc: Mocked ProfileService instance.
    :return: None
    """
    # Act
    await profile_hdlr.cmd_help(message=msg)
    # Assert
    mocked(msg.delete).assert_called_once()
    mocked(profile_svc.help).assert_called_once_with(message=msg)
