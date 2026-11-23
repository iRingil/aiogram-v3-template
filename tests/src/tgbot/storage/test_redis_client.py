"""Unit tests for src/tgbot/storage/redis_client.py."""

# ruff: noqa: S101

import pytest
from pydantic import SecretStr

from tgbot.misc.dataclasses import RedisCredentials
from tgbot.storage.redis_client import RedisClient

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
    assert "host" not in kwargs


def test_no_address() -> None:
    """
    Credentials built without validation and without any address are rejected.

    :return: None
    """
    credentials: RedisCredentials = RedisCredentials.model_construct(db=0, user="user", password=SecretStr("pass"))
    with pytest.raises(expected_exception=ValueError, match="either a socket path or both a host and a port"):
        RedisClient(credentials=credentials)
