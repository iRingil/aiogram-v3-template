"""Tests of src/tgbot/db/schema.py against the test PostgreSQL."""

# ruff: noqa: S101

from typing import TYPE_CHECKING

from tgbot.db.pg_client import PostgresClient, Row
from tgbot.db.schema import Schema

if TYPE_CHECKING:
    from asyncpg import Record

__all__: tuple[str, ...] = ()


async def _columns(*, client: PostgresClient) -> dict[str, tuple[str, int | None, str]]:
    """
    Reads the columns of the users table from the catalog.

    :param client: The test client.
    :return: Type, maximum length and nullability by column name.
    """
    rows: list[Record] = await client.pool.fetch(
        """
        SELECT column_name, data_type, character_maximum_length, is_nullable
        FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'users'
        """
    )
    columns: dict[str, tuple[str, int | None, str]] = {}
    for record in rows:
        row: Row = Row(record=record)
        columns[row.get(column="column_name", kind=str)] = (
            row.get(column="data_type", kind=str),
            row.get_optional(column="character_maximum_length", kind=int),
            row.get(column="is_nullable", kind=str),
        )
    return columns


async def test_create(pg_client: PostgresClient) -> None:
    """
    create() makes the users table with Telegram's limits and the id as the primary key.

    :param pg_client: The test client.
    :return: None
    """
    await Schema(client=pg_client).create()
    assert await _columns(client=pg_client) == {
        "id": ("bigint", None, "NO"),
        "username": ("character varying", 32, "YES"),
        "first_name": ("character varying", 64, "NO"),
        "last_name": ("character varying", 64, "YES"),
        "locale": ("character varying", 2, "YES"),
        "registered_on": ("date", None, "NO"),
        "last_seen_on": ("date", None, "NO"),
    }
    primary_key: Record | None = await pg_client.pool.fetchrow(
        """
        SELECT a.attname AS name
        FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = 'users'::regclass AND i.indisprimary
        """
    )
    assert primary_key is not None
    assert Row(record=primary_key).get(column="name", kind=str) == "id"


async def test_create_keeps_an_existing_table(pg_client: PostgresClient) -> None:
    """
    A second create() leaves the table and its rows as they are.

    :param pg_client: The test client.
    :return: None
    """
    await Schema(client=pg_client).create()
    await pg_client.pool.execute(
        "INSERT INTO users (id, first_name, registered_on, last_seen_on) VALUES (1, 'Ann', CURRENT_DATE, CURRENT_DATE)"
    )
    await Schema(client=pg_client).create()
    count: Record | None = await pg_client.pool.fetchrow("SELECT count(*) AS n FROM users")
    assert count is not None
    assert Row(record=count).get(column="n", kind=int) == 1
