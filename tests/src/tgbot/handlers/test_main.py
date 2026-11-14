"""Unit tests for src/tgbot/handlers/main.py."""

# ruff: noqa: S101, SLF001

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, cast
from unittest.mock import MagicMock, _Call

import pytest
from aiogram import Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.utils.magic_filter import MagicFilter
from pytest_mock import MockerFixture

from tgbot.handlers.errors import ErrHandler
from tgbot.handlers.main import MainHandler
from tgbot.misc.filters import IsAdmin

__all__: tuple = ()


type FilterType = type[Command | MagicFilter] | MagicMock
type FilterConfig = tuple[FilterType, dict[str, Any]]
type HandlerSetup = tuple[Callable[..., Any], list[FilterConfig]]

MODULE_PATH_PREFIX = "tgbot.handlers.main"


@dataclass
class Mocks:
    """
    Mocks of everything MainHandler receives or creates.

    :param mock_config: Config passed to MainHandler.
    :param mock_dp: Dispatcher passed to MainHandler.
    :param mock_tmpl: TmplRender passed to MainHandler.
    :param mock_kb: KeyboardManager passed to MainHandler.
    :param mock_is_admin: Patched IsAdmin class.
    :param mock_is_admin_instance: Instance the patched IsAdmin returns.
    :param mock_admin_service: Patched AdminService class.
    :param mock_admin_svc_instance: Instance the patched AdminService returns.
    :param mock_base_service: Patched BaseService class.
    :param mock_base_svc_instance: Instance the patched BaseService returns.
    :param mock_profile_service: Patched ProfileService class.
    :param mock_profile_svc_instance: Instance the patched ProfileService returns.
    :param mock_settings_service: Patched SettingsService class.
    :param mock_settings_svc_instance: Instance the patched SettingsService returns.
    :param mock_admin_handler: Patched AdminHandler class.
    :param mock_admin_hdlr_instance: Instance the patched AdminHandler returns.
    :param mock_common_handler: Patched CommonHandler class.
    :param mock_common_hdlr_instance: Instance the patched CommonHandler returns.
    :param mock_profile_handler: Patched ProfileHandler class.
    :param mock_profile_hdlr_instance: Instance the patched ProfileHandler returns.
    :param mock_settings_handler: Patched SettingsHandler class.
    :param mock_settings_hdlr_instance: Instance the patched SettingsHandler returns.
    :param mock_router: Patched Router class.
    :param mock_private_router: Instance the patched Router returns.
    """

    mock_config: MagicMock
    mock_dp: MagicMock
    mock_tmpl: MagicMock
    mock_kb: MagicMock
    mock_is_admin: MagicMock
    mock_is_admin_instance: MagicMock
    mock_admin_service: MagicMock
    mock_admin_svc_instance: MagicMock
    mock_base_service: MagicMock
    mock_base_svc_instance: MagicMock
    mock_profile_service: MagicMock
    mock_profile_svc_instance: MagicMock
    mock_settings_service: MagicMock
    mock_settings_svc_instance: MagicMock
    mock_admin_handler: MagicMock
    mock_admin_hdlr_instance: MagicMock
    mock_common_handler: MagicMock
    mock_common_hdlr_instance: MagicMock
    mock_profile_handler: MagicMock
    mock_profile_hdlr_instance: MagicMock
    mock_settings_handler: MagicMock
    mock_settings_hdlr_instance: MagicMock
    mock_router: MagicMock
    mock_private_router: MagicMock


