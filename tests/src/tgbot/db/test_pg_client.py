"""Tests of src/tgbot/db/pg_client.py (PostgresClient and Row) against the test PostgreSQL."""

# ruff: noqa: S101, S106, SLF001

from collections.abc import Generator
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from asyncpg import Pool, Record

from tests.conftest import TEST_POSTGRES
from tgbot.db.pg_client import PostgresClient, Row
from tgbot.misc.data_types import PostgresCredentials

__all__: tuple[str, ...] = ()


class _AwaitablePool:
    """Stands in for the asyncpg Pool create_pool returns: awaiting it gives the mock pool back."""

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


async def test_connect(pg_client: PostgresClient) -> None:
    """
    connect() opens a pool that runs queries on the test database.

    :param pg_client: The connected test client.
    :return: None
    """
    row: Record | None = await pg_client.pool.fetchrow("SELECT current_database() AS db, current_user AS usr")
    assert row is not None
    assert Row(record=row).get(column="db", kind=str) == "test_db"
    assert Row(record=row).get(column="usr", kind=str) == "test_user"


async def test_connect_twice_keeps_the_pool(pg_client: PostgresClient) -> None:
    """
    A second connect() keeps the open pool.

    :param pg_client: The connected test client.
    :return: None
    """
    pool: Pool[Record] = pg_client.pool
    await pg_client.connect()
    assert pg_client.pool is pool


async def test_connect_over_socket() -> None:
    """
    connect() passes the socket path as the host, which is how asyncpg takes a Unix socket, and the time limits.

    No socket is reachable from the tests, so create_pool is replaced.

    :return: None
    """
    credentials: PostgresCredentials = PostgresCredentials.model_validate(
        {"socket_path": "/run/postgresql/.s.PGSQL.5432", "database": "db", "user": "user", "password": "pass"}
    )
    pool: MagicMock = MagicMock()
    with patch(target="tgbot.db.pg_client.create_pool", return_value=_AwaitablePool(pool=pool)) as mock_create:
        await PostgresClient(credentials=credentials).connect()
    mock_create.assert_called_once_with(
        host=str(credentials.socket_path),
        port=None,
        database="db",
        user="user",
        password="pass",
        timeout=10.0,
        command_timeout=30.0,
    )


async def test_close() -> None:
    """
    close() closes the pool and forgets it; a second close() does nothing.

    :return: None
    """
    client: PostgresClient = PostgresClient(credentials=TEST_POSTGRES)
    await client.connect()
    pool: Pool[Record] = client.pool
    await client.close()
    await client.close()
    assert pool.is_closing()
    assert client._pool is None


def test_pool_before_connect() -> None:
    """
    Reading the pool before connect() is a programming error.

    :return: None
    """
    with pytest.raises(expected_exception=RuntimeError, match="not connected"):
        _ = PostgresClient(credentials=TEST_POSTGRES).pool


async def test_transaction_commits(pg_client: PostgresClient) -> None:
    """
    The queries of a transaction block are committed on exit.

    :param pg_client: The connected test client.
    :return: None
    """
    await pg_client.pool.execute("CREATE TABLE users (id BIGINT PRIMARY KEY)")
    async with pg_client.transaction() as conn:
        assert conn.is_in_transaction()
        await conn.execute("INSERT INTO users (id) VALUES (1)")
        await conn.execute("INSERT INTO users (id) VALUES (2)")
    row: Record | None = await pg_client.pool.fetchrow("SELECT count(*) AS n FROM users")
    assert row is not None
    assert Row(record=row).get(column="n", kind=int) == 2  # noqa: PLR2004 - the two inserted rows


async def _insert_then_fail(*, pg_client: PostgresClient) -> None:
    """
    Inserts a row in a transaction, then fails inside it.

    :param pg_client: The connected test client.
    :return: None
    :raises RuntimeError: always, from inside the transaction.
    """
    async with pg_client.transaction() as conn:
        await conn.execute("INSERT INTO users (id) VALUES (1)")
        raise RuntimeError("rollback")


async def test_transaction_rolls_back(pg_client: PostgresClient) -> None:
    """
    An exception in a transaction block rolls back all its queries.

    :param pg_client: The connected test client.
    :return: None
    """
    await pg_client.pool.execute("CREATE TABLE users (id BIGINT PRIMARY KEY)")
    with pytest.raises(expected_exception=RuntimeError, match="rollback"):
        await _insert_then_fail(pg_client=pg_client)
    row: Record | None = await pg_client.pool.fetchrow("SELECT count(*) AS n FROM users")
    assert row is not None
    assert Row(record=row).get(column="n", kind=int) == 0


async def _record(*, pg_client: PostgresClient) -> Record:
    """
    Reads a row with an int, a date, a text and a NULL column.

    :param pg_client: The connected test client.
    :return: The row.
    """
    record: Record | None = await pg_client.pool.fetchrow(
        "SELECT 1::bigint AS id, DATE '2026-01-02' AS day, 'Ann'::text AS name, NULL::text AS last"
    )
    assert record is not None
    return record


async def test_row_get(pg_client: PostgresClient) -> None:
    """
    get() and get_optional() return values of the expected types, get_optional() None for NULL.

    :param pg_client: The connected test client.
    :return: None
    """
    row: Row = Row(record=await _record(pg_client=pg_client))
    assert row.get(column="id", kind=int) == 1
    assert row.get(column="day", kind=date) == date(year=2026, month=1, day=2)
    assert row.get_optional(column="name", kind=str) == "Ann"
    assert row.get_optional(column="last", kind=str) is None


async def test_row_get_null(pg_client: PostgresClient) -> None:
    """
    get() rejects NULL in a column expected to be NOT NULL.

    :param pg_client: The connected test client.
    :return: None
    """
    with pytest.raises(expected_exception=TypeError, match="Column last is NULL, expected str"):
        Row(record=await _record(pg_client=pg_client)).get(column="last", kind=str)


async def test_row_wrong_type(pg_client: PostgresClient) -> None:
    """
    A value of another type than expected is rejected.

    :param pg_client: The connected test client.
    :return: None
    """
    with pytest.raises(expected_exception=TypeError, match="Column name is str, expected int"):
        Row(record=await _record(pg_client=pg_client)).get_optional(column="name", kind=int)
