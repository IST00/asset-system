#!/bin/sh
set -eu

echo "Applying database migrations..."
FLASK_APP=manage.py flask db upgrade

echo "Starting application..."
exec "$@"
