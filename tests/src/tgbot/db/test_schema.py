"""Unit tests for src/tgbot/db/schema.py."""

# ruff: noqa: S101

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

from tgbot.db.schema import Schema

__all__: tuple[str, ...] = ()


async def test_create() -> None:
    """
    create() runs CREATE TABLE IF NOT EXISTS for the users table inside a transaction.

    :return: None
    """
    conn: MagicMock = MagicMock()
    conn.execute = AsyncMock()
    in_transaction: list[bool] = []

    @asynccontextmanager
    async def transaction() -> AsyncGenerator[MagicMock]:
        """
        Stands in for PostgresClient.transaction, recording that the block ran inside it.

        :return: A generator yielding the mock connection.
        """
        in_transaction.append(True)
        yield conn

    client: MagicMock = MagicMock()
    client.transaction = transaction
    await Schema(client=client).create()
    assert in_transaction == [True]
    conn.execute.assert_awaited_once()
    query: str = conn.execute.await_args.args[0]
    assert "CREATE TABLE IF NOT EXISTS users" in query
    for column in ("id BIGINT PRIMARY KEY", "username VARCHAR(32)", "first_name VARCHAR(64) NOT NULL"):
        assert column in query
    for column in ("last_name VARCHAR(64)", "locale VARCHAR(2)", "registered_on DATE NOT NULL"):
        assert column in query
    assert "last_seen_on DATE NOT NULL" in query
