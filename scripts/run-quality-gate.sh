#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$repository_root/back"
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app/ config.py
.venv/bin/python -m pytest

cd "$repository_root/front"
npm run type-check
npm run lint
npm test
npm run build:prod
