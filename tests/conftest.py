"""
Shared pytest fixtures: the throwaway test PostgreSQL and Redis.

Locally they are the WSL ones, in CI the service containers of the pytest workflow, both with the same
credentials. 127.0.0.1, never localhost: localhost resolves to ::1 first, and the WSL port relay is IPv4 only.
Tests create and drop their own tables and flush their own Redis database, never anything else.
"""

from collections.abc import AsyncIterator

import pytest
from pydantic import SecretStr
from redis.asyncio import Redis

from tgbot.db.pg_client import PostgresClient
from tgbot.misc.data_types import PostgresCredentials, RedisCredentials
from tgbot.storage.redis_client import RedisClient

__all__: tuple[str, ...] = ("TEST_POSTGRES", "TEST_REDIS")

TEST_POSTGRES: PostgresCredentials = PostgresCredentials(
    host="127.0.0.1", port=5432, database="test_db", user="test_user", password=SecretStr("test_password")
)
# Database 15: the test user's ACL allows FLUSHDB there
TEST_REDIS: RedisCredentials = RedisCredentials(
    host="127.0.0.1", port=6379, db=15, user="test_user", password=SecretStr("test_password")
)
# Every table the bot creates, dropped before and after each test that uses the database
_TABLES: tuple[str, ...] = ("users",)


@pytest.fixture(name="pg_client")
async def pg_client_fixture() -> AsyncIterator[PostgresClient]:
    """
    A connected client of the test PostgreSQL without the bot's tables, dropped again after the test.

    :return: The client.
    """
    client: PostgresClient = PostgresClient(credentials=TEST_POSTGRES)
    await client.connect()
    await client.pool.execute(f"DROP TABLE IF EXISTS {', '.join(_TABLES)}")
    yield client
    await client.pool.execute(f"DROP TABLE IF EXISTS {', '.join(_TABLES)}")
    await client.close()


@pytest.fixture(name="redis")
async def redis_fixture() -> AsyncIterator[Redis]:
    """
    A client of the test Redis database, empty before the test and flushed again after it.

    :return: The client.
    """
    redis: Redis = RedisClient(credentials=TEST_REDIS).redis
    await redis.flushdb()
    yield redis
    await redis.flushdb()
    await redis.aclose()
