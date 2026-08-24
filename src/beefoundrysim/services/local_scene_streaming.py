from __future__ import annotations

import hashlib
import json
import math
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from beefoundrysim.services.local_scene_materials import LocalMaterialRegistry
from beefoundrysim.services.openusd.asset_cache import (
    atomic_copy,
    atomic_write_bytes,
    atomic_write_text,
)
from beefoundrysim.services.openusd.geometry_bundle import (
    GeometryBundleMesh,
    build_geometry_bundle,
)
from beefoundrysim.services.openusd.mesh_extractor import (
    MeshData,
    _append_geometry,
    _geometry_instances,
    _local_geometry,
    _PointInstancerCopies,
    mesh_to_obj,
)
from beefoundrysim.services.openusd.stage_loader import load_openusd_stage

PARK_SCENE_ID = "brownstone-park"
FULL_PARK_SCENE_ID = "brownstone-park-full"
PARK_ENTRY = Path(
    "Demos/AEC/BrownstoneDemo/World_BrownstoneDemopack_Park(8Gb).usd"
)
CACHE_VERSION = 3
FULL_CACHE_VERSION = 3
MANIFEST_VERSION = 3
TILE_SIZE_METERS = 24.0
MAX_VERTICES_PER_CHUNK = 350_000
MAX_COLLISION_BOXES = 192
INSTANCE_GROUP_VERTEX_BUDGET = 1_500_000
MIN_INSTANCE_PROTOTYPE_VERTICES = 24


@dataclass(frozen=True, slots=True)
class _Bounds:
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    path: str


@dataclass(frozen=True, slots=True)
class _SceneVariant:
    scene_id: str
    name: str
    asset_id: str
    cache_version: int
    content_profile: str


@dataclass(slots=True)
class _InstanceRecord:
    matrix: list[float]
    bounds: _Bounds


@dataclass(slots=True)
class _InstanceGroup:
    geometry_id: str
    material_id: str
    mesh: MeshData
    local_bounds: _Bounds
    records: list[_InstanceRecord] = field(default_factory=list)


@dataclass(slots=True)
class _SceneState:
    variant: _SceneVariant
    cache_root: Path
    status: str = "disabled"
    error: str | None = None
    manifest: dict[str, Any] | None = None


PARK_VARIANTS = (
    _SceneVariant(
        PARK_SCENE_ID,
        "Architectural Brownstone Park (Optimized)",
        "openusd_brownstone_park_8gb",
        CACHE_VERSION,
        "optimized",
    ),
    _SceneVariant(
        FULL_PARK_SCENE_ID,
        "Architectural Brownstone Park (Full)",
        "openusd_brownstone_park_full",
        FULL_CACHE_VERSION,
        "full",
    ),
)


def _merge_mesh(target: MeshData, source: MeshData) -> None:
    base = target.vertex_count
    target.positions.extend(source.positions)
    target.indices.extend(base + index for index in source.indices)
    target.colors.extend(source.colors)
    if source.uvs:
        if not target.uvs and base:
            target.uvs.extend([0.0] * base * 2)
        target.uvs.extend(source.uvs)
    elif target.uvs:
        target.uvs.extend([0.0] * source.vertex_count * 2)
    target.source_prim_paths.extend(
        path for path in source.source_prim_paths if path not in target.source_prim_paths
    )


