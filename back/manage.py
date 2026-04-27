"""Flask CLI entry point.

Usage::

    python manage.py run                     # flask dev server
    python manage.py db upgrade              # apply migrations
    python manage.py db migrate -m "..."     # autogen a migration
"""

from __future__ import annotations

import os

import click

from app import create_app

app = create_app()


@app.cli.command("run")
@click.option("--host", default="0.0.0.0")
@click.option("--port", default=5000, type=int)
def run_cmd(host: str, port: int) -> None:  # pragma: no cover
    """Start the dev server (equivalent to `flask run`)."""
    app.run(host=host, port=port, debug=app.config.get("DEBUG", False))


if __name__ == "__main__":  # pragma: no cover
    # Allow `python manage.py run` without `flask` on PATH.
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "run":
        host = os.getenv("FLASK_RUN_HOST", "0.0.0.0")
        port = int(os.getenv("FLASK_RUN_PORT", "5000"))
        app.run(host=host, port=port, debug=app.config.get("DEBUG", False))
    else:
        # Fall through to Flask's CLI for `db`, etc.
        from flask.cli import main

        main()
