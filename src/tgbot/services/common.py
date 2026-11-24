"""Base service classes for shared functionality."""

from asyncio import sleep

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, MaybeInaccessibleMessageUnion, Message, User

from tgbot.config import Config
from tgbot.misc.keyboards import KeyboardManager
from tgbot.misc.tmpl_render import TmplRender

__all__: tuple[str] = ("BaseService",)

_NOT_MODIFIED: str = "message is not modified"  # Telegram refuses an edit that changes nothing


class BaseService:
    """
    Base service class with shared functionality for other services.

    :cvar _DEFAULT_LOCALE: Locale used when Telegram doesn't report the user's language.
    :cvar _msg_expired_action: Path to the expired action template.
    :cvar _msg_unsupported: Path to the unsupported template.
    """

    _DEFAULT_LOCALE: str = "en"
    _msg_expired_action: str = "common/msg_expired_action.jinja2"
    _msg_unsupported: str = "common/msg_unsupported.jinja2"

    def __init__(self, config: Config, tmpl: TmplRender, kb: KeyboardManager) -> None:
        """
        Initialize shared dependencies for services.

        :param config: Config object with configuration settings.
        :param tmpl: TmplRender object for rendering templates.
        :param kb: KeyboardManager object for keyboard generation.
        """
        self._config: Config = config
        self._tmpl: TmplRender = tmpl
        self._kb: KeyboardManager = kb

    # region Public methods
    async def any_delete(self, message: Message) -> None:
        """
        Deletes content sent by a user if the bot should not respond to it.

        :param message: The incoming message from the user.
        :return: None
        """
        text: str = await self._tmpl.render(tmpl=self._msg_unsupported, locale=self._locale(user=message.from_user))
        msg: Message = await message.reply(text=text)
        await sleep(delay=3)
        await msg.delete()
        await message.delete()

    # endregion

    # region Private methods
    @classmethod
    def _locale(cls, user: User | None) -> str:
        """
        Returns the language code of a user.

        :param user: Telegram user, if known.
        :return: First two characters of the language code reported by Telegram, or the default locale.
        """
        # The locale folders are named by two letters, as the locale column of the users table
        return user.language_code[:2] if user is not None and user.language_code else cls._DEFAULT_LOCALE

    @staticmethod
    def _bot_of(event: Message | CallbackQuery) -> Bot:
        """
        Returns the bot an incoming message or callback query is bound to.

        aiogram binds every update it dispatches to its bot, so a missing one is a programming error.

        :param event: The incoming message or callback query.
        :return: The bot.
        :raises RuntimeError: if the event is not bound to a bot.
        """
        bot: Bot | None = event.bot
        if bot is None:
            raise RuntimeError("The event is not bound to a bot")
        return bot

    async def _edit_or_send_callback(
        self, call: CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None
    ) -> Message:
        """
        Edit the existing message from a callback if possible, otherwise send a new one.

        Shows a fixed alert "Action expired" once the new message is sent (e.g., the old one is older than 48 hours).

        :param call: The callback query to edit or reply to.
        :param text: The text to send or edit into the message.
        :param reply_markup: The keyboard markup to include (optional).
        :return: The edited message or a new one.
        :raises aiogram.exceptions.TelegramAPIError: if the new message can't be sent either; the callback is answered.
        """
        origin: MaybeInaccessibleMessageUnion | None = call.message
        # Trying to edit an existing message, if it does not exist or 48 hours have passed, the try will fail
        if isinstance(origin, Message):
            try:
                edited: Message | bool = await origin.edit_text(text=text, reply_markup=reply_markup)
            except TelegramBadRequest as e:
                # If the new content is the same as the current one
                if _NOT_MODIFIED in e.message:
                    await call.answer()
                    return origin
            else:
                await call.answer()
                return edited if isinstance(edited, Message) else origin
        # The message can't be edited (e.g. older than 48 hours, or deleted): send the content as a new one.
        # The "Action expired" alert is shown only once the new message is sent: an edit that failed for another
        # reason (e.g. a markup error) fails as a new message too, and then nothing expired is to be reported
        try:
            sent: Message = (
                await self._bot_of(event=call).send_message(
                    chat_id=call.from_user.id, text=text, reply_markup=reply_markup
                )
                if origin is None
                else await origin.answer(text=text, reply_markup=reply_markup)
            )
        except TelegramAPIError:
            await call.answer()  # Stops the button's loading indicator; the error goes on to the error handler
            raise
        alert_text: str = await self._tmpl.render(
            tmpl=self._msg_expired_action, locale=self._locale(user=call.from_user)
        )
        await call.answer(text=alert_text, show_alert=True)
        return sent

    @staticmethod
    async def _edit_or_send_msg(
        bot: Bot, chat_id: int, msg_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None
    ) -> Message | None:
        """
        Edit the existing message if possible, otherwise send a new one.

        Sends nothing if the new content is the same as the current one: there is no Message object
        at hand here (unlike _edit_or_send_callback) to return as the unchanged result.

        :param bot: The bot instance.
        :param chat_id: The chat ID to send the message to.
        :param msg_id: The message ID to edit.
        :param text: The text to edit into the message.
        :param reply_markup: The keyboard markup to include (optional).
        :return: The edited message, a new one, or None if the content was unchanged.
        :raises TypeError: if Telegram returns no message for the edit.
        """
        # Trying to edit an existing message, if it does not exist or 48 hours have passed, the try will fail
        try:
            edited: Message | bool = await bot.edit_message_text(
                chat_id=chat_id, message_id=msg_id, text=text, reply_markup=reply_markup
            )
        except TelegramBadRequest as e:
            if _NOT_MODIFIED in e.message:  # Nothing to change, and no need for a duplicate
                return None
            # If the message is too old, send a new one
            return await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        if not isinstance(edited, Message):  # Telegram returns True only for inline messages
            raise TypeError("Telegram returned no message for an edit by chat and message IDs")
        return edited

    # endregion
