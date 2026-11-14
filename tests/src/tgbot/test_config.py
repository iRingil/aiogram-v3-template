"""Unit tests for src/tgbot/config.py."""

# ruff: noqa: PLR2004, S101, S105

import os
import sys
from collections.abc import Generator, Sequence
from pathlib import Path
from typing import Any

import pytest
from environs import EnvError
from redis.asyncio import ConnectionPool, Redis

from tgbot.config import Config
from tgbot.misc.dataclasses import Paths, WebhookCredentials

__all__: tuple[str, ...] = ()

ENV_FILE_CONTENT: str = """
    BOT_TOKEN=testtoken
    ADMIN_IDS=123,456
    REDIS_HOST=localhost
    REDIS_PORT=6379
    REDIS_DB_INDEX=0
    REDIS_DB_PASS=testpass
    REDIS_DB_USER=testuser_redis
    REDIS_SOCKET_PATH=/var/run/redis/redis-server.sock
    WEBHOOK_HOST=webhook-host
    WEBHOOK_PATH=webhook-path
    WEBHOOK_TOKEN=webhook-token
    WEBAPP_HOST=app-host
    WEBAPP_PORT=8080
"""


# region Fixtures
@pytest.fixture
def env_file_path(tmp_path: Path) -> Generator[Path]:
    """
    Fixture to create a .env file one level above the base_dir (tmp_path).

    :param tmp_path: Temporary directory provided by pytest (represents base_dir).
    :return: Path to the created .env file.
    """
    env_p = tmp_path.parent / ".env"
    env_p.parent.mkdir(parents=True, exist_ok=True)
    env_p.write_text(data=ENV_FILE_CONTENT, encoding="utf-8")
    yield env_p
    if env_p.exists():
        env_p.unlink()


def _write_env(tmp_path: Path, flags: str = "", vars_to_remove: Sequence[str] = ()) -> None:
    """
    Writes the .env file one level above the base_dir (tmp_path).

    :param tmp_path: Temporary directory provided by pytest (represents base_dir).
    :param flags: Mode switches to add, one "NAME=value" per line.
    :param vars_to_remove: Variables to leave out of the file.
    :return: None
    """
    lines: list[str] = [*ENV_FILE_CONTENT.splitlines(), *flags.splitlines()]
    content: str = "\n".join(line for line in lines if not any(var in line for var in vars_to_remove))
    Path(tmp_path.parent, ".env").write_text(data=content, encoding="utf-8")


@pytest.fixture
def config_instance(tmp_path: Path, request: pytest.FixtureRequest) -> Config:
    """
    Fixture to create a Config instance with a populated .env file.

    :param tmp_path: Temporary directory provided by pytest.
    :param request: Pytest request object, used to create the .env file first.
    :return: Config instance with loaded environment variables.
    """
    request.getfixturevalue("env_file_path")
    return Config(base_dir=tmp_path)


@pytest.fixture(autouse=True)
def clear_env() -> Generator[None]:
    """
    Fixture to clear relevant environment variables before each test.

    :return: None
    """
    env_keys_to_clear: list[str] = [
        "DEBUG",
        "USE_WEBHOOK",
        "USE_REDIS",
        "USE_REDIS_SOCKET",
        "BOT_TOKEN",
        "ADMIN_IDS",
        "REDIS_HOST",
        "REDIS_PORT",
        "REDIS_DB_INDEX",
        "REDIS_DB_PASS",
        "REDIS_DB_USER",
        "REDIS_SOCKET_PATH",
        "WEBHOOK_HOST",
        "WEBHOOK_PATH",
        "WEBHOOK_TOKEN",
        "WEBAPP_HOST",
        "WEBAPP_PORT",
    ]
    original_values: dict[str, str | None] = {key: os.environ.get(key) for key in env_keys_to_clear}
    for key in env_keys_to_clear:
        if key in os.environ:
            del os.environ[key]
    yield
    # Restore original values
    for key, value in original_values.items():
        if value is not None:
            os.environ[key] = value
        elif key in os.environ:
            # If the key was added during the test but wasn't there originally
            del os.environ[key]


