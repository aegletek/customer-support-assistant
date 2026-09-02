"""Initialize a repository created from the Orbit use-case template."""

from __future__ import annotations

import argparse
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
MARKER = ROOT / ".template-uninitialized"
TEXT_SUFFIXES = {".md", ".py", ".toml", ".yaml", ".yml", ".example"}
IGNORED_PARTS = {".git", ".pytest_cache", ".venv", "__pycache__", "build", "dist"}


def kebab_name(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not result or not re.fullmatch(r"[a-z][a-z0-9-]*", result):
        raise ValueError("project name must begin with a letter and contain letters, numbers, or hyphens")
    return result


def package_name(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")
    if not result or not re.fullmatch(r"[a-z][a-z0-9_]*", result):
        raise ValueError("package name must be a valid lowercase Python package name")
    return result


def editable_files() -> list[Path]:
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path == Path(__file__).resolve():
            continue
        if any(part in IGNORED_PARTS for part in path.relative_to(ROOT).parts):
            continue
        if path.name == ".env" or path.name == MARKER.name:
            continue
        if path.suffix in TEXT_SUFFIXES or path.name in {".gitignore"}:
            files.append(path)
    return files


def initialize(project: str, package: str, display: str, description: str) -> None:
    if not MARKER.exists():
        raise RuntimeError("this repository has already been initialized")

    replacements = {
        "orbit-usecase": project,
        "orbit_usecase": package,
        "Orbit Use Case": display,
        "Independent business use case powered by Orbit Core": description,
        "usecase_workflow": f"{package}_workflow",
    }
    for path in editable_files():
        content = path.read_text(encoding="utf-8")
        updated = content
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        if updated != content:
            path.write_text(updated, encoding="utf-8")

    source_package = ROOT / "orbit_usecase"
    target_package = ROOT / package
    if target_package.exists():
        raise RuntimeError(f"target package already exists: {target_package}")
    source_package.rename(target_package)
    MARKER.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name", required=True, help="Distribution name, for example customer-risk-assistant")
    parser.add_argument("--package-name", help="Python package name; defaults from project name")
    parser.add_argument("--display-name", help="Human-readable application name")
    parser.add_argument("--description", help="Package description")
    args = parser.parse_args()

    project = kebab_name(args.project_name)
    package = package_name(args.package_name or project)
    display = args.display_name or project.replace("-", " ").title()
    description = args.description or f"{display} powered by Orbit Core"
    initialize(project, package, display, description)
    print(f"Initialized {display} ({project}, package {package}).")


if __name__ == "__main__":
    main()
