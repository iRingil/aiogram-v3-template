"""
Unit tests for src/tgbot/misc/middlewares.py (AntiFloodMiddleware and UserSyncMiddleware).

AntiFloodMiddleware keeps its windows in the test Redis; its clock (middlewares.time) is replaced with _FakeClock,
which tests advance explicitly. The wrapped handler is a scripted async spy (_HandlerSpy) rather than a mock.
UserSyncMiddleware gets a fake UTC date, writes to the test PostgreSQL and keeps its marks in the test Redis.
"""

# ruff: noqa: PLR2004, S101, SLF001

from asyncio import sleep
from datetime import UTC, date, datetime, time
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import Chat, TelegramObject, User
from asyncpg import PostgresError
from redis.asyncio import Redis

from tgbot.db.pg_client import PostgresClient
from tgbot.db.schema import Schema
from tgbot.db.users import UserRepo
from tgbot.misc import middlewares
from tgbot.misc.data_types import TgUser
from tgbot.misc.middlewares import AntiFloodMiddleware, UserSyncMiddleware
from tgbot.storage.synced_users import SyncedUsers

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

__all__: tuple[str, ...] = ()

# A bare TelegramObject stand-in - the middleware never inspects the event itself, only data.
_EVENT: TelegramObject = TelegramObject()


class _FakeClock:
    """A controllable stand-in for time.time, advanced explicitly by tests."""

    def __init__(self, start: float = 1_000_000.0) -> None:
        """
        Sets the initial fake time.

        :param start: Time value returned before advance() is ever called.
        """
        self.now: float = start

    def __call__(self) -> float:
        """:return: The current fake time."""
        return self.now

    def advance(self, delta: float) -> None:
        """
        Moves the fake clock forward.

        :param delta: Seconds to add to the current fake time.
        :return: None
        """
        self.now += delta


class _HandlerSpy:
    """An async callable standing in for the wrapped handler, recording every call and returning a fixed result."""

    def __init__(self, result: object = "handled") -> None:
        """
        Sets the value every call returns.

        :param result: Value __call__ returns every time it's invoked.
        """
        self._result: Any = result
        self.calls: list[tuple[Any, dict[str, Any]]] = []

    async def __call__(self, event: object, data: dict[str, object]) -> object:
        """
        Records the call, then returns the scripted result.

        :param event: The event the middleware forwarded.
        :param data: The contextual data dict the middleware forwarded.
        :return: The scripted result.
        """
        self.calls.append((event, data))
        return self._result


def _user_data(user_id: int | None) -> dict[str, Any]:
    """
    Builds a data dict as the middleware would receive it from earlier middlewares.

    :param user_id: ID of the aiogram User to put in "event_from_user", or None to omit the key
        entirely, simulating an event with no resolvable user.
    :return: A data dict suitable for passing to AntiFloodMiddleware.__call__.
    """
    if user_id is None:
        return {}
    return {"event_from_user": User(id=user_id, is_bot=False, first_name="Test")}


