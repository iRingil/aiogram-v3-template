"""The module presents a function that changes the default list of commands for the bot."""

from aiogram import Bot
from aiogram.types import BotCommand, BotCommandScopeAllGroupChats, BotCommandScopeAllPrivateChats, BotCommandScopeChat

from tgbot.misc.tmpl_render import TmplRender

__all__: tuple[str] = ("BotCommands",)


class BotCommands:
    """
    The class provides a function that changes the default list of commands for the bot.

    :cvar _cmd_start: Path to the template for the '/start' command.
    :cvar _cmd_help: Path to the template for the '/help' command.
    :cvar _cmd_profile: Path to the template for the '/profile' command.
    :cvar _cmd_settings: Path to the template for the '/settings' command.
    :cvar _cmd_admin: Path to the template for the '/admin' command.
    :cvar _DEFAULT_LOCALE: Locale of the commands shown to users whose language has no translation.
    """

    _cmd_start: str = "common/cmd_start.jinja2"
    _cmd_help: str = "common/cmd_help.jinja2"
    _cmd_profile: str = "common/cmd_profile.jinja2"
    _cmd_settings: str = "common/cmd_settings.jinja2"
    _cmd_admin: str = "admin/cmd_admin.jinja2"
    _DEFAULT_LOCALE: str = "en"

    def __init__(self, bot: Bot, tmpl_render: TmplRender, admin_ids: list[int]) -> None:
        """
        Initializes the BotCommands class with the necessary parameters.

        :param bot: Bot instance.
        :param tmpl_render: TmplRender instance for rendering templates.
        :param admin_ids: List of admin user IDs.
        """
        self._bot: Bot = bot
        self._tmpl: TmplRender = tmpl_render
        self._admin_ids: list[int] = admin_ids

    async def _get_commands(self, lang_code: str) -> list[BotCommand]:
        """
        Returns a list of 'BotCommand' instances for the given language code.

        :param lang_code: The language code for which to return the commands.
        :return: A list of 'BotCommand' instances.
        """
        start_desc: str = await self._tmpl.render(tmpl=self._cmd_start, locale=lang_code)
        help_desc: str = await self._tmpl.render(tmpl=self._cmd_help, locale=lang_code)
        profile_desc: str = await self._tmpl.render(tmpl=self._cmd_profile, locale=lang_code)
        settings_desc: str = await self._tmpl.render(tmpl=self._cmd_settings, locale=lang_code)
        return [
            BotCommand(command="start", description=start_desc),
            BotCommand(command="profile", description=profile_desc),
            BotCommand(command="settings", description=settings_desc),
            BotCommand(command="help", description=help_desc),
        ]

    async def _get_admins_commands(self, lang_code: str) -> list[BotCommand]:
        """
        Returns a list of 'BotCommand' instances for admin users for the given language code.

        :param lang_code: The language code for which to return the commands.
        :return: A list of 'BotCommand' instances.
        """
        admin_desc: str = await self._tmpl.render(tmpl=self._cmd_admin, locale=lang_code)
        return [BotCommand(command="admin", description=admin_desc)]

    async def set_commands(self) -> None:
        """
        Sets default commands for the bot, depending on the available translations in the program.

        :return: None
        """
        # Cleaning commands
        await self._bot.set_my_commands(commands=[], scope=BotCommandScopeAllGroupChats())
        await self._bot.set_my_commands(commands=[], scope=BotCommandScopeAllPrivateChats())
        await self._set_for_locale(locale=self._DEFAULT_LOCALE, language_code=None)
        for locale in self._tmpl.get_locales():
            await self._set_for_locale(locale=locale, language_code=locale)

    async def _set_for_locale(self, locale: str, language_code: str | None) -> None:
        """
        Sets the commands of one locale.

        The user commands for every private chat, plus the admin commands in each admin's own chat.

        :param locale: Locale to render the command descriptions in.
        :param language_code: Telegram language code the commands apply to, or None for the
            default commands shown to users of any language without its own.
        :return: None
        """
        commands: list[BotCommand] = await self._get_commands(lang_code=locale)
        await self._bot.set_my_commands(
            commands=commands, language_code=language_code, scope=BotCommandScopeAllPrivateChats()
        )
        admin_commands: list[BotCommand] = commands + await self._get_admins_commands(lang_code=locale)
        for admin_id in self._admin_ids:
            await self._bot.set_my_commands(
                commands=admin_commands, language_code=language_code, scope=BotCommandScopeChat(chat_id=admin_id)
            )
