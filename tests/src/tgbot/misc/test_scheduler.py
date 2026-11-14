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
    return Scheduler(config=config, broadcaster=broadcaster, tmpl=tmpl)


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


def test_start(scheduler: Scheduler) -> None:
    """
    Test that start() starts the scheduler without adding any job.

    :param scheduler: Instance of Scheduler to test.
    :return: None
    """
    with patch.object(target=scheduler._scheduler, attribute="start") as mock_start:
        scheduler.start()
        assert scheduler._scheduler.get_jobs() == []  # The template schedules no tasks
        mock_start.assert_called_once_with()


@pytest.mark.parametrize(("kwargs", "expected"), [({}, True), ({"wait": False}, False)])
def test_shutdown(*, scheduler: Scheduler, kwargs: dict[str, bool], expected: bool) -> None:
    """
    Test that shutdown() waits for the running jobs by default, or not if asked.

    :param scheduler: Instance of Scheduler to test.
    :param kwargs: Arguments passed to Scheduler.shutdown().
    :param expected: The wait value expected to reach the underlying scheduler.
    :return: None
    """
    with patch.object(target=scheduler._scheduler, attribute="shutdown") as mock_shutdown:
        scheduler.shutdown(**kwargs)
        mock_shutdown.assert_called_once_with(wait=expected)
