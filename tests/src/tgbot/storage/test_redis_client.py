"""Unit tests for src/tgbot/storage/redis_client.py."""

# ruff: noqa: S101

from collections.abc import AsyncIterator
from unittest.mock import MagicMock

import pytest
from pydantic import SecretStr

from tgbot.misc.data_types import RedisCredentials
from tgbot.storage.redis_client import RedisClient, RedisValue

__all__: tuple[str, ...] = ()


def test_tcp() -> None:
    """
    With a host and a port the client connects over TCP, with the password revealed.

    :return: None
    """
    credentials: RedisCredentials = RedisCredentials.model_validate(
        {"host": "localhost", "port": 6379, "db": 1, "user": "user", "password": "pass"}
    )
    kwargs: dict[str, object] = RedisClient(credentials=credentials).redis.connection_pool.connection_kwargs
    assert (kwargs["host"], kwargs["port"], kwargs["db"]) == ("localhost", 6379, 1)
    assert (kwargs["username"], kwargs["password"]) == ("user", "pass")
    assert kwargs["decode_responses"] is True
    assert "path" not in kwargs


def test_socket() -> None:
    """
    With a socket path the client connects over the Unix socket.

    :return: None
    """
    credentials: RedisCredentials = RedisCredentials.model_validate(
        {"socket_path": "/run/redis/redis.sock", "db": 0, "user": "user", "password": "pass"}
    )
    kwargs: dict[str, object] = RedisClient(credentials=credentials).redis.connection_pool.connection_kwargs
    assert kwargs["path"] == str(credentials.socket_path)
    assert kwargs["decode_responses"] is True
    assert "host" not in kwargs


def test_no_address() -> None:
    """
    Credentials built without validation and without any address are rejected.

    :return: None
    """
    credentials: RedisCredentials = RedisCredentials.model_construct(db=0, user="user", password=SecretStr("pass"))
    with pytest.raises(expected_exception=ValueError, match="either a socket path or both a host and a port"):
        RedisClient(credentials=credentials)


@pytest.mark.parametrize("value", ["text", None])
def test_value_text(value: str | None) -> None:
    """
    A str value, or None for a missing key, is returned as is.

    :param value: The value Redis returned.
    :return: None
    """
    assert RedisValue.text(value=value) == value


def test_value_bytes() -> None:
    """
    A bytes value means a client built without decode_responses and is rejected.

    :return: None
    """
    with pytest.raises(expected_exception=TypeError, match="decode_responses=True"):
        RedisValue.text(value=b"text")


async def test_scan_keys() -> None:
    """
    scan_keys() reads the matching keys with SCAN and returns them as str.

    :return: None
    """

    async def scan(match: str) -> AsyncIterator[str]:
        """
        Stands in for Redis.scan_iter.

        :param match: The pattern passed by scan_keys.
        :return: An iterator over two keys.
        """
        assert match == "signal:*"
        for key in ("signal:BTC", "signal:ETH"):
            yield key

    redis: MagicMock = MagicMock()
    redis.scan_iter = scan
    assert await RedisValue.scan_keys(redis=redis, pattern="signal:*") == ["signal:BTC", "signal:ETH"]
