from __future__ import annotations

import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from simlab.services.openusd.import_report import ImportReport


def openusd_asset_id(path: Path) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", path.stem.lower()).strip("_") or "asset"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:10]
    return f"openusd_{cleaned}_{digest}"


def upsert_asset_metadata(path: Path, asset: dict[str, Any]) -> None:
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"assets": []}
    assets = data.setdefault("assets", [])
    assets[:] = [item for item in assets if item.get("id") != asset["id"]]
    assets.append(asset)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


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
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dependency, destination)
        copied[str(dependency.resolve())] = destination
    return copied
