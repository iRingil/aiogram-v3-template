"""Async PostgreSQL client: the connection pool and transactions."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, cast

from asyncpg import Pool, Record, create_pool
from asyncpg.pool import PoolConnectionProxy

from tgbot.misc.dataclasses import PostgresCredentials

if TYPE_CHECKING:
    from pathlib import Path

__all__: tuple[str, ...] = ("Executor", "PostgresClient", "Row")


# What a repository runs its queries on: the pool (each query on its own connection) or one connection of a transaction
type Executor = Pool[Record] | PoolConnectionProxy[Record]


class PostgresClient:
    """
    Owns the connection pool: opens it on startup, closes it on shutdown and runs transactions.

    The pool is opened in connect(), not in __init__, because it binds to the running event loop.
    """

    def __init__(self, *, credentials: PostgresCredentials) -> None:
        """
        Initializes the client without connecting.

        :param credentials: PostgreSQL connection parameters.
        """
        self._credentials: PostgresCredentials = credentials
        self._pool: Pool[Record] | None = None

    async def connect(self) -> None:
        """
        Opens the connection pool; fails at once if the server is unreachable or the credentials are wrong.

        :return: None
        """
        if self._pool is not None:
            return
        # Separate parameters instead of a DSN: no escaping of special characters in the password
        # asyncpg takes a Unix socket path as the host
        socket_path: Path | None = self._credentials.socket_path
        pool: Pool[Record] = create_pool(
            host=str(socket_path) if socket_path is not None else self._credentials.host,
            port=self._credentials.port,
            database=self._credentials.database,
            user=self._credentials.user,
            password=self._credentials.password.get_secret_value(),
        )
        self._pool = await pool

    async def close(self) -> None:
        """
        Closes the connection pool, waiting for the queries in progress.

        :return: None
        """
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> "Pool[Record]":
        """
        Returns the connection pool, to run single queries on.

        :return: The open connection pool.
        :raises RuntimeError: if connect() has not been called.
        """
        if self._pool is None:
            raise RuntimeError("PostgresClient is not connected: call connect() on startup")
        return self._pool

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator["PoolConnectionProxy[Record]"]:
        """
        Runs the block in one transaction: committed on exit, rolled back on an exception.

        Pass the yielded connection to the repositories whose queries must succeed or fail together.

        :return: A generator yielding the connection of the transaction.
        """
        async with self.pool.acquire() as conn, conn.transaction():
            yield conn


class Row:
    """
    Typed access to the columns of an asyncpg Record.

    asyncpg types every column value as Any; Row checks the actual type instead, so a schema that no
    longer matches the code fails with a clear TypeError at the read, not somewhere later.
    """

    def __init__(self, *, record: Record) -> None:
        """
        Initializes the row.

        :param record: A row returned by asyncpg.
        """
        self._record: Record = record

    def get[T](self, *, column: str, kind: type[T]) -> T:
        """
        Returns a NOT NULL column value.

        :param column: Column name.
        :param kind: Expected Python type of the value.
        :return: The value.
        :raises TypeError: if the value is NULL or of another type.
        """
        value: T | None = self.get_optional(column=column, kind=kind)
        if value is None:
            raise TypeError(f"Column {column} is NULL, expected {kind.__name__}")
        return value

    def get_optional[T](self, *, column: str, kind: type[T]) -> T | None:
        """
        Returns a nullable column value.

        :param column: Column name.
        :param kind: Expected Python type of the value.
        :return: The value, or None for NULL.
        :raises TypeError: if the value is of another type.
        """
        # noinspection unnecessary-cast
        value: object = cast("object", self._record[column])
        if value is None or isinstance(value, kind):
            return value
        raise TypeError(f"Column {column} is {type(value).__name__}, expected {kind.__name__}")
