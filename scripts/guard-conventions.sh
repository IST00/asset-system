#!/usr/bin/env bash
#
# Lightweight convention guard (Python edition).
# Scans STAGED files only (git diff --cached) for obvious anti-patterns
# described in docs/conventions/*.md.
#
# Exit 0 when clean, 1 on violation.
# Runs from the scaffolding-python/ working directory.

set -u

staged="$(git diff --cached --name-only --diff-filter=ACM)"
[ -z "$staged" ] && exit 0

status=0
violations=""

add_violation() {
  violations+="  • $1"$'\n'
  status=1
}

# starts_with <path> <prefix>
starts_with() { case "$1" in "$2"*) return 0 ;; *) return 1 ;; esac; }
# ends_with <path> <suffix>
ends_with() { case "$1" in *"$2") return 0 ;; *) return 1 ;; esac; }

while IFS= read -r f; do
  [ -z "$f" ] && continue
  [ ! -f "$f" ] && continue

  # ============================================================
  # back/app/api/: API blueprints — no model import, no hand-built Result.fail,
  # no direct JWT decode (use flask_jwt_extended helpers)
  # ============================================================
  if starts_with "$f" "back/app/api/" && ends_with "$f" ".py"; then
    if grep -E '^[[:space:]]*from[[:space:]]+app\.models(\.|[[:space:]]+import)' "$f" >/dev/null 2>&1; then
      add_violation "$f: api blueprint imports a model directly (go through a service). See docs/conventions/backend.md §1"
    fi
    if grep -E '^[[:space:]]*from[[:space:]]+app\.(extensions[[:space:]]+import[[:space:]]+db|extensions)[[:space:]]*$' "$f" >/dev/null 2>&1; then
      add_violation "$f: api blueprint touches the db session directly (go through a service). See docs/conventions/backend.md §1"
    fi
    if grep -E 'Result\.fail[[:space:]]*\(' "$f" >/dev/null 2>&1; then
      add_violation "$f: do not build Result.fail() by hand — raise BusinessException(ResultCode.X). See docs/conventions/backend.md §2"
    fi
    if grep -E '\b(jwt\.decode|PyJWT|jose\.jwt)\b' "$f" >/dev/null 2>&1; then
      add_violation "$f: parse JWT only inside app/security/* (use flask_jwt_extended in api/*). See docs/conventions/backend.md §5"
    fi
  fi

  # ============================================================
  # back/app/services/: services — no hand-built Result.fail, no direct JWT decode
  # ============================================================
  if starts_with "$f" "back/app/services/" && ends_with "$f" ".py"; then
    if grep -E 'Result\.fail[[:space:]]*\(' "$f" >/dev/null 2>&1; then
      add_violation "$f: do not build Result.fail() by hand — raise BusinessException(ResultCode.X). See docs/conventions/backend.md §2"
    fi
    if grep -E '\b(jwt\.decode|PyJWT|jose\.jwt)\b' "$f" >/dev/null 2>&1; then
      add_violation "$f: parse JWT only inside app/security/* (not services/). See docs/conventions/backend.md §5"
    fi
  fi

  # ============================================================
  # back/requirements.txt — disallow alternate ORMs/web frameworks
  # ============================================================
  if [ "$f" = "back/requirements.txt" ]; then
    if grep -E '^[[:space:]]*(django|fastapi|tornado|peewee)([[:space:]<>=!~]|$)' "$f" >/dev/null 2>&1; then
      add_violation "$f: stick to Flask + SQLAlchemy — do not introduce a competing framework/ORM. See docs/conventions/backend.md §4"
    fi
  fi

  # ============================================================
  # back/migrations/versions/: Alembic migrations — strict {n}_{snake}.py naming
  # ============================================================
  if starts_with "$f" "back/migrations/versions/" && ends_with "$f" ".py"; then
    base="$(basename "$f")"
    if ! echo "$base" | grep -E '^[0-9]{3,}_[a-z0-9_]+\.py$' >/dev/null 2>&1; then
      add_violation "$f: migration filename must match {NNN}_<snake_desc>.py. See docs/conventions/backend.md §4"
    fi
  fi

  # ============================================================
  # front/src/: bypass @/api/http, deep relative imports, any, file-wide eslint-disable
  # ============================================================
  if starts_with "$f" "front/src/" && { ends_with "$f" ".ts" || ends_with "$f" ".tsx"; }; then
    if [ "$f" != "front/src/api/http.ts" ]; then
      if grep -E "^[[:space:]]*import[[:space:]]+.*['\"]axios['\"]" "$f" >/dev/null 2>&1; then
        add_violation "$f: do not import 'axios' directly — use '@/api/http'. See docs/conventions/frontend.md §1"
      fi
    fi
    if grep -E "fetch\([[:space:]]*['\"](/api/|https?://[^'\"]*:8080)" "$f" >/dev/null 2>&1; then
      add_violation "$f: do not call the backend via fetch() — use '@/api/http'. See docs/conventions/frontend.md §1"
    fi
    if grep -E "from[[:space:]]+['\"](\.\./){2,}" "$f" >/dev/null 2>&1; then
      add_violation "$f: use '@/' alias instead of '../../...'. See docs/conventions/frontend.md §3"
    fi
    if ! ends_with "$f" ".d.ts"; then
      if grep -E ':[[:space:]]*any([[:space:]]|,|=|\)|>|\|)' "$f" >/dev/null 2>&1; then
        add_violation "$f: TypeScript 'any' is forbidden — use a real type or 'unknown'. See docs/conventions/frontend.md §6"
      fi
    fi
    if head -5 "$f" | grep -E '/\*[[:space:]]*eslint-disable[[:space:]]*\*/' >/dev/null 2>&1; then
      add_violation "$f: file-wide /* eslint-disable */ is forbidden (line-level with reason is OK). See docs/conventions/frontend.md §6"
    fi
  fi

done <<< "$staged"

if [ $status -ne 0 ]; then
  echo ""
  echo "╭─ scaffold convention guard failed ────────────────────────────"
  echo "│"
  printf "%s" "$violations" | sed 's/^/│/'
  echo "│"
  echo "│  Fix the issues above, 'git add' again, then re-commit."
  echo "│  To read the full rules: docs/conventions/*.md"
  echo "╰────────────────────────────────────────────────────────────────"
  exit 1
fi

exit 0
