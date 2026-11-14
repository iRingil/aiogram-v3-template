"""The module allows running tasks on a schedule."""

from datetime import UTC

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from tgbot.config import Config
from tgbot.misc.broadcaster import Broadcaster
from tgbot.misc.tmpl_render import TmplRender

__all__: tuple[str] = ("Scheduler",)


class Scheduler:
    """
    Thin wrapper around a single AsyncIOScheduler instance (UTC).

    Add the jobs in start(), before the scheduler itself is started, for example:
    self._scheduler.add_job(func=self._job, trigger="cron", minute="*", second=0, max_instances=1).
    APScheduler is untyped, so add_job needs `# pyright: ignore[reportUnknownMemberType]`.
    """

    def __init__(self, config: Config, broadcaster: Broadcaster, tmpl: TmplRender) -> None:
        """
        Initialize the necessary parameters.

        :param config: Config object with configuration parameters.
        :param broadcaster: Broadcaster object for broadcasting messages.
        :param tmpl: TmplRender object for rendering templates.
        """
        self._scheduler: AsyncIOScheduler = AsyncIOScheduler(timezone=UTC)
        self._config: Config = config
        self._broadcaster: Broadcaster = broadcaster
        self._tmpl: TmplRender = tmpl

    def start(self) -> None:
        """
        Adds the jobs and starts the scheduler.

        :return: None
        """
        self._scheduler.start()

    def shutdown(self, *, wait: bool = True) -> None:
        """
        Stops the scheduler.

        :param wait: If True, waits for the running jobs to finish before returning.
        :return: None
        """
        self._scheduler.shutdown(wait=wait)
