# CLAUDE.md

Template for Telegram bots on **aiogram 3.x** (Python 3.13): handler/service layers, Jinja2 messages,
Babel i18n, PostgreSQL (asyncpg) and Redis (FSM, anti-flood) both required, optional webhook,
APScheduler. Meant to be forked; most modules are thin scaffolding.

## Commands

`src/` is the source root (on `pythonpath` via `pyproject.toml`); the bot runs from `src/`, the rest from
the repo root.

```bash
cd src && python bot.py
pytest tests --cov                                     # fails below 100% coverage, as in CI
ruff check src tests && ruff format --check src tests
basedpyright                                           # 0 errors, typeCheckingMode "all"
pip install -r src/requirements.txt -r src/requirements-dev.txt
```

CI on push/PR to `master`: pytest and `Lint` (pip-audit, Ruff, basedpyright). Ruff and basedpyright are
global installs (`%APPDATA%\Python\Scripts`), not in `.venv`; their versions are pinned in
`.github/workflows/lint.yml` - bump both together.

## Code rules

- Ruff `select = ["ALL"]`; a new global ignore in `pyproject.toml` only with the user's consent. Test-only
  rules go in a per-file `# ruff: noqa: ...` with just the codes that file needs; other exceptions are
  local `# noqa: CODE - reason` / `# pyright: ignore[rule] - reason`. `src/` has no `Any`.
- Docstrings: text from the second line, closing quotes on their own line (D213 + D209).
- PyCharm inspections (grammar included) are not in CI: before a commit run `get_file_problems`
  (PyCharm MCP, `errorsOnly: false`) on every changed file and fix the findings. A false positive gets
  `# noinspection Id` above the statement with the reason above it; one reported as redundant does not
  work there.
- Handlers only delegate to services; services never build message text inline (templates and
  `KeyboardManager`); callback data is a `CallbackData` factory. DI is manual, through constructors.
- Exceptions are caught where an async result is awaited, not logged and swallowed inside.
- Queries live in repositories (`tgbot/db/`), DDL in `db/schema.py` (`CREATE TABLE IF NOT EXISTS`, no
  migrations: change an existing table by hand). Stores (`tgbot/storage/`) call Redis commands directly;
  `RedisValue` narrows redis-py's loose types. The PostgreSQL pool opens in `connect()`, not `__init__`.
- A new update type must be added to `_ALLOWED_UPDATES` in `bot.py`.

## Configuration

Everything comes from `src/.env` (copy `src/.env.example`); real environment variables win. Pydantic
models in `misc/data_types.py` validate the values, `Config` raises `EnvError` on bad or missing ones.
Secrets are `SecretStr`. Switches are false when absent: `DEBUG`, `USE_WEBHOOK`,
`USE_POSTGRES_SOCKET` / `USE_REDIS_SOCKET`.

## Localization

Languages `en`, `ru` (`all_locales` in the update/init scripts). After changing template strings run the
scripts in `infrastructure/localization/` (`.sh` / `.cmd`): `extract_strings_for_translate`,
`update_translations` (`init_translations` for a new language), `compile_translations`. Commit `.po`
and `.mo` together.

## Tests

`tests/` mirrors `src/`; `asyncio_mode = "auto"`. Reach a mock that replaced a typed attribute through
`tests.helpers.mocked(...)`. Database code runs against real databases (`tests/conftest.py`): PostgreSQL
`test_db` and Redis db 15, user `test_user` / `test_password`, cleaned around each test. Locally they are
WSL PostgreSQL 17 and Redis 8.4 on `127.0.0.1` (WSL must be running); CI starts service containers. Mock
only what a test database can't produce (a Unix socket, a database error).

## Deployment

Manual, by `README.md` ("Installation on a server"): `/opt/tgbot`, user `tgbot`. Reference nginx,
systemd and logrotate configs are in `infrastructure/`, install steps in each file's header.
