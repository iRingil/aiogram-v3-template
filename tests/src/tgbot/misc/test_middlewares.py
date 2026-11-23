"""
Unit tests for src/tgbot/misc/middlewares.py (AntiFloodMiddleware and UserSyncMiddleware).

The middleware's only real dependency is time.monotonic - replaced here with _FakeClock, a
controllable stand-in tests advance explicitly. The wrapped handler is a scripted async spy
(_HandlerSpy) rather than a mock, since it has no real external dependency of its own either.
UserSyncMiddleware gets a fake UTC date and a mocked UserRepo.
"""

# ruff: noqa: PLR2004, S101, SLF001

from collections.abc import Iterator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.types import TelegramObject, User
from asyncpg import PostgresError

from tgbot.misc import middlewares
from tgbot.misc.data_types import TgUser
from tgbot.misc.middlewares import AntiFloodMiddleware, UserSyncMiddleware

__all__: tuple[str, ...] = ()

# A bare TelegramObject stand-in - the middleware never inspects the event itself, only data.
_EVENT: TelegramObject = TelegramObject()


class _FakeClock:
    """A controllable stand-in for time.monotonic, advanced explicitly by tests."""

    def __init__(self, start: float = 0.0) -> None:
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
    Replaces middlewares.monotonic with a controllable fake clock starting at 0.0.

    :param monkeypatch: pytest fixture used to patch middlewares.monotonic.
    :return: The _FakeClock instance the middleware under test will read time from.
    """
    clock: _FakeClock = _FakeClock()
    monkeypatch.setattr(target=middlewares, name="monotonic", value=clock)
    return clock


@pytest.fixture(name="handler")
def handler_fixture() -> _HandlerSpy:
    """
    A fresh handler spy for each test.

    :return: A _HandlerSpy returning "handled" and recording every call.
    """
    return _HandlerSpy()


@pytest.fixture(name="middleware")
def middleware_fixture() -> AntiFloodMiddleware:
    """
    A fresh AntiFloodMiddleware instance, with its own empty per-user hit history.

    :return: The AntiFloodMiddleware instance under test.
    """
    return AntiFloodMiddleware()


class TestNoResolvableUser:
    """Tests the middleware's behavior when data has no "event_from_user" to key the rate limit by."""

    @pytest.mark.usefixtures("clock")
    async def test_calls_the_handler_regardless_of_call_count(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy
    ) -> None:
        """
        Without a user to track, every call is let through unconditionally, even past the normal limit.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :return: None
        """
        data: dict[str, Any] = _user_data(user_id=None)
        for _ in range(AntiFloodMiddleware._limit + 5):
            result: Any = await middleware(handler=handler, event=_EVENT, data=data)
            assert result == "handled"
        assert len(handler.calls) == AntiFloodMiddleware._limit + 5


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
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy
    ) -> None:
        """
        Repeated calls past the limit stay dropped - a dropped call isn't itself recorded as a hit.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
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


class TestSlidingWindowExpiry:
    """Tests that a throttled user is let through again once old hits age out of the window."""

    async def test_still_blocked_exactly_at_the_window_boundary(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy, clock: _FakeClock
    ) -> None:
        """
        The oldest hit is only dropped once it's strictly older than the window, not merely as old as it.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :param clock: The fake clock fixture, advanced to exactly the window's length.
        :return: None
        """
        data: dict[str, Any] = _user_data(user_id=1)
        limit: int = AntiFloodMiddleware._limit
        period: float = AntiFloodMiddleware._period
        for _ in range(limit):
            await middleware(handler=handler, event=_EVENT, data=data)
        clock.advance(delta=period)
        result: Any = await middleware(handler=handler, event=_EVENT, data=data)
        assert result is None
        assert len(handler.calls) == limit

    async def test_allows_one_more_once_the_oldest_hit_falls_out_of_the_window(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy, clock: _FakeClock
    ) -> None:
        """
        Once enough time passes for the oldest recorded hit to age out, a new call is let through again.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :param clock: The fake clock fixture, advanced past the window's length.
        :return: None
        """
        data: dict[str, Any] = _user_data(user_id=1)
        limit: int = AntiFloodMiddleware._limit
        period: float = AntiFloodMiddleware._period
        for _ in range(limit):
            await middleware(handler=handler, event=_EVENT, data=data)
        clock.advance(delta=period + 0.001)
        result: Any = await middleware(handler=handler, event=_EVENT, data=data)
        assert result == "handled"
        assert len(handler.calls) == limit + 1

    async def test_immediately_throttled_again_after_the_single_slot_is_used(
        self, middleware: AntiFloodMiddleware, handler: _HandlerSpy, clock: _FakeClock
    ) -> None:
        """
        The slot freed by one aged-out hit only lets a single new call through before throttling resumes.

        Hits are staggered by a tiny step so they age out one at a time, not all together.

        :param middleware: The AntiFloodMiddleware fixture.
        :param handler: The handler spy fixture.
        :param clock: The fake clock fixture, advanced just past the point where only the very
            first hit has aged out of the window.
        :return: None
        """
        data: dict[str, Any] = _user_data(user_id=1)
        limit: int = AntiFloodMiddleware._limit
        period: float = AntiFloodMiddleware._period
        step: float = 0.01
        for i in range(limit):
            clock.now = i * step
            await middleware(handler=handler, event=_EVENT, data=data)
        clock.now = period + step / 2  # only the hit at t=0 is older than the window now
        await middleware(handler=handler, event=_EVENT, data=data)
        result: Any = await middleware(handler=handler, event=_EVENT, data=data)
        assert result is None
        assert len(handler.calls) == limit + 1


# region UserSyncMiddleware
_DAY_1: date = date(year=2026, month=1, day=1)
_DAY_2: date = date(year=2026, month=1, day=2)


class _FakeToday:
    """A stand-in for middlewares.datetime whose now().date() returns a date the test sets."""

    def __init__(self, today: date) -> None:
        """
        Sets the date now() reports.

        :param today: The current UTC date.
        """
        self.today: date = today

    def now(self, tz: object) -> MagicMock:
        """
        Returns an object whose date() is the current fake date.

        :param tz: Time zone the middleware asks for; ignored.
        :return: A mock with date() returning the fake date.
        """
        del tz
        moment: MagicMock = MagicMock()
        moment.date.return_value = self.today
        return moment


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


@pytest.fixture(name="repo")
def repo_fixture() -> Iterator[MagicMock]:
    """
    Replaces UserRepo in the middleware module with a mock class whose instances have an awaitable upsert().

    :return: The mock UserRepo class.
    """
    with patch.object(target=middlewares, attribute="UserRepo") as repo_cls:
        repo_cls.return_value.upsert = AsyncMock()
        yield repo_cls


@pytest.fixture(name="sync")
def sync_fixture(today: _FakeToday) -> UserSyncMiddleware:
    """
    A fresh UserSyncMiddleware with a mock PostgreSQL client, created on the fake date.

    :param today: The fake clock, set before the middleware reads the date.
    :return: The UserSyncMiddleware instance under test.
    """
    del today
    return UserSyncMiddleware(client=MagicMock())


def _tg_user(language_code: str | None = "en") -> dict[str, Any]:
    """
    Builds a data dict with a full Telegram user.

    :param language_code: The language code Telegram reports.
    :return: A data dict with "event_from_user".
    """
    return {
        "event_from_user": User(
            id=7, is_bot=False, first_name="Ann", last_name="Lee", username="ann", language_code=language_code
        )
    }


class TestUserSync:
    """Tests UserSyncMiddleware: one upsert per user per UTC day, never blocking the handler."""

    async def test_first_update_upserts(self, sync: UserSyncMiddleware, repo: MagicMock, handler: _HandlerSpy) -> None:
        """
        The first update of the day upserts the user with today as both dates, then calls the handler.

        :param sync: The UserSyncMiddleware fixture.
        :param repo: The mock UserRepo class.
        :param handler: The handler spy fixture.
        :return: None
        """
        result: Any = await sync(handler=handler, event=_EVENT, data=_tg_user())
        assert result == "handled"
        repo.return_value.upsert.assert_awaited_once_with(
            user=TgUser(
                id=7,
                username="ann",
                first_name="Ann",
                last_name="Lee",
                locale="en",
                registered_on=_DAY_1,
                last_seen_on=_DAY_1,
            )
        )

    @pytest.mark.usefixtures("today")
    async def test_same_day_skips_the_database(
        self, sync: UserSyncMiddleware, repo: MagicMock, handler: _HandlerSpy
    ) -> None:
        """
        Later updates of the same day don't touch the database.

        :param sync: The UserSyncMiddleware fixture.
        :param repo: The mock UserRepo class.
        :param handler: The handler spy fixture.
        :return: None
        """
        await sync(handler=handler, event=_EVENT, data=_tg_user())
        await sync(handler=handler, event=_EVENT, data=_tg_user())
        repo.return_value.upsert.assert_awaited_once()
        assert len(handler.calls) == 2

    async def test_new_day_upserts_again(
        self, sync: UserSyncMiddleware, repo: MagicMock, handler: _HandlerSpy, today: _FakeToday
    ) -> None:
        """
        On a new UTC day the user is upserted once more, with the new date.

        :param sync: The UserSyncMiddleware fixture.
        :param repo: The mock UserRepo class.
        :param handler: The handler spy fixture.
        :param today: The fake clock.
        :return: None
        """
        await sync(handler=handler, event=_EVENT, data=_tg_user())
        today.today = _DAY_2
        await sync(handler=handler, event=_EVENT, data=_tg_user())
        assert repo.return_value.upsert.await_count == 2
        assert repo.return_value.upsert.await_args.kwargs["user"].last_seen_on == _DAY_2

    @pytest.mark.parametrize(("language_code", "locale"), [("pt-br", "pt"), ("en", "en"), (None, None), ("", None)])
    async def test_locale_is_cut_to_two_characters(
        self,
        sync: UserSyncMiddleware,
        repo: MagicMock,
        handler: _HandlerSpy,
        language_code: str | None,
        locale: str | None,
    ) -> None:
        """
        The language code is cut to its first two characters; a missing or empty one is stored as NULL.

        :param sync: The UserSyncMiddleware fixture.
        :param repo: The mock UserRepo class.
        :param handler: The handler spy fixture.
        :param language_code: The language code Telegram reports.
        :param locale: The locale expected in the database.
        :return: None
        """
        await sync(handler=handler, event=_EVENT, data=_tg_user(language_code=language_code))
        assert repo.return_value.upsert.await_args.kwargs["user"].locale == locale

    @pytest.mark.parametrize(
        "data", [{}, {"event_from_user": User(id=8, is_bot=True, first_name="Bot")}], ids=["no user", "bot"]
    )
    async def test_no_user_or_bot_skips_the_database(
        self, sync: UserSyncMiddleware, repo: MagicMock, handler: _HandlerSpy, data: dict[str, Any]
    ) -> None:
        """
        An update without a user, or from a bot, goes to the handler without a database write.

        :param sync: The UserSyncMiddleware fixture.
        :param repo: The mock UserRepo class.
        :param handler: The handler spy fixture.
        :param data: The data dict of the update.
        :return: None
        """
        assert await sync(handler=handler, event=_EVENT, data=data) == "handled"
        repo.return_value.upsert.assert_not_awaited()

    async def test_database_error_is_logged_and_retried(
        self, sync: UserSyncMiddleware, repo: MagicMock, handler: _HandlerSpy
    ) -> None:
        """
        A database error is logged, the handler still runs, and the next update retries the upsert.

        :param sync: The UserSyncMiddleware fixture.
        :param repo: The mock UserRepo class.
        :param handler: The handler spy fixture.
        :return: None
        """
        repo.return_value.upsert.side_effect = [PostgresError("down"), None]
        with patch.object(target=middlewares, attribute="logger") as mock_logger:
            assert await sync(handler=handler, event=_EVENT, data=_tg_user()) == "handled"
            mock_logger.error.assert_called_once()
        await sync(handler=handler, event=_EVENT, data=_tg_user())
        assert repo.return_value.upsert.await_count == 2
        assert len(handler.calls) == 2


# endregion
