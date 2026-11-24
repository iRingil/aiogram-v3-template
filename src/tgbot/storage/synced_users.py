"""Redis store of the users already saved to the users table today."""

from datetime import UTC, date, datetime, time, timedelta
from math import ceil

from redis.asyncio import Redis

from tgbot.storage.redis_client import RedisValue

__all__: tuple[str, ...] = ("SyncedUsers",)


class SyncedUsers:
    """
    Remembers which users UserSyncMiddleware has saved today (UTC), so they are saved once a day.

    A key per user holds the date of the last save and expires at the end of that day. It is shared by every bot
    process and survives a restart; deleting a user's data forgets it, so the next update saves the user again.

    :cvar _prefix: Prefix of the Redis keys, followed by the user ID.
    """

    _prefix: str = "tgbot_synced"

    def __init__(self, *, redis: Redis) -> None:
        """
        Initializes the store.

        :param redis: Redis client.
        """
        self._redis: Redis = redis

    async def is_synced(self, *, user_id: int, day: date) -> bool:
        """
        Tells whether the user was saved on the given day.

        :param user_id: Telegram user ID.
        :param day: The current UTC date.
        :return: True if the user was saved that day.
        """
        saved_on: str | None = RedisValue.text(value=await self._redis.get(name=self._key(user_id=user_id)))
        return saved_on == day.isoformat()

    async def mark(self, *, user_id: int, now: datetime) -> None:
        """
        Remembers that the user was saved now, until the end of the UTC day.

        :param user_id: Telegram user ID.
        :param now: The current UTC time.
        :return: None
        """
        midnight: datetime = datetime.combine(date=now.date() + timedelta(days=1), time=time(), tzinfo=UTC)
        ttl: int = max(1, ceil((midnight - now).total_seconds()))
        await self._redis.set(name=self._key(user_id=user_id), value=now.date().isoformat(), ex=ttl)

    async def forget(self, *, user_id: int) -> None:
        """
        Forgets the user, so the next update saves them again (after their data was deleted).

        :param user_id: Telegram user ID.
        :return: None
        """
        await self._redis.delete(self._key(user_id=user_id))

    def _key(self, *, user_id: int) -> str:
        """
        Returns the Redis key of a user.

        :param user_id: Telegram user ID.
        :return: The key.
        """
        return f"{self._prefix}:{user_id}"
