"""The module implements the decorators used in the application."""

import sys
from asyncio import CancelledError, sleep
from collections.abc import Awaitable, Callable, Coroutine
from functools import wraps
from traceback import format_exc

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

from tgbot.config import logger

__all__: tuple[str, ...] = ("handle_exc", "handle_telegram_exc")


def handle_telegram_exc[**P, R](func: Callable[P, Awaitable[R]]) -> Callable[P, Coroutine[None, None, R | int]]:
    """
    Async decorator to handle Telegram API exceptions.

    :param func: The asynchronous function to wrap.
    :return: The wrapped asynchronous function.
    """

    @wraps(wrapped=func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | int:
        """
        Wrapper function to catch and handle exceptions during the execution of the wrapped function.

        :param args: Positional arguments for the wrapped function.
        :param kwargs: Keyword arguments for the wrapped function.
        :return: The result of the wrapped function (message ID) or 0 in case of an exception.
        """
        try:
            return await func(*args, **kwargs)
        except TelegramForbiddenError as exc:
            logger.error(f"Target [ID:{kwargs.get('user_id')}]: failed with error {exc}")
        except TelegramBadRequest as exc:
            logger.error(f"Target [ID:{kwargs.get('user_id')}]: failed with error {exc}")
        except TelegramRetryAfter as exc:
            logger.warning(f"Target [ID:{kwargs.get('user_id')}]: Flood limit, sleep {exc.retry_after} sec.")
            await sleep(delay=exc.retry_after)
            return await wrapper(*args, **kwargs)
        except TelegramAPIError as exc:
            logger.error(f"Target [ID:{kwargs.get('user_id')}]: failed with error {exc}")
        return 0

    return wrapper


def handle_exc[**P, R](func: Callable[P, Awaitable[R]]) -> Callable[P, Coroutine[None, None, R | None]]:
    """
    A decorator that catches exceptions in an async function.

    :param func: The asynchronous function to decorate.
    :return: The decorated function with error handling.
    """

    @wraps(wrapped=func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
        """
        Wraps the decorated async function and handles exceptions.

        :param args: Positional arguments passed to the wrapped function.
        :param kwargs: Keyword arguments passed to the wrapped function.
        :return: The result of the wrapped async function, or None if it raised or was canceled.
        """
        try:
            return await func(*args, **kwargs)
        except CancelledError:
            pass
        except Exception as exc:  # noqa: BLE001 - logs any failure of a background task
            tb: str = f"\n{format_exc()}" if not hasattr(sys, "tracebacklimit") else ""
            logger.error(f"Task '{wrapper.__name__}' caused an exception: {exc}{tb}")
        return None

    return wrapper
