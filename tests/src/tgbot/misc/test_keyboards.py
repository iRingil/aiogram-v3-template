"""Unit tests for src/tgbot/misc/keyboards.py."""

# ruff: noqa: S101, SLF001

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from tests.helpers import mocked
from tgbot.misc.keyboards import KeyboardManager, ProfileCallback
from tgbot.misc.tmpl_render import TmplRender

if TYPE_CHECKING:
    from aiogram.types import InlineKeyboardMarkup

__all__: tuple[str, ...] = ()


@pytest.fixture
def mock_tmpl_render() -> TmplRender:
    """
    Provides a mocked TmplRender instance whose render returns the template path, to tell the buttons apart.

    :return: A mocked TmplRender instance.
    """

    async def render(tmpl: str, locale: str) -> str:
        """
        Returns the template path and the locale instead of a rendered text.

        :param tmpl: Template path.
        :param locale: Language code.
        :return: "<tmpl>@<locale>".
        """
        return f"{tmpl}@{locale}"

    mock: MagicMock = MagicMock(spec=TmplRender)
    mock.render = AsyncMock(side_effect=render)
    return mock


def test_init(mock_tmpl_render: TmplRender) -> None:
    """
    Tests the __init__ method of KeyboardManager.

    :param mock_tmpl_render: The mocked TmplRender instance provided by fixture.
    :return: None
    """
    keyboard_manager: KeyboardManager = KeyboardManager(tmpl=mock_tmpl_render)
    assert keyboard_manager._tmpl is mock_tmpl_render


async def test_profile(mock_tmpl_render: TmplRender) -> None:
    """
    Tests the profile keyboard: one "Delete my data" button in the user's language.

    :param mock_tmpl_render: The mocked TmplRender instance provided by fixture.
    :return: None
    """
    keyboard: InlineKeyboardMarkup = await KeyboardManager(tmpl=mock_tmpl_render).profile(locale="ru")
    assert [[(b.text, b.callback_data) for b in row] for row in keyboard.inline_keyboard] == [
        [("profile/kb_delete_data.jinja2@ru", "profile:delete")]
    ]
    mocked(mock_tmpl_render.render).assert_awaited_once_with(tmpl="profile/kb_delete_data.jinja2", locale="ru")


async def test_confirm_delete(mock_tmpl_render: TmplRender) -> None:
    """
    Tests the confirmation keyboard: "No, cancel" and "Yes, delete" side by side, cancel first.

    :param mock_tmpl_render: The mocked TmplRender instance provided by fixture.
    :return: None
    """
    keyboard: InlineKeyboardMarkup = await KeyboardManager(tmpl=mock_tmpl_render).confirm_delete(locale="en")
    assert [[(b.text, b.callback_data) for b in row] for row in keyboard.inline_keyboard] == [
        [
            ("profile/kb_delete_cancel.jinja2@en", "profile:cancel"),
            ("profile/kb_delete_confirm.jinja2@en", "profile:confirm"),
        ]
    ]


@pytest.mark.parametrize("action", ["delete", "cancel", "confirm"])
def test_profile_callback_round_trip(action: str) -> None:
    """
    Tests that the profile callback data packs and unpacks every action.

    :param action: The action of the button.
    :return: None
    """
    assert ProfileCallback.unpack(value=f"profile:{action}").action == action


@pytest.mark.parametrize("value", ["profile:drop", "settings:delete"])
def test_profile_callback_rejects_forged_data(value: str) -> None:
    """
    Tests that callback data of another action or another prefix is rejected, not taken for a profile action.

    :param value: The forged callback data.
    :return: None
    """
    with pytest.raises(expected_exception=(ValidationError, ValueError)):
        ProfileCallback.unpack(value=value)
