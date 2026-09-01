#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temporary_root="$(mktemp -d)"

cleanup() {
  case "$temporary_root" in
    /tmp/*|/private/tmp/*|/private/var/folders/*) rm -rf -- "$temporary_root" ;;
    *) printf 'Refusing to remove unexpected temporary path\n' >&2 ;;
  esac
}
trap cleanup EXIT

uv venv --python 3.13 "$temporary_root/python"
UV_CACHE_DIR="$temporary_root/uv-cache" uv pip sync \
  --python "$temporary_root/python/bin/python" \
  --no-cache \
  "$repository_root/back/requirements.lock"
UV_CACHE_DIR="$temporary_root/uv-cache" uv pip install \
  --python "$temporary_root/python/bin/python" \
  --no-cache \
  "pip==$(tr -d '[:space:]' < "$repository_root/back/.pip-version")"
"$temporary_root/python/bin/python" -m pip check

mkdir -p "$temporary_root/root"
cp "$repository_root/package.json" "$repository_root/package-lock.json" \
  "$temporary_root/root/"
(
  cd "$temporary_root/root"
  npm ci --ignore-scripts --cache "$temporary_root/npm-root-cache"
)

rsync -a \
  --exclude node_modules \
  --exclude dist \
  "$repository_root/front/" "$temporary_root/front/"
(
  cd "$temporary_root/front"
  npm ci --ignore-scripts --cache "$temporary_root/npm-front-cache"
)
npm --prefix "$temporary_root/front" run type-check
npm --prefix "$temporary_root/front" test
npm --prefix "$temporary_root/front" run lint
npm --prefix "$temporary_root/front" run build:prod
