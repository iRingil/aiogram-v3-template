"""
Unit tests for src/tgbot/misc/tmpl_render.py.

Real Jinja2 templates and real Babel .mo catalogs (compiled in-process) are built under tmp_path,
nothing about the i18n wiring is mocked.
"""

# ruff: noqa: S101, SLF001

from asyncio import gather
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from babel.messages.catalog import Catalog
from babel.messages.mofile import write_mo
from babel.support import NullTranslations, Translations
from jinja2 import Environment, TemplateNotFound, meta, nodes

from tgbot.misc.data_types import Paths
from tgbot.misc.tmpl_render import TmplRender

if TYPE_CHECKING:
    from collections.abc import Callable

__all__: tuple[str, ...] = ()

# The bot's own templates (tests/src/tgbot/misc -> the repository root -> src/tgbot)
_BOT_DIR: Path = Path(__file__).parents[4] / "src" / "tgbot"
# Markup put into every value of a template, and how it must come out
_MARKUP: str = '<b>&"'
_ESCAPED: str = "&lt;b&gt;&amp;&#34;"


@pytest.fixture(name="paths")
def paths_fixture(tmp_path: Path) -> Paths:
    """
    Creates a Paths object with the template and locale directories.

    :param tmp_path: Temporary directory provided by pytest.
    :return: Paths object.
    """
    paths: Paths = Paths(
        locale=tmp_path / "locales", bot_logo=tmp_path / "logo.jpg", temp=tmp_path / "temp", tmpl=tmp_path / "tmpl"
    )
    paths.locale.mkdir()
    paths.tmpl.mkdir()
    return paths


def _write_template(paths: Paths, content: str, name: str = "test.jinja2") -> None:
    """
    Writes a template file.

    :param paths: Paths object.
    :param content: Template source.
    :param name: Template file name.
    :return: None
    """
    (paths.tmpl / name).write_text(content, encoding="utf-8")


def _compile_catalog(paths: Paths, locale: str, messages: dict[str | tuple[str, str], str | tuple[str, str]]) -> None:
    """
    Compiles a .mo catalog for one locale in the layout Translations.load expects.

    :param paths: Paths object.
    :param locale: Language code.
    :param messages: Maps each msgid (or singular/plural pair) to its translation.
    :return: None
    """
    catalog: Catalog = Catalog(locale=locale)
    for msgid, msgstr in messages.items():
        catalog.add(id=msgid, string=msgstr)
    mo_dir: Path = paths.locale / locale / "LC_MESSAGES"
    mo_dir.mkdir(parents=True)
    with (mo_dir / "messages.mo").open(mode="wb") as file:
        write_mo(fileobj=file, catalog=catalog)


@pytest.mark.parametrize(
    ("html", "max_len", "expected"),
    [
        ("<b>hi</b>", 4096, "<b>hi</b>"),  # Fits, unchanged
        ("plain text no tags at all", 10, "plain t..."),  # No tags
        ("<b>Hello</b><i>World</i>", 15, "<b>Hello</b>..."),  # Cut right after a balanced pair, content kept
        ("<b>Hello</b><i>World</i>", 20, "<b>Hello</b>..."),  # Backs up before a tag left open
        ("<b>unterminated", 10, "..."),  # The first tag is left open
        ("<br/>Hello World, this is a long line of text", 15, "<br/>Hello W..."),  # Self-closing tag
        ('<a href="x">Link</a> and some trailing padding text here', 25, '<a href="x">Link</a> a...'),  # Attributes
        ("<i>a</i></b> and some trailing padding", 20, "<i>a</i></b> and ..."),  # Unmatched closing tag
        ('plain text <a href="https://example.com/very/long">link</a>', 23, "plain text ..."),  # Cut inside a tag
        ('<b>Hello <a href="https://example.com/very/long">link</a></b>', 23, "..."),  # Inside a nested tag
    ],
)
def test_smart_trunc(html: str, max_len: int, expected: str) -> None:
    """
    Test the HTML-aware truncation.

    :param html: Source HTML.
    :param max_len: Maximum length.
    :param expected: Expected result.
    :return: None
    """
    assert TmplRender._smart_trunc(html=html, max_len=max_len) == expected


