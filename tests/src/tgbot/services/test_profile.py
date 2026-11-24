"""
Unit tests for src/tgbot/services/profile.py.

Telegram objects, the renderer and the keyboards are mocks; the users table is the test PostgreSQL, the
"saved today" marks are in the test Redis.
"""

# ruff: noqa: S101, SLF001

from datetime import UTC, date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import CallbackQuery, Message, User
from pytest_mock import MockerFixture
from redis.asyncio import Redis

from tests.helpers import mocked
from tgbot.config import Config
from tgbot.db.pg_client import PostgresClient
from tgbot.db.schema import Schema
from tgbot.db.users import UserRepo
from tgbot.misc.data_types import TgUser
from tgbot.misc.keyboards import KeyboardManager
from tgbot.misc.tmpl_render import TmplRender
from tgbot.services.profile import ProfileService
from tgbot.storage.synced_users import SyncedUsers

__all__: tuple[str, ...] = ()

# The keyboards the mocked KeyboardManager returns
_PROFILE_KB: MagicMock = MagicMock(name="profile_kb")
_CONFIRM_KB: MagicMock = MagicMock(name="confirm_kb")


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
    kb.profile = AsyncMock(return_value=_PROFILE_KB)
    kb.confirm_delete = AsyncMock(return_value=_CONFIRM_KB)
    return kb


@pytest.fixture
async def users(pg_client: PostgresClient) -> UserRepo:
    """
    A UserRepo over the test PostgreSQL with an empty users table.

    :param pg_client: The test client.
    :return: The repository.
    """
    await Schema(client=pg_client).create()
    return UserRepo(db=pg_client.pool)


@pytest.fixture
def synced(redis: Redis) -> SyncedUsers:
    """
    The store of the users saved today, over the empty test Redis.

    :param redis: The test Redis client.
    :return: The store.
    """
    return SyncedUsers(redis=redis)


@pytest.fixture
def profile_svc(
    config: Config, tmpl: TmplRender, kb: KeyboardManager, pg_client: PostgresClient, synced: SyncedUsers
) -> ProfileService:
    """
    Fixture for creating ProfileService instance with mocked dependencies and the test PostgreSQL and Redis.

    :param config: Mocked Config instance.
    :param tmpl: Mocked TmplRender instance.
    :param kb: Mocked KeyboardManager instance.
    :param pg_client: The test client.
    :param synced: The store of the users saved today.
    :return: ProfileService instance.
    """
    return ProfileService(config=config, tmpl=tmpl, kb=kb, db=pg_client, synced=synced)


def _user(mocker: MockerFixture) -> User:
    """
    Builds the mocked Telegram user of the tests.

    :param mocker: pytest-mock fixture for creating mock objects.
    :return: Mocked User with ID 999, first name "Test" and language "en".
    """
    user: User = mocker.Mock(spec=User)
    user.id = 999
    user.first_name = "Test"
    user.language_code = "en"
    return user


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
    msg.from_user = _user(mocker=mocker)
    return msg


@pytest.fixture
def call(mocker: MockerFixture) -> CallbackQuery:
    """
    Fixture for mocking a CallbackQuery of a profile button.

    :param mocker: pytest-mock fixture for creating mock objects.
    :return: Mocked CallbackQuery instance.
    """
    call: CallbackQuery = mocker.Mock(spec=CallbackQuery)
    call.from_user = _user(mocker=mocker)
    return call


async def test_start(profile_svc: ProfileService, msg: Message, tmpl: TmplRender) -> None:
    """
    Test start method.

    :param profile_svc: ProfileService instance with mocked dependencies.
    :param msg: Mocked Message instance.
    :param tmpl: Mocked TmplRender instance.
    :return: None
    """
    await profile_svc.start(message=msg)
    mocked(tmpl.render).assert_called_once_with(
        tmpl=profile_svc._cmd_start, locale="en", data={"username": "Test"}, max_len=4096
    )
    mocked(msg.answer).assert_called_once_with(text="rendered_text")


async def test_help(profile_svc: ProfileService, msg: Message, tmpl: TmplRender) -> None:
    """
    Test help method: the caption of the photo is cut to Telegram's 1024-character limit of a caption.

    :param profile_svc: ProfileService instance with mocked dependencies.
    :param msg: Mocked Message instance.
    :param tmpl: Mocked TmplRender instance.
    :return: None
    """
    await profile_svc.help(message=msg)
    mocked(tmpl.render).assert_called_once_with(
        tmpl=profile_svc._cmd_help, locale="en", data={"username": "Test"}, max_len=1024
    )
    mocked(msg.answer_photo).assert_called_once_with(photo=profile_svc._bot_logo, caption="rendered_text")


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
    mocked(tmpl.render).assert_called_once_with(
        tmpl=profile_svc._cmd_start, locale="en", data={"username": ""}, max_len=4096
    )


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
    mocked(tmpl.render).assert_called_once_with(
        tmpl=profile_svc._cmd_help, locale="en", data={"username": ""}, max_len=1024
    )


