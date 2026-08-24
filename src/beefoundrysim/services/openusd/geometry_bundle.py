from __future__ import annotations

import json
import math
import sys
from array import array
from dataclasses import dataclass
from typing import Any

from beefoundrysim.services.openusd.mesh_extractor import MeshData

BUNDLE_MAGIC = b"SIMGEOM1"
BUNDLE_VERSION = 1


@dataclass(frozen=True, slots=True)
class GeometryBundle:
    content: bytes
    geometry_count: int
    vertex_count: int
    triangle_count: int


@dataclass(frozen=True, slots=True)
class GeometryBundleMesh:
    geometry_id: str
    mesh: MeshData
    material_id: str | None = None
    instance_matrices: list[float] | None = None


def _align4(value: int) -> int:
    return (value + 3) & ~3


def _array_bytes(typecode: str, values: list[float] | list[int]) -> bytes:
    packed = array(typecode, values)
    if sys.byteorder != "little":
        packed.byteswap()
    return packed.tobytes()


def _vertex_normals(mesh: MeshData) -> list[float]:
    normals = [0.0] * len(mesh.positions)
    positions = mesh.positions
    indices = mesh.indices
    for offset in range(0, len(indices) - 2, 3):
        a = indices[offset] * 3
        b = indices[offset + 1] * 3
        c = indices[offset + 2] * 3
        abx = positions[b] - positions[a]
        aby = positions[b + 1] - positions[a + 1]
        abz = positions[b + 2] - positions[a + 2]
        acx = positions[c] - positions[a]
        acy = positions[c + 1] - positions[a + 1]
        acz = positions[c + 2] - positions[a + 2]
        nx = aby * acz - abz * acy
        ny = abz * acx - abx * acz
        nz = abx * acy - aby * acx
        for vertex in (a, b, c):
            normals[vertex] += nx
            normals[vertex + 1] += ny
            normals[vertex + 2] += nz
    for offset in range(0, len(normals), 3):
        length = math.sqrt(
            normals[offset] ** 2
            + normals[offset + 1] ** 2
            + normals[offset + 2] ** 2
        )
        if length > 1e-15:
            normals[offset] /= length
            normals[offset + 1] /= length
            normals[offset + 2] /= length
        else:
            normals[offset + 2] = 1.0
    return normals


def _rgb_bytes(mesh: MeshData) -> bytes:
    if len(mesh.colors) != mesh.vertex_count * 4:
        return b""
    output = bytearray(mesh.vertex_count * 3)
    target = 0
    for source in range(0, len(mesh.colors), 4):
        for channel in range(3):
            value = max(0.0, min(1.0, float(mesh.colors[source + channel])))
            output[target] = round(value * 255.0)
            target += 1
    return bytes(output)


def _bounds(positions: list[float]) -> dict[str, list[float]]:
    minimum = [min(positions[index::3]) for index in range(3)]
    maximum = [max(positions[index::3]) for index in range(3)]
    center = [(minimum[index] + maximum[index]) / 2.0 for index in range(3)]
    radius = 0.0
    for offset in range(0, len(positions), 3):
        radius = max(
            radius,
            math.sqrt(
                sum(
                    (positions[offset + index] - center[index]) ** 2
                    for index in range(3)
                )
            ),
        )
    return {"min": minimum, "max": maximum, "sphere": [*center, radius]}


def build_geometry_bundle(
    meshes: list[tuple[str, MeshData] | GeometryBundleMesh],
) -> GeometryBundle:
    """Pack robot viewport meshes into one little-endian, browser-readable file."""
    payload = bytearray()
    geometries: dict[str, dict[str, Any]] = {}
    vertex_count = 0
    triangle_count = 0

    def append_blob(blob: bytes, count: int) -> list[int]:
        aligned = _align4(len(payload))
        payload.extend(b"\0" * (aligned - len(payload)))
        offset = len(payload)
        payload.extend(blob)
        return [offset, count]

    for item in meshes:
        if isinstance(item, GeometryBundleMesh):
            geometry_id = item.geometry_id
            mesh = item.mesh
            material_id = item.material_id
            instance_matrices = item.instance_matrices
        else:
            geometry_id, mesh = item
            material_id = None
            instance_matrices = None
        if not mesh.positions or not mesh.indices:
            continue
        if instance_matrices is not None and (
            not instance_matrices or len(instance_matrices) % 16
        ):
            raise ValueError(
                f"Geometry '{geometry_id}' has invalid instance matrices"
            )
        entry: dict[str, Any] = {
            "positions": append_blob(
                _array_bytes("f", mesh.positions), len(mesh.positions)
            ),
            "indices": append_blob(_array_bytes("I", mesh.indices), len(mesh.indices)),
            "normals": append_blob(
                _array_bytes("f", _vertex_normals(mesh)), len(mesh.positions)
            ),
            "bounds": _bounds(mesh.positions),
        }
        if material_id is not None:
            entry["material"] = material_id
        instance_count = 1
        if instance_matrices is not None:
            entry["instances"] = append_blob(
                _array_bytes("f", instance_matrices),
                len(instance_matrices),
            )
            instance_count = len(instance_matrices) // 16
        colors = _rgb_bytes(mesh)
        if colors:
            entry["colors"] = append_blob(colors, len(colors))
        if len(mesh.uvs) == mesh.vertex_count * 2:
            entry["uvs"] = append_blob(_array_bytes("f", mesh.uvs), len(mesh.uvs))
        geometries[geometry_id] = entry
        vertex_count += mesh.vertex_count * instance_count
        triangle_count += mesh.triangle_count * instance_count

    header = json.dumps(
        {
            "format": "beefoundrysim-geometry-bundle",
            "version": BUNDLE_VERSION,
            "geometries": geometries,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    prefix = BUNDLE_MAGIC + len(header).to_bytes(4, "little") + header
    prefix += b"\0" * (_align4(len(prefix)) - len(prefix))
    return GeometryBundle(
        content=prefix + payload,
        geometry_count=len(geometries),
        vertex_count=vertex_count,
        triangle_count=triangle_count,
    )


def read_geometry_bundle_header(content: bytes) -> dict[str, Any]:
    """Read and minimally validate a bundle header for diagnostics and tests."""
    if content[: len(BUNDLE_MAGIC)] != BUNDLE_MAGIC or len(content) < 12:
        raise ValueError("Invalid BeeFoundrySim geometry bundle magic")
    header_length = int.from_bytes(content[8:12], "little")
    header_end = 12 + header_length
    if header_end > len(content):
        raise ValueError("Truncated BeeFoundrySim geometry bundle header")
    header = json.loads(content[12:header_end])
    if (
        header.get("format") != "beefoundrysim-geometry-bundle"
        or header.get("version") != BUNDLE_VERSION
        or not isinstance(header.get("geometries"), dict)
    ):
        raise ValueError("Unsupported BeeFoundrySim geometry bundle header")
    return header
