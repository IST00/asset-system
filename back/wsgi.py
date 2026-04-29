"""Gunicorn entry point: `gunicorn -c gunicorn.conf.py wsgi:app`.

Profile selection happens via the FLASK_ENV environment variable. Set it
on the deploy environment, e.g.::

    FLASK_ENV=prod gunicorn -c gunicorn.conf.py wsgi:app

We bootstrap the matching .env file (.env.dev or .env.prod) before
calling create_app() so that os.getenv() lookups in config.py see the
file's values. System env vars always override file values.
"""

from config import bootstrap_env

bootstrap_env()

from app import create_app  # noqa: E402

app = create_app()