# endregion


# region Tests for Config
@pytest.mark.parametrize(
    ("flags", "exp_debug", "exp_tb_limit"),  # sys.tracebacklimit default is 1000
    [("DEBUG=true", True, 1000), ("DEBUG=false", False, 0), ("", False, 0)],
)
def test_config_debug(*, flags: str, exp_debug: bool, exp_tb_limit: int, tmp_path: Path) -> None:
    """
    Test that Config reads DEBUG from the .env file (false when absent) and sets sys.tracebacklimit by it.

    :param flags: Mode switches added to the .env file.
    :param exp_debug: Expected debug value.
    :param exp_tb_limit: Expected tracebacklimit value.
    :param tmp_path: Temporary directory provided by pytest.
    :return: None
    """
    _write_env(tmp_path=tmp_path, flags=flags)
    original_limit: int = getattr(sys, "tracebacklimit", 1000)
    sys.tracebacklimit = 1000
    try:
        config: Config = Config(base_dir=tmp_path)
        assert config.debug is exp_debug
        assert sys.tracebacklimit == exp_tb_limit
    finally:
        sys.tracebacklimit = original_limit


def test_config_log_dir(config_instance: Config, tmp_path: Path) -> None:
    """
    Test that the log files folder lies next to the .env file.

    :param config_instance: Fixture providing a Config instance.
    :param tmp_path: Temporary directory (used as base_dir in the fixture).
    :return: None
    """
    assert config_instance.log_dir == Path(tmp_path, "../logs")


def test_config_init_no_env_file(tmp_path: Path) -> None:
    """
    Test that Config raises FileNotFoundError when .env file is missing.

    :param tmp_path: Temporary directory provided by pytest (used as base_dir).
    :return: None
    """
    env_p: Path = Path(tmp_path.parent, ".env")
    if env_p.exists():
        env_p.unlink()
    with pytest.raises(expected_exception=FileNotFoundError, match=r"The \.env file was not found"):
        Config(base_dir=tmp_path)


def test_config_reads_env_variables(config_instance: Config) -> None:
    """
    Test that Config reads environment variables correctly using the fixture.

    :param config_instance: Fixture providing a Config instance.
    :return: None
    """
    assert config_instance.token == "testtoken"
    assert config_instance.admins == [123, 456]


def test_config_paths(config_instance: Config, tmp_path: Path) -> None:
    """
    Test that Config initializes file paths correctly relative to base_dir.

    :param config_instance: Fixture providing a Config instance.
    :param tmp_path: Temporary directory (used as base_dir in the fixture).
    :return: None
    """
    expected_locale: Path = Path(tmp_path, "locales")
    expected_logo: Path = Path(tmp_path, "assets/img/bot_logo.jpg")
    expected_temp: Path = Path(tmp_path, "temp")
    expected_tmpl: Path = Path(tmp_path, "templates")
    assert isinstance(config_instance.paths, Paths)
    assert config_instance.paths.locale == expected_locale
    assert config_instance.paths.bot_logo == expected_logo
    assert config_instance.paths.temp == expected_temp
    assert config_instance.paths.tmpl == expected_tmpl
    assert expected_locale.exists()
    assert expected_temp.exists()
    assert expected_tmpl.exists()