@pytest.fixture
def mocks(mocker: MockerFixture) -> Mocks:
    """
    Fixture to set up mocks for testing MainHandler.

    :param mocker: Pytest mocker fixture used to patch and create mocks.
    :return: The mocks.
    """
    result: Mocks = Mocks(
        mock_config=MagicMock(admins=[123, 456]),
        mock_dp=MagicMock(spec=Dispatcher),
        mock_tmpl=MagicMock(),
        mock_kb=MagicMock(),
        mock_is_admin=mocker.patch(f"{MODULE_PATH_PREFIX}.IsAdmin"),
        mock_is_admin_instance=MagicMock(spec=IsAdmin),
        mock_admin_service=mocker.patch(f"{MODULE_PATH_PREFIX}.AdminService"),
        mock_admin_svc_instance=MagicMock(),
        mock_base_service=mocker.patch(f"{MODULE_PATH_PREFIX}.BaseService"),
        mock_base_svc_instance=MagicMock(),
        mock_profile_service=mocker.patch(f"{MODULE_PATH_PREFIX}.ProfileService"),
        mock_profile_svc_instance=MagicMock(),
        mock_settings_service=mocker.patch(f"{MODULE_PATH_PREFIX}.SettingsService"),
        mock_settings_svc_instance=MagicMock(),
        mock_admin_handler=mocker.patch(f"{MODULE_PATH_PREFIX}.AdminHandler"),
        mock_admin_hdlr_instance=MagicMock(),
        mock_common_handler=mocker.patch(f"{MODULE_PATH_PREFIX}.CommonHandler"),
        mock_common_hdlr_instance=MagicMock(),
        mock_profile_handler=mocker.patch(f"{MODULE_PATH_PREFIX}.ProfileHandler"),
        mock_profile_hdlr_instance=MagicMock(),
        mock_settings_handler=mocker.patch(f"{MODULE_PATH_PREFIX}.SettingsHandler"),
        mock_settings_hdlr_instance=MagicMock(),
        mock_router=mocker.patch(f"{MODULE_PATH_PREFIX}.Router"),
        mock_private_router=MagicMock(spec=Router),
    )
    result.mock_is_admin.return_value = result.mock_is_admin_instance
    result.mock_admin_service.return_value = result.mock_admin_svc_instance
    result.mock_base_service.return_value = result.mock_base_svc_instance
    result.mock_profile_service.return_value = result.mock_profile_svc_instance
    result.mock_settings_service.return_value = result.mock_settings_svc_instance
    result.mock_admin_handler.return_value = result.mock_admin_hdlr_instance
    result.mock_common_handler.return_value = result.mock_common_hdlr_instance
    result.mock_profile_handler.return_value = result.mock_profile_hdlr_instance
    result.mock_settings_handler.return_value = result.mock_settings_hdlr_instance
    result.mock_private_router.message = MagicMock()
    result.mock_private_router.errors = MagicMock()
    result.mock_router.return_value = result.mock_private_router
    return result


