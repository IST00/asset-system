#!/bin/sh
set -eu

echo "Checking database environment contract..."
FLASK_APP=manage.py flask check-database-environment

echo "Applying database migrations..."
FLASK_APP=manage.py flask db upgrade

echo "Starting application..."
exec "$@"
