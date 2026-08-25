#!/usr/bin/env python3
"""Build and verify a deterministic top-level Anki .ankiaddon archive."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.release import VELLUM_VERSION  # noqa: E402


OUTPUT = ROOT / "dist" / f"vellum-{VELLUM_VERSION}.ankiaddon"
ROOT_FILES = {
    "__init__.py",
    "bootstrap.py",
    "config.json",
    "config.md",
    "manifest.json",
    "README.md",
}
PACKAGE_DIRS = {
    "anki",
    "builder",
    "continuity",
    "core",
    "features",
    "notes",
    "recovery",
    "sessions",
    "timing",
    "topics",
    "ui",
}


def included_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if path.name in {".DS_Store"} or "__pycache__" in relative.parts:
            continue
        if len(relative.parts) == 1 and relative.name in ROOT_FILES:
            files.append(path)
        elif relative.parts[0] in PACKAGE_DIRS:
            files.append(path)
        elif relative == Path("user_files/README.txt"):
            files.append(path)
    return sorted(files, key=lambda path: path.relative_to(ROOT).as_posix())


def build() -> Path:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    files = included_files()
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(relative, date_time=(2026, 8, 22, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)
    verify(OUTPUT)
    return OUTPUT


def verify(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if "__init__.py" not in names or "manifest.json" not in names:
            raise RuntimeError("Archive is missing Anki entry metadata")
        required_runtime = {
            "builder/__init__.py",
            "builder/catalog.py",
            "builder/models.py",
            "builder/query.py",
            "builder/repository.py",
            "builder/scope.py",
            "anki/study_builder.py",
            "features/study_builder.py",
            "ui/study_builder.py",
        }
        missing_runtime = sorted(required_runtime.difference(names))
        if missing_runtime:
            raise RuntimeError(
                "Archive is missing Study Builder runtime files: "
                + ", ".join(missing_runtime)
            )
        if any(name.startswith("vellum/") for name in names):
            raise RuntimeError("Top-level add-on folder must not be included")
        if any("__pycache__" in name or name.endswith((".sqlite3", ".log")) for name in names):
            raise RuntimeError("Archive contains generated or private runtime data")
        forbidden_parts = {"tests", "scripts", "qa", ".git", ".github"}
        if any(forbidden_parts.intersection(Path(name).parts) for name in names):
            raise RuntimeError("Archive contains development-only files")
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("package") != "vellum" or manifest.get("name") != "Vellum":
            raise RuntimeError("Invalid manifest identity")
        if manifest.get("human_version") != VELLUM_VERSION:
            raise RuntimeError("Manifest and package version differ")


if __name__ == "__main__":
    print(build())
