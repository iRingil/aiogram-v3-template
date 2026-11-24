"""Module for working with data."""

import re
from datetime import date
from ipaddress import ip_address
from pathlib import Path
from typing import Annotated, ClassVar, NamedTuple, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    NonNegativeInt,
    SecretStr,
    model_validator,
)

__all__: tuple[str, ...] = ("Paths", "PostgresCredentials", "RedisCredentials", "TgUser", "WebhookCredentials")


# A host name by RFC 1123: dot-separated labels of letters, digits and inner hyphens, at most 253 characters
_HOSTNAME: re.Pattern[str] = re.compile(
    r"(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))*", re.IGNORECASE
)
# Telegram setWebhook secret_token: 1-256 characters, only A-Z, a-z, 0-9, "_" and "-"
_SECRET_TOKEN: re.Pattern[str] = re.compile(r"[A-Za-z0-9_-]{1,256}")


def _validate_host(value: str) -> str:
    """
    Accepts an IPv4 address, an IPv6 address or a host name.

    :param value: The host.
    :return: The host unchanged.
    :raises ValueError: if the value is neither an IP address nor a valid host name.
    """
    try:
        ip_address(value)
    except ValueError:
        if not _HOSTNAME.fullmatch(value):
            raise ValueError(f"'{value}' is neither an IP address nor a valid host name") from None
    return value


def _validate_https(value: HttpUrl) -> HttpUrl:
    """
    Accepts only an HTTPS URL: Telegram sends webhook updates over HTTPS only.

    :param value: The URL.
    :return: The URL unchanged.
    :raises ValueError: if the scheme is not https.
    """
    if value.scheme != "https":
        raise ValueError(f"'{value}' is not an HTTPS URL")
    return value


def _validate_socket_path(value: Path) -> Path:
    """
    Accepts a socket path that is not empty: an empty value in the .env file would point to the current folder.

    :param value: The path.
    :return: The path unchanged.
    :raises ValueError: if the path is empty.
    """
    if value == Path():
        raise ValueError("The socket path is empty")
    return value


def _validate_secret_token(value: SecretStr) -> SecretStr:
    """
    Accepts a webhook secret token in the format Telegram allows.

    :param value: The token.
    :return: The token unchanged.
    :raises ValueError: if the token is not 1-256 characters of Latin letters, digits, '_' and '-'.
    """
    if not _SECRET_TOKEN.fullmatch(value.get_secret_value()):
        raise ValueError("The webhook token must be 1-256 characters of A-Z, a-z, 0-9, '_' and '-'")
    return value


type _Host = Annotated[str, AfterValidator(_validate_host)]
type _Port = Annotated[int, Field(gt=0, le=65535)]
type _NonEmptyStr = Annotated[str, Field(min_length=1)]
type _SocketPath = Annotated[Path, AfterValidator(_validate_socket_path)]


# region TelegramBot
class Paths(NamedTuple):
    """
    A class to represent paths to folders and files used in the program.

    :param locale: Path to the folder containing localization files.
    :param bot_logo: Path to the file containing the bot logo.
    :param temp: Path to the folder containing temporary files.
    :param tmpl: Path to the folder containing Jinja2 templates.
    """

    locale: Path
    bot_logo: Path
    temp: Path
    tmpl: Path


class WebhookCredentials(BaseModel):
    """
    A class to represent data to be used by the webhook connection in the Telegram bot.

    :cvar model_config: Frozen: the values don't change after the config is read.
    :param wh_host: Public HTTPS address of the bot, without the path.
    :param wh_path: Webhook path, without the leading "/": slash-separated segments of Latin letters, digits, '_', '-'.
    :param wh_token: Secret token Telegram sends in every webhook request.
    :param app_host: Address the webapp listens on.
    :param app_port: Port the webapp listens on.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    wh_host: Annotated[HttpUrl, AfterValidator(_validate_https)]
    wh_path: Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*$")]
    wh_token: Annotated[SecretStr, AfterValidator(_validate_secret_token)]
    app_host: _Host
    app_port: _Port


# endregion


# region Database
class RedisCredentials(BaseModel):
    """
    A class to represent data to be used by the Redis connection: host and port, or a Unix socket.

    :cvar model_config: Frozen: the values don't change after the config is read.
    :param host: Server host, or None for a Unix socket.
    :param port: Server port, or None for a Unix socket.
    :param socket_path: Path of the Unix socket file, or None for host and port.
    :param db: Database index.
    :param user: Database user.
    :param password: Database user password.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    host: _Host | None = None
    port: _Port | None = None
    socket_path: _SocketPath | None = None
    db: NonNegativeInt
    user: _NonEmptyStr
    password: SecretStr

    @model_validator(mode="after")
    def _validate_address(self) -> Self:
        """
        Ensures there is either a socket path or both a host and a port.

        :return: The instance of the model.
        :raises ValueError: if neither is set.
        """
        if self.socket_path is None and (self.host is None or self.port is None):
            raise ValueError("Redis needs either a socket path or both a host and a port")
        return self


class PostgresCredentials(BaseModel):
    """
    A class to represent data to be used by the PostgreSQL connection: host and port, or a Unix socket.

    :cvar model_config: Frozen: the values don't change after the config is read.
    :param host: Server host, or None for a Unix socket.
    :param port: Server port, or None for a Unix socket.
    :param socket_path: Path of the Unix socket file (e.g. /var/run/postgresql/.s.PGSQL.5432), or None for host
        and port.
    :param database: Database name.
    :param user: Database user.
    :param password: Database user password.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)

    host: _Host | None = None
    port: _Port | None = None
    socket_path: _SocketPath | None = None
    database: _NonEmptyStr
    user: _NonEmptyStr
    password: SecretStr

    @model_validator(mode="after")
    def _validate_address(self) -> Self:
        """
        Ensures there is either a socket path or both a host and a port.

        :return: The instance of the model.
        :raises ValueError: if neither is set.
        """
        if self.socket_path is None and (self.host is None or self.port is None):
            raise ValueError("PostgreSQL needs either a socket path or both a host and a port")
        return self


class TgUser(NamedTuple):
    """
    A row of the users table: a Telegram user who has written to the bot.

    :param id: Telegram user ID.
    :param username: Telegram @username without the "@", or None if unset.
    :param first_name: Telegram first name.
    :param last_name: Telegram last name, or None if unset.
    :param locale: Language code reported by Telegram (e.g. "en", "pt-br"), or None if not reported.
    :param registered_on: UTC date of the first update from the user.
    :param last_seen_on: UTC date of the last day the user wrote to the bot.
    """

    id: int
    username: str | None
    first_name: str
    last_name: str | None
    locale: str | None
    registered_on: date
    last_seen_on: date


# endregion
