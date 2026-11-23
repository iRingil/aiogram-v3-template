"""Unit tests for src/tgbot/db/users.py (UserRepo)."""

# ruff: noqa: PLR2004, S101

from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

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
    last_seen_on=date(year=2026, month=1, day=2),
)


@pytest.fixture(name="db")
def db_fixture() -> MagicMock:
    """
    A mock pool or connection with awaitable query methods.

    :return: The mock executor.
    """
    db: MagicMock = MagicMock()
    db.execute = AsyncMock()
    db.fetchrow = AsyncMock()
    return db


async def test_upsert(db: MagicMock) -> None:
    """
    upsert() inserts the user, and on a known ID updates everything but registered_on.

    :param db: The mock executor.
    :return: None
    """
    await UserRepo(db=db).upsert(user=_USER)
    db.execute.assert_awaited_once()
    query: str = db.execute.await_args.args[0]
    assert "INSERT INTO users" in query
    assert "ON CONFLICT (id) DO UPDATE" in query
    assert "registered_on = " not in query
    assert db.execute.await_args.args[1:] == tuple(_USER)


async def test_get_found(db: MagicMock) -> None:
    """
    get() converts the row into a TgUser.

    :param db: The mock executor.
    :return: None
    """
    record: MagicMock = MagicMock()
    record.__getitem__.side_effect = _USER._asdict().__getitem__
    db.fetchrow.return_value = record
    assert await UserRepo(db=db).get(user_id=42) == _USER
    assert db.fetchrow.await_args.args[1] == 42


async def test_get_missing(db: MagicMock) -> None:
    """
    get() returns None for an unknown user.

    :param db: The mock executor.
    :return: None
    """
    db.fetchrow.return_value = None
    assert await UserRepo(db=db).get(user_id=42) is None


async def test_delete(db: MagicMock) -> None:
    """
    delete() deletes the user by ID.

    :param db: The mock executor.
    :return: None
    """
    await UserRepo(db=db).delete(user_id=42)
    db.execute.assert_awaited_once_with("DELETE FROM users WHERE id = $1", 42)
