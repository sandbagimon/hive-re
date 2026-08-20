from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest

from simlab.services.local_scene_streaming import PARK_ENTRY, build_park_cache
from simlab.services.openusd.geometry_bundle import read_geometry_bundle_header
from simlab.web_server import create_app

pytest.importorskip("pxr")

PARK_FIXTURE = '''#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1
    upAxis = "Z"
)
def Xform "World"
{
    def Cube "Road"
    {
        double size = 4
        float3[] primvars:displayColor = [(0.2, 0.2, 0.2)]
        rel material:binding = </World/Looks/Road>
    }
    def Cube "Tree"
    {
        double size = 1
        double3 xformOp:translate = (8, 0, 1)
        uniform token[] xformOpOrder = ["xformOp:translate"]
        float3[] primvars:displayColor = [(0.1, 0.5, 0.1)]
        rel material:binding = </World/Looks/OpaqueMdl>
    }
    def Scope "Looks"
    {
        def Material "Road"
        {
            token outputs:surface.connect = </World/Looks/Road/P.outputs:surface>
            def Shader "P"
            {
                uniform token info:id = "UsdPreviewSurface"
                color3f inputs:diffuseColor = (0.25, 0.3, 0.35)
                color3f inputs:diffuseColor.connect = </World/Looks/Road/T.outputs:rgb>
                float inputs:roughness = 0.4
                float2 inputs:texture_scale = (2, 3)
                token outputs:surface
            }
            def Shader "T"
            {
                uniform token info:id = "UsdUVTexture"
                asset inputs:file = @road.png@
                float3 outputs:rgb
            }
        }
        def Material "OpaqueMdl"
        {
            def Shader "Shader"
            {
                uniform token info:id = "OmniPBR"
                bool inputs:enable_opacity = 0
                float inputs:opacity_constant = 0
            }
        }
    }
}
'''

TEXTURE_BYTES = b"fixture-original-park-texture"


def test_park_cache_builds_stream_chunks_and_box_collision_proxy(tmp_path: Path) -> None:
    source = tmp_path / "park.usda"
    source.write_text(PARK_FIXTURE, encoding="utf-8")
    (tmp_path / "road.png").write_bytes(TEXTURE_BYTES)
    cache = tmp_path / "cache"

    manifest = build_park_cache(source, cache, "fixture-fingerprint")

    persisted = json.loads((cache / "manifest.json").read_text(encoding="utf-8"))
    assert persisted == manifest
    assert manifest["format"] == "simlab-local-scene"
    assert manifest["statistics"]["chunk_count"] == 1
    assert manifest["statistics"]["collision_box_count"] == 1
    chunk = cache / f"{manifest['chunks'][0]['id']}.simbin"
    header = read_geometry_bundle_header(chunk.read_bytes())
    assert len(header["geometries"]) == 2
    assert all(item.startswith("mat_") for item in header["geometries"])
    assert manifest["statistics"]["material_count"] == 2
    assert manifest["statistics"]["texture_count"] == 1
    road_material = next(
        item for item in manifest["materials"].values()
        if item["name"] == "Road"
    )
    texture_id = road_material["textures"]["base_color"]
    assert road_material["texture_scale"] == [2.0, 3.0]
    opaque_material = next(
        item for item in manifest["materials"].values()
        if item["name"] == "OpaqueMdl"
    )
    assert opaque_material["opacity"] == 1.0
    texture = manifest["textures"][texture_id]
    assert (cache / "textures" / texture["filename"]).read_bytes() == TEXTURE_BYTES
    collision = (cache / "collision.obj").read_text(encoding="utf-8")
    assert collision.count("\nv ") == 8
    assert collision.count("\nf ") == 12


def test_material_texture_recovers_pack_relative_path(tmp_path: Path) -> None:
    pack_root = tmp_path / "pack"
    source = pack_root / "Scenes" / "Assets" / "park.usda"
    source.parent.mkdir(parents=True)
    source.write_text(
        PARK_FIXTURE.replace("@road.png@", "@./Assets/Textures/road.png@"),
        encoding="utf-8",
    )
    texture = pack_root / "Scenes" / "Assets" / "Textures" / "road.png"
    texture.parent.mkdir(parents=True)
    texture.write_bytes(TEXTURE_BYTES)

    manifest = build_park_cache(source, tmp_path / "cache", "fixture", pack_root)

    assert manifest["statistics"]["texture_count"] == 1
    assert manifest["statistics"]["missing_texture_count"] == 0


def test_local_scene_api_publishes_ready_asset_manifest_and_chunk(tmp_path: Path) -> None:
    pack_root = tmp_path / "pack"
    source = pack_root / PARK_ENTRY
    source.parent.mkdir(parents=True)
    source.write_text(PARK_FIXTURE, encoding="utf-8")
    (source.parent / "road.png").write_bytes(TEXTURE_BYTES)
    app = create_app(
        tmp_path / "data",
        seed_assets=tmp_path / "missing-assets",
        local_scene_root=pack_root,
    )
    try:
        async def exercise_api() -> None:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as client:
                created = await client.post("/api/v1/projects", json={"name": "Park"})
                project_id = created.json()["id"]
                payload: dict[str, object] = {}
                for _ in range(500):
                    response = await client.get(f"/api/v1/projects/{project_id}/assets")
                    payload = response.json()
                    local_scenes = payload["local_scenes"]
                    if local_scenes[0]["status"] == "ready":  # type: ignore[index]
                        break
                    await asyncio.sleep(0.02)
                assert local_scenes[0]["status"] == "ready"  # type: ignore[index]
                local_asset = next(
                    item for item in payload["assets"]  # type: ignore[union-attr]
                    if item["id"] == "openusd_brownstone_park_8gb"
                )
                geometry = local_asset["default_properties"]["geometry"]
                assert geometry["stream_scene_id"] == "brownstone-park"
                assert geometry["collision_mesh"].startswith("art_")

                manifest_response = await client.get(
                    f"/api/v1/projects/{project_id}"
                    "/local-scenes/brownstone-park/manifest"
                )
                manifest = manifest_response.json()
                chunk_id = manifest["chunks"][0]["id"]
                chunk = await client.get(
                    f"/api/v1/projects/{project_id}"
                    f"/local-scenes/brownstone-park/chunks/{chunk_id}"
                )
                assert chunk.status_code == 200
                assert chunk.content.startswith(b"SIMGEOM1")
                assert chunk.headers["cache-control"].endswith("immutable")
                texture_id = next(iter(manifest["textures"]))
                texture = await client.get(
                    f"/api/v1/projects/{project_id}"
                    f"/local-scenes/brownstone-park/textures/{texture_id}"
                )
                assert texture.status_code == 200
                assert texture.content == TEXTURE_BYTES
                assert texture.headers["cache-control"].endswith("immutable")

        asyncio.run(exercise_api())
    finally:
        app.state.resources.close()
