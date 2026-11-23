"""Queries to the users table."""

from datetime import date

from asyncpg import Record

from tgbot.db.pg_client import Executor, Row
from tgbot.misc.data_types import TgUser

__all__: tuple[str, ...] = ("UserRepo",)


class UserRepo:
    """
    Reads and writes the users table.

    Runs its queries on the pool, or on a transaction connection from PostgresClient.transaction().
    """

    def __init__(self, *, db: Executor) -> None:
        """
        Initializes the repository.

        :param db: The pool or a transaction connection to run the queries on.
        """
        self._db: Executor = db

    async def upsert(self, *, user: TgUser) -> None:
        """
        Adds a new user or refreshes the profile fields and last_seen_on of a known one.

        registered_on is written only when the row is created.

        :param user: The user as Telegram reports them now.
        :return: None
        """
        await self._db.execute(
            """
            INSERT INTO users (id, username, first_name, last_name, locale, registered_on, last_seen_on)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (id) DO UPDATE SET
                username = EXCLUDED.username,
                first_name = EXCLUDED.first_name,
                last_name = EXCLUDED.last_name,
                locale = EXCLUDED.locale,
                last_seen_on = EXCLUDED.last_seen_on
            """,
            *user,
        )

    async def get(self, *, user_id: int) -> TgUser | None:
        """
        Returns a user by Telegram ID.

        :param user_id: Telegram user ID.
        :return: The user, or None if they never wrote to the bot.
        """
        row: Record | None = await self._db.fetchrow(
            "SELECT id, username, first_name, last_name, locale, registered_on, last_seen_on FROM users WHERE id = $1",
            user_id,
        )
        return None if row is None else self._from_row(row=row)

    async def delete(self, *, user_id: int) -> None:
        """
        Deletes a user by Telegram ID; does nothing if there is no such user.

        :param user_id: Telegram user ID.
        :return: None
        """
        await self._db.execute("DELETE FROM users WHERE id = $1", user_id)

    @staticmethod
    def _from_row(*, row: Record) -> TgUser:
        """
        Converts a users row into a TgUser.

        :param row: Row with all the users columns.
        :return: The user.
        """
        typed: Row = Row(record=row)
        return TgUser(
            id=typed.get(column="id", kind=int),
            username=typed.get_optional(column="username", kind=str),
            first_name=typed.get(column="first_name", kind=str),
            last_name=typed.get_optional(column="last_name", kind=str),
            locale=typed.get_optional(column="locale", kind=str),
            registered_on=typed.get(column="registered_on", kind=date),
            last_seen_on=typed.get(column="last_seen_on", kind=date),
        )
