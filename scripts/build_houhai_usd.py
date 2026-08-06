#!/usr/bin/env python3
"""Download a 2 km Overture building extract for Shenzhen Houhai and build USD."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import fsspec
import pyarrow.compute as pc
import pyarrow.parquet as pq
from pxr import Gf, Usd, UsdGeom, UsdPhysics
from shapely import from_wkb, to_wkb
from shapely.geometry import (
    LineString,
    MultiLineString,
    MultiPolygon,
    Polygon,
    box,
    mapping,
    shape,
)
from shapely.ops import polygonize, transform, triangulate

DEFAULT_CENTER = (113.919790, 22.526595)
DEFAULT_SIZE_METERS = 2000.0
DEFAULT_RELEASE = "2026-07-22.0"
EARTH_RADIUS_METERS = 6_378_137.0

# The browser importer currently preserves one authored display color per USD prim. Keep the
# number of prims bounded, but split the city into a compact semantic palette so thousands of
# buildings do not collapse into one grey material.
BUILDING_STYLES: dict[
    str, tuple[tuple[float, float, float], tuple[float, float, float]]
] = {
    "glass_blue": ((0.19, 0.37, 0.52), (0.10, 0.19, 0.27)),
    "glass_teal": ((0.18, 0.43, 0.45), (0.09, 0.22, 0.23)),
    "glass_slate": ((0.31, 0.40, 0.50), (0.16, 0.21, 0.28)),
    "residential_sand": ((0.69, 0.55, 0.39), (0.40, 0.27, 0.19)),
    "residential_clay": ((0.62, 0.36, 0.29), (0.34, 0.18, 0.16)),
    "residential_sage": ((0.39, 0.52, 0.46), (0.22, 0.32, 0.28)),
    "residential_blue": ((0.38, 0.50, 0.61), (0.20, 0.29, 0.38)),
    "civic_cream": ((0.76, 0.66, 0.48), (0.45, 0.34, 0.23)),
    "civic_coral": ((0.72, 0.46, 0.38), (0.43, 0.25, 0.21)),
    "industrial_slate": ((0.39, 0.44, 0.46), (0.20, 0.24, 0.26)),
    "urban_stone": ((0.55, 0.53, 0.48), (0.32, 0.30, 0.27)),
    "urban_warm": ((0.60, 0.48, 0.39), (0.35, 0.26, 0.22)),
    "urban_cool": ((0.43, 0.50, 0.54), (0.23, 0.29, 0.32)),
}

BUILDING_STYLE_GROUPS: dict[str, tuple[str, ...]] = {
    "highrise": ("glass_blue", "glass_teal", "glass_slate"),
    "residential": (
        "residential_sand",
        "residential_clay",
        "residential_sage",
        "residential_blue",
    ),
    "commercial": ("glass_blue", "glass_teal", "glass_slate", "urban_cool"),
    "civic": ("civic_cream", "civic_coral", "residential_sand"),
    "industrial": ("industrial_slate", "urban_stone", "urban_cool"),
    "urban": ("urban_stone", "urban_warm", "urban_cool", "residential_sage"),
}

ROAD_STYLES: dict[str, tuple[tuple[float, float, float], float]] = {
    "arterial": ((0.055, 0.065, 0.075), 0.095),
    "collector": ((0.075, 0.085, 0.095), 0.085),
    "local": ((0.105, 0.115, 0.120), 0.075),
    "pedestrian": ((0.26, 0.24, 0.21), 0.070),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("assets/external/shenzhen_houhai_2km"),
    )
    parser.add_argument("--center-lon", type=float, default=DEFAULT_CENTER[0])
    parser.add_argument("--center-lat", type=float, default=DEFAULT_CENTER[1])
    parser.add_argument("--size", type=float, default=DEFAULT_SIZE_METERS)
    parser.add_argument("--release", default=DEFAULT_RELEASE)
    parser.add_argument(
        "--refresh", action="store_true", help="Ignore the cached building GeoJSON."
    )
    return parser.parse_args()


def area_bbox(center_lon: float, center_lat: float, size: float) -> tuple[float, ...]:
    half = size * 0.5
    lat_delta = math.degrees(half / EARTH_RADIUS_METERS)
    lon_delta = math.degrees(half / (EARTH_RADIUS_METERS * math.cos(math.radians(center_lat))))
    return (
        center_lon - lon_delta,
        center_lat - lat_delta,
        center_lon + lon_delta,
        center_lat + lat_delta,
    )


def feature_url(
    index_path: Path,
    release: str,
    collection: str,
    bbox: tuple[float, ...],
) -> str:
    table = pq.read_table(index_path)
    west, south, east, north = bbox
    filtered = table.filter(
        (pc.field("collection") == collection)
        & (pc.field("type") == "Feature")
        & (pc.field("bbox", "xmin") < east)
        & (pc.field("bbox", "xmax") > west)
        & (pc.field("bbox", "ymin") < north)
        & (pc.field("bbox", "ymax") > south)
    )
    if filtered.num_rows != 1:
        raise RuntimeError(
            f"Expected one Overture {collection} partition for {bbox}, got {filtered.num_rows}."
        )
    row = filtered.select(["assets"]).to_pylist()[0]
    url = row["assets"]["azure"]["href"]
    if f"/{release}/" not in url:
        raise RuntimeError(f"Spatial index does not match release {release}: {url}")
    return str(url)


def intersects_row_group(
    parquet: pq.ParquetFile[Any], row_group: int, bbox: tuple[float, ...]
) -> bool:
    columns = {
        parquet.metadata.schema.column(index).path: index
        for index in range(parquet.metadata.num_columns)
    }
    metadata = parquet.metadata.row_group(row_group)

    def statistics(path: str) -> Any:
        return metadata.column(columns[path]).statistics

    west, south, east, north = bbox
    return not (
        statistics("bbox.xmin").min >= east
        or statistics("bbox.xmax").max <= west
        or statistics("bbox.ymin").min >= north
        or statistics("bbox.ymax").max <= south
    )


def download_features(
    url: str,
    bbox: tuple[float, ...],
    columns: list[str],
) -> list[dict[str, Any]]:
    with fsspec.open(url, block_size=4 << 20).open() as stream:
        parquet = pq.ParquetFile(stream)
        row_groups = [
            index
            for index in range(parquet.metadata.num_row_groups)
            if intersects_row_group(parquet, index, bbox)
        ]
        if not row_groups:
            return []
        table = parquet.read_row_groups(row_groups, columns=[*columns, "geometry", "bbox"])

    west, south, east, north = bbox
    table = table.filter(
        (pc.field("bbox", "xmin") < east)
        & (pc.field("bbox", "xmax") > west)
        & (pc.field("bbox", "ymin") < north)
        & (pc.field("bbox", "ymax") > south)
    )
    return table.to_pylist()


def local_transformer(center_lon: float, center_lat: float) -> Any:
    meters_per_lon = math.pi * EARTH_RADIUS_METERS * math.cos(math.radians(center_lat)) / 180.0
    meters_per_lat = math.pi * EARTH_RADIUS_METERS / 180.0

    def project(x: Any, y: Any, z: Any = None) -> tuple[Any, ...]:
        projected = ((x - center_lon) * meters_per_lon, (y - center_lat) * meters_per_lat)
        return (*projected, z) if z is not None else projected

    return project


def normalized_polygons(geometry: Any) -> list[Polygon]:
    if isinstance(geometry, Polygon):
        return [geometry]
    if isinstance(geometry, MultiPolygon):
        return list(geometry.geoms)
    return []


def normalized_lines(geometry: Any) -> list[LineString]:
    if isinstance(geometry, LineString):
        return [geometry]
    if isinstance(geometry, MultiLineString):
        return list(geometry.geoms)
    return []


def inferred_height(row: dict[str, Any], footprint: Any) -> tuple[float, str]:
    height = row.get("height")
    if height is not None and math.isfinite(height) and 2.0 <= height <= 600.0:
        return float(height), "authored_height"
    floors = row.get("num_floors")
    if floors is not None and math.isfinite(floors) and 1.0 <= floors <= 180.0:
        return float(floors) * 3.2, "num_floors"

    area = footprint.area
    if area >= 5_000.0:
        return 24.0, "footprint_heuristic"
    if area >= 1_500.0:
        return 18.0, "footprint_heuristic"
    if area >= 500.0:
        return 12.0, "footprint_heuristic"
    return 9.0, "footprint_heuristic"


def _empty_geometry() -> tuple[list[Any], list[int], list[int]]:
    return ([], [], [])


def _stable_choice(identity: Any, choices: tuple[str, ...]) -> str:
    digest = hashlib.sha256(str(identity).encode("utf-8")).digest()
    return choices[int.from_bytes(digest[:2], "big") % len(choices)]


def building_style(row: dict[str, Any], height: float) -> str:
    building_class = str(row.get("class") or "").lower()
    subtype = str(row.get("subtype") or "").lower()
    if height >= 55.0:
        group = "highrise"
    elif subtype == "residential" or building_class in {
        "apartments", "dormitory", "residential", "hotel"
    }:
        group = "residential"
    elif subtype == "commercial" or building_class in {"commercial", "office", "retail"}:
        group = "commercial"
    elif subtype in {"education", "medical", "civic", "religious"} or building_class in {
        "hospital", "kindergarten", "school", "university"
    }:
        group = "civic"
    elif subtype == "industrial" or building_class == "industrial":
        group = "industrial"
    else:
        group = "urban"
    return _stable_choice(row.get("id"), BUILDING_STYLE_GROUPS[group])


def road_style(row: dict[str, Any]) -> str:
    road_class = str(row.get("class") or "")
    if road_class in {"motorway", "trunk", "primary"}:
        return "arterial"
    if road_class in {"secondary", "tertiary"}:
        return "collector"
    if road_class in {"pedestrian", "footway", "path", "cycleway", "steps"}:
        return "pedestrian"
    return "local"


def append_building_mesh(
    polygon: Polygon,
    height: float,
    wall_geometry: tuple[list[Any], list[int], list[int]],
    roof_geometry: tuple[list[Any], list[int], list[int]],
) -> None:
    roof_points, roof_counts, roof_indices = roof_geometry
    for triangle in triangulate(polygon):
        if not polygon.covers(triangle):
            continue
        coordinates = list(triangle.exterior.coords)[:3]
        start = len(roof_points)
        roof_points.extend(
            Gf.Vec3f(float(x), float(y), float(height)) for x, y in coordinates
        )
        roof_counts.append(3)
        roof_indices.extend((start, start + 1, start + 2))

    wall_points, wall_counts, wall_indices = wall_geometry
    for ring in (polygon.exterior, *polygon.interiors):
        coordinates = list(ring.coords)
        for (x0, y0), (x1, y1) in zip(coordinates, coordinates[1:], strict=False):
            if x0 == x1 and y0 == y1:
                continue
            start = len(wall_points)
            wall_points.extend(
                (
                    Gf.Vec3f(float(x0), float(y0), 0.0),
                    Gf.Vec3f(float(x1), float(y1), 0.0),
                    Gf.Vec3f(float(x1), float(y1), float(height)),
                    Gf.Vec3f(float(x0), float(y0), float(height)),
                )
            )
            wall_counts.append(4)
            wall_indices.extend((start, start + 1, start + 2, start + 3))


def append_flat_polygon_mesh(
    polygon: Polygon,
    elevation: float,
    points: list[Gf.Vec3f],
    counts: list[int],
    indices: list[int],
) -> None:
    for triangle in triangulate(polygon):
        if not polygon.covers(triangle):
            continue
        coordinates = list(triangle.exterior.coords)[:3]
        start = len(points)
        points.extend(Gf.Vec3f(float(x), float(y), float(elevation)) for x, y in coordinates)
        counts.append(3)
        indices.extend((start, start + 1, start + 2))


def write_geojson(
    path: Path,
    rows: list[dict[str, Any]],
    clip_bounds: tuple[float, ...],
    properties: tuple[str, ...],
) -> None:
    clip = box(*clip_bounds)
    features = []
    for row in rows:
        geometry = from_wkb(row["geometry"]).intersection(clip)
        if geometry.is_empty:
            continue
        features.append(
            {
                "type": "Feature",
                "id": row["id"],
                "properties": {key: row.get(key) for key in properties},
                "geometry": mapping(geometry),
            }
        )
    path.write_text(
        json.dumps(
            {"type": "FeatureCollection", "features": features},
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        encoding="utf-8",
    )


def read_geojson(path: Path) -> list[dict[str, Any]]:
    collection = json.loads(path.read_text(encoding="utf-8"))
    return [
        {
            "id": feature.get("id"),
            **feature.get("properties", {}),
            "geometry": to_wkb(shape(feature["geometry"])),
        }
        for feature in collection["features"]
    ]


def osm_roads_and_water(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    elements = payload["elements"]
    nodes = {
        element["id"]: (element["lon"], element["lat"])
        for element in elements
        if element["type"] == "node"
    }
    ways = {element["id"]: element for element in elements if element["type"] == "way"}
    roads: list[dict[str, Any]] = []
    waters: list[dict[str, Any]] = []

    def coordinates(way: dict[str, Any]) -> list[tuple[float, float]]:
        return [nodes[node_id] for node_id in way.get("nodes", []) if node_id in nodes]

    for way in ways.values():
        tags = way.get("tags", {})
        coords = coordinates(way)
        if "highway" in tags and len(coords) >= 2:
            roads.append(
                {
                    "id": f"osm_way_{way['id']}",
                    "subtype": "road",
                    "class": tags["highway"],
                    "subclass": tags.get("service"),
                    "road_surface": tags.get("surface"),
                    "geometry": to_wkb(LineString(coords)),
                }
            )
        is_water = tags.get("natural") == "water" or "water" in tags or "waterway" in tags
        if not is_water or len(coords) < 2:
            continue
        geometry: Any
        if len(coords) >= 4 and coords[0] == coords[-1]:
            geometry = Polygon(coords)
        else:
            geometry = LineString(coords)
        waters.append(
            {
                "id": f"osm_way_{way['id']}",
                "subtype": tags.get("water", tags.get("waterway", "water")),
                "class": tags.get("natural", "water"),
                "is_salt": tags.get("salt") == "yes",
                "geometry": to_wkb(geometry),
            }
        )

    for relation in (item for item in elements if item["type"] == "relation"):
        tags = relation.get("tags", {})
        if tags.get("natural") != "water" and "water" not in tags:
            continue
        outer_lines = []
        for member in relation.get("members", []):
            if member.get("type") != "way" or member.get("role", "") not in {"", "outer"}:
                continue
            way = ways.get(member.get("ref"))
            coords = coordinates(way) if way else []
            if len(coords) >= 2:
                outer_lines.append(LineString(coords))
        polygons = list(polygonize(outer_lines))
        if not polygons:
            continue
        geometry = polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)
        waters.append(
            {
                "id": f"osm_relation_{relation['id']}",
                "subtype": tags.get("water", "water"),
                "class": tags.get("natural", "water"),
                "is_salt": tags.get("salt") == "yes",
                "geometry": to_wkb(geometry),
            }
        )
    return roads, waters


def load_or_download(
    path: Path,
    url: str,
    bbox: tuple[float, ...],
    columns: list[str],
    refresh: bool,
) -> list[dict[str, Any]]:
    if path.exists() and not refresh:
        return read_geojson(path)
    rows = download_features(url, bbox, columns)
    if not rows:
        raise RuntimeError(f"No Overture features found for {path.stem} inside {bbox}.")
    write_geojson(path, rows, bbox, tuple(columns))
    return rows


def road_width(row: dict[str, Any]) -> float:
    road_class = row.get("class")
    return {
        "motorway": 20.0,
        "primary": 14.0,
        "secondary": 11.0,
        "tertiary": 9.0,
        "residential": 7.0,
        "unclassified": 7.0,
        "service": 4.0,
        "pedestrian": 3.0,
        "footway": 2.0,
        "path": 2.0,
    }.get(str(road_class), 5.0)


def define_mesh(
    stage: Usd.Stage,
    path: str,
    geometry: tuple[list[Any], list[int], list[int]],
    color: tuple[float, float, float],
    *,
    collision: bool = False,
) -> None:
    points, counts, indices = geometry
    if not points:
        return
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
    mesh.CreatePointsAttr(points)
    mesh.CreateFaceVertexCountsAttr(counts)
    mesh.CreateFaceVertexIndicesAttr(indices)
    mesh.CreateDoubleSidedAttr(True)
    mesh.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    if collision:
        UsdPhysics.CollisionAPI.Apply(mesh.GetPrim()).CreateCollisionEnabledAttr(True)


def write_usd(
    path: Path,
    buildings: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    water_features: list[dict[str, Any]],
    center: tuple[float, float],
    clip_bounds: tuple[float, ...],
    size: float,
) -> dict[str, Any]:
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    root = UsdGeom.Xform.Define(stage, "/Houhai")
    stage.SetDefaultPrim(root.GetPrim())

    ground = UsdGeom.Cube.Define(stage, "/Houhai/Ground")
    ground.CreateSizeAttr(1.0)
    ground.AddScaleOp().Set(Gf.Vec3d(size, size, 0.2))
    ground.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, -0.1))
    ground.CreateDisplayColorAttr([Gf.Vec3f(0.16, 0.23, 0.20)])
    UsdPhysics.CollisionAPI.Apply(ground.GetPrim()).CreateCollisionEnabledAttr(True)

    project = local_transformer(*center)
    clip = box(*clip_bounds)
    wall_meshes: dict[tuple[int, int, str], tuple[list[Any], list[int], list[int]]] = {}
    roof_meshes: dict[tuple[int, int, str], tuple[list[Any], list[int], list[int]]] = {}
    style_counts: defaultdict[str, int] = defaultdict(int)
    height_sources: defaultdict[str, int] = defaultdict(int)
    building_count = 0

    for row in buildings:
        lonlat = from_wkb(row["geometry"]).intersection(clip)
        if lonlat.is_empty:
            continue
        footprint = transform(project, lonlat)
        height, height_source = inferred_height(row, footprint)
        height_sources[height_source] += 1
        building_count += 1
        centroid = footprint.centroid
        tile = (0 if centroid.x < 0.0 else 1, 0 if centroid.y < 0.0 else 1)
        style = building_style(row, height)
        style_counts[style] += 1
        walls = wall_meshes.setdefault((*tile, style), _empty_geometry())
        roofs = roof_meshes.setdefault((*tile, style), _empty_geometry())
        for polygon in normalized_polygons(footprint):
            if polygon.area < 1.0:
                continue
            append_building_mesh(polygon, height, walls, roofs)

    buildings_root = UsdGeom.Xform.Define(stage, "/Houhai/Buildings")
    buildings_root.GetPrim().SetCustomDataByKey("source", "Overture Maps Foundation")
    for (tile_x, tile_y, style), geometry in sorted(wall_meshes.items()):
        wall_color, _roof_color = BUILDING_STYLES[style]
        define_mesh(
            stage,
            f"/Houhai/Buildings/Tile_{tile_x}_{tile_y}/{style}_Walls",
            geometry,
            wall_color,
            collision=True,
        )
    for (tile_x, tile_y, style), geometry in sorted(roof_meshes.items()):
        _wall_color, roof_color = BUILDING_STYLES[style]
        define_mesh(
            stage,
            f"/Houhai/Buildings/Tile_{tile_x}_{tile_y}/{style}_Roofs",
            geometry,
            roof_color,
            collision=True,
        )

    local_clip = box(-size * 0.5, -size * 0.5, size * 0.5, size * 0.5)
    road_meshes: dict[str, tuple[list[Any], list[int], list[int]]] = {}
    centerline_geometry = _empty_geometry()
    road_style_counts: defaultdict[str, int] = defaultdict(int)
    road_count = 0
    for row in segments:
        if row.get("subtype") != "road":
            continue
        style = road_style(row)
        _color, elevation = ROAD_STYLES[style]
        road_style_counts[style] += 1
        road_geometry = road_meshes.setdefault(style, _empty_geometry())
        geometry = transform(project, from_wkb(row["geometry"]))
        for line in normalized_lines(geometry):
            surface = line.buffer(
                road_width(row) * 0.5, cap_style="flat", join_style="round"
            ).intersection(local_clip)
            for polygon in normalized_polygons(surface):
                append_flat_polygon_mesh(polygon, elevation, *road_geometry)
                road_count += 1
            if style in {"arterial", "collector"}:
                marking = line.buffer(
                    0.18 if style == "arterial" else 0.12,
                    cap_style="flat",
                    join_style="round",
                ).intersection(local_clip)
                for polygon in normalized_polygons(marking):
                    append_flat_polygon_mesh(polygon, elevation + 0.012, *centerline_geometry)
    roads_root = UsdGeom.Xform.Define(stage, "/Houhai/Roads")
    roads_root.GetPrim().SetCustomDataByKey("source", "OpenStreetMap")
    for style, geometry in sorted(road_meshes.items()):
        color, _elevation = ROAD_STYLES[style]
        define_mesh(stage, f"/Houhai/Roads/{style}", geometry, color)
    define_mesh(stage, "/Houhai/Roads/CenterLines", centerline_geometry, (0.92, 0.68, 0.20))

    water_geometry: tuple[list[Any], list[int], list[int]] = ([], [], [])
    water_count = 0
    for row in water_features:
        geometry = transform(project, from_wkb(row["geometry"])).intersection(local_clip)
        if isinstance(geometry, (LineString, MultiLineString)):
            geometry = geometry.buffer(2.0, cap_style="flat", join_style="round")
        for polygon in normalized_polygons(geometry):
            append_flat_polygon_mesh(polygon, 0.03, *water_geometry)
            water_count += 1
    define_mesh(stage, "/Houhai/Water", water_geometry, (0.035, 0.28, 0.48))

    root.GetPrim().SetCustomDataByKey("centerLongitude", center[0])
    root.GetPrim().SetCustomDataByKey("centerLatitude", center[1])
    root.GetPrim().SetCustomDataByKey("extentMeters", size)
    root.GetPrim().SetCustomDataByKey("buildingCount", building_count)
    stage.GetRootLayer().Save()
    return {
        "buildings": building_count,
        "road_surfaces": road_count,
        "water_surfaces": water_count,
        "building_style_counts": dict(sorted(style_counts.items())),
        "road_style_counts": dict(sorted(road_style_counts.items())),
        "visual_meshes": len(wall_meshes) + len(roof_meshes) + len(road_meshes) + 3,
        **height_sources,
    }


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    source_dir = output_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    index_path = source_dir / f"collections-{args.release}.parquet"
    if not index_path.exists():
        raise SystemExit(
            f"Missing {index_path}. Download it from "
            f"https://stac.overturemaps.org/{args.release}/collections.parquet"
        )

    bbox = area_bbox(args.center_lon, args.center_lat, args.size)
    building_source_url = feature_url(index_path, args.release, "building", bbox)
    buildings = load_or_download(
        source_dir / "buildings.geojson",
        building_source_url,
        bbox,
        ["height", "num_floors", "class", "subtype"],
        args.refresh,
    )
    osm_path = source_dir / "osm-roads-water.json"
    if not osm_path.exists():
        raise SystemExit(
            f"Missing {osm_path}. Run the Overpass query stored in "
            f"{source_dir / 'osm-overpass.ql'}."
        )
    segments_path = source_dir / "segments.geojson"
    water_path = source_dir / "water.geojson"
    if args.refresh or not segments_path.exists() or not water_path.exists():
        segments, water_features = osm_roads_and_water(osm_path)
        write_geojson(
            segments_path,
            segments,
            bbox,
            ("subtype", "class", "subclass", "road_surface"),
        )
        write_geojson(
            water_path,
            water_features,
            bbox,
            ("subtype", "class", "is_salt"),
        )
    else:
        segments = read_geojson(segments_path)
        water_features = read_geojson(water_path)
    stats = write_usd(
        output_dir / "houhai_2km.usdc",
        buildings,
        segments,
        water_features,
        (args.center_lon, args.center_lat),
        bbox,
        args.size,
    )
    manifest = {
        "name": "Shenzhen Houhai 2 km x 2 km",
        "center_wgs84": [args.center_lon, args.center_lat],
        "bbox_wgs84": list(bbox),
        "size_meters": args.size,
        "overture_release": args.release,
        "source_urls": {
            "buildings": building_source_url,
            "roads_and_water": "https://overpass.kumi.systems/api/interpreter",
        },
        "model": "houhai_2km.usdc",
        "statistics": stats,
        "height_policy": {
            "height": "use Overture height",
            "num_floors": "num_floors * 3.2 m",
            "missing": "9/12/18/24 m footprint-area heuristic",
        },
        "visual_style": {
            "name": "Houhai daylight",
            "building_palette_count": len(BUILDING_STYLES),
            "separate_roofs": True,
            "semantic_road_materials": True,
        },
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
