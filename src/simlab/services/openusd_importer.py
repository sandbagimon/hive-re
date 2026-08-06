from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from simlab.models.robotics import RoboticsModel
from simlab.services.openusd import ImportReport, OpenUsdStageError, load_openusd_stage
from simlab.services.openusd.asset_cache import (
    atomic_copy,
    atomic_write_text,
    copy_openusd_dependencies,
    openusd_asset_id,
    upsert_asset_metadata,
)
from simlab.services.openusd.mesh_extractor import extract_stage_meshes, mesh_to_obj
from simlab.services.openusd.robot_asset_importer import import_openusd_robot_asset


class OpenUsdImportError(RuntimeError):
    """Raised when an OpenUSD asset cannot be converted into a SimLab asset."""

    def __init__(self, message: str, report: ImportReport | None = None) -> None:
        self.report = report
        super().__init__(message)


@dataclass(slots=True)
class OpenUsdImportResult:
    asset: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
    cache_directory: Path | None = None
    report: ImportReport | None = None
    robotics_model: RoboticsModel | None = None


def import_openusd_asset(source: str | Path, project_root: str | Path) -> OpenUsdImportResult:
    """Import a USD stage as one editable rigid-body asset with cached mesh geometry."""
    source_path = Path(source).expanduser().resolve()
    root = Path(project_root).resolve()
    try:
        stage_result = load_openusd_stage(source_path)
    except OpenUsdStageError as exc:
        raise OpenUsdImportError(str(exc), report=exc.report) from exc
    if stage_result.report.has_errors:
        issue = next(
            item for item in stage_result.report.issues if item.severity == "error"
        )
        raise OpenUsdImportError(issue.message, report=stage_result.report)
    if any(
        "PhysicsArticulationRootAPI" in prim.GetAppliedSchemas()
        for prim in stage_result.stage.Traverse()
    ):
        try:
            robot = import_openusd_robot_asset(source_path, root)
        except Exception as exc:
            report = getattr(exc, "report", stage_result.report)
            raise OpenUsdImportError(str(exc), report=report) from exc
        return OpenUsdImportResult(
            asset=robot.asset,
            warnings=[
                issue.message for issue in robot.report.issues if issue.severity == "warning"
            ],
            cache_directory=robot.cache_directory,
            report=robot.report,
            robotics_model=robot.model,
        )

    stage = stage_result.stage

    asset_id = openusd_asset_id(source_path)
    cache_dir = root / "assets" / "imported" / asset_id

    warnings = [
        issue.message for issue in stage_result.report.issues if issue.severity == "warning"
    ]
    extracted = extract_stage_meshes(stage, warnings)
    positions = extracted.visual.positions
    indices = extracted.visual.indices
    if not positions or not indices:
        stage_result.report.add(
            "error",
            "usd.no_supported_geometry",
            "The OpenUSD stage contains no supported renderable geometry.",
            field="stage",
        )
        raise OpenUsdImportError(
            "The OpenUSD stage contains no supported renderable geometry.",
            report=stage_result.report,
        )
    _validate_mesh_data(positions, indices)
    _validate_mesh_data(extracted.collision.positions, extracted.collision.indices)

    cache_existed = cache_dir.exists()
    cache_dir.mkdir(parents=True, exist_ok=True)
    source_dir = cache_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    copied_source = source_dir / source_path.name
    if source_path != copied_source:
        atomic_copy(source_path, copied_source)
    copied_dependencies = copy_openusd_dependencies(
        source_path,
        source_dir,
        stage_result.report,
    )
    if stage_result.report.has_errors:
        if not cache_existed:
            shutil.rmtree(cache_dir, ignore_errors=True)
        issue = next(
            item for item in stage_result.report.issues if item.severity == "error"
        )
        raise OpenUsdImportError(issue.message, report=stage_result.report)
    def preserve_texture(texture_value: str | None, label: str) -> str | None:
        if not texture_value:
            return None
        copied_texture = copied_dependencies.get(texture_value)
        if copied_texture is None:
            texture_source = Path(texture_value)
            if not texture_source.is_absolute():
                texture_source = (source_path.parent / texture_source).resolve()
            copied_texture = copied_dependencies.get(str(texture_source.resolve()))
        if copied_texture is not None:
            return copied_texture.relative_to(root).as_posix()
        warnings.append(
            f"The authored {label} texture could not be preserved; "
            "the viewport will use a scalar material fallback."
        )
        return None

    material = extracted.material
    relative_texture = preserve_texture(material.base_color_texture, "base-color")
    relative_normal_texture = preserve_texture(material.normal_texture, "normal")
    relative_roughness_texture = preserve_texture(
        material.roughness_texture, "roughness"
    )
    relative_metallic_texture = preserve_texture(
        material.metallic_texture, "metallic"
    )

    visual_path = cache_dir / "visual.json"
    collision_path = cache_dir / "collision.obj"
    manifest_path = cache_dir / "manifest.json"
    atomic_write_text(
        visual_path,
        json.dumps(
            {
                "positions": positions,
                "indices": indices,
                "colors": extracted.visual.colors,
                "uvs": extracted.visual.uvs,
                "base_color_texture": relative_texture,
                "normal_texture": relative_normal_texture,
                "roughness_texture": relative_roughness_texture,
                "metallic_texture": relative_metallic_texture,
                "roughness": material.roughness,
                "metalness": material.metalness,
            },
            separators=(",", ":"),
        ),
    )
    atomic_write_text(
        collision_path,
        mesh_to_obj(extracted.collision.positions, extracted.collision.indices),
    )

    physics, physics_warnings = _extract_physics(stage)
    warnings.extend(physics_warnings)
    relative_source = copied_source.relative_to(root).as_posix()
    relative_visual = visual_path.relative_to(root).as_posix()
    relative_collision = collision_path.relative_to(root).as_posix()
    bounds = _bounds(positions)
    mesh_count = len(extracted.visual.source_prim_paths)
    manifest = {
        "version": 1,
        "format": "openusd",
        "source": relative_source,
        "source_name": source_path.name,
        "dependencies": [
            path.relative_to(root).as_posix() for path in copied_dependencies.values()
        ],
        "visual_cache": relative_visual,
        "collision_mesh": relative_collision,
        "mesh_count": mesh_count,
        "vertex_count": len(positions) // 3,
        "triangle_count": len(indices) // 3,
        "collision_vertex_count": extracted.collision.vertex_count,
        "collision_triangle_count": extracted.collision.triangle_count,
        "dedicated_collision": extracted.used_dedicated_collision,
        "point_instance_count": extracted.point_instance_count,
        "native_primitive_count": extracted.native_primitive_count,
        "source_prim_paths": extracted.visual.source_prim_paths,
        "collision_prim_paths": extracted.collision.source_prim_paths,
        "base_color_texture": relative_texture,
        "normal_texture": relative_normal_texture,
        "roughness_texture": relative_roughness_texture,
        "metallic_texture": relative_metallic_texture,
        "roughness": material.roughness,
        "metalness": material.metalness,
        "bounds": bounds,
        "warnings": warnings,
    }
    atomic_write_text(manifest_path, json.dumps(manifest, indent=2) + "\n")

    rgba = extracted.visual.colors[:4] or [0.55, 0.62, 0.7, 1.0]
    asset = {
        "id": asset_id,
        "name": source_path.stem,
        "type": "object",
        "source_format": "openusd",
        "default_properties": {
            "geometry": {
                "kind": "mesh",
                "source_format": "openusd",
                "source": relative_source,
                "visual_cache": relative_visual,
                "collision_mesh": relative_collision,
                "bounds": bounds,
            },
            "rgba": rgba,
            "physics": physics,
            "import_warnings": warnings,
        },
    }
    upsert_asset_metadata(root / "assets" / "metadata.json", asset)
    return OpenUsdImportResult(
        asset=asset,
        warnings=warnings,
        cache_directory=cache_dir,
        report=stage_result.report,
    )


