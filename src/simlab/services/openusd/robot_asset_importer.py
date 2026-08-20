from __future__ import annotations

import hashlib
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
    atomic_copy,
    atomic_write_bytes,
    atomic_write_text,
    copy_openusd_dependencies,
    openusd_asset_id,
    upsert_asset_metadata,
)
from simlab.services.openusd.geometry_bundle import build_geometry_bundle
from simlab.services.openusd.import_report import ImportReport
from simlab.services.openusd.mesh_extractor import extract_prim_mesh, mesh_to_obj
from simlab.services.openusd.stage_loader import load_openusd_stage


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


def _cache_geometry_meshes(
    model: RoboticsModel,
    source_path: Path,
    cache_dir: Path,
    root: Path,
    report: ImportReport,
) -> tuple[str | None, list[str]]:
    stage = load_openusd_stage(source_path).stage
    from pxr import UsdGeom

    up_axis = str(UsdGeom.GetStageUpAxis(stage)).upper()
    meters_per_unit = float(UsdGeom.GetStageMetersPerUnit(stage) or 1.0)
    visual_meshes = []
    collision_meshes: list[str] = []
    for articulation in model.articulations:
        for link in articulation.links:
            for visual in link.visual_geometries:
                if visual.geometry_type != "mesh" or not visual.source_prim_path:
                    continue
                prim = stage.GetPrimAtPath(visual.source_prim_path)
                if not prim.IsValid():
                    report.add(
                        "warning",
                        "usd.visual_prim_unavailable",
                        "Mesh visual could not be cached because its source prim is unavailable.",
                        prim_path=visual.source_prim_path,
                        field="source_prim_path",
                        fallback="viewport box proxy",
                    )
                    continue
                mesh = extract_prim_mesh(
                    prim,
                    up_axis=up_axis,
                    meters_per_unit=meters_per_unit,
                    local_scale=visual.size,
                )
                if not mesh.positions or not mesh.indices:
                    report.add(
                        "warning",
                        "usd.visual_mesh_empty",
                        "Mesh visual contained no renderable triangles.",
                        prim_path=visual.source_prim_path,
                        field="points",
                        fallback="viewport box proxy",
                    )
                    continue
                visual_meshes.append((visual.id, mesh))
            for collider in link.colliders:
                if collider.geometry_type != "mesh" or not collider.source_prim_path:
                    continue
                prim = stage.GetPrimAtPath(collider.source_prim_path)
                if not prim.IsValid():
                    report.add(
                        "error",
                        "usd.collider_prim_unavailable",
                        "Mesh collider could not be cached because its source prim is unavailable.",
                        prim_path=collider.source_prim_path,
                        field="source_prim_path",
                    )
                    continue
                mesh = extract_prim_mesh(
                    prim,
                    up_axis=up_axis,
                    meters_per_unit=meters_per_unit,
                    local_scale=collider.size,
                )
                if not mesh.positions or not mesh.indices:
                    report.add(
                        "error",
                        "usd.collider_mesh_empty",
                        "Mesh collider contained no triangles for physics export.",
                        prim_path=collider.source_prim_path,
                        field="points",
                    )
                    continue
                collision_path = cache_dir / "colliders" / collider.id / "collision.obj"
                collision_path.parent.mkdir(parents=True, exist_ok=True)
                atomic_write_text(
                    collision_path, mesh_to_obj(mesh.positions, mesh.indices)
                )
                relative = collision_path.relative_to(root).as_posix()
                collider.collision_mesh = relative
                collision_meshes.append(relative)
    relative_bundle: str | None = None
    if visual_meshes:
        bundle = build_geometry_bundle(visual_meshes)
        digest = hashlib.sha256(bundle.content).hexdigest()[:16]
        bundle_path = cache_dir / f"visual-{digest}.simbin"
        atomic_write_bytes(bundle_path, bundle.content)
        relative_bundle = bundle_path.relative_to(root).as_posix()
        for articulation in model.articulations:
            articulation.visual_bundle = relative_bundle
        legacy_visuals = cache_dir / "visuals"
        if legacy_visuals.is_dir():
            shutil.rmtree(legacy_visuals)
        for old_bundle in cache_dir.glob("visual-*.simbin"):
            if old_bundle != bundle_path:
                old_bundle.unlink()
    return relative_bundle, collision_meshes


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
        atomic_copy(source_path, copied_source)
    copied_dependencies = copy_openusd_dependencies(source_path, source_dir, report)
    if report.has_errors:
        if not cache_existed:
            shutil.rmtree(cache_dir, ignore_errors=True)
        raise OpenUsdArticulationError(report)

    relative_source = copied_source.relative_to(root).as_posix()
    _rewrite_source_uris(imported.model, relative_source)
    report.source_path = relative_source
    visual_bundle, collision_meshes = _cache_geometry_meshes(
        imported.model,
        copied_source,
        cache_dir,
        root,
        report,
    )
    if report.has_errors:
        if not cache_existed:
            shutil.rmtree(cache_dir, ignore_errors=True)
        raise OpenUsdArticulationError(report)
    robotics_path = cache_dir / "robotics.json"
    report_path = cache_dir / "import-report.json"
    manifest_path = cache_dir / "manifest.json"
    atomic_write_text(
        robotics_path,
        json.dumps(imported.model.to_dict(), indent=2, allow_nan=False) + "\n",
    )
    atomic_write_text(report_path, json.dumps(report.to_dict(), indent=2) + "\n")

    relative_robotics = robotics_path.relative_to(root).as_posix()
    relative_report = report_path.relative_to(root).as_posix()
    relative_manifest = manifest_path.relative_to(root).as_posix()
    manifest = {
        "version": 4,
        "format": "openusd",
        "kind": "robot",
        "kinematics_contract_version": 2,
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "source": relative_source,
        "robotics_model": relative_robotics,
        "import_report": relative_report,
        "dependencies": [
            path.relative_to(root).as_posix() for path in copied_dependencies.values()
        ],
        "visual_bundle": visual_bundle,
        "visual_bundle_format": 1 if visual_bundle else None,
        "collision_meshes": collision_meshes,
        "articulation_ids": [item.id for item in imported.model.articulations],
    }
    atomic_write_text(manifest_path, json.dumps(manifest, indent=2) + "\n")

    asset = {
        "id": asset_id,
        "name": source_path.stem,
        "type": "robot",
        "category": "robot",
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
