#!/usr/bin/env python3
"""Read-only verification of the locked local pilot toolchain."""

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def evaluate_versions(
    python_version: str,
    pip_version: str,
    node_version: str,
    npm_version: str,
) -> dict[str, bool]:
    """Return whether each supplied runtime matches the repository contract."""
    return {
        "python": python_version == "3.13" or python_version.startswith("3.13."),
        "pip": pip_version == "25.2",
        "node": node_version == "22.23.1",
        "npm": npm_version == "10.9.8",
    }


def _command_output(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return "unavailable"
    if completed.returncode != 0:
        return "unavailable"
    return completed.stdout.strip()


def _pip_version() -> str:
    output = _command_output([sys.executable, "-m", "pip", "--version"])
    parts = output.split()
    return parts[1] if len(parts) >= 2 and parts[0] == "pip" else "unavailable"


def main() -> int:
    python_version = platform.python_version()
    pip_version = _pip_version()
    node_version = _command_output(["node", "--version"]).removeprefix("v")
    npm_version = _command_output(["npm", "--version"])
    versions = evaluate_versions(
        python_version,
        pip_version,
        node_version,
        npm_version,
    )
    displayed = {
        "python": python_version,
        "pip": pip_version,
        "node": node_version,
        "npm": npm_version,
    }
    for name in ("python", "pip", "node", "npm"):
        status = "ok" if versions[name] else "mismatch"
        print(f"{name}={displayed[name]} status={status}")

    lockfiles = (
        REPOSITORY_ROOT / "package-lock.json",
        REPOSITORY_ROOT / "front/package-lock.json",
        REPOSITORY_ROOT / "back/requirements.lock",
    )
    found = sum(path.is_file() for path in lockfiles)
    lock_status = "ok" if found == len(lockfiles) else "mismatch"
    print(f"lockfiles={found}/{len(lockfiles)} status={lock_status}")
    return 0 if all(versions.values()) and found == len(lockfiles) else 1


if __name__ == "__main__":
    raise SystemExit(main())
