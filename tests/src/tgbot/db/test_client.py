"""Unit tests for src/tgbot/db/client.py (PostgresClient and Row)."""

# ruff: noqa: S101, S106, SLF001

from collections.abc import Generator
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tgbot.db.client import PostgresClient, Row
from tgbot.misc.dataclasses import PostgresCredentials

__all__: tuple[str, ...] = ()

_TCP: PostgresCredentials = PostgresCredentials.model_validate(
    {"host": "localhost", "port": 5432, "database": "db", "user": "user", "password": "pass"}
)
_SOCKET: PostgresCredentials = PostgresCredentials.model_validate(
    {"socket_path": "/run/postgresql/.s.PGSQL.5432", "database": "db", "user": "user", "password": "pass"}
)


class _AwaitablePool:
    """Stands in for the asyncpg Pool create_pool returns: awaiting it opens it and gives the pool back."""

    def __init__(self, pool: MagicMock) -> None:
        """
        Sets the pool awaiting returns.

        :param pool: The mock pool.
        """
        self._pool: MagicMock = pool

    def __await__(self) -> Generator[None, None, MagicMock]:
        """
        Returns the pool, as awaiting a real Pool does once its connections are open.

        :return: A generator returning the mock pool.
        """
        return self._open().__await__()

    async def _open(self) -> MagicMock:
        """
        Returns the mock pool.

        :return: The mock pool.
        """
        return self._pool


@pytest.fixture(name="pool")
def pool_fixture() -> MagicMock:
    """
    A mock pool whose close() is awaitable.

    :return: The mock pool.
    """
    pool: MagicMock = MagicMock()
    pool.close = AsyncMock()
    return pool


async def test_connect_over_tcp(pool: MagicMock) -> None:
    """
    connect() opens the pool with the host, port and the password revealed.

    :param pool: The mock pool.
    :return: None
    """
    client: PostgresClient = PostgresClient(credentials=_TCP)
    with patch(target="tgbot.db.client.create_pool", return_value=_AwaitablePool(pool=pool)) as mock_create:
        await client.connect()
    mock_create.assert_called_once_with(host="localhost", port=5432, database="db", user="user", password="pass")
    assert client.pool is pool


async def test_connect_over_socket(pool: MagicMock) -> None:
    """
    connect() passes the socket path as the host, which is how asyncpg takes a Unix socket.

    :param pool: The mock pool.
    :return: None
    """
    client: PostgresClient = PostgresClient(credentials=_SOCKET)
    with patch(target="tgbot.db.client.create_pool", return_value=_AwaitablePool(pool=pool)) as mock_create:
        await client.connect()
    assert mock_create.call_args.kwargs["host"] == str(_SOCKET.socket_path)
    assert mock_create.call_args.kwargs["port"] is None


async def test_connect_twice_keeps_the_pool(pool: MagicMock) -> None:
    """
    A second connect() does not open another pool.

    :param pool: The mock pool.
    :return: None
    """
    client: PostgresClient = PostgresClient(credentials=_TCP)
    with patch(target="tgbot.db.client.create_pool", return_value=_AwaitablePool(pool=pool)) as mock_create:
        await client.connect()
        await client.connect()
    mock_create.assert_called_once()


async def test_close(pool: MagicMock) -> None:
    """
    close() closes the pool and forgets it; a second close() does nothing.

    :param pool: The mock pool.
    :return: None
    """
    client: PostgresClient = PostgresClient(credentials=_TCP)
    with patch(target="tgbot.db.client.create_pool", return_value=_AwaitablePool(pool=pool)):
        await client.connect()
    await client.close()
    await client.close()
    pool.close.assert_awaited_once_with()
    assert client._pool is None


def test_pool_before_connect() -> None:
    """
    Reading the pool before connect() is a programming error.

    :return: None
    """
    with pytest.raises(expected_exception=RuntimeError, match="not connected"):
        _ = PostgresClient(credentials=_TCP).pool


async def test_transaction(pool: MagicMock) -> None:
    """
    transaction() yields a connection from the pool inside its transaction.

    :param pool: The mock pool.
    :return: None
    """
    conn: MagicMock = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    client: PostgresClient = PostgresClient(credentials=_TCP)
    with patch(target="tgbot.db.client.create_pool", return_value=_AwaitablePool(pool=pool)):
        await client.connect()
    async with client.transaction() as tx_conn:
        assert tx_conn is conn
        conn.transaction.return_value.__aenter__.assert_awaited_once()
    conn.transaction.return_value.__aexit__.assert_awaited_once()
    pool.acquire.return_value.__aexit__.assert_awaited_once()


def _record(values: dict[str, object]) -> MagicMock:
    """
    Builds a stand-in for an asyncpg Record with the given columns.

    :param values: Column values by name.
    :return: The mock record.
    """
    record: MagicMock = MagicMock()
    record.__getitem__.side_effect = values.__getitem__
    return record


def test_row_get() -> None:
    """
    get() returns a value of the expected type.

    :return: None
    """
    row: Row = Row(record=_record(values={"id": 1, "day": date(year=2026, month=1, day=2)}))
    assert row.get(column="id", kind=int) == 1
    assert row.get(column="day", kind=date) == date(year=2026, month=1, day=2)


def test_row_get_null() -> None:
    """
    get() rejects NULL in a column expected to be NOT NULL.

    :return: None
    """
    with pytest.raises(expected_exception=TypeError, match="Column id is NULL, expected int"):
        Row(record=_record(values={"id": None})).get(column="id", kind=int)


def test_row_get_optional() -> None:
    """
    get_optional() returns the value or None for NULL.

    :return: None
    """
    row: Row = Row(record=_record(values={"name": "Ann", "last": None}))
    assert row.get_optional(column="name", kind=str) == "Ann"
    assert row.get_optional(column="last", kind=str) is None


def test_row_wrong_type() -> None:
    """
    A value of another type than expected is rejected.

    :return: None
    """
    with pytest.raises(expected_exception=TypeError, match="Column id is str, expected int"):
        Row(record=_record(values={"id": "1"})).get_optional(column="id", kind=int)