def _instance_lod_mesh(mesh: MeshData, instance_count: int) -> MeshData:
    target_vertices = min(
        MAX_VERTICES_PER_CHUNK,
        max(
            MIN_INSTANCE_PROTOTYPE_VERTICES,
            INSTANCE_GROUP_VERTEX_BUDGET // max(instance_count, 1),
        ),
    )
    target_triangles = max(1, target_vertices // 3)
    triangle_count = mesh.triangle_count
    if triangle_count <= target_triangles:
        return mesh

    output = MeshData(source_prim_paths=list(mesh.source_prim_paths))
    has_colors = len(mesh.colors) == mesh.vertex_count * 4
    has_uvs = len(mesh.uvs) == mesh.vertex_count * 2
    for sample in range(target_triangles):
        triangle = min(
            triangle_count - 1,
            math.floor(sample * triangle_count / target_triangles),
        )
        for corner in range(3):
            source_vertex = mesh.indices[triangle * 3 + corner]
            position = source_vertex * 3
            output.positions.extend(mesh.positions[position : position + 3])
            if has_colors:
                color = source_vertex * 4
                output.colors.extend(mesh.colors[color : color + 4])
            if has_uvs:
                uv = source_vertex * 2
                output.uvs.extend(mesh.uvs[uv : uv + 2])
            output.indices.append(len(output.indices))
    return output


def _mesh_bounds(mesh: MeshData, path: str = "") -> _Bounds:
    return _Bounds(
        tuple(min(mesh.positions[index::3]) for index in range(3)),
        tuple(max(mesh.positions[index::3]) for index in range(3)),
        path,
    )


def _union_bounds(bounds: list[_Bounds]) -> dict[str, list[float]]:
    return {
        "min": [min(item.minimum[index] for item in bounds) for index in range(3)],
        "max": [max(item.maximum[index] for item in bounds) for index in range(3)],
    }


def _visual_path_allowed(path: str) -> bool:
    lowered = path.lower()
    return not any(
        token in lowered
        for token in (
            "/environment/sky",
            "/environment/compass",
            "/looks/",
            "/painttool/",
            "grass",
            "flower",
            "shrub",
            "leaf",
            "lupin",
            "hydrangea",
        )
    )


def _full_visual_path_allowed(path: str) -> bool:
    """Keep all physical authored content; renderer-only helpers remain excluded."""
    lowered = path.lower()
    return not any(
        token in lowered
        for token in (
            "/environment/sky",
            "/environment/compass",
            "/looks/",
        )
    )


def _target_point(
    matrix: Any,
    point: tuple[float, float, float],
    gf: Any,
    up_axis: str,
    scale: float,
) -> tuple[float, float, float]:
    transformed = matrix.Transform(gf.Vec3d(*point))
    x, y, z = (float(value) * scale for value in transformed)
    return (x, -z, y) if up_axis == "Y" else (x, y, z)


def _three_instance_matrix(
    matrix: Any,
    gf: Any,
    up_axis: str,
    scale: float,
) -> list[float]:
    origin = _target_point(matrix, (0.0, 0.0, 0.0), gf, up_axis, scale)
    inverse_scale = 1.0 / scale
    source_axes = (
        (
            (inverse_scale, 0.0, 0.0),
            (0.0, 0.0, -inverse_scale),
            (0.0, inverse_scale, 0.0),
        )
        if up_axis == "Y"
        else (
            (inverse_scale, 0.0, 0.0),
            (0.0, inverse_scale, 0.0),
            (0.0, 0.0, inverse_scale),
        )
    )
    columns = []
    for axis in source_axes:
        point = _target_point(matrix, axis, gf, up_axis, scale)
        columns.append(tuple(point[index] - origin[index] for index in range(3)))
    return [
        *columns[0],
        0.0,
        *columns[1],
        0.0,
        *columns[2],
        0.0,
        *origin,
        1.0,
    ]


def _transformed_bounds(
    bounds: _Bounds,
    matrix: list[float],
    path: str,
) -> _Bounds:
    points = []
    for x in (bounds.minimum[0], bounds.maximum[0]):
        for y in (bounds.minimum[1], bounds.maximum[1]):
            for z in (bounds.minimum[2], bounds.maximum[2]):
                points.append(
                    (
                        matrix[0] * x + matrix[4] * y + matrix[8] * z + matrix[12],
                        matrix[1] * x + matrix[5] * y + matrix[9] * z + matrix[13],
                        matrix[2] * x + matrix[6] * y + matrix[10] * z + matrix[14],
                    )
                )
    return _Bounds(
        tuple(min(point[index] for point in points) for index in range(3)),
        tuple(max(point[index] for point in points) for index in range(3)),
        path,
    )


def _fast_display_color(prim: Any, usd_geom: Any) -> list[float]:
    colors = usd_geom.Gprim(prim).GetDisplayColorAttr().Get() or []
    opacity_values = usd_geom.Gprim(prim).GetDisplayOpacityAttr().Get() or []
    if colors:
        return [
            float(colors[0][0]),
            float(colors[0][1]),
            float(colors[0][2]),
            float(opacity_values[0]) if opacity_values else 1.0,
        ]
    path = str(prim.GetPath()).lower()
    if any(token in path for token in ("tree", "vegetation", "canopy")):
        return [0.22, 0.42, 0.18, 1.0]
    if any(token in path for token in ("road", "sidewalk", "path", "hardscape")):
        return [0.34, 0.35, 0.34, 1.0]
    if any(token in path for token in ("bench", "table", "chair")):
        return [0.38, 0.28, 0.18, 1.0]
    return [0.55, 0.58, 0.54, 1.0]


def _collision_path_allowed(path: str) -> bool:
    lowered = path.lower()
    if any(
        token in lowered
        for token in (
            "sky",
            "tree",
            "plant",
            "grass",
            "leaf",
            "flower",
            "painttool",
            "canopy",
            "bush",
        )
    ):
        return False
    return any(
        token in lowered
        for token in (
            "road",
            "sidewalk",
            "walkway",
            "path",
            "hardscape",
            "curb",
            "ground",
            "step",
            "stair",
            "wall",
            "building",
            "brownstone",
            "fence",
            "bench",
            "hydrant",
            "trash",
            "mailbox",
            "shelter",
            "bollard",
        )
    )


def _append_box(mesh: MeshData, bounds: _Bounds) -> None:
    minimum = list(bounds.minimum)
    maximum = list(bounds.maximum)
    lowered = bounds.path.lower()
    if any(
        token in lowered
        for token in ("road", "sidewalk", "walkway", "path", "hardscape", "ground")
    ):
        maximum[2] = max(maximum[2], minimum[2] + 0.05)
        minimum[2] = maximum[2] - min(maximum[2] - minimum[2], 0.18)
    if any(maximum[index] - minimum[index] < 0.025 for index in range(3)):
        for index in range(3):
            if maximum[index] - minimum[index] < 0.025:
                center = (minimum[index] + maximum[index]) / 2.0
                minimum[index], maximum[index] = center - 0.0125, center + 0.0125
    base = mesh.vertex_count
    for x, y, z in (
        (minimum[0], minimum[1], minimum[2]),
        (maximum[0], minimum[1], minimum[2]),
        (maximum[0], maximum[1], minimum[2]),
        (minimum[0], maximum[1], minimum[2]),
        (minimum[0], minimum[1], maximum[2]),
        (maximum[0], minimum[1], maximum[2]),
        (maximum[0], maximum[1], maximum[2]),
        (minimum[0], maximum[1], maximum[2]),
    ):
        mesh.positions.extend((x, y, z))
    mesh.indices.extend(
        base + index
        for index in (
            0, 2, 1, 0, 3, 2, 4, 5, 6, 4, 6, 7,
            0, 1, 5, 0, 5, 4, 1, 2, 6, 1, 6, 5,
            2, 3, 7, 2, 7, 6, 3, 0, 4, 3, 4, 7,
        )
    )


def _build_collision_proxy(candidates: list[_Bounds]) -> MeshData:
    unique: dict[tuple[int, ...], _Bounds] = {}
    for item in candidates:
        key = tuple(
            round(value * 20.0)
            for value in (*item.minimum, *item.maximum)
        )
        unique.setdefault(key, item)
    values = list(unique.values())
    values.sort(
        key=lambda item: (
            0 if any(token in item.path.lower() for token in ("road", "sidewalk", "path")) else 1,
            -math.prod(
                max(item.maximum[index] - item.minimum[index], 0.01)
                for index in range(3)
            ),
        )
    )
    output = MeshData()
    for item in values[:MAX_COLLISION_BOXES]:
        _append_box(output, item)
    return output


def _full_point_instance_groups(
    stage: Any,
    xform_cache: Any,
    usd: Any,
    usd_geom: Any,
    usd_shade: Any,
    gf: Any,
    material_registry: LocalMaterialRegistry,
    up_axis: str,
    meters_per_unit: float,
    warnings: list[str],
) -> tuple[list[tuple[str, list[_InstanceGroup]]], int]:
    """Preserve every PointInstancer copy as GPU instance matrices.

    Nested instancers are composed with their parent instance transforms via
    ``_PointInstancerCopies``, so prototype-authored scatter content follows
    each painted instance instead of collapsing onto its authored location.
    """
    geometry_cache: dict[str, tuple[MeshData, str, _Bounds]] = {}
    groups: dict[str, _InstanceGroup] = {}
    output: list[tuple[str, list[_InstanceGroup]]] = []
    current_root: str | None = None
    entry_groups: list[_InstanceGroup] = []

    copies = _PointInstancerCopies(
        stage, xform_cache, usd, usd_geom, warnings, _full_visual_path_allowed
    )

    def close_entry() -> None:
        nonlocal entry_groups
        if current_root is not None and entry_groups:
            output.append((current_root, entry_groups))
        entry_groups = []

    for root_path, prim, matrix, visible in copies:
        if root_path != current_root:
            close_entry()
            current_root = root_path
        if not visible:
            continue
        child_path = str(prim.GetPath())
        cached = geometry_cache.get(child_path)
        if cached is None:
            positions, indices, uvs, _native = _local_geometry(prim, usd_geom)
            material_id, vertex_color = material_registry.material_for_prim(
                prim,
                _fast_display_color(prim, usd_geom),
                usd_shade,
            )
            mesh = MeshData()
            if positions and indices:
                _append_geometry(
                    mesh,
                    positions,
                    indices,
                    gf.Matrix4d(1.0),
                    vertex_color,
                    uvs,
                    child_path,
                    gf,
                    up_axis,
                    meters_per_unit,
                )
            local_bounds = (
                _mesh_bounds(mesh, child_path)
                if mesh.vertex_count
                else _Bounds((0, 0, 0), (0, 0, 0), child_path)
            )
            cached = (mesh, material_id, local_bounds)
            geometry_cache[child_path] = cached
        mesh, material_id, _local_bounds = cached
        if not mesh.vertex_count:
            continue
        group_key = f"{root_path}:{child_path}"
        group = groups.get(group_key)
        if group is None:
            digest = hashlib.sha256(group_key.encode()).hexdigest()[:16]
            group = _InstanceGroup(f"inst_{digest}", material_id, mesh, cached[2])
            groups[group_key] = group
            entry_groups.append(group)
        world = _three_instance_matrix(matrix, gf, up_axis, meters_per_unit)
        group.records.append(
            _InstanceRecord(
                world,
                _transformed_bounds(group.local_bounds, world, child_path),
            )
        )
    close_entry()
    return output, copies.instance_count


def build_park_cache(
    source: Path,
    cache_root: Path,
    fingerprint: str,
    asset_root: Path | None = None,
    *,
    scene_id: str = PARK_SCENE_ID,
    name: str = "Architectural Brownstone Park (Optimized)",
    content_profile: str = "optimized",
) -> dict[str, Any]:
    loaded = load_openusd_stage(source)
    try:
        from pxr import Gf, Usd, UsdGeom, UsdShade
    except ImportError as exc:
        raise RuntimeError("OpenUSD Python bindings are unavailable") from exc

    stage = loaded.stage
    warnings: list[str] = []
    meters_per_unit = float(UsdGeom.GetStageMetersPerUnit(stage) or 1.0)
    up_axis = str(UsdGeom.GetStageUpAxis(stage)).upper()
    path_allowed = (
        _full_visual_path_allowed
        if content_profile == "full"
        else _visual_path_allowed
    )
    xform_cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    instances, point_instance_count = _geometry_instances(
        stage,
        xform_cache,
        Usd,
        UsdGeom,
        warnings,
        path_filter=path_allowed,
        expand_point_instancers=content_profile != "full",
    )
    cache_root.mkdir(parents=True, exist_ok=True)
    material_registry = LocalMaterialRegistry(asset_root or source.parent, cache_root)
    local_cache: dict[
        str,
        tuple[list[list[float]], list[int], list[float], str, list[float]],
    ] = {}
    tile_chunks: dict[tuple[int, int], dict[str, MeshData]] = {}
    chunk_entries: list[dict[str, Any]] = []
    all_bounds: list[_Bounds] = []
    collision_candidates: list[_Bounds] = []

    def chunk_vertex_count(meshes: dict[str, MeshData]) -> int:
        return sum(mesh.vertex_count for mesh in meshes.values())

    def write_chunk(
        tile: tuple[int, int],
        bundle: Any,
        bounds: list[_Bounds],
    ) -> None:
        content_hash = hashlib.sha256(bundle.content).hexdigest()[:16]
        chunk_id = f"chunk-{len(chunk_entries):04d}-{content_hash}"
        atomic_write_bytes(cache_root / f"{chunk_id}.simbin", bundle.content)
        chunk_entries.append(
            {
                "id": chunk_id,
                "tile": [tile[0], tile[1]],
                "byte_length": len(bundle.content),
                "vertex_count": bundle.vertex_count,
                "triangle_count": bundle.triangle_count,
                "bounds": _union_bounds(bounds),
            }
        )

    def flush_chunk(tile: tuple[int, int], meshes: dict[str, MeshData]) -> None:
        if not chunk_vertex_count(meshes):
            return
        bundle = build_geometry_bundle(sorted(meshes.items()))
        write_chunk(
            tile,
            bundle,
            [_mesh_bounds(mesh) for mesh in meshes.values() if mesh.vertex_count],
        )

    for instance in instances:
        path = str(instance.prim.GetPath())
        if not instance.visible or not path_allowed(path):
            continue
        cached = local_cache.get(path)
        if cached is None:
            positions, indices, uvs, _native = _local_geometry(instance.prim, UsdGeom)
            material_id, vertex_color = material_registry.material_for_prim(
                instance.prim,
                _fast_display_color(instance.prim, UsdGeom),
                UsdShade,
            )
            cached = (positions, indices, uvs, material_id, vertex_color)
            local_cache[path] = cached
        positions, indices, uvs, material_id, vertex_color = cached
        if not positions or not indices:
            continue
        mesh = MeshData()
        _append_geometry(
            mesh,
            positions,
            indices,
            instance.matrix,
            vertex_color,
            uvs,
            path,
            Gf,
            up_axis,
            meters_per_unit,
        )
        bounds = _mesh_bounds(mesh, path)
        all_bounds.append(bounds)
        if _collision_path_allowed(path):
            collision_candidates.append(bounds)
        center_x = (bounds.minimum[0] + bounds.maximum[0]) / 2.0
        center_y = (bounds.minimum[1] + bounds.maximum[1]) / 2.0
        tile = (math.floor(center_x / TILE_SIZE_METERS), math.floor(center_y / TILE_SIZE_METERS))
        chunk = tile_chunks.setdefault(tile, {})
        if (
            chunk_vertex_count(chunk)
            and chunk_vertex_count(chunk) + mesh.vertex_count > MAX_VERTICES_PER_CHUNK
        ):
            flush_chunk(tile, chunk)
            chunk = {}
            tile_chunks[tile] = chunk
        _merge_mesh(chunk.setdefault(material_id, MeshData()), mesh)
        if chunk_vertex_count(chunk) >= MAX_VERTICES_PER_CHUNK:
            flush_chunk(tile, chunk)
            tile_chunks[tile] = {}

    instance_group_count = 0
    instance_lod_group_count = 0
    source_instance_vertex_count = 0
    if content_profile == "full":
        instancers, point_instance_count = _full_point_instance_groups(
            stage,
            xform_cache,
            Usd,
            UsdGeom,
            UsdShade,
            Gf,
            material_registry,
            up_axis,
            meters_per_unit,
            warnings,
        )
        for _instancer_path, groups in instancers:
            pending: list[_InstanceGroup] = []
            pending_base_vertices = 0

            def flush_instances() -> None:
                nonlocal pending, pending_base_vertices
                nonlocal instance_group_count, instance_lod_group_count
                nonlocal source_instance_vertex_count
                if not pending:
                    return
                bounds = [record.bounds for group in pending for record in group.records]
                union = _union_bounds(bounds)
                center_x = (union["min"][0] + union["max"][0]) / 2.0
                center_y = (union["min"][1] + union["max"][1]) / 2.0
                tile = (
                    math.floor(center_x / TILE_SIZE_METERS),
                    math.floor(center_y / TILE_SIZE_METERS),
                )
                bundle_meshes = []
                for group in pending:
                    instance_count = len(group.records)
                    source_instance_vertex_count += (
                        group.mesh.vertex_count * instance_count
                    )
                    render_mesh = _instance_lod_mesh(group.mesh, instance_count)
                    if render_mesh is not group.mesh:
                        instance_lod_group_count += 1
                    bundle_meshes.append(
                        GeometryBundleMesh(
                            group.geometry_id,
                            render_mesh,
                            group.material_id,
                            [
                                value
                                for record in group.records
                                for value in record.matrix
                            ],
                        )
                    )
                bundle = build_geometry_bundle(bundle_meshes)
                write_chunk(tile, bundle, bounds)
                instance_group_count += len(pending)
                all_bounds.extend(bounds)
                pending = []
                pending_base_vertices = 0

            for group in groups:
                if (
                    pending
                    and pending_base_vertices + group.mesh.vertex_count
                    > MAX_VERTICES_PER_CHUNK
                ):
                    flush_instances()
                pending.append(group)
                pending_base_vertices += group.mesh.vertex_count
            flush_instances()
        if point_instance_count:
            warnings.append(
                f"Preserved {point_instance_count} PointInstancer instance(s) "
                "as GPU instances."
            )
        if instance_lod_group_count:
            warnings.append(
                f"Applied automatic prototype LOD to {instance_lod_group_count} "
                "dense instance group(s) while retaining every instance."
            )

    if not all_bounds:
        raise RuntimeError("Park stage did not produce any visible geometry")

    for tile, meshes in sorted(tile_chunks.items()):
        flush_chunk(tile, meshes)

    collision = _build_collision_proxy(collision_candidates)
    if not collision.vertex_count:
        raise RuntimeError("Park stage did not produce collision proxy candidates")
    atomic_write_text(
        cache_root / "collision.obj",
        mesh_to_obj(collision.positions, collision.indices),
    )
    manifest: dict[str, Any] = {
        "format": "beefoundrysim-local-scene",
        "version": MANIFEST_VERSION,
        "scene_id": scene_id,
        "name": name,
        "content_profile": content_profile,
        "source": PARK_ENTRY.as_posix(),
        "source_fingerprint": fingerprint,
        "bounds": _union_bounds(all_bounds),
        "chunks": chunk_entries,
        "materials": material_registry.materials,
        "textures": material_registry.textures,
        "statistics": {
            "chunk_count": len(chunk_entries),
            "vertex_count": sum(item["vertex_count"] for item in chunk_entries),
            "triangle_count": sum(item["triangle_count"] for item in chunk_entries),
            "point_instance_count": point_instance_count,
            "instance_group_count": instance_group_count,
            "instance_lod_group_count": instance_lod_group_count,
            "source_instance_vertex_count": source_instance_vertex_count,
            "collision_box_count": collision.vertex_count // 8,
            "material_count": len(material_registry.materials),
            "texture_count": len(material_registry.textures),
            "missing_texture_count": material_registry.missing_texture_count,
            "mdl_material_count": sum(
                1
                for material in material_registry.materials.values()
                if material.get("source_model") == "MDL:OmniPBR"
            ),
            "mdl_source_count": len(material_registry.mdl_source_paths),
            "missing_mdl_count": material_registry.missing_mdl_count,
        },
        "warnings": (
            warnings
            + (
                [
                    f"{material_registry.missing_texture_count} authored texture references "
                    "were unavailable; their material constants were used instead."
                ]
                if material_registry.missing_texture_count
                else []
            )
            + (
                [
                    f"{material_registry.missing_mdl_count} MDL source references "
                    "were unavailable or outside the asset root."
                ]
                if material_registry.missing_mdl_count
                else []
            )
        )[:100],
    }
    atomic_write_text(cache_root / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    active_chunks = {f"{item['id']}.simbin" for item in chunk_entries}
    for stale_chunk in cache_root.glob("chunk-*.simbin"):
        if stale_chunk.name not in active_chunks:
            stale_chunk.unlink(missing_ok=True)
    active_textures = {item["filename"] for item in material_registry.textures.values()}
    texture_root = cache_root / "textures"
    for stale_texture in texture_root.glob("tex_*.*"):
        if stale_texture.name not in active_textures:
            stale_texture.unlink(missing_ok=True)
    return manifest


class LocalSceneService:
    """Prepare and expose an allowlisted local OpenUSD scene without copying its source pack."""

    def __init__(self, data_root: Path, asset_root: Path | None) -> None:
        self.data_root = data_root
        self.asset_root = asset_root.resolve() if asset_root is not None else None
        self._lock = threading.RLock()
        self._states = {
            variant.scene_id: _SceneState(
                variant,
                data_root
                / "local-scenes"
                / f"{variant.scene_id}-v{variant.cache_version}",
            )
            for variant in PARK_VARIANTS
        }
        self._thread: threading.Thread | None = None
        if self.asset_root is not None:
            self._start()

    @property
    def source(self) -> Path | None:
        return (self.asset_root / PARK_ENTRY) if self.asset_root is not None else None

    def _fingerprint(self, source: Path, variant: _SceneVariant) -> str:
        stat = source.stat()
        payload = (
            f"{variant.cache_version}:{source}:{stat.st_size}:{stat.st_mtime_ns}"
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:20]

    def _start(self) -> None:
        source = self.source
        if source is None or not source.is_file():
            for state in self._states.values():
                state.status = "unavailable"
                state.error = f"Park entry not found: {source}"
            return
        pending: list[tuple[_SceneState, str]] = []
        for state in self._states.values():
            fingerprint = self._fingerprint(source, state.variant)
            if self._load_cached(state, fingerprint):
                continue
            state.status = "preparing"
            pending.append((state, fingerprint))
        if not pending:
            return
        self._thread = threading.Thread(
            target=self._build_pending,
            args=(source, pending),
            name="beefoundrysim-park-caches",
            daemon=True,
        )
        self._thread.start()

    def _load_cached(self, state: _SceneState, fingerprint: str) -> bool:
        manifest_path = state.cache_root / "manifest.json"
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if (
                    state.variant.content_profile == "optimized"
                    and manifest.get("content_profile") is None
                ):
                    manifest["content_profile"] = "optimized"
                    manifest["name"] = state.variant.name
                    atomic_write_text(
                        manifest_path, json.dumps(manifest, indent=2) + "\n"
                    )
                chunks = manifest.get("chunks", [])
                textures = manifest.get("textures", {}).values()
                if (
                    manifest.get("version") == MANIFEST_VERSION
                    and manifest.get("scene_id") == state.variant.scene_id
                    and manifest.get("content_profile")
                    == state.variant.content_profile
                    and manifest.get("source_fingerprint") == fingerprint
                    and chunks
                    and all(
                        (state.cache_root / f"{item['id']}.simbin").is_file()
                        for item in chunks
                    )
                    and all(
                        (state.cache_root / "textures" / item["filename"]).is_file()
                        for item in textures
                    )
                    and (state.cache_root / "collision.obj").is_file()
                ):
                    state.manifest = manifest
                    state.status = "ready"
                    state.error = None
                    return True
            except (OSError, ValueError, KeyError, TypeError):
                pass
        return False

    def _build_pending(
        self,
        source: Path,
        pending: list[tuple[_SceneState, str]],
    ) -> None:
        for state, fingerprint in pending:
            try:
                manifest = build_park_cache(
                    source,
                    state.cache_root,
                    fingerprint,
                    self.asset_root,
                    scene_id=state.variant.scene_id,
                    name=state.variant.name,
                    content_profile=state.variant.content_profile,
                )
            except Exception as exc:
                with self._lock:
                    state.status = "failed"
                    state.error = str(exc)
                continue
            with self._lock:
                state.manifest = manifest
                state.status = "ready"
                state.error = None

    def statuses(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "scene_id": state.variant.scene_id,
                    "name": state.variant.name,
                    "content_profile": state.variant.content_profile,
                    "status": state.status,
                    **({"error": state.error} if state.error else {}),
                    **(
                        {"statistics": state.manifest.get("statistics", {})}
                        if state.manifest is not None
                        else {}
                    ),
                }
                for state in self._states.values()
            ]

    def _ready_state(self, scene_id: str) -> _SceneState:
        state = self._states.get(scene_id)
        if state is None:
            raise KeyError(f"Unknown local scene: {scene_id}")
        with self._lock:
            if state.status != "ready" or state.manifest is None:
                raise ValueError(f"Local scene is not ready: {state.status}")
            return state

    def _asset(self, project_root: Path, state: _SceneState) -> dict[str, Any]:
        manifest = state.manifest
        if manifest is None:
            raise ValueError(f"Local scene is not ready: {state.status}")
        fingerprint = str(manifest["source_fingerprint"])
        collision_reference = Path(
            f"assets/imported/{state.variant.scene_id}/collision-{fingerprint}.obj"
        )
        collision_path = project_root / collision_reference
        if not collision_path.is_file():
            atomic_copy(state.cache_root / "collision.obj", collision_path)
        return {
            "id": state.variant.asset_id,
            "name": manifest["name"],
            "type": "object",
            "category": "environment",
            "source_format": "openusd",
            "license": "NVIDIA Omniverse Asset License",
            "default_transform": {
                "position": [0, 0, 0],
                "rotation": [0, 0, 0],
                "scale": [1, 1, 1],
            },
            "default_properties": {
                "rgba": [1, 1, 1, 1],
                "physics": {"dynamic": False},
                "geometry": {
                    "kind": "mesh",
                    "source_format": "openusd",
                    "source": f"local-scene:{state.variant.scene_id}",
                    "stream_scene_id": state.variant.scene_id,
                    "collision_mesh": collision_reference.as_posix(),
                    "bounds": manifest["bounds"],
                },
            },
        }

    def assets(self, project_root: Path) -> list[dict[str, Any]]:
        with self._lock:
            ready = [
                state
                for state in self._states.values()
                if state.status == "ready" and state.manifest is not None
            ]
        return [self._asset(project_root, state) for state in ready]

    def manifest(self, scene_id: str) -> dict[str, Any]:
        state = self._ready_state(scene_id)
        return json.loads(json.dumps(state.manifest))

    def chunk_path(self, scene_id: str, chunk_id: str) -> Path:
        state = self._ready_state(scene_id)
        manifest = state.manifest
        if manifest is None:
            raise ValueError(f"Local scene is not ready: {state.status}")
        allowed = {str(item["id"]) for item in manifest["chunks"]}
        if chunk_id not in allowed:
            raise KeyError(f"Unknown local scene chunk: {chunk_id}")
        path = state.cache_root / f"{chunk_id}.simbin"
        if not path.is_file():
            raise KeyError(f"Local scene chunk is unavailable: {chunk_id}")
        return path

    def texture_path(self, scene_id: str, texture_id: str) -> tuple[Path, str]:
        state = self._ready_state(scene_id)
        manifest = state.manifest
        if manifest is None:
            raise ValueError(f"Local scene is not ready: {state.status}")
        texture = manifest.get("textures", {}).get(texture_id)
        if not isinstance(texture, dict):
            raise KeyError(f"Unknown local scene texture: {texture_id}")
        filename = texture.get("filename")
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise KeyError(f"Invalid local scene texture: {texture_id}")
        path = state.cache_root / "textures" / filename
        if not path.is_file():
            raise KeyError(f"Local scene texture is unavailable: {texture_id}")
        return path, str(texture.get("media_type") or "application/octet-stream")
