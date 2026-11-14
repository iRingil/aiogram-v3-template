"""Business logic for profile-related functionality."""

from aiogram.types import FSInputFile, Message, User

from tgbot.config import Config
from tgbot.misc.keyboards import KeyboardManager
from tgbot.misc.tmpl_render import TmplRender
from tgbot.services.common import BaseService

__all__: tuple[str] = ("ProfileService",)


class ProfileService(BaseService):
    """
    The class implements business logic for profile-related operations.

    :cvar _cmd_help: Path to the help template.
    :cvar _cmd_start: Path to the start template.
    """

    _cmd_help: str = "profile/cmd_help.jinja2"
    _cmd_start: str = "profile/cmd_start.jinja2"

    def __init__(self, config: Config, tmpl: TmplRender, kb: KeyboardManager) -> None:
        """
        Initialize necessary parameters.

        :param config: Config object with configuration settings.
        :param tmpl: TmplRender object for rendering templates.
        :param kb: KeyboardManager object for keyboard generation.
        """
        BaseService.__init__(self, config=config, tmpl=tmpl, kb=kb)
        self._bot_logo: FSInputFile = FSInputFile(path=config.paths.bot_logo)

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
        caption: str = await self._render_for_user(tmpl=self._cmd_help, message=message)
        await message.answer_photo(photo=self._bot_logo, caption=caption)

    async def _render_for_user(self, *, tmpl: str, message: Message) -> str:
        """
        Renders a template addressed to the sender of the message, in the language of the sender.

        :param tmpl: Path to the template.
        :param message: The incoming message from the user.
        :return: The rendered text.
        """
        user: User | None = message.from_user
        data: dict[str, str] = {"username": user.first_name if user is not None else ""}
        return await self._tmpl.render(tmpl=tmpl, locale=self._locale(user=user), data=data)
