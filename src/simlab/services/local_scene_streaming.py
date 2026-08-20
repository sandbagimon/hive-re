from __future__ import annotations

import hashlib
import json
import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from simlab.services.openusd.asset_cache import (
    atomic_copy,
    atomic_write_bytes,
    atomic_write_text,
)
from simlab.services.openusd.geometry_bundle import build_geometry_bundle
from simlab.services.openusd.mesh_extractor import (
    MeshData,
    _append_geometry,
    _geometry_instances,
    _local_geometry,
    mesh_to_obj,
)
from simlab.services.openusd.stage_loader import load_openusd_stage

PARK_SCENE_ID = "brownstone-park"
PARK_ENTRY = Path(
    "Demos/AEC/BrownstoneDemo/World_BrownstoneDemopack_Park(8Gb).usd"
)
CACHE_VERSION = 1
TILE_SIZE_METERS = 24.0
MAX_VERTICES_PER_CHUNK = 350_000
MAX_COLLISION_BOXES = 192


@dataclass(frozen=True, slots=True)
class _Bounds:
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    path: str


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


def build_park_cache(source: Path, cache_root: Path, fingerprint: str) -> dict[str, Any]:
    loaded = load_openusd_stage(source)
    try:
        from pxr import Gf, Usd, UsdGeom
    except ImportError as exc:
        raise RuntimeError("OpenUSD Python bindings are unavailable") from exc

    stage = loaded.stage
    warnings: list[str] = []
    meters_per_unit = float(UsdGeom.GetStageMetersPerUnit(stage) or 1.0)
    up_axis = str(UsdGeom.GetStageUpAxis(stage)).upper()
    instances, point_instance_count = _geometry_instances(
        stage,
        UsdGeom.XformCache(Usd.TimeCode.Default()),
        Usd,
        UsdGeom,
        warnings,
        path_filter=_visual_path_allowed,
    )
    local_cache: dict[str, tuple[list[list[float]], list[int], list[float], list[float]]] = {}
    cache_root.mkdir(parents=True, exist_ok=True)
    tile_chunks: dict[tuple[int, int], MeshData] = {}
    chunk_entries: list[dict[str, Any]] = []
    all_bounds: list[_Bounds] = []
    collision_candidates: list[_Bounds] = []

    def flush_chunk(tile: tuple[int, int], mesh: MeshData) -> None:
        if not mesh.vertex_count:
            return
        bundle = build_geometry_bundle([("scene", mesh)])
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
                "bounds": _union_bounds([_mesh_bounds(mesh)]),
            }
        )

    for instance in instances:
        path = str(instance.prim.GetPath())
        if not instance.visible or not _visual_path_allowed(path):
            continue
        cached = local_cache.get(path)
        if cached is None:
            positions, indices, uvs, _native = _local_geometry(instance.prim, UsdGeom)
            color = _fast_display_color(instance.prim, UsdGeom)
            cached = (positions, indices, uvs, color)
            local_cache[path] = cached
        positions, indices, uvs, color = cached
        if not positions or not indices:
            continue
        mesh = MeshData()
        _append_geometry(
            mesh,
            positions,
            indices,
            instance.matrix,
            color,
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
        chunk = tile_chunks.setdefault(tile, MeshData())
        if chunk.vertex_count and chunk.vertex_count + mesh.vertex_count > MAX_VERTICES_PER_CHUNK:
            flush_chunk(tile, chunk)
            chunk = MeshData()
            tile_chunks[tile] = chunk
        _merge_mesh(chunk, mesh)
        if chunk.vertex_count >= MAX_VERTICES_PER_CHUNK:
            flush_chunk(tile, chunk)
            tile_chunks[tile] = MeshData()

    if not all_bounds:
        raise RuntimeError("Park stage did not produce any visible geometry")

    for tile, mesh in sorted(tile_chunks.items()):
        flush_chunk(tile, mesh)

    collision = _build_collision_proxy(collision_candidates)
    if not collision.vertex_count:
        raise RuntimeError("Park stage did not produce collision proxy candidates")
    atomic_write_text(
        cache_root / "collision.obj",
        mesh_to_obj(collision.positions, collision.indices),
    )
    manifest: dict[str, Any] = {
        "format": "simlab-local-scene",
        "version": 1,
        "scene_id": PARK_SCENE_ID,
        "name": "Architectural Brownstone Park (8GB)",
        "source": PARK_ENTRY.as_posix(),
        "source_fingerprint": fingerprint,
        "bounds": _union_bounds(all_bounds),
        "chunks": chunk_entries,
        "statistics": {
            "chunk_count": len(chunk_entries),
            "vertex_count": sum(item["vertex_count"] for item in chunk_entries),
            "triangle_count": sum(item["triangle_count"] for item in chunk_entries),
            "point_instance_count": point_instance_count,
            "collision_box_count": collision.vertex_count // 8,
        },
        "warnings": warnings[:100],
    }
    atomic_write_text(cache_root / "manifest.json", json.dumps(manifest, indent=2) + "\n")
    return manifest


class LocalSceneService:
    """Prepare and expose an allowlisted local OpenUSD scene without copying its source pack."""

    def __init__(self, data_root: Path, asset_root: Path | None) -> None:
        self.data_root = data_root
        self.asset_root = asset_root.resolve() if asset_root is not None else None
        self.cache_root = data_root / "local-scenes" / f"{PARK_SCENE_ID}-v{CACHE_VERSION}"
        self._lock = threading.RLock()
        self._status = "disabled"
        self._error: str | None = None
        self._manifest: dict[str, Any] | None = None
        self._thread: threading.Thread | None = None
        if self.asset_root is not None:
            self._start()

    @property
    def source(self) -> Path | None:
        return (self.asset_root / PARK_ENTRY) if self.asset_root is not None else None

    def _fingerprint(self, source: Path) -> str:
        stat = source.stat()
        payload = f"{CACHE_VERSION}:{source}:{stat.st_size}:{stat.st_mtime_ns}"
        return hashlib.sha256(payload.encode()).hexdigest()[:20]

    def _start(self) -> None:
        source = self.source
        if source is None or not source.is_file():
            self._status = "unavailable"
            self._error = f"Park entry not found: {source}"
            return
        fingerprint = self._fingerprint(source)
        manifest_path = self.cache_root / "manifest.json"
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                chunks = manifest.get("chunks", [])
                if (
                    manifest.get("source_fingerprint") == fingerprint
                    and chunks
                    and all((self.cache_root / f"{item['id']}.simbin").is_file() for item in chunks)
                    and (self.cache_root / "collision.obj").is_file()
                ):
                    self._manifest = manifest
                    self._status = "ready"
                    return
            except (OSError, ValueError, KeyError, TypeError):
                pass
        self._status = "preparing"
        self._thread = threading.Thread(
            target=self._build,
            args=(source, fingerprint),
            name="simlab-park-cache",
            daemon=True,
        )
        self._thread.start()

    def _build(self, source: Path, fingerprint: str) -> None:
        try:
            manifest = build_park_cache(source, self.cache_root, fingerprint)
        except Exception as exc:
            with self._lock:
                self._status = "failed"
                self._error = str(exc)
            return
        with self._lock:
            self._manifest = manifest
            self._status = "ready"
            self._error = None

    def statuses(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "scene_id": PARK_SCENE_ID,
                    "name": "Architectural Brownstone Park (8GB)",
                    "status": self._status,
                    **({"error": self._error} if self._error else {}),
                    **(
                        {"statistics": self._manifest.get("statistics", {})}
                        if self._manifest is not None
                        else {}
                    ),
                }
            ]

    def _ready_manifest(self, scene_id: str) -> dict[str, Any]:
        if scene_id != PARK_SCENE_ID:
            raise KeyError(f"Unknown local scene: {scene_id}")
        with self._lock:
            if self._status != "ready" or self._manifest is None:
                raise ValueError(f"Local scene is not ready: {self._status}")
            return self._manifest

    def asset(self, project_root: Path) -> dict[str, Any] | None:
        manifest = self._ready_manifest(PARK_SCENE_ID) if self._status == "ready" else None
        if manifest is None:
            return None
        fingerprint = str(manifest["source_fingerprint"])
        collision_reference = Path(
            f"assets/imported/local_brownstone_park/collision-{fingerprint}.obj"
        )
        collision_path = project_root / collision_reference
        if not collision_path.is_file():
            atomic_copy(self.cache_root / "collision.obj", collision_path)
        return {
            "id": "openusd_brownstone_park_8gb",
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
                    "source": f"local-scene:{PARK_SCENE_ID}",
                    "stream_scene_id": PARK_SCENE_ID,
                    "collision_mesh": collision_reference.as_posix(),
                    "bounds": manifest["bounds"],
                },
            },
        }

    def manifest(self, scene_id: str) -> dict[str, Any]:
        return json.loads(json.dumps(self._ready_manifest(scene_id)))

    def chunk_path(self, scene_id: str, chunk_id: str) -> Path:
        manifest = self._ready_manifest(scene_id)
        allowed = {str(item["id"]) for item in manifest["chunks"]}
        if chunk_id not in allowed:
            raise KeyError(f"Unknown local scene chunk: {chunk_id}")
        path = self.cache_root / f"{chunk_id}.simbin"
        if not path.is_file():
            raise KeyError(f"Local scene chunk is unavailable: {chunk_id}")
        return path
