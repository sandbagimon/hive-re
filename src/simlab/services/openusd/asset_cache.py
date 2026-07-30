from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from simlab.services.openusd.import_report import ImportReport


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
        temporary.chmod(mode)
        temporary.replace(path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def atomic_write_text(path: Path, content: str) -> None:
    atomic_write_bytes(path, content.encode("utf-8"))


def atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def openusd_asset_id(path: Path) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_") or "asset"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:10]
    return f"openusd_{cleaned}_{digest}"


def upsert_asset_metadata(path: Path, asset: dict[str, Any]) -> None:
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"assets": []}
    assets = data.setdefault("assets", [])
    assets[:] = [item for item in assets if item.get("id") != asset["id"]]
    assets.append(asset)
    atomic_write_text(path, json.dumps(data, indent=2) + "\n")


def copy_openusd_dependencies(
    source_path: Path,
    cache_source_dir: Path,
    report: ImportReport,
) -> dict[str, Path]:
    copied: dict[str, Path] = {}
    dependencies: list[Path] = []
    for dependency_value in report.resolved_dependencies:
        dependency = Path(dependency_value)
        if not dependency.is_absolute():
            dependency = (source_path.parent / dependency).resolve()
        if dependency == source_path or not dependency.is_file():
            continue
        try:
            relative = dependency.relative_to(source_path.parent)
        except ValueError:
            report.add(
                "error",
                "usd.dependency_outside_source_root",
                f"Dependency is outside the imported asset directory: {dependency}",
                field="asset_path",
                fallback="Move the dependency under the USD asset directory and import again.",
            )
            continue
        dependencies.append(dependency)
    if report.has_errors:
        return copied
    for dependency in dependencies:
        relative = dependency.relative_to(source_path.parent)
        destination = cache_source_dir / relative
        atomic_copy(dependency, destination)
        copied[str(dependency.resolve())] = destination
    return copied
