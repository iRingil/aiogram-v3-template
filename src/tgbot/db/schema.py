"""Creates the database tables that don't exist yet."""

from tgbot.db.client import PostgresClient

__all__: tuple[str, ...] = ("Schema",)


class Schema:
    """
    Creates the tables on startup with CREATE TABLE IF NOT EXISTS.

    An existing table is left as it is: a change to a table is applied to the database by hand.
    """

    def __init__(self, *, client: PostgresClient) -> None:
        """
        Initializes the schema.

        :param client: Connected PostgreSQL client.
        """
        self._client: PostgresClient = client

    async def create(self) -> None:
        """
        Creates all the tables in one transaction.

        :return: None
        """
        async with self._client.transaction() as conn:
            await conn.execute(self._users())

    @staticmethod
    def _users() -> str:
        """
        Returns the query that creates the users table.

        Text limits are Telegram's: first name 1-64, last name 0-64, username 5-32 characters. Only the
        maximums are enforced: Telegram enforces the rest when a user sets them.

        :return: The CREATE TABLE query.
        """
        return """
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,           -- Telegram user ID
                username VARCHAR(32),            -- @username without the "@", NULL if unset
                first_name VARCHAR(64) NOT NULL,
                last_name VARCHAR(64),           -- NULL if unset
                locale VARCHAR(2),               -- first 2 characters of Telegram's language_code, or NULL
                registered_on DATE NOT NULL,     -- UTC date of the first update
                last_seen_on DATE NOT NULL       -- UTC date of the last day with an update
            )
        """
