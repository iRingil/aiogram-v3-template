"""Redis client built from the connection parameters."""

from redis.asyncio import Redis

from tgbot.misc.dataclasses import RedisCredentials

__all__: tuple[str, ...] = ("RedisClient",)


class RedisClient:
    """
    Builds the Redis client.

    Nothing connects here: redis-py opens a connection on the first command.
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
            )
        elif host is not None and port is not None:
            self._redis = Redis(host=host, port=port, db=credentials.db, username=credentials.user, password=password)
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
