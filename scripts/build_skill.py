#!/usr/bin/env python3
"""Build the Hermes Skill as a standalone release archive."""

from __future__ import annotations

import argparse
import tarfile
import tomllib
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skill" / "steam"


def project_version() -> str:
    with (ROOT / "pyproject.toml").open("rb") as file:
        project = tomllib.load(file)["project"]
    version = project.get("version")
    if not isinstance(version, str) or not version:
        raise RuntimeError("pyproject.toml does not define a project version")
    return version


def build_skill(output_dir: Path) -> Path:
    if not SKILL_DIR.is_dir():
        raise RuntimeError(f"Skill directory does not exist: {SKILL_DIR}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"steam-skill-{project_version()}.tar.gz"
    with tarfile.open(output, "w:gz") as archive:
        for path in sorted(SKILL_DIR.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts:
                continue
            relative = path.relative_to(SKILL_DIR)
            archive_name = PurePosixPath("steam", *relative.parts)
            archive.add(path, arcname=str(archive_name), recursive=False)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dist") / "skill",
        help="directory for the Skill archive (default: dist/skill)",
    )
    args = parser.parse_args()
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    print(build_skill(output_dir))


if __name__ == "__main__":
    main()
