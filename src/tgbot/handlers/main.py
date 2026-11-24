"""Event handlers registration for the bot."""

from aiogram import Dispatcher, F, Router
from aiogram.filters import Command

from tgbot.config import Config
from tgbot.db.pg_client import PostgresClient
from tgbot.handlers.admin import AdminHandler
from tgbot.handlers.common import CommonHandler
from tgbot.handlers.errors import ErrHandler
from tgbot.handlers.profile import ProfileHandler
from tgbot.handlers.settings import SettingsHandler
from tgbot.misc.filters import IsAdmin
from tgbot.misc.keyboards import KeyboardManager, ProfileCallback
from tgbot.misc.tmpl_render import TmplRender
from tgbot.services.admin import AdminService
from tgbot.services.common import BaseService
from tgbot.services.profile import ProfileService
from tgbot.services.settings import SettingsService
from tgbot.storage.synced_users import SyncedUsers

__all__: tuple[str] = ("MainHandler",)


class MainHandler:
    """Registers event handlers for the bot."""

    def __init__(  # noqa: PLR0913 - the shared dependencies the services need
        self,
        *,
        config: Config,
        dp: Dispatcher,
        tmpl: TmplRender,
        kb: KeyboardManager,
        db: PostgresClient,
        synced: SyncedUsers,
    ) -> None:
        """
        Initialize necessary parameters and handlers.

        :param config: Config object with configuration settings.
        :param dp: Aiogram Dispatcher object for handling events.
        :param tmpl: TmplRender object for rendering templates.
        :param kb: KeyboardManager object for keyboard generation.
        :param db: PostgreSQL client, connected on startup.
        :param synced: Redis store of the users saved to the users table today.
        """
        self._dp: Dispatcher = dp
        self._is_admin: IsAdmin = IsAdmin(admins_ids=config.admins)

        # region Initialize services
        self._admin_svc: AdminService = AdminService(config=config, tmpl=tmpl, kb=kb)
        self._base_svc: BaseService = BaseService(config=config, tmpl=tmpl, kb=kb)
        self._profile_svc: ProfileService = ProfileService(config=config, tmpl=tmpl, kb=kb, db=db, synced=synced)
        self._settings_svc: SettingsService = SettingsService(config=config, tmpl=tmpl, kb=kb)
        # endregion

        # region Initialize handlers
        self._admin_hdlr: AdminHandler = AdminHandler(service=self._admin_svc)
        self._common_hdlr: CommonHandler = CommonHandler(service=self._base_svc)
        self._profile_hdlr: ProfileHandler = ProfileHandler(service=self._profile_svc)
        self._settings_hdlr: SettingsHandler = SettingsHandler(service=self._settings_svc)
        # endregion

        self._register_handlers()

    def _register_handlers(self) -> None:
        """
        Register event and error handlers for the bot.

        :return: None
        """
        pr: Router = Router(name="Private chat")
        pr.message.filter(F.chat.type == "private")  # Filter for handling messages in private chats only
        pr.callback_query.filter(F.message.chat.type == "private")  # Buttons of messages in private chats only
        self._dp.include_router(router=pr)

        # region Commands handlers
        pr.message.register(self._profile_hdlr.cmd_start, Command(commands=["start"]), F.text == "/start")
        pr.message.register(self._profile_hdlr.cmd_help, Command(commands=["help"]))
        pr.message.register(self._profile_hdlr.cmd_profile, Command(commands=["profile"]))
        # Starting a settings menu
        pr.message.register(self._settings_hdlr.cmd_or_msg_settings, Command(commands=["settings"]))
        # Show admin menu
        pr.message.register(self._admin_hdlr.cmd_admin, Command(commands=["admin"]), self._is_admin)
        # endregion

        # region Profile buttons
        pr.callback_query.register(self._profile_hdlr.call_delete_request, ProfileCallback.filter(F.action == "delete"))
        pr.callback_query.register(self._profile_hdlr.call_delete_cancel, ProfileCallback.filter(F.action == "cancel"))
        pr.callback_query.register(
            self._profile_hdlr.call_delete_confirm, ProfileCallback.filter(F.action == "confirm")
        )
        # endregion

        # region Delete unhandled messages
        # Delete messages in bot chats
        pr.message.register(self._common_hdlr.any_delete, ~F.text | F.text)
        # endregion

        # region Error handler
        pr.errors.register(ErrHandler)
        # endregion
