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

import logging
import os
import sys
import threading

import click

_log = logging.getLogger("manage.scaffold")


def _start_health_thread(business_app) -> None:  # type: ignore[no-untyped-def]
    """Boot the health-check Flask app on a daemon thread (dev/test path).

    Mirrors what gunicorn.conf.py:post_fork does for prod, so `:8081/health`
    works the same regardless of how the server was launched.
    """
    try:
        from app.health import bind_business_app, run_health_server

        bind_business_app(business_app)
        t = threading.Thread(
            target=run_health_server,
            name="health-server",
            daemon=True,
        )
        t.start()
        _log.info("health server thread started (dev/test)")
    except Exception as exc:  # pragma: no cover
        _log.warning("failed to start health server: %s", exc)


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
    _start_health_thread(app)
    app.run(host=host, port=port, debug=app.config.get("DEBUG", False))


@app.cli.command("reset-admin-password")
@click.option("--username", default="admin", show_default=True)
@click.password_option(confirmation_prompt=True)
def reset_admin_password(username: str, password: str) -> None:
    """Reset a local SUPER_ADMIN password and force first-login change."""
    from app.common import BusinessException
    from app.services import security_service

    try:
        security_service.reset_super_admin_password(
            username=username, new_password=password
        )
    except BusinessException as exc:
        raise click.ClickException(exc.message) from exc
    click.echo(f"Password reset for {username}; next login must change it.")


@app.cli.command("cleanup-security-data")
@click.option(
    "--event-retention-days", default=365, show_default=True, type=click.IntRange(min=1)
)
@click.option(
    "--session-retention-days",
    default=30,
    show_default=True,
    type=click.IntRange(min=1),
)
def cleanup_security_data(
    event_retention_days: int, session_retention_days: int
) -> None:
    """Remove expired limiter buckets and security records past retention."""
    from app.services import security_service

    result = security_service.cleanup_security_data(
        event_retention_days=event_retention_days,
        session_retention_days=session_retention_days,
    )
    click.echo(
        "Security cleanup complete: "
        f"events={result['security_events']}, "
        f"sessions={result['user_sessions']}, "
        f"rate_buckets={result['rate_limit_buckets']}"
    )


@app.cli.command("cleanup-export-files")
def cleanup_export_files() -> None:
    """Delete expired generated exports and mark their jobs expired."""
    from app.services import export_service

    removed = export_service.cleanup_expired_files()
    click.echo(f"Export cleanup complete: files={removed}")


@app.cli.command("check-database-environment")
def check_database_environment() -> None:
    """Validate MySQL version, utf8mb4 charsets, and the UTC session."""
    from sqlalchemy import text

    from app.environment import validate_database_contract
    from app.extensions import db

    metadata = (
        db.session.execute(
            text(
                """
                SELECT VERSION() AS version,
                       @@character_set_server AS character_set_server,
                       @@character_set_database AS character_set_database,
                       @@character_set_connection AS character_set_connection,
                       @@session.time_zone AS session_time_zone,
                       TIMESTAMPDIFF(SECOND, UTC_TIMESTAMP(), NOW())
                           AS utc_offset_seconds
                """
            )
        )
        .mappings()
        .one()
    )
    try:
        validate_database_contract(
            metadata,
            required_series=str(app.config["MYSQL_REQUIRED_SERIES"]),
        )
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo("database environment contract passed")


if __name__ == "__main__":  # pragma: no cover
    # Allow `python manage.py run` without `flask` on PATH.
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        host = os.getenv("FLASK_RUN_HOST", "0.0.0.0")
        port = int(os.getenv("FLASK_RUN_PORT", "8080"))
        _start_health_thread(app)
        app.run(host=host, port=port, debug=app.config.get("DEBUG", False))
    else:
        # Fall through to Flask's CLI for `db`, etc.
        from flask.cli import main

        main()
