"""Unit tests for src/tgbot/misc/decorators.py."""

# ruff: noqa: PLR2004, S101

from asyncio import CancelledError
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from tgbot.misc.decorators import handle_exc, handle_telegram_exc

__all__: tuple = ()


@pytest.mark.asyncio
async def test_handle_telegram_exc_no_exception() -> None:
    """
    Test handle_telegram_exc decorator when no exception is raised.

    :return: None
    """

    @handle_telegram_exc
    async def test_func() -> int:
        """
        Test function that returns a value without raising an exception.

        :return: Integer value.
        """
        return 10

    result: int = await test_func()
    assert result == 10


@pytest.mark.asyncio
async def test_handle_telegram_exc_bad_request() -> None:
    """
    Test handle_telegram_exc decorator with TelegramBadRequest exception.

    :return: None
    """

    @handle_telegram_exc
    async def test_func(user_id: int) -> None:
        """
        Test function that raises TelegramBadRequest.

        :param user_id: User ID.
        :return: None
        :raises TelegramBadRequest: Simulated TelegramBadRequest exception.
        """
        raise TelegramBadRequest(message=f"Bad request for {user_id}", method=MagicMock())

    result: int | None = await test_func(user_id=123)
    assert result == 0


@pytest.mark.asyncio
async def test_handle_telegram_exc_forbidden_other() -> None:
    """
    Test handle_telegram_exc decorator with TelegramForbiddenError for other reasons.

    :return: None
    """

    @handle_telegram_exc
    async def test_func(user_id: int) -> None:
        """
        Test function that raises TelegramForbiddenError without bot blocked message.

        :param user_id: User ID.
        :return: None
        :raises TelegramForbiddenError: Simulated TelegramForbiddenError exception.
        """
        raise TelegramForbiddenError(message=f"Forbidden for {user_id}: other reason", method=MagicMock())

    result: int | None = await test_func(user_id=789)
    assert result == 0


@pytest.mark.asyncio
@patch(target="tgbot.misc.decorators.sleep", new_callable=AsyncMock)
async def test_handle_telegram_exc_retry_after(mock_sleep: AsyncMock) -> None:
    """
    Test handle_telegram_exc decorator with TelegramRetryAfter exception and retry logic.

    :param mock_sleep: A mocked sleep function
    :return: None
    """
    calls: list[int] = []

    @handle_telegram_exc
    async def test_func(user_id: int) -> int:
        """
        Test function that raises TelegramRetryAfter on first call and succeeds on retry.

        :param user_id: User ID
        :return: Integer value
        :raises TelegramRetryAfter: Simulated TelegramRetryAfter exception
        """
        calls.append(user_id)
        if len(calls) == 1:
            raise TelegramRetryAfter(retry_after=1, method=MagicMock(), message="Flood limit")
        return 10

    result: int = await test_func(user_id=789)
    assert result == 10
    assert calls == [789, 789]
    mock_sleep.assert_called_once_with(delay=1)


@pytest.mark.asyncio
async def test_handle_telegram_exc_api_error() -> None:
    """
    Test handle_telegram_exc decorator with TelegramAPIError exception.

    :return: None
    """

    @handle_telegram_exc
    async def test_func(user_id: int) -> None:
        """
        Test function that raises TelegramAPIError.

        :param user_id: User ID
        :return: None
        :raises TelegramAPIError: Simulated TelegramAPIError exception
        """
        raise TelegramAPIError(message=f"API error for {user_id}", method=MagicMock())

    result: int | None = await test_func(user_id=999)
    assert result == 0


@pytest.mark.asyncio
async def test_handle_telegram_exc_no_user_id() -> None:
    """
    Test handle_telegram_exc decorator when user_id is not provided.

    :return: None
    """

    @handle_telegram_exc
    async def test_func() -> None:
        """
        Test function that raises TelegramAPIError without user_id.

        :return: None
        :raises TelegramAPIError: Simulated TelegramAPIError exception
        """
        raise TelegramAPIError(message="API error", method=MagicMock())

    result: int | None = await test_func()
    assert result == 0


@pytest.mark.asyncio
async def test_handle_exc_no_exception() -> None:
    """
    Test handle_exc decorator when no exception is raised.

    :return: None
    """

    @handle_exc
    async def test_func() -> int:
        """
        Test function that returns a value without raising an exception.

        :return: Integer value
        """
        return 20

    result: int | None = await test_func()
    assert result == 20


@pytest.mark.asyncio
async def test_handle_exc_cancelled_error() -> None:
    """
    Test handle_exc decorator with CancelledError exception.

    :return: None
    """

    @handle_exc
    async def test_func() -> None:
        """
        Test function that raises CancelledError.

        :return: None
        :raises CancelledError: Simulated CancelledError exception
        """
        raise CancelledError("Cancelled")

    result: None = await test_func()
    assert result is None


@pytest.mark.asyncio
async def test_handle_exc_generic_exception() -> None:
    """
    Test handle_exc decorator with a generic exception.

    :return: None
    """

    @handle_exc
    async def test_func() -> None:
        """
        Test function that raises a generic ValueError.

        :return: None
        :raises ValueError: Simulated ValueError exception
        """
        raise ValueError("Generic error")

    result: None = await test_func()
    assert result is None