def test_get_locales(paths: Paths) -> None:
    """
    Test that only the subdirectories of the locale directory are listed.

    :param paths: Fixture providing the Paths object.
    :return: None
    """
    (paths.locale / "ru").mkdir()
    (paths.locale / "en").mkdir()
    (paths.locale / "README.txt").write_text("not a locale", encoding="utf-8")
    assert sorted(TmplRender(paths=paths).get_locales()) == ["en", "ru"]


async def test_render_data(paths: Paths) -> None:
    """
    Test that template variables are substituted, and a template without data renders too.

    :param paths: Fixture providing the Paths object.
    :return: None
    """
    _write_template(paths, "Hello, {{ name }}!")
    _write_template(paths, "Static", name="static.jinja2")
    tmpl: TmplRender = TmplRender(paths=paths)
    assert await tmpl.render(tmpl="test.jinja2", locale="en", data={"name": "Test"}) == "Hello, Test!"
    assert await tmpl.render(tmpl="static.jinja2", locale="en") == "Static"


async def test_render_escapes_data(paths: Paths) -> None:
    """
    Test that a passed value is escaped for Telegram HTML, while the markup of the template and the translation stays.

    A user named "<3" would otherwise be taken for a tag and Telegram would reject the message.

    :param paths: Fixture providing the Paths object.
    :return: None
    """
    _write_template(paths, "<b>{% trans %}Hi{% endtrans %}</b> {{ name }}")
    _write_template(paths, "{% trans name=name %}Hi, {{ name }}{% endtrans %}", name="trans_var.jinja2")
    _compile_catalog(paths, "ru", {"Hi": "<i>Privet</i>", "Hi, %(name)s": "<i>Privet</i>, %(name)s"})
    tmpl: TmplRender = TmplRender(paths=paths)
    name: str = '<3 & <a href="x">'
    escaped: str = "&lt;3 &amp; &lt;a href=&#34;x&#34;&gt;"
    assert await tmpl.render(tmpl="test.jinja2", locale="ru", data={"name": name}) == f"<b><i>Privet</i></b> {escaped}"
    assert await tmpl.render(tmpl="trans_var.jinja2", locale="ru", data={"name": name}) == f"<i>Privet</i>, {escaped}"


async def test_render_translation(paths: Paths) -> None:
    """
    Test that a trans block is translated, and a locale without a catalog falls back to the source.

    :param paths: Fixture providing the Paths object.
    :return: None
    """
    _write_template(paths, "{% trans %}Hello{% endtrans %}")
    _compile_catalog(paths, "ru", {"Hello": "Privet"})
    tmpl: TmplRender = TmplRender(paths=paths)
    assert await tmpl.render(tmpl="test.jinja2", locale="ru") == "Privet"
    assert await tmpl.render(tmpl="test.jinja2", locale="en") == "Hello"


async def test_render_plural(paths: Paths) -> None:
    """
    Test that a pluralize block picks the form by count.

    :param paths: Fixture providing the Paths object.
    :return: None
    """
    _write_template(paths, "{% trans count=count %}{{ count }} apple{% pluralize %}{{ count }} apples{% endtrans %}")
    _compile_catalog(paths, "en", {("%(count)s apple", "%(count)s apples"): ("one %(count)s", "many %(count)s")})
    tmpl: TmplRender = TmplRender(paths=paths)
    assert await tmpl.render(tmpl="test.jinja2", locale="en", data={"count": 1}) == "one 1"
    assert await tmpl.render(tmpl="test.jinja2", locale="en", data={"count": 3}) == "many 3"


