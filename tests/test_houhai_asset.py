import json
from pathlib import Path

from beefoundrysim.resources import ResourceManager


def test_houhai_asset_uses_semantic_daylight_palette() -> None:
    external_root = Path("assets/external/shenzhen_houhai_2km")
    source_manifest = json.loads((external_root / "manifest.json").read_text(encoding="utf-8"))
    metadata = json.loads(Path("assets/metadata.json").read_text(encoding="utf-8"))
    houhai_assets = [
        asset for asset in metadata["assets"] if asset["name"] == "Shenzhen Houhai 2km"
    ]

    assert len(houhai_assets) == 1
    assert houhai_assets[0]["id"] == "openusd_houhai_2km_b463d22fff"
    assert source_manifest["visual_style"] == {
        "name": "Houhai daylight",
        "building_palette_count": 13,
        "separate_roofs": True,
        "semantic_road_materials": True,
    }
    assert len(source_manifest["statistics"]["building_style_counts"]) == 13
    assert source_manifest["statistics"]["road_style_counts"] == {
        "arterial": 72,
        "collector": 120,
        "local": 417,
        "pedestrian": 339,
    }

    geometry = houhai_assets[0]["default_properties"]["geometry"]
    imported_root = Path(geometry["visual_cache"]).parent
    imported_manifest = json.loads(
        (imported_root / "manifest.json").read_text(encoding="utf-8")
    )
    visual = json.loads(Path(geometry["visual_cache"]).read_text(encoding="utf-8"))
    palette = {
        tuple(round(component, 3) for component in visual["colors"][index : index + 4])
        for index in range(0, len(visual["colors"]), 4)
    }

    assert imported_manifest["mesh_count"] == 103
    assert imported_manifest["dedicated_collision"] is True
    assert imported_manifest["collision_vertex_count"] == 112_445
    assert imported_manifest["collision_triangle_count"] == 49_797
    assert len(visual["positions"]) // 3 == 187_391
    assert len(visual["colors"]) // 4 == 187_391
    assert len(palette) == 33
    assert (0.92, 0.68, 0.2, 1.0) in palette
    assert (0.035, 0.28, 0.48, 1.0) in palette


def test_houhai_visual_cache_is_separate_from_collision_geometry() -> None:
    metadata = json.loads(Path("assets/metadata.json").read_text(encoding="utf-8"))
    asset = next(
        item for item in metadata["assets"] if item["name"] == "Shenzhen Houhai 2km"
    )
    geometry = asset["default_properties"]["geometry"]
    manifest = json.loads(
        (Path(geometry["visual_cache"]).parent / "manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["vertex_count"] > manifest["collision_vertex_count"]
    assert "/Houhai/Roads/CenterLines" in manifest["source_prim_paths"]
    assert "/Houhai/Roads/CenterLines" not in manifest["collision_prim_paths"]
    assert "/Houhai/Water" not in manifest["collision_prim_paths"]


def test_saved_houhai_scene_rebinds_to_styled_cache(tmp_path: Path) -> None:
    manager = ResourceManager(tmp_path, Path.cwd() / "assets")
    project = manager.create_project("Legacy Houhai")
    legacy_scene = {
        "version": "1.0",
        "name": "Legacy Houhai",
        "units": "meters",
        "actors": [
            {
                "id": "actor_houhai",
                "name": "Shenzhen Houhai 2km",
                "type": "object",
                "asset_id": "openusd_houhai_2km_b463d22fff",
                "transform": {
                    "position": [0.0, 0.0, 0.0],
                    "rotation": [0.0, 0.0, 0.0],
                    "scale": [1.0, 1.0, 1.0],
                },
                "properties": {
                    "geometry": {
                        "kind": "mesh",
                        "source_format": "openusd",
                        "source": (
                            "assets/imported/openusd_houhai_2km_b463d22fff/"
                            "source/houhai_2km.usdc"
                        ),
                        "visual_cache": (
                            "assets/imported/openusd_houhai_2km_b463d22fff/visual.json"
                        ),
                        "collision_mesh": (
                            "assets/imported/openusd_houhai_2km_b463d22fff/collision.obj"
                        ),
                    },
                    "physics": {"dynamic": False, "mass": 1.0, "friction": [0.8, 0.005, 0.0001]},
                },
            }
        ],
        "simulation_config": {"timestep": 0.01, "duration": 1.0},
    }

    try:
        updated = manager.update_scene(project.id, legacy_scene)
        hydrated = manager.hydrate(updated, updated.scene)
    finally:
        manager.close()

    geometry = hydrated["actors"][0]["properties"]["geometry"]
    assert "openusd_houhai_2km_7e5a5eb3ce" in geometry["visual_cache"]
    assert "openusd_houhai_2km_7e5a5eb3ce" in geometry["collision_mesh"]
