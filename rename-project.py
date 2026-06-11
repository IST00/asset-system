#!/usr/bin/env python3
"""Fork 后一次性替换脚手架项目名占位。

Windows 用法：
  py rename-project.py <new-name>
  py rename-project.py <new-name> --apply --backup --pom
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


PROJECT_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
PLACEHOLDER_RE = re.compile(r"\bScaffold\b|\bscaffold\b")
LOWER_RE = re.compile(r"\bscaffold\b")
TITLE_RE = re.compile(r"\bScaffold\b")
FRONT_NAME_RE = re.compile(r'^(\s*"name"\s*:\s*")[^"]*(",?\s*)$', re.MULTILINE)

EXCLUDE_DIRS = {
    "node_modules",
    "target",
    "dist",
    "build",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "__pycache__",
    ".git",
    ".idea",
    ".vscode",
    ".gradle",
    ".next",
    ".turbo",
    ".venv",
    "venv",
    "logs",
}

BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".webp",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".jar",
    ".class",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".mp4",
    ".mov",
}

POM_CANDIDATES = (
    Path("back/pom.xml"),
    Path("scaffolding-java/back/pom.xml"),
)
PY_CANDIDATES = (
    Path("back/pyproject.toml"),
    Path("back/requirements.txt"),
    Path("scaffolding-python/back/pyproject.toml"),
    Path("scaffolding-python/back/requirements.txt"),
)
FRONT_PKG_CANDIDATES = (
    Path("front/package.json"),
    Path("scaffolding-java/front/package.json"),
    Path("scaffolding-python/front/package.json"),
)


@dataclass(frozen=True)
class Detection:
    project_type: str
    pom: Path | None
    front_packages: tuple[Path, ...]


def derive_title(name: str) -> str:
    return "".join(token[:1].upper() + token[1:] for token in name.split("-") if token)


def detect_project(repo_root: Path) -> Detection:
    detected_pom = next((path for path in POM_CANDIDATES if (repo_root / path).is_file()), None)
    if detected_pom:
        project_type = "java"
    elif any((repo_root / path).is_file() for path in PY_CANDIDATES):
        project_type = "python"
    else:
        project_type = "unknown"

    front_packages = tuple(path for path in FRONT_PKG_CANDIDATES if (repo_root / path).is_file())
    return Detection(project_type, detected_pom, front_packages)


def is_under_excluded_dir(relative_path: Path) -> bool:
    return any(part in EXCLUDE_DIRS for part in relative_path.parts[:-1])


def is_binary_candidate(path: Path) -> bool:
    return path.suffix.lower() in BINARY_SUFFIXES


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None
    except OSError:
        return None


def discover_candidates(repo_root: Path, script_names: set[str]) -> list[Path]:
    candidates: list[Path] = []
    for path in repo_root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root)
        if path.name in script_names or is_under_excluded_dir(rel) or is_binary_candidate(path):
            continue
        text = read_text(path)
        if text is not None and PLACEHOLDER_RE.search(text):
            candidates.append(rel)
    return sorted(candidates, key=lambda item: item.as_posix())


def backup_file(path: Path) -> None:
    shutil.copy2(path, Path(str(path) + ".bak"))


def write_text(path: Path, text: str, backup: bool) -> None:
    if backup:
        backup_file(path)
    path.write_text(text, encoding="utf-8")


def rewrite_placeholders(text: str, new_name: str, new_title: str) -> str:
    return LOWER_RE.sub(new_name, TITLE_RE.sub(new_title, text))


def rewrite_pom(text: str, new_name: str) -> str:
    text = text.replace("<artifactId>quick</artifactId>", f"<artifactId>{new_name}</artifactId>")
    return text.replace("<name>quick</name>", f"<name>{new_name}</name>")


def rewrite_front_package(text: str, new_name: str) -> str:
    front_name = f"{new_name}-front"
    return FRONT_NAME_RE.sub(rf'\1{front_name}\2', text, count=1)


def count_hits(path: Path) -> tuple[int, int]:
    text = read_text(path)
    if text is None:
        return 0, 0
    return len(LOWER_RE.findall(text)), len(TITLE_RE.findall(text))


def preview_pom(path: Path) -> list[tuple[int, str]]:
    text = read_text(path)
    if text is None:
        return []
    rows = []
    for lineno, line in enumerate(text.splitlines(keepends=True), start=1):
        if "<artifactId>quick</artifactId>" in line or "<name>quick</name>" in line:
            rows.append((lineno, line))
    return rows


def preview_front_name(path: Path) -> tuple[int, str] | None:
    text = read_text(path)
    if text is None:
        return None
    for lineno, line in enumerate(text.splitlines(keepends=True), start=1):
        if FRONT_NAME_RE.match(line):
            return lineno, line
    return None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rename-project.py",
        usage="%(prog)s <new-name> [--apply] [--backup] [--pom] [--title <TitleCase>]",
    )
    parser.add_argument("new_name", help="new project name in kebab/lower form")
    parser.add_argument("--apply", action="store_true", help="actually write changes")
    parser.add_argument("--backup", action="store_true", help="keep .bak files when writing")
    parser.add_argument("--pom", action="store_true", help="rewrite back/pom.xml artifactId/name for Java projects")
    parser.add_argument("--title", default="", help="override TitleCase form")
    return parser


def print_header(
    repo_root: Path,
    new_name: str,
    new_title: str,
    detection: Detection,
    apply: bool,
    backup: bool,
    do_pom: bool,
) -> None:
    pom_info = f" (pom: {detection.pom.as_posix()})" if detection.pom else ""
    print("========================================================================")
    print(f" scaffold  -> {new_name}")
    print(f" Scaffold  -> {new_title}")
    print(f" root:       {repo_root}")
    print(f" project:    {detection.project_type}{pom_info}")
    if detection.front_packages:
        found = " ".join(path.as_posix() for path in detection.front_packages)
        print(f" front pkg:  {len(detection.front_packages)} found -> {found}")
    else:
        print(" front pkg:  0 found")
    print(f" mode:       {'APPLY' if apply else 'DRY-RUN (no changes)'}")
    print(f" backup:     {'yes' if backup else 'no'}")
    pom_rename = f"yes ({detection.pom.as_posix()} artifactId+name)" if do_pom and detection.pom else "no"
    print(f" pom rename: {pom_rename}")
    print("========================================================================")
    print()


def print_dry_run(
    repo_root: Path,
    candidates: Sequence[Path],
    detection: Detection,
    new_name: str,
    do_pom: bool,
) -> int:
    print("--- dry-run diff preview (word-boundary hit count) ---")
    for rel in candidates:
        lower, title = count_hits(repo_root / rel)
        if lower or title:
            print(f"  {rel.as_posix():<70}  scaffold:{lower}  Scaffold:{title}")

    if do_pom and detection.pom:
        print()
        print(f"--- pom preview ({detection.pom.as_posix()}) ---")
        for lineno, line in preview_pom(repo_root / detection.pom):
            print(f"  L{lineno}: {line}", end="" if line.endswith("\n") else "\n")

    for front_pkg in detection.front_packages:
        print()
        print(f"--- front package.json preview ({front_pkg.as_posix()}) ---")
        row = preview_front_name(repo_root / front_pkg)
        if row:
            lineno, line = row
            print(f"  L{lineno}: {line}", end="" if line.endswith("\n") else "\n")
        print(f'  -> will become: "name": "{new_name}-front"')

    print()
    print("dry-run done. Re-run with --apply to write changes.")
    return 0


def apply_changes(
    repo_root: Path,
    candidates: Sequence[Path],
    detection: Detection,
    new_name: str,
    new_title: str,
    backup: bool,
    do_pom: bool,
) -> int:
    changed = 0
    for rel in candidates:
        path = repo_root / rel
        text = read_text(path)
        if text is None:
            continue
        write_text(path, rewrite_placeholders(text, new_name, new_title), backup)
        changed += 1
        print(f"  rewrote  {rel.as_posix()}")

    pom_changed = 0
    if do_pom and detection.pom:
        path = repo_root / detection.pom
        text = read_text(path)
        if text is not None:
            write_text(path, rewrite_pom(text, new_name), backup)
            print(f"  rewrote  {detection.pom.as_posix()} (pom artifactId + name)")
            pom_changed = 1
    elif do_pom:
        print("  warning: --pom requested but no back/pom.xml found, skipped.")

    front_changed = 0
    for rel in detection.front_packages:
        path = repo_root / rel
        text = read_text(path)
        if text is None:
            continue
        write_text(path, rewrite_front_package(text, new_name), backup)
        print(f'  rewrote  {rel.as_posix()} (front "name" -> "{new_name}-front")')
        front_changed += 1

    suffix = (" +pom" if pom_changed else "") + (f" +{front_changed} front pkg" if front_changed else "")
    print()
    print(f"done. {changed} files rewritten.{suffix}")
    if backup:
        print("backups kept as <file>.bak")
    print()
    print("next steps:")
    print("  1) git diff")
    print("  2) python rename-project.py <new-name>   # dry-run 确认没有 word-boundary 命中残留")
    print("  3) cd front && npm install && npm run build")
    print("     cd back  && mvn -DskipTests compile")
    print("  4) 可选：再手工处理域名 / Java 包名 / Maven 坐标")
    return 0


def main(argv: Sequence[str] | None = None, repo_root: Path | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    new_name = args.new_name

    if not PROJECT_NAME_RE.fullmatch(new_name):
        print("error: <new-name> must be kebab/lower (start with a-z, chars in [a-z0-9-])", file=sys.stderr)
        print(f"       got: {new_name}", file=sys.stderr)
        return 65

    if new_name == "scaffold":
        print("error: new-name is still 'scaffold'; pick a different name.", file=sys.stderr)
        return 66

    root = (repo_root or Path(__file__).resolve().parent).resolve()
    new_title = args.title or derive_title(new_name)
    detection = detect_project(root)
    do_pom = bool(args.pom)
    if do_pom and detection.project_type != "java":
        print(
            f"note: --pom requested but project type is '{detection.project_type}' (no back/pom.xml found).",
            file=sys.stderr,
        )
        print("      pom rewrite will be skipped.", file=sys.stderr)
        do_pom = False

    print_header(root, new_name, new_title, detection, args.apply, args.backup, do_pom)

    script_names = {Path(__file__).name, "rename-project.sh", "rename-project.py"}
    candidates = discover_candidates(root, script_names)
    if not candidates:
        print("no files contain 'scaffold' / 'Scaffold' - nothing to do.")
        return 0

    print(f"files to touch ({len(candidates)}):")
    for rel in candidates:
        print(f"  {rel.as_posix()}")
    print()

    if not args.apply:
        return print_dry_run(root, candidates, detection, new_name, do_pom)

    return apply_changes(root, candidates, detection, new_name, new_title, args.backup, do_pom)


if __name__ == "__main__":
    raise SystemExit(main())
