"""Unit tests for src/tgbot/misc/data_types.py (validation of the credentials models)."""

# ruff: noqa: S101

from pathlib import Path

import pytest
from pydantic import ValidationError

from tgbot.misc.data_types import PostgresCredentials, RedisCredentials, WebhookCredentials

__all__: tuple[str, ...] = ()

_POSTGRES: dict[str, object] = {"database": "db", "user": "user", "password": "pass"}
_REDIS: dict[str, object] = {"db": 0, "user": "user", "password": "pass"}
_WEBHOOK: dict[str, object] = {
    "wh_host": "https://bot.example.com",
    "wh_path": "hook",
    "wh_token": "abc_DEF-123",
    "app_host": "127.0.0.1",
    "app_port": 8080,
}


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "localhost", "db.example.com"])
def test_host_accepts_ip_and_host_name(host: str) -> None:
    """
    An IPv4 address, an IPv6 address and a host name are all valid hosts.

    :param host: The host to validate.
    :return: None
    """
    credentials: PostgresCredentials = PostgresCredentials.model_validate({**_POSTGRES, "host": host, "port": 5432})
    assert credentials.host == host


@pytest.mark.parametrize("host", ["bad host!", "-leading.example.com", "a" * 64])
def test_host_rejects_invalid(host: str) -> None:
    """
    A value that is neither an IP address nor an RFC 1123 host name is rejected.

    :param host: The invalid host.
    :return: None
    """
    with pytest.raises(expected_exception=ValidationError, match="neither an IP address nor a valid host name"):
        PostgresCredentials.model_validate({**_POSTGRES, "host": host, "port": 5432})


@pytest.mark.parametrize(("port", "valid"), [(0, False), (1, True), (65535, True), (65536, False)])
def test_port_range(*, port: int, valid: bool) -> None:
    """
    A port is valid from 1 to 65535.

    :param port: The port to validate.
    :param valid: Whether the port should be accepted.
    :return: None
    """
    values: dict[str, object] = {**_POSTGRES, "host": "localhost", "port": port}
    if valid:
        assert PostgresCredentials.model_validate(values).port == port
    else:
        with pytest.raises(expected_exception=ValidationError):
            PostgresCredentials.model_validate(values)


def test_postgres_socket_path() -> None:
    """
    A socket path alone is enough, without a host and a port.

    :return: None
    """
    credentials: PostgresCredentials = PostgresCredentials.model_validate(
        {**_POSTGRES, "socket_path": "/var/run/postgresql/.s.PGSQL.5432"}
    )
    assert credentials.socket_path == Path("/var/run/postgresql/.s.PGSQL.5432")
    assert credentials.password.get_secret_value() == "pass"


@pytest.mark.parametrize("address", [{}, {"host": "localhost"}, {"port": 5432}])
def test_postgres_needs_socket_or_host_and_port(address: dict[str, object]) -> None:
    """
    Without a socket path, both a host and a port are required.

    :param address: The address fields given.
    :return: None
    """
    with pytest.raises(expected_exception=ValidationError, match="either a socket path or both a host and a port"):
        PostgresCredentials.model_validate({**_POSTGRES, **address})


def test_postgres_rejects_empty_user() -> None:
    """
    The database user can't be empty.

    :return: None
    """
    with pytest.raises(expected_exception=ValidationError):
        PostgresCredentials.model_validate({**_POSTGRES, "user": "", "host": "localhost", "port": 5432})


def test_redis_socket_path() -> None:
    """
    A socket path alone is enough, without a host and a port.

    :return: None
    """
    credentials: RedisCredentials = RedisCredentials.model_validate(
        {**_REDIS, "socket_path": "/var/run/redis/redis.sock"}
    )
    assert credentials.socket_path == Path("/var/run/redis/redis.sock")


@pytest.mark.parametrize("address", [{}, {"host": "localhost"}, {"port": 6379}])
def test_redis_needs_socket_or_host_and_port(address: dict[str, object]) -> None:
    """
    Without a socket path, both a host and a port are required.

    :param address: The address fields given.
    :return: None
    """
    with pytest.raises(expected_exception=ValidationError, match="either a socket path or both a host and a port"):
        RedisCredentials.model_validate({**_REDIS, **address})


def test_redis_rejects_negative_db() -> None:
    """
    The database index can't be negative.

    :return: None
    """
    with pytest.raises(expected_exception=ValidationError):
        RedisCredentials.model_validate({**_REDIS, "db": -1, "host": "localhost", "port": 6379})


def test_webhook_valid() -> None:
    """
    Valid webhook values are accepted, the token kept secret.

    :return: None
    """
    webhook: WebhookCredentials = WebhookCredentials.model_validate(_WEBHOOK)
    assert str(webhook.wh_host) == "https://bot.example.com/"
    assert webhook.wh_token.get_secret_value() == "abc_DEF-123"
    assert "abc_DEF-123" not in repr(webhook)


@pytest.mark.parametrize(
    ("field", "value", "error_match"),
    [
        ("wh_host", "http://bot.example.com", "is not an HTTPS URL"),
        ("wh_path", "/hook", "String should match pattern"),
        ("wh_token", "a b", "must be 1-256 characters"),
        ("wh_token", "a" * 257, "must be 1-256 characters"),
        ("wh_token", "", "must be 1-256 characters"),
        ("app_host", "bad host!", "neither an IP address nor a valid host name"),
    ],
)
def test_webhook_rejects_invalid(*, field: str, value: str, error_match: str) -> None:
    """
    Each invalid webhook value is rejected with its own message.

    :param field: The field to set.
    :param value: The invalid value.
    :param error_match: Expected substring in the error message.
    :return: None
    """
    with pytest.raises(expected_exception=ValidationError, match=error_match):
        WebhookCredentials.model_validate({**_WEBHOOK, field: value})