@pytest.fixture(name="clock")
def clock_fixture(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    """
    Replaces middlewares.time with a controllable fake clock.

    :param monkeypatch: pytest fixture used to patch middlewares.time.
    :return: The _FakeClock instance the middleware under test will read time from.
    """
    clock: _FakeClock = _FakeClock()
    monkeypatch.setattr(target=middlewares, name="time", value=clock)
    return clock


@pytest.fixture(name="handler")
def handler_fixture() -> _HandlerSpy:
    """
    A fresh handler spy for each test.

    :return: A _HandlerSpy returning "handled" and recording every call.
    """
    return _HandlerSpy()


@pytest.fixture(name="middleware")
def middleware_fixture(redis: Redis) -> AntiFloodMiddleware:
    """
    An AntiFloodMiddleware over the empty test Redis.

    :param redis: The test Redis client.
    :return: The AntiFloodMiddleware instance under test.
    """
    return AntiFloodMiddleware(redis=redis)


class TestNoResolvableUser:
    """Tests the middleware's behavior when data has no "event_from_user" to key the rate limit by."""

    async def test_calls_the_handler_regardless_of_call_count(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy, redis: Redis
    ) -> None:
        """
        Without a user to track, every call is let through unconditionally and nothing is written to Redis.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :param redis: The test Redis client.
        :return: None
        """
        data: dict[str, Any] = _user_data(user_id=None)
        for _ in range(AntiFloodMiddleware._limit + 5):
            result: Any = await middleware(handler=handler, event=_EVENT, data=data)
            assert result == "handled"
        assert len(handler.calls) == AntiFloodMiddleware._limit + 5
        assert await redis.dbsize() == 0


class TestWithinLimit:
    """Tests calls that stay within the configured limit inside the sliding window."""

    async def test_allows_every_call_up_to_the_limit(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy
    ) -> None:
        """
        Every call up to and including the limit-th is passed through to the handler.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :return: None
        """
        data: dict[str, Any] = _user_data(user_id=1)
        for _ in range(AntiFloodMiddleware._limit):
            result: Any = await middleware(handler=handler, event=_EVENT, data=data)
            assert result == "handled"
        assert len(handler.calls) == AntiFloodMiddleware._limit

    async def test_tracks_separate_users_independently(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy
    ) -> None:
        """
        Using up one user's limit doesn't affect a different user's own limit.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :return: None
        """
        limit: int = AntiFloodMiddleware._limit
        for _ in range(limit):
            await middleware(handler=handler, event=_EVENT, data=_user_data(user_id=1))
        result: Any = await middleware(handler=handler, event=_EVENT, data=_user_data(user_id=2))
        assert result == "handled"
        assert len(handler.calls) == limit + 1

    async def test_forwards_event_and_data_unchanged(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy
    ) -> None:
        """
        The exact event and data objects reach the handler, not copies.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :return: None
        """
        event: TelegramObject = TelegramObject()
        data: dict[str, Any] = _user_data(user_id=1)
        await middleware(handler=handler, event=event, data=data)
        called_event, called_data = handler.calls[0]
        assert called_event is event
        assert called_data is data


class TestExceedsLimit:
    """Tests calls that exceed the configured limit inside the sliding window."""

    async def test_drops_the_call_past_the_limit(self, middleware: AntiFloodMiddleware, handler: _HandlerSpy) -> None:
        """
        The call right after the limit is reached is dropped: the handler isn't called and None is returned.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :return: None
        """
        data: dict[str, Any] = _user_data(user_id=1)
        limit: int = AntiFloodMiddleware._limit
        for _ in range(limit):
            await middleware(handler=handler, event=_EVENT, data=data)
        result: Any = await middleware(handler=handler, event=_EVENT, data=data)
        assert result is None
        assert len(handler.calls) == limit

    async def test_dropped_calls_dont_count_towards_future_allowance(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy, redis: Redis
    ) -> None:
        """
        Repeated calls past the limit stay dropped - a dropped call isn't itself kept in the window.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :param redis: The test Redis client.
        :return: None
        """
        data: dict[str, Any] = _user_data(user_id=1)
        limit: int = AntiFloodMiddleware._limit
        for _ in range(limit):
            await middleware(handler=handler, event=_EVENT, data=data)
        for _ in range(5):
            result: Any = await middleware(handler=handler, event=_EVENT, data=data)
            assert result is None
        assert len(handler.calls) == limit
        assert await redis.zcard(name="tgbot_flood:1") == limit

    async def test_window_is_shared_between_instances(self, redis: Redis, handler: _HandlerSpy) -> None:
        """
        Two middleware instances over the same Redis (two bot processes) count the same window.

        :param redis: The test Redis client.
        :param handler: The handler spy fixture.
        :return: None
        """
        first: AntiFloodMiddleware = AntiFloodMiddleware(redis=redis)
        second: AntiFloodMiddleware = AntiFloodMiddleware(redis=redis)
        data: dict[str, Any] = _user_data(user_id=1)
        for _ in range(AntiFloodMiddleware._limit):
            await first(handler=handler, event=_EVENT, data=data)
        assert await second(handler=handler, event=_EVENT, data=data) is None

    async def test_zcard_of_another_type_is_an_error(self, handler: _HandlerSpy) -> None:
        """
        A ZCARD result other than an integer fails loudly instead of letting the update through.

        :param handler: The handler spy fixture.
        :return: None
        """
        pipe: MagicMock = MagicMock()
        pipe.execute = AsyncMock(return_value=[0, 1, "1", True])
        redis: MagicMock = MagicMock()
        redis.pipeline.return_value.__aenter__ = AsyncMock(return_value=pipe)
        redis.pipeline.return_value.__aexit__ = AsyncMock(return_value=None)
        with pytest.raises(expected_exception=TypeError, match="Redis returned str for ZCARD"):
            await AntiFloodMiddleware(redis=redis)(handler=handler, event=_EVENT, data=_user_data(user_id=1))
        assert handler.calls == []


class TestWindowExpiry:
    """Tests that a throttled user is let through again once old updates age out, and that Redis forgets them."""

    async def test_still_blocked_exactly_at_the_window_boundary(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy, clock: _FakeClock
    ) -> None:
        """
        The oldest update is only dropped once it's strictly older than the window, not merely as old as it.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :param clock: The fake clock fixture, advanced to exactly the window's length.
        :return: None
        """
        data: dict[str, Any] = _user_data(user_id=1)
        limit: int = AntiFloodMiddleware._limit
        for _ in range(limit):
            await middleware(handler=handler, event=_EVENT, data=data)
        clock.advance(delta=AntiFloodMiddleware._period)
        result: Any = await middleware(handler=handler, event=_EVENT, data=data)
        assert result is None
        assert len(handler.calls) == limit

    async def test_allows_one_more_once_the_oldest_hit_falls_out_of_the_window(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy, clock: _FakeClock
    ) -> None:
        """
        Once enough time passes for the oldest recorded update to age out, a new call is let through again.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :param clock: The fake clock fixture, advanced past the window's length.
        :return: None
        """
        data: dict[str, Any] = _user_data(user_id=1)
        limit: int = AntiFloodMiddleware._limit
        for _ in range(limit):
            await middleware(handler=handler, event=_EVENT, data=data)
        clock.advance(delta=AntiFloodMiddleware._period + 0.001)
        result: Any = await middleware(handler=handler, event=_EVENT, data=data)
        assert result == "handled"
        assert len(handler.calls) == limit + 1

    async def test_immediately_throttled_again_after_the_single_slot_is_used(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy, clock: _FakeClock
    ) -> None:
        """
        The slot freed by one aged-out update only lets a single new call through before throttling resumes.

        Updates are staggered by a tiny step so they age out one at a time, not all together.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :param clock: The fake clock fixture, advanced just past the point where only the very
            first update has aged out of the window.
        :return: None
        """
        data: dict[str, Any] = _user_data(user_id=1)
        limit: int = AntiFloodMiddleware._limit
        start: float = clock.now
        step: float = 0.01
        for i in range(limit):
            clock.now = start + i * step
            await middleware(handler=handler, event=_EVENT, data=data)
        clock.now = start + AntiFloodMiddleware._period + step / 2  # only the first update is older than the window
        await middleware(handler=handler, event=_EVENT, data=data)
        result: Any = await middleware(handler=handler, event=_EVENT, data=data)
        assert result is None
        assert len(handler.calls) == limit + 1

    async def test_redis_expires_the_window(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy, redis: Redis
    ) -> None:
        """
        The window key expires one window after the last update, so Redis removes a user who stopped writing.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :param redis: The test Redis client.
        :return: None
        """
        await middleware(handler=handler, event=_EVENT, data=_user_data(user_id=1))
        assert 0 < await redis.pttl(name="tgbot_flood:1") <= AntiFloodMiddleware._period * 1000


# region UserSyncMiddleware
_DAY_1: date = date(year=2026, month=1, day=1)
_DAY_2: date = date(year=2026, month=1, day=2)
_PRIVATE_CHAT: Chat = Chat(id=7, type="private")


class _FakeToday:
    """A stand-in for middlewares.datetime whose now() is noon (UTC) of a date the test sets."""

    def __init__(self, today: date) -> None:
        """
        Sets the date now() reports.

        :param today: The current UTC date.
        """
        self.today: date = today

    def now(self, tz: object) -> datetime:
        """
        Returns noon of the current fake date.

        :param tz: Time zone the middleware asks for; always UTC.
        :return: The fake current time.
        """
        del tz
        return datetime.combine(date=self.today, time=time(hour=12), tzinfo=UTC)


@pytest.fixture(name="today")
def today_fixture(monkeypatch: pytest.MonkeyPatch) -> _FakeToday:
    """
    Replaces middlewares.datetime with a fake clock starting on _DAY_1.

    :param monkeypatch: pytest fixture used to patch middlewares.datetime.
    :return: The fake clock.
    """
    today: _FakeToday = _FakeToday(today=_DAY_1)
    monkeypatch.setattr(target=middlewares, name="datetime", value=today)
    return today


@pytest.fixture(name="users")
async def users_fixture(pg_client: PostgresClient) -> UserRepo:
    """
    A UserRepo over the test PostgreSQL with an empty users table, to check what the middleware wrote.

    :param pg_client: The test client.
    :return: The repository.
    """
    await Schema(client=pg_client).create()
    return UserRepo(db=pg_client.pool)


@pytest.fixture(name="synced")
def synced_fixture(redis: Redis) -> SyncedUsers:
    """
    The store of the users saved today, over the empty test Redis.

    :param redis: The test Redis client.
    :return: The store.
    """
    return SyncedUsers(redis=redis)


@pytest.fixture(name="sync")
def sync_fixture(today: _FakeToday, pg_client: PostgresClient, synced: SyncedUsers) -> UserSyncMiddleware:
    """
    A UserSyncMiddleware over the test PostgreSQL and Redis, running on the fake date.

    :param today: The fake clock the middleware reads the date from.
    :param pg_client: The test client.
    :param synced: The store of the users saved today.
    :return: The UserSyncMiddleware instance under test.
    """
    del today
    return UserSyncMiddleware(client=pg_client, synced=synced)


def _tg_user(
    language_code: str | None = "en",
    first_name: str = "Ann",
    last_name: str | None = "Lee",
    username: str | None = "ann",
) -> dict[str, Any]:
    """
    Builds a data dict with a full Telegram user writing in a private chat.

    :param language_code: The language code Telegram reports.
    :param first_name: The first name Telegram reports.
    :param last_name: The last name Telegram reports.
    :param username: The username Telegram reports.
    :return: A data dict with "event_from_user" and "event_chat".
    """
    return {
        "event_from_user": User(
            id=7,
            is_bot=False,
            first_name=first_name,
            last_name=last_name,
            username=username,
            language_code=language_code,
        ),
        "event_chat": _PRIVATE_CHAT,
    }


class TestUserSync:
    """Tests UserSyncMiddleware: one upsert per user per UTC day, never blocking the handler."""

    async def test_first_update_saves_the_user(
        self, sync: UserSyncMiddleware, users: UserRepo, handler: _HandlerSpy
    ) -> None:
        """
        The first update of the day saves the user with today as both dates, then calls the handler.

        :param sync: The UserSyncMiddleware fixture.
        :param users: The repository to check the table.
        :param handler: The handler spy fixture.
        :return: None
        """
        assert await sync(handler=handler, event=_EVENT, data=_tg_user()) == "handled"
        assert await users.get(user_id=7) == TgUser(
            id=7,
            username="ann",
            first_name="Ann",
            last_name="Lee",
            locale="en",
            registered_on=_DAY_1,
            last_seen_on=_DAY_1,
        )

    async def test_same_day_skips_the_database(
        self, sync: UserSyncMiddleware, users: UserRepo, handler: _HandlerSpy
    ) -> None:
        """
        Later updates of the same day don't touch the database: a row deleted meanwhile is not written again.

        :param sync: The UserSyncMiddleware fixture.
        :param users: The repository to check the table.
        :param handler: The handler spy fixture.
        :return: None
        """
        await sync(handler=handler, event=_EVENT, data=_tg_user())
        await users.delete(user_id=7)
        await sync(handler=handler, event=_EVENT, data=_tg_user())
        assert await users.get(user_id=7) is None
        assert len(handler.calls) == 2

    async def test_new_day_saves_again(
        self, sync: UserSyncMiddleware, users: UserRepo, handler: _HandlerSpy, today: _FakeToday
    ) -> None:
        """
        On a new UTC day the user is saved once more: last_seen_on moves, registered_on stays.

        :param sync: The UserSyncMiddleware fixture.
        :param users: The repository to check the table.
        :param handler: The handler spy fixture.
        :param today: The fake clock.
        :return: None
        """
        await sync(handler=handler, event=_EVENT, data=_tg_user())
        today.today = _DAY_2
        await sync(handler=handler, event=_EVENT, data=_tg_user(first_name="Anna"))
        user: TgUser | None = await users.get(user_id=7)
        assert user is not None
        assert (user.first_name, user.registered_on, user.last_seen_on) == ("Anna", _DAY_1, _DAY_2)

    @pytest.mark.parametrize(("language_code", "locale"), [("pt-br", "pt"), ("en", "en"), (None, None), ("", None)])
    async def test_locale_is_cut_to_two_characters(
        self,
        sync: UserSyncMiddleware,
        users: UserRepo,
        handler: _HandlerSpy,
        language_code: str | None,
        locale: str | None,
    ) -> None:
        """
        The language code is cut to its first two characters; a missing or empty one is stored as NULL.

        :param sync: The UserSyncMiddleware fixture.
        :param users: The repository to check the table.
        :param handler: The handler spy fixture.
        :param language_code: The language code Telegram reports.
        :param locale: The locale expected in the database.
        :return: None
        """
        await sync(handler=handler, event=_EVENT, data=_tg_user(language_code=language_code))
        user: TgUser | None = await users.get(user_id=7)
        assert user is not None
        assert user.locale == locale

    async def test_text_fields_are_cut_to_column_sizes(
        self, sync: UserSyncMiddleware, users: UserRepo, handler: _HandlerSpy
    ) -> None:
        """
        Username, first and last name longer than their columns are cut to 32, 64 and 64 characters and saved.

        :param sync: The UserSyncMiddleware fixture.
        :param users: The repository to check the table.
        :param handler: The handler spy fixture.
        :return: None
        """
        data: dict[str, Any] = _tg_user(first_name="f" * 70, last_name="l" * 70, username="u" * 40)
        await sync(handler=handler, event=_EVENT, data=data)
        user: TgUser | None = await users.get(user_id=7)
        assert user is not None
        assert (user.first_name, user.last_name, user.username) == ("f" * 64, "l" * 64, "u" * 32)

    async def test_missing_optional_fields_are_null(
        self, sync: UserSyncMiddleware, users: UserRepo, handler: _HandlerSpy
    ) -> None:
        """
        A user without a last name or a username is stored with NULL in those columns.

        :param sync: The UserSyncMiddleware fixture.
        :param users: The repository to check the table.
        :param handler: The handler spy fixture.
        :return: None
        """
        await sync(handler=handler, event=_EVENT, data=_tg_user(last_name=None, username=None))
        user: TgUser | None = await users.get(user_id=7)
        assert user is not None
        assert (user.last_name, user.username) == (None, None)

    @pytest.mark.parametrize(
        "data",
        [
            {},
            {"event_from_user": User(id=7, is_bot=True, first_name="Bot"), "event_chat": _PRIVATE_CHAT},
            {"event_from_user": User(id=7, is_bot=False, first_name="Ann")},
            {"event_from_user": User(id=7, is_bot=False, first_name="Ann"), "event_chat": Chat(id=-1, type="group")},
        ],
        ids=["no user", "bot", "no chat", "group chat"],
    )
    async def test_skips_the_database(
        self, sync: UserSyncMiddleware, users: UserRepo, handler: _HandlerSpy, data: dict[str, Any]
    ) -> None:
        """
        Updates without a user or chat, from a bot or a non-private chat skip the database write.

        :param sync: The UserSyncMiddleware fixture.
        :param users: The repository to check the table.
        :param handler: The handler spy fixture.
        :param data: The data dict of the update.
        :return: None
        """
        assert await sync(handler=handler, event=_EVENT, data=data) == "handled"
        assert await users.get(user_id=7) is None

    async def test_database_error_is_logged_and_retried(
        self, sync: UserSyncMiddleware, users: UserRepo, handler: _HandlerSpy
    ) -> None:
        """
        A database error is logged, the handler still runs, and the next update retries the upsert.

        The error is simulated: the first upsert raises, the second one goes to the test database.

        :param sync: The UserSyncMiddleware fixture.
        :param users: The repository to check the table.
        :param handler: The handler spy fixture.
        :return: None
        """
        real_upsert: Callable[..., Awaitable[None]] = UserRepo.upsert
        calls: list[int] = []

        async def failing_once(repo: UserRepo, *, user: TgUser) -> None:
            """
            Raises on the first call, then saves the user for real.

            :param repo: The repository.
            :param user: The user to save.
            :return: None
            """
            calls.append(user.id)
            if len(calls) == 1:
                raise PostgresError("down")
            await real_upsert(repo, user=user)

        with (
            patch.object(target=UserRepo, attribute="upsert", new=failing_once),
            patch(target="tgbot.misc.middlewares.logger") as mock_logger,
        ):
            assert await sync(handler=handler, event=_EVENT, data=_tg_user()) == "handled"
            mock_logger.error.assert_called_once()
            assert await users.get(user_id=7) is None
            await sync(handler=handler, event=_EVENT, data=_tg_user())
        assert await users.get(user_id=7) is not None
        assert len(handler.calls) == 2

    async def test_deleted_user_is_saved_again_the_same_day(
        self, sync: UserSyncMiddleware, users: UserRepo, handler: _HandlerSpy, synced: SyncedUsers
    ) -> None:
        """
        After the user's data is deleted (the row and the "saved today" mark), the next update creates the row again.

        :param sync: The UserSyncMiddleware fixture.
        :param users: The repository to check the table.
        :param handler: The handler spy fixture.
        :param synced: The store of the users saved today.
        :return: None
        """
        await sync(handler=handler, event=_EVENT, data=_tg_user())
        await users.delete(user_id=7)
        await synced.forget(user_id=7)
        await sync(handler=handler, event=_EVENT, data=_tg_user())
        assert await users.get(user_id=7) is not None

    async def test_mark_is_shared_between_instances(
        self,
        sync: UserSyncMiddleware,
        users: UserRepo,
        handler: _HandlerSpy,
        pg_client: PostgresClient,
        synced: SyncedUsers,
    ) -> None:
        """
        A user saved by one middleware instance (one bot process) is not saved again by another the same day.

        :param sync: The UserSyncMiddleware fixture.
        :param users: The repository to check the table.
        :param handler: The handler spy fixture.
        :param pg_client: The test client.
        :param synced: The store of the users saved today.
        :return: None
        """
        await sync(handler=handler, event=_EVENT, data=_tg_user())
        await users.delete(user_id=7)
        other: UserSyncMiddleware = UserSyncMiddleware(client=pg_client, synced=synced)
        await other(handler=handler, event=_EVENT, data=_tg_user())
        assert await users.get(user_id=7) is None

    async def test_slow_database_is_given_up(
        self, sync: UserSyncMiddleware, users: UserRepo, handler: _HandlerSpy, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        An upsert slower than the time limit is given up and logged; the handler runs without waiting for it.

        :param sync: The UserSyncMiddleware fixture.
        :param users: The repository to check the table.
        :param handler: The handler spy fixture.
        :param monkeypatch: pytest fixture used to shorten the time limit.
        :return: None
        """

        async def hanging(repo: UserRepo, *, user: TgUser) -> None:
            """
            Stands in for an upsert on a database that doesn't answer.

            :param repo: The repository.
            :param user: The user to save.
            :return: None
            """
            del repo, user
            await sleep(delay=10)

        monkeypatch.setattr(target=sync, name="_timeout", value=0.05)
        with (
            patch.object(target=UserRepo, attribute="upsert", new=hanging),
            patch(target="tgbot.misc.middlewares.logger") as mock_logger,
        ):
            assert await sync(handler=handler, event=_EVENT, data=_tg_user()) == "handled"
        mock_logger.error.assert_called_once()
        assert "TimeoutError" in mock_logger.error.call_args.args[0]
        assert await users.get(user_id=7) is None


# endregion