async def test_render_caches_translations(paths: Paths, monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Test that a locale catalog is loaded from disk only once.

    :param paths: Fixture providing the Paths object.
    :param monkeypatch: pytest fixture used to spy on Translations.load.
    :return: None
    """
    _write_template(paths, "{% trans %}Hello{% endtrans %}")
    _compile_catalog(paths, "ru", {"Hello": "Privet"})
    original_load: Callable[..., NullTranslations] = Translations.load
    load_calls: list[str] = []

    def _counting_load(dirname: Path, locales: str) -> NullTranslations:
        """
        Records the call and delegates to the real Translations.load.

        :param dirname: Locale root directory.
        :param locales: Language code.
        :return: The loaded translations.
        """
        load_calls.append(locales)
        return original_load(dirname=dirname, locales=locales)

    monkeypatch.setattr(target=Translations, name="load", value=_counting_load)
    tmpl: TmplRender = TmplRender(paths=paths)
    await tmpl.render(tmpl="test.jinja2", locale="ru")
    await tmpl.render(tmpl="test.jinja2", locale="ru")
    assert load_calls == ["ru"]


async def test_render_concurrent_locales(paths: Paths) -> None:
    """
    Test that concurrent renders keep their own locale.

    :param paths: Fixture providing the Paths object.
    :return: None
    """
    _write_template(paths, "{% trans %}Hello{% endtrans %}")
    _compile_catalog(paths, "ru", {"Hello": "Privet"})
    tmpl: TmplRender = TmplRender(paths=paths)
    results = await gather(*(tmpl.render(tmpl="test.jinja2", locale="ru" if i % 2 == 0 else "en") for i in range(20)))
    assert set(results[0::2]) == {"Privet"}
    assert set(results[1::2]) == {"Hello"}


async def test_render_truncation(paths: Paths) -> None:
    """
    Test that output under max_len is untouched and longer output is truncated.

    :param paths: Fixture providing the Paths object.
    :return: None
    """
    _write_template(paths, "a very long piece of text")
    tmpl: TmplRender = TmplRender(paths=paths)
    assert await tmpl.render(tmpl="test.jinja2", locale="en", max_len=100) == "a very long piece of text"
    assert await tmpl.render(tmpl="test.jinja2", locale="en", max_len=10) == "a very ..."


async def test_render_missing_template(paths: Paths) -> None:
    """
    Test that a missing template raises TemplateNotFound.

    :param paths: Fixture providing the Paths object.
    :return: None
    """
    with pytest.raises(expected_exception=TemplateNotFound):
        await TmplRender(paths=paths).render(tmpl="missing.jinja2", locale="en")


@pytest.mark.parametrize(
    "name", sorted(path.relative_to(_BOT_DIR / "templates").as_posix() for path in _BOT_DIR.rglob("*.jinja2"))
)
async def test_bot_templates_escape_their_data(name: str) -> None:
    """
    Test that every template of the bot escapes the values passed to it, in both languages.

    Each variable the template uses gets markup; a template that outputs it raw (e.g. marked |safe) fails, since
    Telegram would reject the message or show the markup of a user.

    :param name: Template path under src/tgbot/templates.
    :return: None
    """
    templates: Path = _BOT_DIR / "templates"
    source: str = (templates / name).read_text(encoding="utf-8")
    parsed: nodes.Template = Environment(autoescape=True, extensions=["jinja2.ext.i18n"]).parse(source=source)
    variables: set[str] = meta.find_undeclared_variables(ast=parsed) - {"gettext", "ngettext", "_"}
    paths: Paths = Paths(
        locale=_BOT_DIR / "locales", bot_logo=_BOT_DIR / "assets", temp=_BOT_DIR / "temp", tmpl=templates
    )
    tmpl: TmplRender = TmplRender(paths=paths)
    for locale in ("en", "ru"):
        rendered: str = await tmpl.render(tmpl=name, locale=locale, data=dict.fromkeys(variables, _MARKUP))
        assert _MARKUP not in rendered
        assert rendered.count(_ESCAPED) == sum(source.count("{{ " + variable) for variable in variables)
