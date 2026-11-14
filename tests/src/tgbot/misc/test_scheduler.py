"""Unit tests for src/tgbot/misc/scheduler.py."""

# ruff: noqa: S101, SLF001

from datetime import UTC
from unittest.mock import MagicMock, patch

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from tgbot.config import Config
from tgbot.misc.broadcaster import Broadcaster
from tgbot.misc.scheduler import Scheduler
from tgbot.misc.tmpl_render import TmplRender

__all__: tuple[str, ...] = ()


@pytest.fixture
def scheduler() -> Scheduler:
    """
    Provide a fresh Scheduler instance for each test.

    :return: Scheduler instance.
    """
    config: Config = MagicMock(spec=Config)
    broadcaster: Broadcaster = MagicMock(spec=Broadcaster)
    tmpl: TmplRender = MagicMock(spec=TmplRender)
    scheduler: Scheduler = Scheduler(config=config, broadcaster=broadcaster, tmpl=tmpl)
    return scheduler


def test_init(scheduler: Scheduler) -> None:
    """
    Test initialization of Scheduler.

    :param scheduler: Instance of Scheduler to test.
    :return: None
    """
    assert isinstance(scheduler._scheduler, AsyncIOScheduler)
    assert scheduler._scheduler.timezone == UTC
    assert isinstance(scheduler._config, Config)
    assert isinstance(scheduler._broadcaster, Broadcaster)
    assert isinstance(scheduler._tmpl, TmplRender)


@pytest.mark.asyncio
async def test_schedule(scheduler: Scheduler) -> None:
    """
    Test scheduling of all tasks.

    :param scheduler: Instance of Scheduler to test.
    :return: None
    """
    with patch.object(target=scheduler._scheduler, attribute="start") as mock_start:
        await scheduler.schedule()
        assert scheduler._scheduler.get_jobs() == []  # The template schedules no tasks
        mock_start.assert_called_once()
