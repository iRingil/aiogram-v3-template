"""Tests of src/tgbot/db/users.py (UserRepo) against the test PostgreSQL."""

# ruff: noqa: S101

from datetime import date

import pytest

from tgbot.db.pg_client import PostgresClient
from tgbot.db.schema import Schema
from tgbot.db.users import UserRepo
from tgbot.misc.data_types import TgUser

__all__: tuple[str, ...] = ()

_USER: TgUser = TgUser(
    id=42,
    username="ann",
    first_name="Ann",
    last_name=None,
    locale="en",
    registered_on=date(year=2026, month=1, day=1),
    last_seen_on=date(year=2026, month=1, day=1),
)


@pytest.fixture(name="repo")
async def repo_fixture(pg_client: PostgresClient) -> UserRepo:
    """
    A UserRepo over the test PostgreSQL with an empty users table.

    :param pg_client: The test client.
    :return: The repository.
    """
    await Schema(client=pg_client).create()
    return UserRepo(db=pg_client.pool)


async def test_upsert_new_user(repo: UserRepo) -> None:
    """
    upsert() creates the row of a new user.

    :param repo: The repository.
    :return: None
    """
    await repo.upsert(user=_USER)
    assert await repo.get(user_id=42) == _USER


async def test_upsert_known_user(repo: UserRepo) -> None:
    """
    upsert() of a known user refreshes the profile and last_seen_on but keeps registered_on.

    :param repo: The repository.
    :return: None
    """
    await repo.upsert(user=_USER)
    later: TgUser = _USER._replace(
        username=None,
        first_name="Anna",
        last_name="Lee",
        locale="ru",
        registered_on=date(year=2026, month=3, day=1),
        last_seen_on=date(year=2026, month=3, day=1),
    )
    await repo.upsert(user=later)
    assert await repo.get(user_id=42) == later._replace(registered_on=_USER.registered_on)


async def test_get_missing(repo: UserRepo) -> None:
    """
    get() returns None for an unknown user.

    :param repo: The repository.
    :return: None
    """
    assert await repo.get(user_id=42) is None


async def test_delete(repo: UserRepo) -> None:
    """
    delete() removes the user; deleting an unknown user does nothing.

    :param repo: The repository.
    :return: None
    """
    await repo.upsert(user=_USER)
    await repo.delete(user_id=42)
    await repo.delete(user_id=42)
    assert await repo.get(user_id=42) is None


async def _upsert_then_fail(*, pg_client: PostgresClient) -> None:
    """
    Saves the user through a repository over a transaction connection, then fails inside the transaction.

    :param pg_client: The test client.
    :return: None
    :raises RuntimeError: always, from inside the transaction.
    """
    async with pg_client.transaction() as conn:
        await UserRepo(db=conn).upsert(user=_USER)
        raise RuntimeError("rollback")


async def test_works_inside_a_transaction(pg_client: PostgresClient, repo: UserRepo) -> None:
    """
    A repository over a transaction connection: a failed transaction leaves nothing behind.

    :param pg_client: The test client.
    :param repo: The repository over the pool, to check the result.
    :return: None
    """
    with pytest.raises(expected_exception=RuntimeError, match="rollback"):
        await _upsert_then_fail(pg_client=pg_client)
    assert await repo.get(user_id=42) is None
