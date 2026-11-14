"""Setting up the configuration for the application."""

import sys
from pathlib import Path

from environs import Env, EnvError
from loguru import logger
from redis.asyncio import Redis

from tgbot.misc.dataclasses import Paths, WebhookCredentials

__all__: tuple[str, ...] = ("Config", "logger")


_BASE_DIR: Path = Path(__file__).resolve().parent  # Path settings


class Config:
    """
    Reads variables from the .env file.

    The mode switches are read from it too, all false when absent: DEBUG (verbose logging and full
    tracebacks), USE_WEBHOOK (a webhook instead of long polling), USE_REDIS (Redis FSM storage
    instead of memory) and USE_REDIS_SOCKET (connect to Redis over a Unix socket).
    """

    def __init__(self, *, base_dir: Path = _BASE_DIR) -> None:
        """
        Initializing a class or raises an exception if the .env file is not found.

        :param base_dir: Path to the base directory of the application.
        :raises FileNotFoundError: if the .env file is not found.
        """
        self._env_path: Path = Path(base_dir, "../.env")
        if not self._env_path.exists():
            raise FileNotFoundError(f"The .env file was not found in the path: {self._env_path}")
        self._env: Env = Env()
        self._env.read_env(path=self._env_path, recurse=False)
        self._debug: bool = self._env.bool("DEBUG", default=False)
        if not self._debug:
            sys.tracebacklimit = 0
        self._log_dir: Path = Path(base_dir, "../logs")
        self._admins: list[int] = self._get_admins()
        self._paths: Paths = self._get_paths(base_dir=base_dir)
        self._redis: Redis | None = self._get_redis(
            use_redis=self._env.bool("USE_REDIS", default=False),
            use_socket=self._env.bool("USE_REDIS_SOCKET", default=False),
        )
        self._token: str = self._get_token()
        self._webhook: WebhookCredentials | None = self._get_webhook(
            use_webhook=self._env.bool("USE_WEBHOOK", default=False)
        )

    @property
    def debug(self) -> bool:
        """
        Returns whether the bot runs in debug mode (verbose logging, full tracebacks).

        :return: True if debug mode is enabled.
        """
        return self._debug

    @property
    def log_dir(self) -> Path:
        """
        Returns the path to the log files folder.

        :return: Path to the log files folder.
        """
        return self._log_dir

    @property
    def admins(self) -> list[int]:
        """
        Returns bots admins IDs.

        :return: list with bot admins IDs.
        """
        return self._admins

    def _get_admins(self) -> list[int]:
        """
        Returns the list of bot admin IDs.

        :return: list of bot admin IDs.
        :raises EnvError: if the admin IDs are not found in the .env file.
        """
        try:
            return self._env.list("ADMIN_IDS", subcast=int)
        except EnvError as exc:
            raise EnvError(f"Admin IDs not found in the .env file: {exc!r}") from exc

    @staticmethod
    def _get_paths(base_dir: Path) -> Paths:
        """
        Returns the paths to the folders used in the program.

        :param base_dir: Path to the base directory of the application.
        :return: Paths object.
        """
        locale: Path = Path(base_dir, "locales")
        logo: Path = Path(base_dir, "assets/img/bot_logo.jpg")
        temp: Path = Path(base_dir, "temp")
        tmpl: Path = Path(base_dir, "templates")
        locale.mkdir(exist_ok=True)
        temp.mkdir(exist_ok=True)
        tmpl.mkdir(exist_ok=True)
        return Paths(locale=locale, bot_logo=logo, temp=temp, tmpl=tmpl)

    @property
    def paths(self) -> Paths:
        """
        Returns the paths to the folders used in the program.

        :return: Paths object.
        """
        return self._paths

    def _get_redis(self, *, use_redis: bool, use_socket: bool) -> Redis | None:
        """
        Returns an instance of the Redis class to connect to the database.

        :param use_redis: True, if Redis is used, otherwise False.
        :param use_socket: True, if a Redis socket is used, otherwise False.
        :return: Redis instance or None.
        :raises EnvError: if the Redis credentials are not found in the .env file.
        """
        if not use_redis:
            return None
        try:
            db: int = self._env.int("REDIS_DB_INDEX")
            password: str = self._env.str("REDIS_DB_PASS")
            username: str = self._env.str("REDIS_DB_USER")
            if use_socket:
                unix_socket_path: str = self._env.str("REDIS_SOCKET_PATH")
                return Redis(db=db, password=password, unix_socket_path=unix_socket_path, username=username)
            host: str = self._env.str("REDIS_HOST")
            port: int = self._env.int("REDIS_PORT")
        except EnvError as exc:
            raise EnvError(f"Redis credentials not found in the .env file: {exc!r}") from exc
        return Redis(host=host, port=port, db=db, password=password, username=username)

    @property
    def redis(self) -> Redis | None:
        """
        Returns an instance of the Redis class to connect to the database.

        :return: Redis instance or None.
        """
        return self._redis

    def _get_token(self) -> str:
        """
        Returns the bot token or terminates the program in case of an error.

        :return: Telegram bot token.
        :raises EnvError: if the bot token is not found in the .env file.
        """
        try:
            return self._env.str("BOT_TOKEN")
        except EnvError as exc:
            raise EnvError(f"BOT_TOKEN not found: {exc!r}") from exc

    @property
    def token(self) -> str:
        """
        Returns the bot token.

        :return: Telegram bot token.
        """
        return self._token

    def _get_webhook(self, *, use_webhook: bool) -> WebhookCredentials | None:
        """
        Returns the credentials to use webhook.

        :param use_webhook: True, if webhook is used, otherwise False.
        :return: WebhookCredentials or None.
        :raises EnvError: if the webhook credentials are not found in the .env file.
        """
        if not use_webhook:
            return None
        try:
            return WebhookCredentials(
                wh_host=self._env.str("WEBHOOK_HOST"),
                wh_path=self._env.str("WEBHOOK_PATH"),
                wh_token=self._env.str("WEBHOOK_TOKEN"),
                app_host=self._env.str("WEBAPP_HOST"),
                app_port=self._env.int("WEBAPP_PORT"),
            )
        except EnvError as exc:
            raise EnvError(f"Webhook credentials not found in the .env file: {exc!r}") from exc

    @property
    def webhook(self) -> WebhookCredentials | None:
        """
        Returns the credentials to use webhook.

        :return: WebhookCredentials or None.
        """
        return self._webhook
