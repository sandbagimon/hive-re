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
    }
    def Cube "Tree"
    {
        double size = 1
        double3 xformOp:translate = (8, 0, 1)
        uniform token[] xformOpOrder = ["xformOp:translate"]
        float3[] primvars:displayColor = [(0.1, 0.5, 0.1)]
    }
}
'''


def test_park_cache_builds_stream_chunks_and_box_collision_proxy(tmp_path: Path) -> None:
    source = tmp_path / "park.usda"
    source.write_text(PARK_FIXTURE, encoding="utf-8")
    cache = tmp_path / "cache"

    manifest = build_park_cache(source, cache, "fixture-fingerprint")

    persisted = json.loads((cache / "manifest.json").read_text(encoding="utf-8"))
    assert persisted == manifest
    assert manifest["format"] == "simlab-local-scene"
    assert manifest["statistics"]["chunk_count"] == 1
    assert manifest["statistics"]["collision_box_count"] == 1
    chunk = cache / f"{manifest['chunks'][0]['id']}.simbin"
    header = read_geometry_bundle_header(chunk.read_bytes())
    assert set(header["geometries"]) == {"scene"}
    collision = (cache / "collision.obj").read_text(encoding="utf-8")
    assert collision.count("\nv ") == 8
    assert collision.count("\nf ") == 12


def test_local_scene_api_publishes_ready_asset_manifest_and_chunk(tmp_path: Path) -> None:
    pack_root = tmp_path / "pack"
    source = pack_root / PARK_ENTRY
    source.parent.mkdir(parents=True)
    source.write_text(PARK_FIXTURE, encoding="utf-8")
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

        asyncio.run(exercise_api())
    finally:
        app.state.resources.close()
