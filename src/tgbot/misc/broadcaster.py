"""A simple broadcaster with rate limiting for sending messages to bot users."""

from asyncio import Lock, sleep
from typing import Literal

from aiogram import Bot
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramAPIError, TelegramRetryAfter
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, Message

from tgbot.config import logger

__all__: tuple[str] = ("Broadcaster",)

type ContentType = Literal["text", "chat_action", "photo"]


class Broadcaster:
    """
    Implements rate-limited message broadcasting to bot users using Singleton pattern.

    :cvar _instance: Singleton instance of the Broadcaster.
    :cvar _max_msgs_per_sec: Maximum number of messages per second allowed by Telegram (set to 25 for safety).
    :cvar _max_attempts: Sends of one message when Telegram answers with a flood limit (RetryAfter).
    """

    _instance: "Broadcaster | None" = None
    _max_msgs_per_sec: int = 25
    _max_attempts: int = 3

    def __new__(cls, bot: Bot) -> "Broadcaster":  # noqa: ARG004, PYI034 - a singleton; the bot goes to __init__
        """
        Implement the Singleton pattern. The method ensures that only one instance of the class is created.

        :param bot: Bot object, consumed by the class constructor.
        :return: The single instance of the class.
        """
        instance = cls._instance
        if instance is None:
            instance = cls._instance = super().__new__(cls)
        return instance

    def __init__(self, bot: Bot) -> None:
        """
        Initialize the broadcaster with the bot instance.

        :param bot: Bot object.
        """
        if not hasattr(self, "_initialized"):
            self._bot: Bot = bot
            self._lock: Lock = Lock()
            self._initialized: bool = True

    async def send_content(  # noqa: PLR0913 - mirrors the options of the Telegram send methods
        self,
        *,
        user_id: int,
        msg: str | None = None,
        content_type: ContentType = "text",
        notify: bool = True,
        reply_markup: InlineKeyboardMarkup | None = None,
        reply_to_message_id: int | None = None,
        photo: bytes | None = None,
    ) -> int | None:
        """
        Sends a message, chat action, or photo, rate limited against every other concurrent call.

        Serialized through a shared lock, so every caller gets back the result of its own send,
        never another concurrent caller's. On a flood limit (RetryAfter) it waits the time Telegram asks for and
        sends again, keeping the lock: the limit is the bot's, so the other sends wait too.

        :param user_id: Telegram user id.
        :param msg: Message text, or a photo's caption when content_type is "photo".
        :param content_type: Type of content ("text", "chat_action", or "photo").
        :param notify: Notification on or off.
        :param reply_markup: Optional inline keyboard markup.
        :param reply_to_message_id: Optional message ID to reply to.
        :param photo: PNG image bytes to send, required when content_type is "photo".
        :return: Message ID if the content was sent, None otherwise.
        :raises aiogram.exceptions.TelegramAPIError: If Telegram rejects the request or can't deliver it, or still
            answers with a flood limit after the last attempt.
        """
        async with self._lock:
            attempt: int = 1
            while True:
                try:
                    message_id: int | None = await self._send_single_content(
                        user_id=user_id,
                        msg=msg,
                        content_type=content_type,
                        notify=notify,
                        reply_markup=reply_markup,
                        reply_to_message_id=reply_to_message_id,
                        photo=photo,
                    )
                except TelegramRetryAfter as exc:
                    if attempt >= self._max_attempts:
                        raise
                    attempt += 1
                    logger.warning(f"Target [ID:{user_id}]: flood limit, retrying in {exc.retry_after} s")
                    await sleep(delay=exc.retry_after)
                    continue
                await sleep(delay=1.0 / self._max_msgs_per_sec)
                return message_id

    async def _send_single_content(  # noqa: PLR0913 - mirrors the options of the Telegram send methods
        self,
        *,
        user_id: int,
        msg: str | None,
        content_type: ContentType,
        notify: bool,
        reply_markup: InlineKeyboardMarkup | None,
        reply_to_message_id: int | None,
        photo: bytes | None,
    ) -> int | None:
        """
        Internal method to send a single message, chat action, or photo.

        :param user_id: Telegram user id to send the message to.
        :param msg: Message text, or a photo's caption when content_type is "photo".
        :param content_type: Type of content ("text", "chat_action", or "photo").
        :param notify: Whether to send the message with notification.
        :param reply_markup: Optional inline keyboard markup.
        :param reply_to_message_id: Optional message ID to reply to.
        :param photo: PNG image bytes to send, required when content_type is "photo".
        :return: Message ID if the content was sent, None otherwise.
        """
        message: Message
        if content_type == "chat_action":  # Send a chat action (e.g., typing indicator)
            await self._bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)
            return None
        if content_type == "photo":
            if not photo:
                logger.error("Photo cannot be empty")
                return None
            message = await self._bot.send_photo(  # Send a photo, with msg used as its caption
                chat_id=user_id,
                photo=BufferedInputFile(file=photo, filename="photo.png"),
                caption=msg,
                disable_notification=not notify,
                reply_markup=reply_markup,
                reply_to_message_id=reply_to_message_id,
            )
            return message.message_id
        if not msg:
            logger.error("Text message cannot be empty")
            return None
        message = await self._bot.send_message(  # Send a text message to the user
            chat_id=user_id,
            text=msg[:4096],
            disable_notification=not notify,
            reply_markup=reply_markup,
            reply_to_message_id=reply_to_message_id,
        )
        return message.message_id

    async def broadcast(  # noqa: PLR0913 - mirrors the options of the Telegram send methods
        self,
        *,
        users_ids: list[int],
        msg: str | None,
        content_type: ContentType = "text",
        notify: bool = True,
        reply_markup: InlineKeyboardMarkup | None = None,
        reply_to_message_id: int | None = None,
        photo: bytes | None = None,
    ) -> None:
        """
        Broadcast messages, chat actions, or photos to multiple users with rate limiting.

        A Telegram error for one user (e.g. the bot is blocked) is logged and does not stop the others; any
        other exception goes to the caller.

        :param users_ids: List of telegram user ids.
        :param msg: Message text, or a photo's caption when content_type is "photo".
        :param content_type: Type of content ("text", "chat_action", or "photo").
        :param notify: Notification on or off.
        :param reply_markup: Optional inline keyboard markup.
        :param reply_to_message_id: Optional message ID to reply to.
        :param photo: PNG image bytes to send, required when content_type is "photo".
        :return: None
        """
        for user_id in users_ids:
            try:
                await self.send_content(
                    user_id=user_id,
                    msg=msg,
                    content_type=content_type,
                    notify=notify,
                    reply_markup=reply_markup,
                    reply_to_message_id=reply_to_message_id,
                    photo=photo,
                )
            except TelegramAPIError as exc:
                logger.error(f"Target [ID:{user_id}]: failed with error {exc}")
