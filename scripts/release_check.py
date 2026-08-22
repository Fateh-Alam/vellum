#!/usr/bin/env python3
"""Fail closed on public-source privacy and release-package consistency."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.release import (  # noqa: E402
    VELLUM_HOMEPAGE,
    VELLUM_MIN_ANKI_VERSION,
    VELLUM_TESTED_ANKI_VERSION,
    VELLUM_VERSION,
)
from scripts.build_package import build  # noqa: E402


PRIVATE_ROOTS = {".git", "dist", "qa", "__pycache__"}
PRIVATE_DOCS = {
    "ANKI_CORE_INTEGRATION.md",
    "IMPLEMENTATION_STATUS.md",
    "LIVE_QUALIFICATION.md",
    "PERFORMANCE_EVIDENCE.md",
    "SPEC_TRACEABILITY.md",
}
FORBIDDEN_PUBLIC_TEXT = (
    "/" + "Users" + "/",
    "/var/" + "folders" + "/",
    "Fateh Alam" + " profile",
    "mnbhatty.fab" + "@gmail.com",
    "0.1.0-" + "dev",
)


def public_files() -> list[Path]:
    result: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if relative.parts[0] in PRIVATE_ROOTS or "__pycache__" in relative.parts:
            continue
        if relative.parts[0] == "docs" and path.name in PRIVATE_DOCS:
            continue
        result.append(path)
    return result


def check_public_source() -> None:
    offenders: list[str] = []
    for path in public_files():
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for token in FORBIDDEN_PUBLIC_TEXT:
            if token in source:
                offenders.append(f"{path.relative_to(ROOT)} contains {token!r}")
    if offenders:
        raise RuntimeError("Public privacy/version scan failed:\n" + "\n".join(offenders))


def check_versions() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("human_version") != VELLUM_VERSION:
        raise RuntimeError("manifest human_version does not match runtime version")
    if manifest.get("homepage") != VELLUM_HOMEPAGE:
        raise RuntimeError("manifest homepage does not match runtime release identity")
    if manifest.get("min_point_version") != VELLUM_MIN_ANKI_VERSION:
        raise RuntimeError("manifest minimum Anki version does not match release identity")
    if manifest.get("max_point_version") != VELLUM_TESTED_ANKI_VERSION:
        raise RuntimeError("manifest tested Anki version does not match release identity")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    version = re.search(r'^version = "([^"]+)"$', pyproject, flags=re.MULTILINE)
    if version is None or version.group(1) != VELLUM_VERSION:
        raise RuntimeError("pyproject version does not match runtime version")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_archive() -> tuple[Path, str, int]:
    artifact = build()
    first = digest(artifact)
    artifact = build()
    second = digest(artifact)
    if first != second:
        raise RuntimeError("Package build is not deterministic")
    with zipfile.ZipFile(artifact) as archive:
        names = archive.namelist()
        if any(name.startswith("docs/") for name in names):
            raise RuntimeError("Engineering documentation entered the runtime package")
        if any(name.startswith(("tests/", "scripts/", "qa/", ".github/")) for name in names):
            raise RuntimeError("Development-only files entered the runtime package")
        if any(
            name.endswith((".sqlite", ".sqlite3", ".db", ".log", ".pyc"))
            for name in names
        ):
            raise RuntimeError("Private/generated files entered the runtime package")
    (ROOT / "dist" / "SHA256SUMS").write_text(
        f"{second}  {artifact.name}\n", encoding="utf-8"
    )
    return artifact, second, len(names)


def main() -> None:
    check_versions()
    check_public_source()
    artifact, sha256, file_count = check_archive()
    print(
        json.dumps(
            {
                "artifact": str(artifact.relative_to(ROOT)),
                "files": file_count,
                "sha256": sha256,
                "version": VELLUM_VERSION,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
