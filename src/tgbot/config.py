"""Setting up the configuration for the application."""

import sys
from pathlib import Path

from environs import Env, EnvError
from loguru import logger
from pydantic import PositiveInt, SecretStr, TypeAdapter, ValidationError

from tgbot.misc.data_types import Paths, PostgresCredentials, RedisCredentials, WebhookCredentials

__all__: tuple[str, ...] = ("Config", "logger")


_BASE_DIR: Path = Path(__file__).resolve().parent  # Path settings


class Config:
    """
    Reads variables from the .env file.

    The mode switches are read from it too, all false when absent: DEBUG (verbose logging and full
    tracebacks), USE_WEBHOOK (a webhook instead of long polling), USE_REDIS (Redis FSM storage
    instead of memory), USE_REDIS_SOCKET (connect to Redis over a Unix socket) and
    USE_POSTGRES_SOCKET (connect to PostgreSQL over a Unix socket).
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
        self._redis: RedisCredentials | None = self._get_redis(
            use_redis=self._env.bool("USE_REDIS", default=False),
            use_socket=self._env.bool("USE_REDIS_SOCKET", default=False),
        )
        self._postgres: PostgresCredentials = self._get_postgres(
            use_socket=self._env.bool("USE_POSTGRES_SOCKET", default=False)
        )
        self._token: SecretStr = self._get_token()
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
        :raises EnvError: if the admin IDs are not found in the .env file or are not positive integers.
        """
        try:
            return TypeAdapter(list[PositiveInt]).validate_python(self._env.list("ADMIN_IDS", subcast=int))
        except (EnvError, ValidationError) as exc:
            raise EnvError(f"Admin IDs not found or invalid in the .env file: {exc!r}") from exc

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

    def _get_redis(self, *, use_redis: bool, use_socket: bool) -> RedisCredentials | None:
        """
        Returns the Redis connection parameters.

        :param use_redis: True, if Redis is used, otherwise False.
        :param use_socket: True, if a Redis socket is used, otherwise False.
        :return: RedisCredentials or None.
        :raises EnvError: if the Redis credentials are not found in the .env file or are invalid.
        """
        if not use_redis:
            return None
        try:
            values: dict[str, object] = {
                "db": self._env.int("REDIS_DB_INDEX"),
                "user": self._env.str("REDIS_DB_USER"),
                "password": self._env.str("REDIS_DB_PASS"),
            }
            if use_socket:
                values["socket_path"] = self._env.str("REDIS_SOCKET_PATH")
            else:
                values["host"] = self._env.str("REDIS_HOST")
                values["port"] = self._env.int("REDIS_PORT")
            return RedisCredentials.model_validate(values)
        except (EnvError, ValidationError) as exc:
            raise EnvError(f"Redis credentials not found or invalid in the .env file: {exc!r}") from exc

    @property
    def redis(self) -> RedisCredentials | None:
        """
        Returns the Redis connection parameters.

        :return: RedisCredentials or None.
        """
        return self._redis

    def _get_postgres(self, *, use_socket: bool) -> PostgresCredentials:
        """
        Returns the PostgreSQL connection parameters.

        :param use_socket: True, if a PostgreSQL socket is used, otherwise False.
        :return: PostgresCredentials.
        :raises EnvError: if the PostgreSQL credentials are not found in the .env file or are invalid.
        """
        try:
            values: dict[str, object] = {
                "database": self._env.str("PG_DB_NAME"),
                "user": self._env.str("PG_DB_USER"),
                "password": self._env.str("PG_DB_PASS"),
            }
            if use_socket:
                values["socket_path"] = self._env.str("PG_SOCKET_PATH")
            else:
                values["host"] = self._env.str("PG_HOST")
                values["port"] = self._env.int("PG_PORT")
            return PostgresCredentials.model_validate(values)
        except (EnvError, ValidationError) as exc:
            raise EnvError(f"PostgreSQL credentials not found or invalid in the .env file: {exc!r}") from exc

    @property
    def postgres(self) -> PostgresCredentials:
        """
        Returns the PostgreSQL connection parameters.

        :return: PostgresCredentials.
        """
        return self._postgres

    def _get_token(self) -> SecretStr:
        """
        Returns the bot token or terminates the program in case of an error.

        :return: Telegram bot token.
        :raises EnvError: if the bot token is not found in the .env file.
        """
        try:
            return SecretStr(self._env.str("BOT_TOKEN"))
        except EnvError as exc:
            raise EnvError(f"BOT_TOKEN not found: {exc!r}") from exc

    @property
    def token(self) -> SecretStr:
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
        :raises EnvError: if the webhook credentials are not found in the .env file or are invalid.
        """
        if not use_webhook:
            return None
        try:
            return WebhookCredentials.model_validate(
                {
                    "wh_host": self._env.str("WEBHOOK_HOST"),
                    "wh_path": self._env.str("WEBHOOK_PATH"),
                    "wh_token": self._env.str("WEBHOOK_TOKEN"),
                    "app_host": self._env.str("WEBAPP_HOST"),
                    "app_port": self._env.int("WEBAPP_PORT"),
                }
            )
        except (EnvError, ValidationError) as exc:
            raise EnvError(f"Webhook credentials not found or invalid in the .env file: {exc!r}") from exc

    @property
    def webhook(self) -> WebhookCredentials | None:
        """
        Returns the credentials to use webhook.

        :return: WebhookCredentials or None.
        """
        return self._webhook