@pytest.mark.parametrize(
    ("use_redis", "use_redis_socket", "expect_redis"),
    [(False, False, False), (True, False, True), (True, True, True), (False, True, False)],
)
def test_config_redis(*, use_redis: bool, use_redis_socket: bool, expect_redis: bool, tmp_path: Path) -> None:
    """
    Test that Config initializes Redis correctly based on the USE_REDIS and USE_REDIS_SOCKET switches.

    :param use_redis: Value of USE_REDIS in the .env file.
    :param use_redis_socket: Value of USE_REDIS_SOCKET in the .env file.
    :param expect_redis: Whether Redis should be initialized (True) or not (False).
    :param tmp_path: Temporary directory provided by pytest.
    :return: None
    """
    _write_env(tmp_path=tmp_path, flags=f"USE_REDIS={use_redis}\nUSE_REDIS_SOCKET={use_redis_socket}")
    config: Config = Config(base_dir=tmp_path)
    if expect_redis:
        redis = config.redis
        assert isinstance(redis, Redis)
        pool = redis.connection_pool
        assert isinstance(pool, ConnectionPool)
        conn_kwargs: dict[str, Any] = pool.connection_kwargs
        if use_redis_socket:
            assert conn_kwargs.get("path") == "/var/run/redis/redis-server.sock"
            assert conn_kwargs.get("host") is None
            assert conn_kwargs.get("port") is None
        else:
            assert conn_kwargs.get("host") == "localhost"
            assert conn_kwargs.get("port") == 6379
            assert conn_kwargs.get("path") is None
        assert conn_kwargs.get("db") == 0
        assert conn_kwargs.get("password") == "testpass"
        assert conn_kwargs.get("username") == "testuser_redis"
    else:
        assert config.redis is None


@pytest.mark.parametrize(("use_webhook", "expect_webhook"), [(False, False), (True, True)])
def test_config_webhook(*, use_webhook: bool, expect_webhook: bool, tmp_path: Path) -> None:
    """
    Test that Config initializes webhook correctly based on the USE_WEBHOOK switch.

    :param use_webhook: Value of USE_WEBHOOK in the .env file.
    :param expect_webhook: Whether webhook should be initialized (True) or not (False).
    :param tmp_path: Temporary directory provided by pytest.
    :return: None
    """
    _write_env(tmp_path=tmp_path, flags=f"USE_WEBHOOK={use_webhook}")
    config: Config = Config(base_dir=tmp_path)
    if expect_webhook:
        webhook = config.webhook
        assert isinstance(webhook, WebhookCredentials)
        assert webhook.wh_host == "webhook-host"
        assert webhook.wh_path == "webhook-path"
        assert webhook.wh_token == "webhook-token"
        assert webhook.app_host == "app-host"
        assert webhook.app_port == 8080
    else:
        assert config.webhook is None


# endregion


# region Tests for errors EnvError
@pytest.mark.parametrize(
    ("env_vars_to_remove", "error_message_match"),
    [
        (["ADMIN_IDS"], "Admin IDs not found"),
        (["BOT_TOKEN"], "BOT_TOKEN not found"),
        (["REDIS_HOST"], "Redis credentials not found"),
        (["WEBHOOK_HOST"], "Webhook credentials not found"),
    ],
)
def test_config_missing_env_var(tmp_path: Path, env_vars_to_remove: list[str], error_message_match: str) -> None:
    """
    Test that Config raises EnvError when essential environment variables are missing.

    :param tmp_path: Temporary directory provided by pytest.
    :param env_vars_to_remove: List of environment variables to remove from the content.
    :param error_message_match: Expected substring in the error message.
    :return: None
    """
    _write_env(tmp_path=tmp_path, flags="USE_REDIS=true\nUSE_WEBHOOK=true", vars_to_remove=env_vars_to_remove)
    with pytest.raises(expected_exception=EnvError, match=error_message_match):
        Config(base_dir=tmp_path)


def test_config_missing_redis_socket_path(tmp_path: Path) -> None:
    """
    Test missing socket path when USE_REDIS and USE_REDIS_SOCKET are true.

    :param tmp_path: Temporary directory provided by pytest.
    :return: None
    """
    _write_env(tmp_path=tmp_path, flags="USE_REDIS=true\nUSE_REDIS_SOCKET=true", vars_to_remove=["REDIS_SOCKET_PATH"])
    with pytest.raises(expected_exception=EnvError, match="Redis credentials not found"):
        Config(base_dir=tmp_path)


# endregion
