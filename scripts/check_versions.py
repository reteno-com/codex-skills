#!/usr/bin/env python3
"""Validate that all in-repo skills share the canonical repo version."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "VERSION"
SKILLS_DIR = ROOT / "skills"
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
VERSION_RE = re.compile(r"^version:\s*(.+?)\s*$", re.MULTILINE)


def read_repo_version() -> str:
    version = VERSION_FILE.read_text(encoding="utf-8").strip()
    if not version:
        raise ValueError(f"{VERSION_FILE} is empty")
    return version


def read_skill_version(skill_file: Path) -> str | None:
    content = skill_file.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(content)
    if not match:
        return None

    version_match = VERSION_RE.search(match.group(1))
    if not version_match:
        return None

    return version_match.group(1).strip().strip("\"'")


def main() -> int:
    repo_version = read_repo_version()
    failures: list[str] = []

    for skill_file in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        skill_version = read_skill_version(skill_file)
        if skill_version is None:
            failures.append(f"{skill_file.relative_to(ROOT)}: missing frontmatter version")
            continue
        if skill_version != repo_version:
            failures.append(
                f"{skill_file.relative_to(ROOT)}: version {skill_version} does not match {repo_version}"
            )

    if failures:
        print("Version check failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(f"Version check passed: repo and skills are all {repo_version}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover
        print(f"Version check error: {exc}", file=sys.stderr)
        raise SystemExit(1)
