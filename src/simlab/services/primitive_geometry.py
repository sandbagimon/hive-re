from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from simlab.models.actor import Actor

PRIMITIVE_GEOMS = {
    "primitive_box": "box",
    "primitive_sphere": "sphere",
    "primitive_cylinder": "cylinder",
    "primitive_ground": "box",
    "box": "box",
    "sphere": "sphere",
    "cylinder": "cylinder",
    "ellipsoid": "ellipsoid",
    "ground": "plane",
    "plane": "plane",
}

DEFAULT_SIZES = {
    "box": [0.5, 0.5, 0.5],
    "sphere": [0.5],
    "cylinder": [0.5, 0.5],
    "ellipsoid": [0.5, 0.5, 0.5],
    "plane": [5.0, 5.0, 0.1],
}


class GeometryContractError(ValueError):
    def __init__(self, code: str, field: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.field = field


@dataclass(frozen=True, slots=True)
class ColliderGeometry:
    geom_type: str
    size: list[float]


def source_geom_type(actor: Actor) -> str | None:
    primitive = actor.properties.get("primitive")
    return PRIMITIVE_GEOMS.get(str(primitive), PRIMITIVE_GEOMS.get(actor.asset_id))


def collider_geometry(actor: Actor) -> ColliderGeometry:
    """Return the MuJoCo collider after applying the scene actor scale contract."""
    geom_type = source_geom_type(actor)
    if geom_type is None:
        raise GeometryContractError(
            "UNSUPPORTED_PRIMITIVE",
            "properties.primitive",
            "This object has no supported primitive geometry.",
        )

    scale = _positive_vector(actor.transform.scale, 3, "transform.scale")
    expected_size = 1 if geom_type == "sphere" else 2 if geom_type == "cylinder" else 3
    raw_size = actor.properties.get("size", DEFAULT_SIZES[geom_type])
    size = _positive_vector(raw_size, expected_size, "properties.size")

    if geom_type == "box":
        return ColliderGeometry("box", [size[index] * scale[index] for index in range(3)])
    if geom_type == "ellipsoid":
        return ColliderGeometry(
            "ellipsoid",
            [size[index] * scale[index] for index in range(3)],
        )
    if geom_type == "sphere":
        radii = [size[0] * component for component in scale]
        if math.isclose(radii[0], radii[1]) and math.isclose(radii[1], radii[2]):
            return ColliderGeometry("sphere", [radii[0]])
        return ColliderGeometry("ellipsoid", radii)
    if geom_type == "cylinder":
        if not math.isclose(scale[0], scale[1], rel_tol=1e-6, abs_tol=1e-9):
            raise GeometryContractError(
                "NON_UNIFORM_CYLINDER_RADIUS",
                "transform.scale",
                "Cylinder X and Y scale must match so its circular collider matches the viewport.",
            )
        return ColliderGeometry("cylinder", [size[0] * scale[0], size[1] * scale[2]])

    return ColliderGeometry("plane", [size[0] * scale[0], size[1] * scale[1], size[2]])


def euler_xyz_to_mujoco_quaternion(rotation: list[float]) -> list[float]:
    """Convert three.js XYZ Euler radians to a MuJoCo wxyz quaternion."""
    x, y, z = _finite_vector(rotation, 3, "transform.rotation")
    cx, sx = math.cos(x / 2), math.sin(x / 2)
    cy, sy = math.cos(y / 2), math.sin(y / 2)
    cz, sz = math.cos(z / 2), math.sin(z / 2)
    return [
        cx * cy * cz - sx * sy * sz,
        sx * cy * cz + cx * sy * sz,
        cx * sy * cz - sx * cy * sz,
        cx * cy * sz + sx * sy * cz,
    ]


def _positive_vector(value: Any, length: int, field: str) -> list[float]:
    values = _finite_vector(value, length, field)
    if any(item <= 0 for item in values):
        raise GeometryContractError(
            "NON_POSITIVE_GEOMETRY_VALUE",
            field,
            f"{field} values must be greater than zero.",
        )
    return values


def _finite_vector(value: Any, length: int, field: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise GeometryContractError(
            "INVALID_GEOMETRY_VECTOR",
            field,
            f"{field} must contain exactly {length} numbers.",
        )
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        raise GeometryContractError(
            "INVALID_GEOMETRY_VECTOR",
            field,
            f"{field} must contain exactly {length} numbers.",
        )
    values = [float(item) for item in value]
    if not all(math.isfinite(item) for item in values):
        raise GeometryContractError(
            "NON_FINITE_GEOMETRY_VALUE",
            field,
            f"{field} values must be finite.",
        )
    return values
