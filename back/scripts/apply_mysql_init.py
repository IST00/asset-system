#!/usr/bin/env python3
"""Apply back/migrations/sql/mysql_init.sql to a MySQL database.

Reads connection info from back/.env.prod (DB_HOST / DB_PORT / DB_USER /
DB_PASSWORD / DB_NAME, or DB_URL). Env vars in the current shell win over
the file — matches the convention in back/config.py.

Usage (from anywhere):
    python3 back/scripts/apply_mysql_init.py

Or, with overrides:
    DB_HOST=... DB_USER=... DB_PASSWORD=... DB_NAME=... \\
        python3 back/scripts/apply_mysql_init.py

Requires `aiomysql` to be installed in the active Python:
    pip install aiomysql cryptography
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import aiomysql  # type: ignore[import-not-found]

BACK_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACK_DIR / ".env.prod"
SQL_FILE = BACK_DIR / "migrations" / "sql" / "mysql_init.sql"


def load_env_file(path: Path) -> dict[str, str]:
    """Parse a dotenv file. Lines starting with `#` or blank are skipped.

    Quotes around values are stripped. Inline comments are NOT handled —
    keep that complexity out of secrets handling.
    """
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        out[key] = value
    return out


def resolve_db_config() -> dict[str, object]:
    """Build aiomysql.connect kwargs from env vars + .env.prod fallback.

    Precedence: real env > .env.prod (matches config.bootstrap_env's
    override=False loading).
    """
    file_vars = load_env_file(ENV_FILE)

    def get(name: str, default: str = "") -> str:
        return os.environ.get(name, file_vars.get(name, default))

    db_url = get("DB_URL", "")
    if db_url:
        # mysql+pymysql://user:pwd@host:3306/db?charset=utf8mb4
        parsed = urlparse(db_url.replace("mysql+pymysql://", "mysql://"))
        return {
            "host": parsed.hostname or "",
            "port": parsed.port or 3306,
            "user": unquote(parsed.username or ""),
            "password": unquote(parsed.password or ""),
            "db": (parsed.path or "/").lstrip("/"),
            "charset": "utf8mb4",
            "autocommit": False,
        }

    return {
        "host": get("DB_HOST"),
        "port": int(get("DB_PORT", "3306")),
        "user": get("DB_USER"),
        "password": get("DB_PASSWORD"),
        "db": get("DB_NAME"),
        "charset": "utf8mb4",
        "autocommit": False,
    }


def split_statements(sql_text: str) -> list[str]:
    """Naive splitter: drop -- comments, split on ';' at top level.

    Adequate for our init script (no stored procs, no string literals
    containing ';' that matter for parsing). For anything fancier, swap
    in sqlparse.
    """
    no_line_comments = re.sub(r"--[^\n]*", "", sql_text)
    pieces = [p.strip() for p in no_line_comments.split(";")]
    return [p for p in pieces if p]


async def run() -> int:
    cfg = resolve_db_config()
    missing = [k for k in ("host", "user", "db") if not cfg.get(k)]
    if missing:
        sys.stderr.write(
            "DB connection info incomplete. Missing: "
            + ", ".join(missing)
            + "\nProvide DB_HOST / DB_USER / DB_PASSWORD / DB_NAME via env "
            "vars or uncomment them in back/.env.prod.\n"
        )
        return 2

    if not SQL_FILE.is_file():
        sys.stderr.write(f"SQL file not found: {SQL_FILE}\n")
        return 2

    sql_text = SQL_FILE.read_text(encoding="utf-8")
    statements = split_statements(sql_text)

    print(
        f"Connecting to {cfg['user']}@{cfg['host']}:{cfg['port']}/{cfg['db']} ..."
    )
    conn = await aiomysql.connect(**cfg)
    try:
        async with conn.cursor() as cur:
            for i, stmt in enumerate(statements, 1):
                head = stmt.splitlines()[0][:80]
                print(f"  [{i}/{len(statements)}] {head} ...")
                await cur.execute(stmt)
        await conn.commit()
    finally:
        conn.close()

    print("Done.")
    return 0


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
