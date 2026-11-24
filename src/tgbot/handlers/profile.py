"""Handlers for profile-related functionality."""

from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from tgbot.services.profile import ProfileService

__all__: tuple[str] = ("ProfileHandler",)


class ProfileHandler:
    """The class implements handlers for profile-related user interactions."""

    def __init__(self, service: ProfileService) -> None:
        """
        Initialize necessary parameters.

        :param service: ProfileService object for business logic.
        """
        self._service: ProfileService = service

    async def cmd_start(self, message: Message, state: FSMContext) -> None:
        """
        Handle the '/start' command.

        :param message: The incoming message from the user.
        :param state: The Finite State Machine (FSM) context for managing user states.
        :return: None
        """
        await state.clear()
        await message.delete()
        await self._service.start(message=message)

    async def cmd_help(self, message: Message) -> None:
        """
        Handle the '/help' command.

        :param message: The incoming message from the user.
        :return: None
        """
        await message.delete()
        await self._service.help(message=message)

    async def cmd_profile(self, message: Message, state: FSMContext) -> None:
        """
        Handle the '/profile' command.

        :param message: The incoming message from the user.
        :param state: The Finite State Machine (FSM) context for managing user states.
        :return: None
        """
        await state.clear()
        await message.delete()
        await self._service.profile(message=message)

    async def call_delete_request(self, call: CallbackQuery) -> None:
        """
        Handle the "Delete my data" button.

        :param call: The callback query of the button.
        :return: None
        """
        await self._service.delete_request(call=call)

    async def call_delete_cancel(self, call: CallbackQuery) -> None:
        """
        Handle the "No, cancel" button.

        :param call: The callback query of the button.
        :return: None
        """
        await self._service.delete_cancel(call=call)

    async def call_delete_confirm(self, call: CallbackQuery, state: FSMContext) -> None:
        """
        Handle the "Yes, delete" button; the user's FSM state and data are cleared too.

        :param call: The callback query of the button.
        :param state: The Finite State Machine (FSM) context for managing user states.
        :return: None
        """
        await state.clear()
        await self._service.delete_confirm(call=call)
