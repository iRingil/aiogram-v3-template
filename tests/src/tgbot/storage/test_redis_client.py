"""Tests of src/tgbot/storage/redis_client.py against the test Redis."""

# ruff: noqa: S101

import pytest
from pydantic import SecretStr
from redis.asyncio import Redis

from tgbot.misc.data_types import RedisCredentials
from tgbot.storage.redis_client import RedisClient, RedisValue

__all__: tuple[str, ...] = ()


async def test_tcp_round_trip(redis: Redis) -> None:
    """
    The client connects to the test Redis over TCP and returns the values as str.

    :param redis: The test Redis client.
    :return: None
    """
    await redis.set(name="key", value="value")
    value: bytes | str | None = await redis.get(name="key")
    assert value == "value"
    assert isinstance(value, str)


def test_socket() -> None:
    """
    With a socket path the client connects over the Unix socket.

    No socket is reachable from the tests, so only the connection parameters are checked.

    :return: None
    """
    credentials: RedisCredentials = RedisCredentials.model_validate(
        {"socket_path": "/run/redis/redis.sock", "db": 0, "user": "user", "password": "pass"}
    )
    kwargs: dict[str, object] = RedisClient(credentials=credentials).redis.connection_pool.connection_kwargs
    assert kwargs["path"] == str(credentials.socket_path)
    assert (kwargs["username"], kwargs["password"]) == ("user", "pass")
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


async def test_value_text(redis: Redis) -> None:
    """
    A value read from Redis is returned as str, a missing key as None.

    :param redis: The test Redis client.
    :return: None
    """
    await redis.set(name="key", value="value")
    assert RedisValue.text(value=await redis.get(name="key")) == "value"
    assert RedisValue.text(value=await redis.get(name="missing")) is None


def test_value_bytes() -> None:
    """
    A bytes value means a client built without decode_responses and is rejected.

    :return: None
    """
    with pytest.raises(expected_exception=TypeError, match="decode_responses=True"):
        RedisValue.text(value=b"text")


async def test_scan_keys(redis: Redis) -> None:
    """
    scan_keys() returns the keys matching the pattern, and only them.

    :param redis: The test Redis client.
    :return: None
    """
    for key in ("signal:BTC", "signal:ETH", "other:BTC"):
        await redis.set(name=key, value="1")
    assert sorted(await RedisValue.scan_keys(redis=redis, pattern="signal:*")) == ["signal:BTC", "signal:ETH"]
    assert await RedisValue.scan_keys(redis=redis, pattern="none:*") == []
