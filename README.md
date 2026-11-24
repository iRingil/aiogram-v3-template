<!--suppress ALL -->
<p align="center">
    <a href="https://www.python.org/downloads/release/python-3130/">
        <img src="https://img.shields.io/badge/python-v3.13-informational" alt="python version">
    </a>
    <a href="https://pypi.org/project/aiogram/3.31.0/">
        <img src="https://img.shields.io/badge/aiogram-v3.31.0-informational" alt="aiogram version">
    </a>
    <a href="https://pypi.org/project/asyncpg/0.32.0/">
        <img src="https://img.shields.io/badge/asyncpg-v0.32.0-informational" alt="asyncpg version">
    </a>
    <a href="https://pypi.org/project/redis/8.1.0/">
        <img src="https://img.shields.io/badge/redis-v8.1.0-informational" alt="redis version">
    </a>
    <a href="https://pypi.org/project/pydantic/2.13.5/">
        <img src="https://img.shields.io/badge/pydantic-v2.13.5-informational" alt="pydantic version">
    </a>
    <a href="https://pypi.org/project/APScheduler/3.11.3/">
        <img src="https://img.shields.io/badge/APScheduler-v3.11.3-informational" alt="APScheduler version">
    </a>
    <a href="https://pypi.org/project/Jinja2/3.1.6/">
        <img src="https://img.shields.io/badge/Jinja2-v3.1.6-informational" alt="Jinja2 version">
    </a>
    <a href="https://pypi.org/project/babel/2.18.0/">
        <img src="https://img.shields.io/badge/babel-v2.18.0-informational" alt="babel version">
    </a>
    <a href="https://pypi.org/project/environs/15.2.0/">
        <img src="https://img.shields.io/badge/environs-v15.2.0-informational" alt="environs version">
    </a>
    <a href="https://pypi.org/project/loguru/0.8.0/">
        <img src="https://img.shields.io/badge/loguru-v0.8.0-informational" alt="loguru version">
    </a>
</p>

<p align="center">
    <a href="https://github.com/iRingil/aiogram-v3-template/actions/workflows/dependabot/dependabot-updates">
        <img src="https://github.com/iRingil/aiogram-v3-template/actions/workflows/dependabot/dependabot-updates/badge.svg" alt="Dependabot Updates">
    </a>
    <a href="https://github.com/iRingil/aiogram-v3-template/actions/workflows/dependency-review.yml">
        <img src="https://github.com/iRingil/aiogram-v3-template/actions/workflows/dependency-review.yml/badge.svg" alt="Dependency Review">
    </a>
    <a href="https://github.com/iRingil/aiogram-v3-template/actions/workflows/codeql.yml">
        <img src="https://github.com/iRingil/aiogram-v3-template/actions/workflows/codeql.yml/badge.svg" alt="Code QL">
    </a>
    <a href="https://github.com/iRingil/aiogram-v3-template/actions/workflows/lint.yml">
        <img src="https://github.com/iRingil/aiogram-v3-template/actions/workflows/lint.yml/badge.svg" alt="Lint">
    </a>
    <a href="https://github.com/iRingil/aiogram-v3-template/actions/workflows/pytest.yml">
        <img src="https://github.com/iRingil/aiogram-v3-template/actions/workflows/pytest.yml/badge.svg" alt="Pytest">
    </a>
    <a href="https://github.com/astral-sh/ruff">
        <img alt="Ruff" src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json">
    </a>
    <a href="https://github.com/iRingil/aiogram-v3-template/blob/master/LICENCE.md">
        <img src="https://img.shields.io/badge/license-Unlicense-success" alt="Unlicense">
    </a>
</p>

# aiogram v3 bot template

A starting point for a Telegram bot on **aiogram 3**: fork it and build the bot on top. The modules are thin
scaffolding with the plumbing a production bot needs already in place, covered by tests line for line.

### Features

- **Layered handlers** - thin aiogram handlers, services with the logic, Jinja2 templates for every message.
- **English and Russian** - messages and the command menu are translated with Babel, per user language.
- **PostgreSQL** - a connection pool, transactions, typed rows and a `users` table the bot fills on its own.
- **Redis** - FSM storage and an anti-flood limit shared by every bot process.
- **Long polling or a webhook** - the webhook server runs behind nginx and checks Telegram's secret token.
- **Config validation** - every value of `.env` is checked on start; a wrong one stops the bot with a clear error.
- **Logging** - loguru on the console and in a file, the standard logging of aiogram and APScheduler included.
- **Scheduler** - APScheduler for cron jobs, a rate-limited broadcaster for sending to many users.

### Architecture

`src/bot.py` builds everything and starts the bot. A request goes through three layers:

1. **Handlers** (`tgbot/handlers/`) - aiogram entry points; `handlers/main.py` registers every route.
2. **Services** (`tgbot/services/`) - the logic; the base service edits a message or sends a new one.
3. **Presentation** - templates in `tgbot/templates/<feature>/`, keyboards in `tgbot/misc/keyboards.py`.

