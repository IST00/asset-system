"""Repository contracts for locked pilot runtimes and dependencies."""

from __future__ import annotations

import json
import importlib.util
import tomllib
from pathlib import Path
from types import ModuleType

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _json(path: str) -> dict[str, object]:
    return json.loads((REPOSITORY_ROOT / path).read_text(encoding="utf-8"))


def _load_toolchain_checker() -> ModuleType:
    path = REPOSITORY_ROOT / "scripts/check_toolchain.py"
    spec = importlib.util.spec_from_file_location("check_toolchain", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_python_and_node_versions_are_declared() -> None:
    assert (REPOSITORY_ROOT / ".python-version").read_text().strip() == "3.13"
    assert (REPOSITORY_ROOT / "back/.pip-version").read_text().strip() == "25.2"
    assert (REPOSITORY_ROOT / ".nvmrc").read_text().strip() == "22.23.1"
    assert (REPOSITORY_ROOT / ".node-version").read_text().strip() == "22.23.1"


def test_python_project_requires_only_python_313() -> None:
    with (REPOSITORY_ROOT / "back/pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    assert project["requires-python"] == "==3.13.*"


def test_npm_runtime_is_exactly_declared() -> None:
    for filename in ("package.json", "front/package.json"):
        package = _json(filename)
        assert package["engines"] == {"node": "22.23.x", "npm": "10.9.8"}
        assert package["packageManager"] == "npm@10.9.8"


def test_dependency_lockfiles_exist() -> None:
    for filename in (
        "package-lock.json",
        "front/package-lock.json",
        "back/requirements.lock",
    ):
        assert (REPOSITORY_ROOT / filename).is_file()


def test_npm_lockfiles_match_their_package_manifests() -> None:
    for package_name, lock_name in (
        ("front/package.json", "front/package-lock.json"),
        ("package.json", "package-lock.json"),
    ):
        package = _json(package_name)
        lock = _json(lock_name)
        locked_package = lock["packages"][""]
        for section in ("dependencies", "devDependencies", "engines"):
            assert locked_package.get(section, {}) == package.get(section, {})
        assert locked_package["packageManager"] == package["packageManager"]


def test_python_lock_uses_hashes() -> None:
    lock = (REPOSITORY_ROOT / "back/requirements.lock").read_text().lower()
    assert "--hash=sha256:" in lock
    assert "flask==3.0.3" in lock


def test_direct_npm_dependencies_are_exact() -> None:
    for filename in ("package.json", "front/package.json"):
        package = _json(filename)
        dependencies = {
            **package.get("dependencies", {}),
            **package.get("devDependencies", {}),
        }
        assert dependencies
        assert all(
            not str(value).startswith(("^", "~", ">", "<"))
            for value in dependencies.values()
        )


def test_dockerfiles_use_required_runtime_series() -> None:
    backend = (REPOSITORY_ROOT / "back/Dockerfile").read_text()
    frontend = (REPOSITORY_ROOT / "front/Dockerfile").read_text()
    assert "FROM python:3.13-slim-bookworm" in backend
    assert "requirements.lock" in backend
    assert "--require-hashes" in backend
    assert "FROM node:22.23.1-alpine" in frontend
    assert "npm ci --ignore-scripts" in frontend


def test_compose_runs_containers_in_utc() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text()
    assert compose.count("TZ: UTC") == 2


def test_compose_uses_health_aware_startup_and_restart_policies() -> None:
    compose = (REPOSITORY_ROOT / "docker-compose.yml").read_text()
    assert compose.count("healthcheck:") == 2
    assert compose.count("restart: unless-stopped") == 2
    assert "condition: service_healthy" in compose
    assert "/health/readiness" in compose


def test_toolchain_checker_accepts_only_the_locked_versions() -> None:
    checker = _load_toolchain_checker()
    assert checker.evaluate_versions("3.13.11", "25.2", "22.23.1", "10.9.8") == {
        "python": True,
        "pip": True,
        "node": True,
        "npm": True,
    }
    assert checker.evaluate_versions("3.12.11", "24.3", "22.23.0", "10.9.7") == {
        "python": False,
        "pip": False,
        "node": False,
        "npm": False,
    }


def test_clean_install_script_uses_isolated_caches_and_no_deployment_env() -> None:
    script = (REPOSITORY_ROOT / "scripts/verify-clean-install.sh").read_text()
    assert "uv venv --python 3.13" in script
    assert "uv pip sync" in script
    assert "--no-cache" in script
    assert script.count("npm ci --ignore-scripts") == 2
    assert ".env.pilot" not in script
    assert ".env.deploy" not in script


def test_quality_gate_runs_every_required_check_in_order() -> None:
    script = (REPOSITORY_ROOT / "scripts/run-quality-gate.sh").read_text()
    commands = (
        ".venv/bin/ruff check .",
        ".venv/bin/ruff format --check .",
        ".venv/bin/mypy app/ config.py",
        ".venv/bin/python -m pytest",
        "npm run type-check",
        "npm run lint",
        "npm test",
        "npm run build:prod",
    )
    positions = [script.index(command) for command in commands]
    assert positions == sorted(positions)
    package = _json("package.json")
    assert package["scripts"]["quality:gate"] == "scripts/run-quality-gate.sh"
