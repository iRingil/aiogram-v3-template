"""The module contains middlewares used by the bot."""

from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from time import monotonic
from typing import override

from aiogram import BaseMiddleware
from aiogram.enums import ChatType
from aiogram.types import Chat, TelegramObject, User
from asyncpg import InterfaceError, PostgresError

from tgbot.config import logger
from tgbot.db.pg_client import PostgresClient
from tgbot.db.users import UserRepo
from tgbot.misc.data_types import TgUser

__all__: tuple[str, ...] = ("AntiFloodMiddleware", "UserSyncMiddleware")


class AntiFloodMiddleware(BaseMiddleware):
    """
    Drops updates from a user who exceeds a fixed number of updates within a sliding time window.

    :cvar _limit: Maximum number of updates allowed from one user within the time window.
    :cvar _period: Length of the sliding time window, in seconds.
    """

    _limit: int = 3
    _period: float = 2.0

    def __init__(self) -> None:
        """Initializes the per-user history of update timestamps."""
        self._hits: dict[int, deque[float]] = defaultdict(deque)

    @override
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, object]], Awaitable[object]],
        event: TelegramObject,
        data: dict[str, object],
    ) -> object:
        """
        Drops the update if the sending user has exceeded the rate limit, otherwise calls the handler.

        :param handler: Wrapped handler in the middlewares chain.
        :param event: Incoming event.
        :param data: Contextual data, expected to already contain "event_from_user".
        :return: The handler's result, or None if the update was dropped.
        """
        # No user to key the rate limit by, so nothing to throttle.
        user: object = data.get("event_from_user")
        if not isinstance(user, User):
            return await handler(event, data)
        now: float = monotonic()
        hits: deque[float] = self._hits[user.id]
        # Drop hits that fell out of the sliding window.
        while hits and now - hits[0] > self._period:
            hits.popleft()
        # Rate limit exceeded within the window - drop the update.
        if len(hits) >= self._limit:
            return None
        hits.append(now)
        return await handler(event, data)


class UserSyncMiddleware(BaseMiddleware):
    """
    Writes the sending user of a private chat to the users table once per UTC day.

    The first update of the day upserts the profile fields and last_seen_on (and creates the row for a
    new user); later updates of that day skip the database. The "synced today" set lives in memory, so
    after a restart, or in each of several bot processes, a user is upserted once more - harmless.
    A database error is logged and does not stop the update; the next update retries.
    """

    def __init__(self, *, client: PostgresClient) -> None:
        """
        Initializes the middleware.

        :param client: PostgreSQL client, connected on startup.
        """
        self._client: PostgresClient = client
        self._day: date = datetime.now(tz=UTC).date()
        self._synced: set[int] = set()

    @override
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, object]], Awaitable[object]],
        event: TelegramObject,
        data: dict[str, object],
    ) -> object:
        """
        Upserts the sending user if they are not synced today, then calls the handler.

        :param handler: Wrapped handler in the middlewares chain.
        :param event: Incoming event.
        :param data: Contextual data, expected to already contain "event_from_user" and "event_chat".
        :return: The handler's result.
        """
        # Only users of private chats; a callback without a message has no chat and is skipped too
        user: object = data.get("event_from_user")
        chat: object = data.get("event_chat")
        if isinstance(user, User) and not user.is_bot and isinstance(chat, Chat) and chat.type == ChatType.PRIVATE:
            await self._sync(user=user)
        return await handler(event, data)

    async def _sync(self, *, user: User) -> None:
        """
        Upserts the user unless already done today.

        :param user: Telegram user who sent the update.
        :return: None
        """
        # 1. A new UTC day: everyone has to be synced again
        today: date = datetime.now(tz=UTC).date()
        if today != self._day:
            self._day = today
            self._synced.clear()
        if user.id in self._synced:
            return
        # 2. Upsert; on failure the user stays unsynced, so the next update retries
        # Text fields are cut to the column sizes of users, so an unexpected long value can't fail the insert
        tg_user: TgUser = TgUser(
            id=user.id,
            username=user.username[:32] if user.username else None,
            first_name=user.first_name[:64],
            last_name=user.last_name[:64] if user.last_name else None,
            # A longer IETF tag ("pt-br") keeps its first two characters
            locale=user.language_code[:2] if user.language_code else None,
            registered_on=today,
            last_seen_on=today,
        )
        try:
            await UserRepo(db=self._client.pool).upsert(user=tg_user)
        except (PostgresError, InterfaceError, OSError) as exc:
            logger.error(f"Failed to save user {user.id}: {exc!r}")
            return
        self._synced.add(user.id)
