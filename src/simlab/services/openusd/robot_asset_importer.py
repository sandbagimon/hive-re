from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from simlab.models.robotics import RoboticsModel
from simlab.services.openusd.articulation_importer import (
    OpenUsdArticulationError,
    import_openusd_articulations,
)
from simlab.services.openusd.asset_cache import (
    copy_openusd_dependencies,
    openusd_asset_id,
    upsert_asset_metadata,
)
from simlab.services.openusd.import_report import ImportReport


@dataclass(slots=True)
class RobotAssetImportResult:
    asset: dict[str, Any]
    model: RoboticsModel
    report: ImportReport
    cache_directory: Path


def _rewrite_source_uris(model: RoboticsModel, source_uri: str) -> None:
    for articulation in model.articulations:
        articulation.source_uri = source_uri
        for link in articulation.links:
            for geometry in link.visual_geometries:
                if geometry.asset_uri is not None:
                    geometry.asset_uri = source_uri
            for collider in link.colliders:
                if collider.asset_uri is not None:
                    collider.asset_uri = source_uri


def import_openusd_robot_asset(
    source: str | Path,
    project_root: str | Path,
) -> RobotAssetImportResult:
    """Import an external USD articulation into a relocatable project cache."""
    source_path = Path(source).expanduser().resolve()
    root = Path(project_root).resolve()
    imported = import_openusd_articulations(source_path)
    report = imported.report
    asset_id = openusd_asset_id(source_path)
    cache_dir = root / "assets" / "imported" / asset_id
    cache_existed = cache_dir.exists()
    source_dir = cache_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    copied_source = source_dir / source_path.name
    if source_path != copied_source:
        shutil.copy2(source_path, copied_source)
    copied_dependencies = copy_openusd_dependencies(source_path, source_dir, report)
    if report.has_errors:
        if not cache_existed:
            shutil.rmtree(cache_dir, ignore_errors=True)
        raise OpenUsdArticulationError(report)

    relative_source = copied_source.relative_to(root).as_posix()
    _rewrite_source_uris(imported.model, relative_source)
    report.source_path = relative_source
    robotics_path = cache_dir / "robotics.json"
    report_path = cache_dir / "import-report.json"
    manifest_path = cache_dir / "manifest.json"
    robotics_path.write_text(
        json.dumps(imported.model.to_dict(), indent=2) + "\n", encoding="utf-8"
    )
    report_path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")

    relative_robotics = robotics_path.relative_to(root).as_posix()
    relative_report = report_path.relative_to(root).as_posix()
    relative_manifest = manifest_path.relative_to(root).as_posix()
    manifest = {
        "version": 2,
        "format": "openusd",
        "kind": "robot",
        "source": relative_source,
        "robotics_model": relative_robotics,
        "import_report": relative_report,
        "dependencies": [
            path.relative_to(root).as_posix() for path in copied_dependencies.values()
        ],
        "articulation_ids": [item.id for item in imported.model.articulations],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    asset = {
        "id": asset_id,
        "name": source_path.stem,
        "type": "robot",
        "source_format": "openusd",
        "default_properties": {
            "source": relative_source,
            "robotics_cache": relative_robotics,
            "import_report": relative_report,
            "manifest": relative_manifest,
            "articulation_ids": manifest["articulation_ids"],
        },
    }
    upsert_asset_metadata(root / "assets" / "metadata.json", asset)
    return RobotAssetImportResult(
        asset=asset,
        model=imported.model,
        report=report,
        cache_directory=cache_dir,
    )