def load_visual_geometry(cache_path: str, project_root: str | Path) -> dict[str, Any]:
    """Load a generated viewport mesh cache while preventing project-root escapes."""
    root = Path(project_root).resolve()
    path = (root / cache_path).resolve()
    try:
        path.relative_to(root / "assets" / "imported")
    except ValueError as exc:
        raise OpenUsdImportError("Visual cache must be inside assets/imported.") from exc
    if path.name != "visual.json" or not path.is_file():
        raise OpenUsdImportError(f"Visual cache is missing: {cache_path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    positions = payload.get("positions")
    indices = payload.get("indices")
    colors = payload.get("colors")
    uvs = payload.get("uvs")
    base_color_texture = payload.get("base_color_texture")
    normal_texture = payload.get("normal_texture")
    roughness_texture = payload.get("roughness_texture")
    metallic_texture = payload.get("metallic_texture")
    roughness = payload.get("roughness")
    metalness = payload.get("metalness")
    if not isinstance(positions, list) or not isinstance(indices, list):
        raise OpenUsdImportError(f"Visual cache is invalid: {cache_path}")
    _validate_mesh_data(positions, indices)
    if colors is not None:
        valid_colors = (
            isinstance(colors, list)
            and len(colors) == (len(positions) // 3) * 4
            and all(_finite_number(value) for value in colors)
        )
        if not valid_colors:
            raise OpenUsdImportError(f"Visual cache colors are invalid: {cache_path}")
    if uvs is not None:
        valid_uvs = (
            isinstance(uvs, list)
            and (not uvs or len(uvs) == (len(positions) // 3) * 2)
            and all(_finite_number(value) for value in uvs)
        )
        if not valid_uvs:
            raise OpenUsdImportError(f"Visual cache UVs are invalid: {cache_path}")
    for texture in (
        base_color_texture,
        normal_texture,
        roughness_texture,
        metallic_texture,
    ):
        if texture is not None and not isinstance(texture, str):
            raise OpenUsdImportError(f"Visual cache texture is invalid: {cache_path}")
    for scalar in (roughness, metalness):
        if scalar is not None and not _finite_number(scalar):
            raise OpenUsdImportError(f"Visual cache material is invalid: {cache_path}")
    return {
        "positions": positions,
        "indices": indices,
        "colors": colors,
        "uvs": uvs,
        "base_color_texture": base_color_texture,
        "normal_texture": normal_texture,
        "roughness_texture": roughness_texture,
        "metallic_texture": metallic_texture,
        "roughness": roughness,
        "metalness": metalness,
    }


def resolve_imported_asset_path(path_value: str, project_root: str | Path) -> Path:
    """Resolve a project-relative imported asset path without allowing directory traversal."""
    root = Path(project_root).resolve()
    path = (root / path_value).resolve()
    try:
        path.relative_to(root / "assets" / "imported")
    except ValueError as exc:
        raise OpenUsdImportError("Imported asset path must be inside assets/imported.") from exc
    return path


def _extract_physics(stage: Any) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    values: dict[str, Any] = {}
    rigid_body_prims = []
    for prim in stage.Traverse():
        attribute_values = {
            attribute.GetName(): attribute.Get() for attribute in prim.GetAttributes()
        }
        if (
            "physics:rigidBodyEnabled" in attribute_values
            or "PhysicsRigidBodyAPI" in prim.GetAppliedSchemas()
        ):
            rigid_body_prims.append(prim)
            enabled = attribute_values.get("physics:rigidBodyEnabled", True)
            kinematic = attribute_values.get("physics:kinematicEnabled", False)
            values["dynamic"] = bool(enabled) and not bool(kinematic)
        for key, target in (
            ("physics:mass", "mass"),
            ("physics:density", "density"),
            ("physics:dynamicFriction", "dynamic_friction"),
            ("physics:staticFriction", "static_friction"),
            ("physics:restitution", "restitution"),
        ):
            value = attribute_values.get(key)
            valid = (
                _positive_number(value)
                if target in {"mass", "density"}
                else _finite_number(value)
            )
            if valid:
                values.setdefault(target, float(cast(int | float, value)))

    dynamic = bool(values.get("dynamic", False))
    mass = float(values.get("mass", 1.0))
    density = float(values.get("density", 1000.0))
    sliding_friction = float(values.get("dynamic_friction", values.get("static_friction", 0.8)))
    physics = {
        "dynamic": dynamic,
        "material": "default",
        "mass_mode": "mass" if "mass" in values else "density",
        "mass": mass,
        "density": density,
        "friction": [max(sliding_friction, 0.0), 0.005, 0.0001],
    }
    if "restitution" in values:
        physics["restitution"] = _clamp(float(values["restitution"]), 0.0, 1.0)
        warnings.append(
            "USD restitution is retained as metadata; MuJoCo contact uses solref/solimp."
        )
    if not rigid_body_prims:
        warnings.append("No UsdPhysics rigid body was found; imported actor defaults to Static.")
    return physics, warnings


def _bounds(positions: list[float]) -> dict[str, list[float]]:
    axes = [positions[index::3] for index in range(3)]
    minimum = [min(axis) for axis in axes]
    maximum = [max(axis) for axis in axes]
    return {"min": minimum, "max": maximum}


def _validate_mesh_data(positions: list[Any], indices: list[Any]) -> None:
    if len(positions) % 3 or len(indices) % 3:
        raise OpenUsdImportError("Mesh positions and triangle indices must be groups of three.")
    if not all(_finite_number(value) for value in positions):
        raise OpenUsdImportError("Mesh positions must contain only finite numbers.")
    vertex_count = len(positions) // 3
    valid_indices = all(
        isinstance(value, int) and not isinstance(value, bool) and 0 <= value < vertex_count
        for value in indices
    )
    if not valid_indices:
        raise OpenUsdImportError("Mesh triangle indices reference an invalid vertex.")


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _positive_number(value: Any) -> bool:
    return _finite_number(value) and float(value) > 0


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
