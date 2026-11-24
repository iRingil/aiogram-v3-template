"""Tests of src/tgbot/storage/synced_users.py against the test Redis."""

# ruff: noqa: S101

from datetime import UTC, date, datetime

from redis.asyncio import Redis

from tgbot.storage.synced_users import SyncedUsers

__all__: tuple[str, ...] = ()

# A moment one hour and a half before the end of a UTC day
_NOW: datetime = datetime(year=2026, month=1, day=1, hour=22, minute=30, tzinfo=UTC)


async def test_unknown_user_is_not_synced(redis: Redis) -> None:
    """
    A user never marked is not synced.

    :param redis: The test Redis client.
    :return: None
    """
    assert not await SyncedUsers(redis=redis).is_synced(user_id=7, day=_NOW.date())


async def test_mark_holds_for_that_day_only(redis: Redis) -> None:
    """
    A marked user is synced on that day and not on the next one; other users are not affected.

    :param redis: The test Redis client.
    :return: None
    """
    synced: SyncedUsers = SyncedUsers(redis=redis)
    await synced.mark(user_id=7, now=_NOW)
    assert await synced.is_synced(user_id=7, day=_NOW.date())
    assert not await synced.is_synced(user_id=7, day=date(year=2026, month=1, day=2))
    assert not await synced.is_synced(user_id=8, day=_NOW.date())


async def test_mark_expires_at_the_end_of_the_day(redis: Redis) -> None:
    """
    The mark expires at the next UTC midnight: 1.5 hours after 22:30, so Redis removes it by itself.

    :param redis: The test Redis client.
    :return: None
    """
    await SyncedUsers(redis=redis).mark(user_id=7, now=_NOW)
    assert 0 < await redis.ttl(name="tgbot_synced:7") <= 90 * 60


async def test_mark_right_before_midnight_still_expires(redis: Redis) -> None:
    """
    A mark made in the last fraction of a second of a day gets at least a second to live, never a zero TTL.

    :param redis: The test Redis client.
    :return: None
    """
    late: datetime = datetime(year=2026, month=1, day=1, hour=23, minute=59, second=59, microsecond=999_999, tzinfo=UTC)
    await SyncedUsers(redis=redis).mark(user_id=7, now=late)
    assert await redis.ttl(name="tgbot_synced:7") == 1


async def test_forget(redis: Redis) -> None:
    """
    A forgotten user is no longer synced, so the next update saves them again.

    :param redis: The test Redis client.
    :return: None
    """
    synced: SyncedUsers = SyncedUsers(redis=redis)
    await synced.mark(user_id=7, now=_NOW)
    await synced.forget(user_id=7)
    assert not await synced.is_synced(user_id=7, day=_NOW.date())