async def test_profile(profile_svc: ProfileService, msg: Message, tmpl: TmplRender, users: UserRepo) -> None:
    """
    Test profile method: the name and ID from Telegram, the registration date from the users table, and the keyboard.

    :param profile_svc: ProfileService instance with mocked dependencies.
    :param msg: Mocked Message instance.
    :param tmpl: Mocked TmplRender instance.
    :param users: The repository over the test users table.
    :return: None
    """
    day: date = date(year=2026, month=1, day=2)
    await users.upsert(
        user=TgUser(
            id=999, username=None, first_name="Test", last_name=None, locale="en", registered_on=day, last_seen_on=day
        )
    )
    await profile_svc.profile(message=msg)
    mocked(tmpl.render).assert_called_once_with(
        tmpl=profile_svc._msg_profile,
        locale="en",
        data={"first_name": "Test", "user_id": 999, "registered_on": "2026-01-02"},
    )
    mocked(msg.answer).assert_called_once_with(text="rendered_text", reply_markup=_PROFILE_KB)


@pytest.mark.usefixtures("users")
async def test_profile_without_row(profile_svc: ProfileService, msg: Message, tmpl: TmplRender) -> None:
    """
    Test profile method for a user missing from the users table (e.g. the database was down): no registration date.

    :param profile_svc: ProfileService instance with mocked dependencies.
    :param msg: Mocked Message instance.
    :param tmpl: Mocked TmplRender instance.
    :return: None
    """
    await profile_svc.profile(message=msg)
    mocked(tmpl.render).assert_called_once_with(
        tmpl=profile_svc._msg_profile, locale="en", data={"first_name": "Test", "user_id": 999, "registered_on": None}
    )


async def test_profile_without_user(profile_svc: ProfileService, msg: Message, tmpl: TmplRender) -> None:
    """
    Test profile method for a message without a sender: nothing is shown.

    :param profile_svc: ProfileService instance with mocked dependencies.
    :param msg: Mocked Message instance.
    :param tmpl: Mocked TmplRender instance.
    :return: None
    """
    mocked(msg).from_user = None
    await profile_svc.profile(message=msg)
    mocked(tmpl.render).assert_not_called()
    mocked(msg.answer).assert_not_called()


async def test_delete_request(profile_svc: ProfileService, call: CallbackQuery, tmpl: TmplRender) -> None:
    """
    Test delete_request method: the profile message turns into the confirmation with the "No" / "Yes" keyboard.

    :param profile_svc: ProfileService instance with mocked dependencies.
    :param call: Mocked CallbackQuery instance.
    :param tmpl: Mocked TmplRender instance.
    :return: None
    """
    with patch.object(target=profile_svc, attribute="_edit_or_send_callback", new=AsyncMock()) as edit:
        await profile_svc.delete_request(call=call)
    mocked(tmpl.render).assert_called_once_with(tmpl=profile_svc._msg_delete_confirm, locale="en")
    edit.assert_awaited_once_with(call=call, text="rendered_text", reply_markup=_CONFIRM_KB)


@pytest.mark.usefixtures("users")
async def test_delete_cancel(profile_svc: ProfileService, call: CallbackQuery, tmpl: TmplRender) -> None:
    """
    Test delete_cancel method: the confirmation turns back into the profile.

    :param profile_svc: ProfileService instance with mocked dependencies.
    :param call: Mocked CallbackQuery instance.
    :param tmpl: Mocked TmplRender instance.
    :return: None
    """
    with patch.object(target=profile_svc, attribute="_edit_or_send_callback", new=AsyncMock()) as edit:
        await profile_svc.delete_cancel(call=call)
    mocked(tmpl.render).assert_called_once_with(
        tmpl=profile_svc._msg_profile, locale="en", data={"first_name": "Test", "user_id": 999, "registered_on": None}
    )
    edit.assert_awaited_once_with(call=call, text="rendered_text", reply_markup=_PROFILE_KB)


async def test_delete_confirm(
    profile_svc: ProfileService, call: CallbackQuery, tmpl: TmplRender, users: UserRepo, synced: SyncedUsers
) -> None:
    """
    Test delete_confirm method: the user's row and "saved today" mark are deleted, the other users stay.

    Without the mark the next update of the user creates the row again the same day.

    :param profile_svc: ProfileService instance with mocked dependencies.
    :param call: Mocked CallbackQuery instance.
    :param tmpl: Mocked TmplRender instance.
    :param users: The repository over the test users table.
    :param synced: The store of the users saved today.
    :return: None
    """
    now: datetime = datetime(year=2026, month=1, day=2, hour=12, tzinfo=UTC)
    day: date = date(year=2026, month=1, day=2)
    for user_id in (999, 1000):
        await users.upsert(
            user=TgUser(
                id=user_id,
                username=None,
                first_name="Test",
                last_name=None,
                locale="en",
                registered_on=day,
                last_seen_on=day,
            )
        )
        await synced.mark(user_id=user_id, now=now)
    with patch.object(target=profile_svc, attribute="_edit_or_send_callback", new=AsyncMock()) as edit:
        await profile_svc.delete_confirm(call=call)
    assert await users.get(user_id=999) is None
    assert await users.get(user_id=1000) is not None
    assert not await synced.is_synced(user_id=999, day=now.date())
    assert await synced.is_synced(user_id=1000, day=now.date())
    mocked(tmpl.render).assert_called_once_with(tmpl=profile_svc._msg_data_deleted, locale="en")
    edit.assert_awaited_once_with(call=call, text="rendered_text")
