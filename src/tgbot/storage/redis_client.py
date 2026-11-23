"""Redis client built from the connection parameters, and typed reading of its values."""

from typing import TYPE_CHECKING, cast

from redis.asyncio import Redis

from tgbot.misc.data_types import RedisCredentials

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

__all__: tuple[str, ...] = ("RedisClient", "RedisValue")


class RedisClient:
    """
    Builds the Redis client, shared by the FSM storage and the stores.

    Nothing connects here: redis-py opens a connection on the first command. The client decodes
    responses, so values come back as str; the FSM storage closes it on shutdown.
    """

    def __init__(self, *, credentials: RedisCredentials) -> None:
        """
        Initializes the client.

        :param credentials: Redis connection parameters.
        :raises ValueError: if there is neither a socket path nor a host and a port.
        """
        password: str = credentials.password.get_secret_value()
        host: str | None = credentials.host
        port: int | None = credentials.port
        if credentials.socket_path is not None:
            self._redis: Redis = Redis(
                unix_socket_path=str(credentials.socket_path),
                db=credentials.db,
                username=credentials.user,
                password=password,
                decode_responses=True,
            )
        elif host is not None and port is not None:
            self._redis = Redis(
                host=host,
                port=port,
                db=credentials.db,
                username=credentials.user,
                password=password,
                decode_responses=True,
            )
        else:
            # RedisCredentials validates that one of the two is set
            raise ValueError("Redis needs either a socket path or both a host and a port")

    @property
    def redis(self) -> Redis:
        """
        Returns the Redis client.

        :return: Redis instance.
        """
        return self._redis


class RedisValue:
    """
    Typed reading of the values Redis returns.

    redis-py types a value as bytes | str | None, since the type depends on decode_responses. RedisClient
    decodes responses, so a bytes value means a client built without it - a programming error.
    """

    @staticmethod
    def text(*, value: bytes | str | None) -> str | None:
        """
        Returns a value as str.

        :param value: A value returned by Redis (e.g. by get or mget).
        :return: The value, or None for a missing key.
        :raises TypeError: if the value is bytes.
        """
        if value is None or isinstance(value, str):
            return value
        raise TypeError("Redis returned bytes: the client must be built with decode_responses=True")

    @classmethod
    async def scan_keys(cls, *, redis: Redis, pattern: str) -> list[str]:
        """
        Returns the keys matching a pattern, read with SCAN (unlike KEYS, it doesn't block the server).

        :param redis: The Redis client.
        :param pattern: A glob-style pattern (e.g. "signal:*").
        :return: The matching keys.
        :raises TypeError: if a key is bytes.
        """
        # redis-py types scan_iter as an AsyncIterator without its item type
        # noinspection unnecessary-cast
        keys: AsyncIterator[bytes | str] = cast(
            "AsyncIterator[bytes | str]",
            redis.scan_iter(match=pattern),  # pyright: ignore[reportUnknownMemberType] - see above
        )
        return [key for key in [cls.text(value=raw) async for raw in keys] if key is not None]
