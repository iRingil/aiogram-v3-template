"""
Unit tests for src/tgbot/misc/log_setup.py.

Both classes configure process-wide singletons (the loguru sinks and the stdlib root logger), so the
autouse fixture restores them after every test.
"""

# ruff: noqa: PLR2004, S101

import io
import logging
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from loguru import logger

from tgbot.misc import log_setup
from tgbot.misc.log_setup import InterceptHandler, LoggingManager

if TYPE_CHECKING:
    from types import TracebackType

__all__: tuple[str, ...] = ()

type ExcInfo = tuple[type[BaseException], BaseException, TracebackType | None] | tuple[None, None, None]


@pytest.fixture(autouse=True)
def _restore_logging_state(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """
    Restores the stdlib root logger's handlers and level, and removes the loguru sinks added by a test.

    :param monkeypatch: pytest fixture used to restore the root logger.
    :return: None
    """
    monkeypatch.setattr(target=logging.root, name="handlers", value=logging.root.handlers[:])
    monkeypatch.setattr(target=logging.root, name="level", value=logging.root.level)
    yield
    logger.remove()


@pytest.fixture(name="records")
def records_fixture() -> Iterator[list]:
    """
    Adds a loguru sink that records every emitted record, regardless of level.

    :return: The list the records are appended to.
    """
    records: list = []
    sink_id: int = logger.add(sink=lambda message: records.append(message.record), level=0)
    yield records
    logger.remove(sink_id)


def _record(level: int, exc_info: ExcInfo | None = None) -> logging.LogRecord:
    """
    Builds a stdlib log record.

    :param level: Numeric level of the record.
    :param exc_info: Exception info to attach.
    :return: The log record.
    """
    return logging.LogRecord(
        name="some.library", level=level, pathname=__file__, lineno=1, msg="disk at %d%%", args=(90,), exc_info=exc_info
    )


def test_emit_known_level(records: list) -> None:
    """
    Test that a known level is forwarded by name, with the message formatted.

    :param records: Fixture capturing every loguru record.
    :return: None
    """
    InterceptHandler().emit(_record(level=logging.WARNING))
    assert records[0]["level"].name == "WARNING"
    assert records[0]["message"] == "disk at 90%"


def test_emit_unknown_level(records: list) -> None:
    """
    Test that a level loguru does not know is forwarded by its number.

    :param records: Fixture capturing every loguru record.
    :return: None
    """
    InterceptHandler().emit(_record(level=15))
    assert records[0]["level"].no == 15


def test_emit_exception(records: list) -> None:
    """
    Test that the exception info of a record is forwarded to loguru.

    :param records: Fixture capturing every loguru record.
    :return: None
    """
    try:
        raise ValueError("boom")  # noqa: TRY301 - the exception info is needed for the record
    except ValueError:
        InterceptHandler().emit(_record(level=logging.ERROR, exc_info=sys.exc_info()))
    assert str(records[0]["exception"].value) == "boom"


def test_emit_caller_location(records: list) -> None:
    """
    Test that the reported location is the real caller, not the logging module internals.

    :param records: Fixture capturing every loguru record.
    :return: None
    """
    std_logger: logging.Logger = logging.getLogger("test.intercept_handler.depth")
    std_logger.handlers = [InterceptHandler()]
    std_logger.propagate = False
    std_logger.warning("boom")
    assert records[0]["file"].path == __file__
    assert records[0]["function"] == "test_emit_caller_location"


def _console(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, debug: bool) -> io.StringIO:
    """
    Constructs a LoggingManager with the console sink redirected to an in-memory stream.

    :param monkeypatch: pytest fixture used to redirect the console sink.
    :param tmp_path: Temporary directory used as the log directory.
    :param debug: Debug flag.
    :return: The stream the console sink writes to.
    """
    stream: io.StringIO = io.StringIO()
    monkeypatch.setattr(target=log_setup, name="stderr", value=stream)
    LoggingManager(debug=debug, log_dir=tmp_path, project_name="test-project")
    return stream


def test_console_debug(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    Test that in debug mode the console gets DEBUG messages with the source location.

    :param monkeypatch: pytest fixture used to redirect the console sink.
    :param tmp_path: Temporary directory used as the log directory.
    :return: None
    """
    stream: io.StringIO = _console(monkeypatch, tmp_path, debug=True)
    logger.debug("debug detail")
    assert "debug detail" in stream.getvalue()
    assert "test_console_debug" in stream.getvalue()


def test_console_no_debug(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    Test that without debug the console gets INFO but not DEBUG messages, without the source location.

    :param monkeypatch: pytest fixture used to redirect the console sink.
    :param tmp_path: Temporary directory used as the log directory.
    :return: None
    """
    stream: io.StringIO = _console(monkeypatch, tmp_path, debug=False)
    logger.debug("debug detail")
    logger.info("heartbeat")
    assert "debug detail" not in stream.getvalue()
    assert "heartbeat" in stream.getvalue()
    assert "test_console_no_debug" not in stream.getvalue()


def test_file_sink(tmp_path: Path) -> None:
    """
    Test the log file: created directory, hyphenated name, INFO level and the source location.

    :param tmp_path: Temporary directory used to nest the log directory.
    :return: None
    """
    log_dir: Path = tmp_path / "nested" / "logs"
    LoggingManager(debug=False, log_dir=log_dir, project_name="My Bot")
    logger.debug("debug detail")
    logger.info("heartbeat")
    logger.complete()
    content: str = (log_dir / "My-Bot.log").read_text(encoding="utf-8")
    assert "debug detail" not in content
    assert "heartbeat" in content
    assert "test_file_sink" in content


def test_removes_previous_sinks(tmp_path: Path) -> None:
    """
    Test that the sinks configured before are removed.

    :param tmp_path: Temporary directory used as the log directory.
    :return: None
    """
    stale: list = []
    logger.add(sink=stale.append, level=0)
    LoggingManager(debug=True, log_dir=tmp_path, project_name="test-project")
    logger.info("after re-init")
    assert not stale


@pytest.mark.parametrize(("debug", "level"), [(True, logging.DEBUG), (False, logging.INFO)])
def test_root_logger(tmp_path: Path, *, debug: bool, level: int) -> None:
    """
    Test that the InterceptHandler is the only root handler and the root level follows the debug flag.

    :param tmp_path: Temporary directory used as the log directory.
    :param debug: Debug flag.
    :param level: Expected root logger level.
    :return: None
    """
    logging.root.handlers = [logging.NullHandler()]
    LoggingManager(debug=debug, log_dir=tmp_path, project_name="test-project")
    assert len(logging.root.handlers) == 1
    assert isinstance(logging.root.handlers[0], InterceptHandler)
    assert logging.root.level == level


def test_stdlib_forwarded(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """
    Test that a stdlib logging message (as aiogram logs) reaches the loguru console sink.

    :param monkeypatch: pytest fixture used to redirect the console sink.
    :param tmp_path: Temporary directory used as the log directory.
    :return: None
    """
    stream: io.StringIO = _console(monkeypatch, tmp_path, debug=True)
    logging.getLogger("some.library").warning("third-party warning")
    assert "third-party warning" in stream.getvalue()
