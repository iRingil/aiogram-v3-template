"""The keyboards used in the bot."""

from typing import Literal

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from tgbot.misc.tmpl_render import TmplRender

__all__: tuple[str, ...] = ("KeyboardManager", "ProfileCallback")


class ProfileCallback(CallbackData, prefix="profile"):
    """
    Callback data of the profile buttons, packed as "profile:<action>" and validated when it comes back.

    :param action: "delete" asks to confirm the deletion of the user's data, "cancel" returns to the profile,
        "confirm" deletes the data.
    """

    action: Literal["delete", "cancel", "confirm"]


class KeyboardManager:
    """
    Implements creation of bot keyboards; the button texts are rendered from templates in the user's language.

    :cvar _kb_delete_data: Path to the "Delete my data" button template.
    :cvar _kb_delete_cancel: Path to the "No, cancel" button template.
    :cvar _kb_delete_confirm: Path to the "Yes, delete" button template.
    """

    _kb_delete_data: str = "profile/kb_delete_data.jinja2"
    _kb_delete_cancel: str = "profile/kb_delete_cancel.jinja2"
    _kb_delete_confirm: str = "profile/kb_delete_confirm.jinja2"

    def __init__(self, tmpl: TmplRender) -> None:
        """
        Initialize the keyboard manager.

        :param tmpl: TmplRender object.
        """
        self._tmpl: TmplRender = tmpl

    async def profile(self, locale: str) -> InlineKeyboardMarkup:
        """
        Returns the keyboard of the profile: the "Delete my data" button.

        :param locale: Language code of the user.
        :return: The keyboard.
        """
        text: str = await self._tmpl.render(tmpl=self._kb_delete_data, locale=locale)
        return InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=ProfileCallback(action="delete").pack())]]
        )

    async def confirm_delete(self, locale: str) -> InlineKeyboardMarkup:
        """
        Returns the keyboard confirming the deletion of the user's data: "No, cancel" and "Yes, delete" in one row.

        :param locale: Language code of the user.
        :return: The keyboard.
        """
        cancel: str = await self._tmpl.render(tmpl=self._kb_delete_cancel, locale=locale)
        confirm: str = await self._tmpl.render(tmpl=self._kb_delete_confirm, locale=locale)
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=cancel, callback_data=ProfileCallback(action="cancel").pack()),
                    InlineKeyboardButton(text=confirm, callback_data=ProfileCallback(action="confirm").pack()),
                ]
            ]
        )
