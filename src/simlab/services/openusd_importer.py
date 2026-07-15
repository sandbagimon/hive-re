from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from simlab.models.robotics import RoboticsModel
from simlab.services.openusd import ImportReport, OpenUsdStageError, load_openusd_stage
from simlab.services.openusd.asset_cache import openusd_asset_id, upsert_asset_metadata
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

    try:
        from pxr import Gf, UsdGeom
    except ImportError as exc:
        raise OpenUsdImportError(
            "OpenUSD Python bindings are unavailable. Install the 'usd-core' package."
        ) from exc

    stage = stage_result.stage

    asset_id = openusd_asset_id(source_path)
    cache_dir = root / "assets" / "imported" / asset_id
    cache_dir.mkdir(parents=True, exist_ok=True)
    copied_source = cache_dir / source_path.name
    if source_path != copied_source:
        shutil.copy2(source_path, copied_source)

    warnings = [
        issue.message for issue in stage_result.report.issues if issue.severity == "warning"
    ]
    positions, indices, display_color = _extract_stage_mesh(stage, Gf, UsdGeom, warnings)
    if not positions or not indices:
        raise OpenUsdImportError("The OpenUSD stage contains no triangulatable UsdGeomMesh data.")
    _validate_mesh_data(positions, indices)

    visual_path = cache_dir / "visual.json"
    collision_path = cache_dir / "collision.obj"
    manifest_path = cache_dir / "manifest.json"
    visual_path.write_text(
        json.dumps({"positions": positions, "indices": indices}, separators=(",", ":")),
        encoding="utf-8",
    )
    collision_path.write_text(_mesh_to_obj(positions, indices), encoding="utf-8")

    physics, physics_warnings = _extract_physics(stage)
    warnings.extend(physics_warnings)
    relative_source = copied_source.relative_to(root).as_posix()
    relative_visual = visual_path.relative_to(root).as_posix()
    relative_collision = collision_path.relative_to(root).as_posix()
    bounds = _bounds(positions)
    mesh_count = sum(1 for prim in stage.Traverse() if prim.IsA(UsdGeom.Mesh))
    manifest = {
        "version": 1,
        "format": "openusd",
        "source": relative_source,
        "source_name": source_path.name,
        "visual_cache": relative_visual,
        "collision_mesh": relative_collision,
        "mesh_count": mesh_count,
        "vertex_count": len(positions) // 3,
        "triangle_count": len(indices) // 3,
        "bounds": bounds,
        "warnings": warnings,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    rgba = [*display_color, 1.0]
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
    if not isinstance(positions, list) or not isinstance(indices, list):
        raise OpenUsdImportError(f"Visual cache is invalid: {cache_path}")
    _validate_mesh_data(positions, indices)
    return {"positions": positions, "indices": indices}


def resolve_imported_asset_path(path_value: str, project_root: str | Path) -> Path:
    """Resolve a project-relative imported asset path without allowing directory traversal."""
    root = Path(project_root).resolve()
    path = (root / path_value).resolve()
    try:
        path.relative_to(root / "assets" / "imported")
    except ValueError as exc:
        raise OpenUsdImportError("Imported asset path must be inside assets/imported.") from exc
    return path


def _extract_stage_mesh(
    stage: Any,
    gf: Any,
    usd_geom: Any,
    warnings: list[str],
) -> tuple[list[float], list[int], list[float]]:
    meters_per_unit = float(usd_geom.GetStageMetersPerUnit(stage) or 1.0)
    up_axis = str(usd_geom.GetStageUpAxis(stage)).upper()
    xform_cache = usd_geom.XformCache()
    positions: list[float] = []
    indices: list[int] = []
    display_color = [0.55, 0.62, 0.7]
    color_found = False
    rigid_body_count = 0

    for prim in stage.Traverse():
        if "PhysicsRigidBodyAPI" in prim.GetAppliedSchemas():
            rigid_body_count += 1
        if not prim.IsA(usd_geom.Mesh):
            continue
        mesh = usd_geom.Mesh(prim)
        points = mesh.GetPointsAttr().Get() or []
        counts = mesh.GetFaceVertexCountsAttr().Get() or []
        face_indices = mesh.GetFaceVertexIndicesAttr().Get() or []
        if not points or not counts or not face_indices:
            warnings.append(f"Skipped empty mesh: {prim.GetPath()}")
            continue
        matrix = xform_cache.GetLocalToWorldTransform(prim)
        base = len(positions) // 3
        for point in points:
            source_point = gf.Vec3d(float(point[0]), float(point[1]), float(point[2]))
            transformed = matrix.Transform(source_point)
            converted = _to_z_up(transformed, up_axis, meters_per_unit)
            positions.extend(converted)

        cursor = 0
        for count_value in counts:
            count = int(count_value)
            face = [int(value) + base for value in face_indices[cursor : cursor + count]]
            cursor += count
            if count < 3:
                continue
            for index in range(1, count - 1):
                indices.extend([face[0], face[index], face[index + 1]])

        if not color_found:
            colors = mesh.GetDisplayColorAttr().Get() or []
            if colors:
                display_color = [_clamp(float(value), 0.0, 1.0) for value in colors[0]]
                color_found = True

    if up_axis not in {"Y", "Z"}:
        warnings.append(f"Unsupported stage up axis '{up_axis}' was treated as Z-up.")
    if rigid_body_count > 1:
        warnings.append(
            f"The stage contains {rigid_body_count} rigid bodies; "
            "this version imports them as one actor."
        )
    return positions, indices, display_color


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
    warnings.append(
        "Collision uses the merged visual mesh; author a dedicated collider for production use."
    )
    return physics, warnings


def _to_z_up(point: Any, up_axis: str, scale: float) -> list[float]:
    x, y, z = (float(point[0]) * scale, float(point[1]) * scale, float(point[2]) * scale)
    if up_axis == "Y":
        return [x, -z, y]
    return [x, y, z]


def _mesh_to_obj(positions: list[float], indices: list[int]) -> str:
    lines = ["# Generated by SimLab OpenUSD importer"]
    for index in range(0, len(positions), 3):
        lines.append(
            f"v {positions[index]:.15g} "
            f"{positions[index + 1]:.15g} {positions[index + 2]:.15g}"
        )
    for index in range(0, len(indices), 3):
        lines.append(f"f {indices[index] + 1} {indices[index + 1] + 1} {indices[index + 2] + 1}")
    return "\n".join(lines) + "\n"


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