Database access goes through repositories (`tgbot/db/`); the tables are created on start, a change to an existing
one is applied by hand. Dependencies are passed in constructors, without a DI framework. The details are in
[.claude/CLAUDE.md](.claude/CLAUDE.md).

### Requirements

- Python 3.13
- PostgreSQL
- Redis with a user and a password (ACL)
- nginx with a TLS certificate - only in webhook mode

### Installation

```bash
git clone https://github.com/iRingil/aiogram-v3-template.git
cd aiogram-v3-template
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r src/requirements.txt
cp src/.env.example src/.env
```

### Setup and run

1. Fill in `src/.env`: `BOT_TOKEN` from [@BotFather](https://t.me/BotFather), `ADMIN_IDS` (Telegram IDs, comma
   separated), the PostgreSQL (`PG_*`) and Redis (`REDIS_*`) connection. The mode switches are `true`/`false`,
   false when absent: `DEBUG` (verbose logs and full tracebacks - never in production), `USE_WEBHOOK`
   (`WEBHOOK_*` and `WEBAPP_*` are then required), `USE_POSTGRES_SOCKET` / `USE_REDIS_SOCKET` (a Unix socket
   instead of a host and a port).
2. Compile the translations: `infrastructure/localization/compile_translations.sh` (`.cmd` on Windows).
3. Run: `cd src && python bot.py`

Logs are written to `src/logs/`.

### Localization

Messages are Jinja2 templates with `{% trans %}` blocks; translations live in `src/tgbot/locales/<lang>`. After a
change of the translatable texts run the scripts in `infrastructure/localization/` in this order:
`extract_strings_for_translate`, `update_translations` (`init_translations` for a new language), then
`compile_translations` - the bot reads only the compiled `.mo` files, which are not kept in git. The language list
is in the update and init scripts.

### Development

```bash
pip install -r src/requirements-dev.txt
ruff check src tests          # lint (Ruff, installed globally - version pinned in .github/workflows/lint.yml)
ruff format src tests         # format
basedpyright                  # type check (installed globally, reads the packages from .venv)
pytest tests --cov            # fails below 100% coverage of lines and branches
```

The database code is tested against a real PostgreSQL (`127.0.0.1:5432`, database `test_db`) and Redis
(`127.0.0.1:6379`, database 15), both with the user `test_user` / `test_password` - see `tests/conftest.py`;
CI starts them as service containers.

### Installation on a server

There is no deploy script: the bot is installed by hand, by these rules.

- **Its own user, never root.** The bot runs as the system user `tgbot` from `/opt/tgbot`; nothing in that folder
  belongs to root.
- **Secrets only in `src/.env`**, readable by the bot's user alone (`chmod 600`), `DEBUG=False`.
- **PostgreSQL and Redis on the same server**, reached over `127.0.0.1` or a Unix socket: the connections are
  not encrypted. Each has its own user and password for the bot.
- **Only the runtime dependencies** (`src/requirements.txt`): no tests or dev tools on the server.
- **A tagged release**, not whatever `master` is at the moment.

The steps, as root:

```bash
# 1. The user and the code
useradd --system --home-dir /opt/tgbot --shell /usr/sbin/nologin tgbot
install -d -o tgbot -g tgbot /opt/tgbot
sudo -u tgbot git clone --branch <tag> --depth 1 https://github.com/<you>/<your-bot>.git /opt/tgbot

# 2. The environment and the translations
cd /opt/tgbot
sudo -u tgbot python3.13 -m venv .venv
sudo -u tgbot .venv/bin/pip install -r src/requirements.txt
sudo -u tgbot .venv/bin/pybabel compile --directory=src/tgbot/locales

# 3. The settings
sudo -u tgbot install -m 600 src/.env.example src/.env
sudo -u tgbot nano src/.env

# 4. The service and the log rotation
cp infrastructure/systemd/tgbot.service /etc/systemd/system/
cp infrastructure/logrotate/tgbot /etc/logrotate.d/
systemctl daemon-reload && systemctl enable --now tgbot
```

PostgreSQL needs a database and a user that owns it (the bot creates its tables on start). In Redis create the
user with an ACL limited to the bot's keys (`tgbot_fsm:*` for FSM, `tgbot_flood:*` for the anti-flood) and its
database index, for example `ACL SETUSER tgbot on '>password' '~tgbot_*' '+@all' '-@dangerous' '-select' '+select|<index>'`.

In webhook mode put `infrastructure/nginx/tgbot.conf` into nginx: replace the domain, the upstream address
(`WEBAPP_HOST:WEBAPP_PORT`) and the secret token (`WEBHOOK_TOKEN`), and make its `location` match `WEBHOOK_PATH`.

To update: `sudo -u tgbot git -C /opt/tgbot fetch --depth 1 origin tag <tag> && sudo -u tgbot git -C /opt/tgbot
checkout <tag>`, then step 2 again and `systemctl restart tgbot`. A change to an existing table is applied to the
database by hand before the restart.

The service writes its log to `/opt/tgbot/src/logs/tgbot.log` and the rest to the journal (`journalctl -u tgbot`).

### Developers

* [Ringil](https://github.com/iRingil)

### License

[The Unlicense](LICENCE.md) - public domain.
