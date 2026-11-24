"""Business logic for profile-related functionality."""

from typing import TYPE_CHECKING

from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardMarkup, Message, User

from tgbot.config import Config
from tgbot.db.pg_client import PostgresClient
from tgbot.db.users import UserRepo
from tgbot.misc.keyboards import KeyboardManager
from tgbot.misc.tmpl_render import TmplRender
from tgbot.services.common import BaseService
from tgbot.storage.synced_users import SyncedUsers

if TYPE_CHECKING:
    from tgbot.misc.data_types import TgUser

__all__: tuple[str] = ("ProfileService",)


class ProfileService(BaseService):
    """
    The class implements business logic for profile-related operations.

    :cvar _cmd_help: Path to the help template.
    :cvar _cmd_start: Path to the start template.
    :cvar _msg_profile: Path to the profile template.
    :cvar _msg_delete_confirm: Path to the template asking to confirm the deletion of the user's data.
    :cvar _msg_data_deleted: Path to the template reporting that the user's data is deleted.
    """

    _cmd_help: str = "profile/cmd_help.jinja2"
    _cmd_start: str = "profile/cmd_start.jinja2"
    _msg_profile: str = "profile/msg_profile.jinja2"
    _msg_delete_confirm: str = "profile/msg_delete_confirm.jinja2"
    _msg_data_deleted: str = "profile/msg_data_deleted.jinja2"

    def __init__(
        self, config: Config, tmpl: TmplRender, kb: KeyboardManager, db: PostgresClient, synced: SyncedUsers
    ) -> None:
        """
        Initialize necessary parameters.

        :param config: Config object with configuration settings.
        :param tmpl: TmplRender object for rendering templates.
        :param kb: KeyboardManager object for keyboard generation.
        :param db: PostgreSQL client, connected on startup.
        :param synced: Redis store of the users saved to the users table today.
        """
        BaseService.__init__(self, config=config, tmpl=tmpl, kb=kb)
        self._bot_logo: FSInputFile = FSInputFile(path=config.paths.bot_logo)
        self._db: PostgresClient = db
        self._synced: SyncedUsers = synced

    async def start(self, message: Message) -> None:
        """
        Process incoming '/start' command.

        :param message: The incoming message from the user.
        :return: None
        """
        text: str = await self._render_for_user(tmpl=self._cmd_start, message=message)
        await message.answer(text=text)

    async def help(self, message: Message) -> None:
        """
        Process incoming '/help' command to show help information.

        :param message: The incoming message from the user.
        :return: None
        """
        # A photo caption is limited to 1024 characters, not the 4096 of a text message
        caption: str = await self._render_for_user(tmpl=self._cmd_help, message=message, max_len=1024)
        await message.answer_photo(photo=self._bot_logo, caption=caption)

    async def profile(self, message: Message) -> None:
        """
        Process incoming '/profile' command: shows the user's profile with the "Delete my data" button.

        :param message: The incoming message from the user.
        :return: None
        """
        user: User | None = message.from_user
        if user is None:
            return
        text, reply_markup = await self._render_profile(user=user)
        await message.answer(text=text, reply_markup=reply_markup)

    async def delete_request(self, call: CallbackQuery) -> None:
        """
        Process the "Delete my data" button: asks to confirm the deletion.

        :param call: The callback query of the button.
        :return: None
        """
        locale: str = self._locale(user=call.from_user)
        text: str = await self._tmpl.render(tmpl=self._msg_delete_confirm, locale=locale)
        reply_markup: InlineKeyboardMarkup = await self._kb.confirm_delete(locale=locale)
        await self._edit_or_send_callback(call=call, text=text, reply_markup=reply_markup)

    async def delete_cancel(self, call: CallbackQuery) -> None:
        """
        Process the "No, cancel" button: returns to the profile without deleting anything.

        :param call: The callback query of the button.
        :return: None
        """
        text, reply_markup = await self._render_profile(user=call.from_user)
        await self._edit_or_send_callback(call=call, text=text, reply_markup=reply_markup)

    async def delete_confirm(self, call: CallbackQuery) -> None:
        """
        Process the "Yes, delete" button: deletes the user from the users table and reports it.

        The "saved today" mark is forgotten too, so the next update of the user creates the row again.

        :param call: The callback query of the button.
        :return: None
        """
        await UserRepo(db=self._db.pool).delete(user_id=call.from_user.id)
        await self._synced.forget(user_id=call.from_user.id)
        text: str = await self._tmpl.render(tmpl=self._msg_data_deleted, locale=self._locale(user=call.from_user))
        await self._edit_or_send_callback(call=call, text=text)

    async def _render_profile(self, *, user: User) -> tuple[str, InlineKeyboardMarkup]:
        """
        Renders the profile of a user and its keyboard, shared by the command and the "No, cancel" button.

        :param user: Telegram user.
        :return: The text and the keyboard.
        """
        locale: str = self._locale(user=user)
        # The row is written by UserSyncMiddleware; without it (e.g. the database was down) the date is left out
        row: TgUser | None = await UserRepo(db=self._db.pool).get(user_id=user.id)
        data: dict[str, object] = {
            "first_name": user.first_name,
            "user_id": user.id,
            "registered_on": row.registered_on.isoformat() if row is not None else None,
        }
        text: str = await self._tmpl.render(tmpl=self._msg_profile, locale=locale, data=data)
        return text, await self._kb.profile(locale=locale)

    async def _render_for_user(self, *, tmpl: str, message: Message, max_len: int = 4096) -> str:
        """
        Renders a template addressed to the sender of the message, in the language of the sender.

        :param tmpl: Path to the template.
        :param message: The incoming message from the user.
        :param max_len: Maximum length of the rendered text: 4096 for a message, 1024 for a photo caption.
        :return: The rendered text.
        """
        user: User | None = message.from_user
        data: dict[str, str] = {"username": user.first_name if user is not None else ""}
        return await self._tmpl.render(tmpl=tmpl, locale=self._locale(user=user), data=data, max_len=max_len)
