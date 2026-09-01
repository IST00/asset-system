#!/usr/bin/env python3
"""Reject pilot and production env files that share DB user or database."""

from __future__ import annotations

import sys
from pathlib import Path


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            "usage: check_environment_isolation.py PILOT_ENV PRODUCTION_ENV",
            file=sys.stderr,
        )
        return 2

    try:
        pilot = _read_env(Path(argv[1]))
        production = _read_env(Path(argv[2]))
    except OSError:
        print("unable to read one or both environment files", file=sys.stderr)
        return 2

    missing = [
        key
        for key in ("DB_USER", "DB_NAME")
        if not pilot.get(key) or not production.get(key)
    ]
    if missing:
        print(
            "missing required database identity keys: " + ", ".join(missing),
            file=sys.stderr,
        )
        return 2

    shared = [
        key
        for key in ("DB_USER", "DB_NAME")
        if pilot[key] == production[key]
    ]
    if shared:
        print(
            "pilot and production must not share: " + ", ".join(shared),
            file=sys.stderr,
        )
        return 1

    print("pilot and production database identities are distinct")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
