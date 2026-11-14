"""Handler of errors that are not caught by other functions."""

from typing import override

from aiogram.handlers import BaseHandler
from aiogram.types import CallbackQuery, ErrorEvent, Message

from tgbot.config import logger

__all__: tuple[str] = ("ErrHandler",)


class ErrHandler(BaseHandler[ErrorEvent]):
    """
    Class for errors handlers that are not caught by other functions.

    Based on BaseHandler[ErrorEvent], not the aiogram ErrorHandler: that one is typed as
    BaseHandler[Exception], while error handlers actually receive an ErrorEvent.
    """

    @override
    async def handle(self) -> None:
        """
        Logs exceptions that are not handled by other functions.

        :return: None
        """
        event: ErrorEvent = self.event
        msg_or_call_from_user: str = (
            f", Message: {event.update.message.text}"
            if isinstance(event.update.message, Message)
            else (
                f", Callback: {event.update.callback_query.data}"
                if isinstance(event.update.callback_query, CallbackQuery)
                else ""
            )
        )
        logger.error(f"Exception while handling an update: {event.exception} {msg_or_call_from_user}")
