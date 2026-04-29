"""Flask CLI entry point.

Usage::

    python manage.py run                     # dev profile (loads .env.dev)
    python manage.py run dev                 # explicit dev (positional)
    python manage.py run prod                # prod profile (loads .env.prod)
    python manage.py run --env prod          # same, flag form
    python manage.py db upgrade              # apply migrations
    python manage.py db migrate -m "..."     # autogen a migration

The active profile is determined by (highest precedence first):
    1. argv ('prod' / 'dev' / 'test', or '--env <name>')
    2. FLASK_ENV env var
    3. default 'dev'

After resolution, the matching .env file (back/.env.dev or back/.env.prod)
is loaded; system env vars always win over the file.
"""

from __future__ import annotations

import os
import sys

import click

_VALID_PROFILES = {"dev", "development", "prod", "production", "test", "testing"}


def _resolve_profile_from_argv() -> str | None:
    """Pop a profile selector out of argv (so Click never sees it).

    Supported forms (only when sys.argv[1] == 'run'):
        python manage.py run prod
        python manage.py run --env prod
    """
    if len(sys.argv) < 3 or sys.argv[1] != "run":
        return None

    token = sys.argv[2]
    if token in _VALID_PROFILES:
        return sys.argv.pop(2).lower()
    if token == "--env" and len(sys.argv) >= 4:
        sys.argv.pop(2)  # drop "--env"
        return sys.argv.pop(2).lower()
    return None


# 1. Resolve profile from argv before anything else.
_argv_profile = _resolve_profile_from_argv()
if _argv_profile:
    os.environ["FLASK_ENV"] = _argv_profile

# 2. Load the matching .env file. Must happen BEFORE `from app import ...`
#    so that any module-level os.getenv() in config.py / app sees the
#    file values.
from config import bootstrap_env  # noqa: E402

bootstrap_env()

# 3. Now safe to build the Flask app.
from app import create_app  # noqa: E402

app = create_app()


@app.cli.command("run")
@click.option("--host", default="0.0.0.0")
@click.option("--port", default=8080, type=int)
def run_cmd(host: str, port: int) -> None:  # pragma: no cover
    """Start the dev server (equivalent to `flask run`)."""
    app.run(host=host, port=port, debug=app.config.get("DEBUG", False))


if __name__ == "__main__":  # pragma: no cover
    # Allow `python manage.py run` without `flask` on PATH.
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        host = os.getenv("FLASK_RUN_HOST", "0.0.0.0")
        port = int(os.getenv("FLASK_RUN_PORT", "8080"))
        app.run(host=host, port=port, debug=app.config.get("DEBUG", False))
    else:
        # Fall through to Flask's CLI for `db`, etc.
        from flask.cli import main

        main()