class TestMainHandler:
    """Unit tests for MainHandler class."""

    def test_initialization(self, mocks: Mocks) -> None:
        """
        Test that MainHandler initializes its components correctly.

        :param mocks: Mocks of everything MainHandler receives or creates.
        :return: None
        """
        main_handler: MainHandler = MainHandler(
            config=mocks.mock_config, dp=mocks.mock_dp, tmpl=mocks.mock_tmpl, kb=mocks.mock_kb
        )
        mocks.mock_is_admin.assert_called_once_with(admins_ids=mocks.mock_config.admins)
        assert main_handler._is_admin == mocks.mock_is_admin_instance
        mocks.mock_admin_service.assert_called_once_with(
            config=mocks.mock_config, tmpl=mocks.mock_tmpl, kb=mocks.mock_kb
        )
        mocks.mock_base_service.assert_called_once_with(
            config=mocks.mock_config, tmpl=mocks.mock_tmpl, kb=mocks.mock_kb
        )
        mocks.mock_profile_service.assert_called_once_with(
            config=mocks.mock_config, tmpl=mocks.mock_tmpl, kb=mocks.mock_kb
        )
        mocks.mock_settings_service.assert_called_once_with(
            config=mocks.mock_config, tmpl=mocks.mock_tmpl, kb=mocks.mock_kb
        )
        mocks.mock_admin_handler.assert_called_once_with(service=mocks.mock_admin_svc_instance)
        mocks.mock_common_handler.assert_called_once_with(service=mocks.mock_base_svc_instance)
        mocks.mock_profile_handler.assert_called_once_with(service=mocks.mock_profile_svc_instance)
        mocks.mock_settings_handler.assert_called_once_with(service=mocks.mock_settings_svc_instance)

    # noinspection PyUnresolvedReferences
    def test_register_handlers_argument_check(self, mocks: Mocks) -> None:
        """
        Test that _register_handlers registers handlers with correct arguments and order.

        :param mocks: Mocks of everything MainHandler receives or creates.
        :return: None
        """
        MainHandler(config=mocks.mock_config, dp=mocks.mock_dp, tmpl=mocks.mock_tmpl, kb=mocks.mock_kb)
        mocks.mock_router.assert_called_once_with(name="Private chat")
        # Checking the router filter
        router_filter_call: _Call | None = mocks.mock_private_router.message.filter.call_args
        assert router_filter_call is not None, "Router.message.filter was not called"
        actual_router_filter_arg: MagicFilter = cast("MagicFilter", router_filter_call.args[0])
        expected_router_magic_filter: MagicFilter = F.chat.type == "private"
        assert isinstance(actual_router_filter_arg, MagicFilter)
        # Compare magic_data, as this captures the essence of the filter
        assert actual_router_filter_arg.magic_data == expected_router_magic_filter.magic_data, (
            f"Router filter mismatch. "
            f"Expected data {expected_router_magic_filter.magic_data}, got {actual_router_filter_arg.magic_data}"
        )
        mocks.mock_dp.include_router.assert_called_once_with(router=mocks.mock_private_router)
        registrations: list[_Call] = mocks.mock_private_router.message.register.call_args_list
        expected_handler_setups: list[HandlerSetup] = [
            (  # command /start
                mocks.mock_profile_hdlr_instance.cmd_start,
                [(Command, {"commands": ("start",)}), (MagicFilter, {"magic_data": (F.text == "/start").magic_data})],
            ),
            (  # command /help
                mocks.mock_profile_hdlr_instance.cmd_help,
                [(Command, {"commands": ("help",)})],
            ),
            (  # command /settings
                mocks.mock_settings_hdlr_instance.cmd_or_msg_settings,
                [(Command, {"commands": ("settings",)})],
            ),
            (  # command /admin
                mocks.mock_admin_hdlr_instance.cmd_admin,
                [(Command, {"commands": ("admin",)}), (mocks.mock_is_admin_instance, {})],  # Здесь MagicMock
            ),
            (  # delete unhandled messages
                mocks.mock_common_hdlr_instance.any_delete,
                [(MagicFilter, {"magic_data": (~F.text | F.text).magic_data})],
            ),
        ]
        assert len(registrations) == len(expected_handler_setups), (
            f"Expected {len(expected_handler_setups)} message handler registrations, "
            f"got {len(registrations)}. Actual calls: {registrations}"
        )
        for i, (expected_handler, expected_filters_config) in enumerate(expected_handler_setups):
            actual_call: _Call = registrations[i]
            actual_call_args: tuple[Any, ...] = actual_call.args  # Get the tuple of call arguments
            # 1. Check the handler itself (first argument)
            actual_handler_arg: Callable[..., Any] = actual_call_args[0]
            assert actual_handler_arg == expected_handler, (
                f"Registration {i}: Handler mismatch. Expected {expected_handler}, got {actual_handler_arg}"
            )
            # 2. Checking filters (other arguments)
            # The actual filters will be instances of Command, MagicFilter, or MagicMock (for IsAdmin)
            actual_filter_args: tuple[Command | MagicFilter | MagicMock, ...] = actual_call_args[1:]
            assert len(actual_filter_args) == len(expected_filters_config), (
                f"Registration {i} for {expected_handler}: Number of filters mismatch. "
                f"Expected {len(expected_filters_config)}, got {len(actual_filter_args)}. "
                f"Actual filters: {actual_filter_args}"
            )
            for j, (expected_filter_type_or_instance, expected_attrs) in enumerate(expected_filters_config):
                actual_filter_obj: Command | MagicFilter | MagicMock = actual_filter_args[j]
                if isinstance(expected_filter_type_or_instance, MagicMock):
                    # If a specific mock instance (like mocks.mock_is_admin_instance) is expected.
                    assert actual_filter_obj == expected_filter_type_or_instance, (
                        f"Registration {i}, Filter {j}: Mock instance mismatch. "
                        f"Expected {expected_filter_type_or_instance}, got {actual_filter_obj}"
                    )
                else:
                    # expected_filter_type_or_instance здесь будет Type[Command] или Type[MagicFilter]
                    # If a filter type is expected (Command, MagicFilter)
                    expected_type_to_check: type[Command | MagicFilter] = expected_filter_type_or_instance
                    assert isinstance(actual_filter_obj, expected_type_to_check), (
                        f"Registration {i}, Filter {j}: Type mismatch. "
                        f"Expected instance of {expected_type_to_check}, got {type(actual_filter_obj)}"
                    )
                    for attr_name, expected_value in expected_attrs.items():
                        actual_value: Any = getattr(actual_filter_obj, attr_name)
                        assert actual_value == expected_value, (
                            f"Registration {i}, Filter {j} ({expected_type_to_check.__name__}): "
                            f"Attribute '{attr_name}' mismatch. "
                            f"Expected {expected_value!r}, got {actual_value!r}"
                        )
        # Checking error handler registration
        mocks.mock_private_router.errors.register.assert_called_once_with(ErrHandler)
