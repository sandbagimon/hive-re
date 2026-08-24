from __future__ import annotations

import asyncio
import json
import struct
from pathlib import Path

import httpx
import pytest

from beefoundrysim.services.local_scene_streaming import (
    FULL_PARK_SCENE_ID,
    PARK_ENTRY,
    _instance_lod_mesh,
    build_park_cache,
)
from beefoundrysim.services.openusd.geometry_bundle import read_geometry_bundle_header
from beefoundrysim.services.openusd.mesh_extractor import MeshData
from beefoundrysim.web_server import create_app

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
    def Cube "GrassBlade"
    {
        double size = 0.25
        float3[] primvars:displayColor = [(0.1, 0.7, 0.1)]
        rel material:binding = </World/Looks/OpaqueMdl>
    }
    def PointInstancer "GrassInstances"
    {
        rel prototypes = [</World/GrassBlade>]
        int[] protoIndices = [0, 0]
        point3f[] positions = [(0, 6, 0), (1, 6, 0)]
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
                asset info:mdl:sourceAsset = @materials/OpaqueMdl.mdl@
                token info:mdl:sourceAsset:subIdentifier = "OpaqueMdl"
                bool inputs:enable_opacity = 0
                float inputs:opacity_constant = 0
            }
        }
    }
}
'''

TEXTURE_BYTES = b"fixture-original-park-texture"

NESTED_INSTANCER_FIXTURE = '''#usda 1.0
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
    def Xform "ScatterAsset"
    {
        def Cube "Trunk"
        {
            double size = 0.4
            double3 xformOp:translate = (0, 0, 1)
            uniform token[] xformOpOrder = ["xformOp:translate"]
        }
        def PointInstancer "BranchInstancer"
        {
            double3 xformOp:translate = (0.5, 0.25, 1.5)
            uniform token[] xformOpOrder = ["xformOp:translate"]
            rel prototypes = [</World/ScatterAsset/BranchInstancer/Branch>]
            int[] protoIndices = [0, 0]
            point3f[] positions = [(0.1, 0, 0), (-0.1, 0, 0)]
            def Cube "Branch"
            {
                double size = 0.1
            }
        }
    }
    def PointInstancer "TreeScatter"
    {
        rel prototypes = [</World/ScatterAsset>]
        int[] protoIndices = [0, 0]
        point3f[] positions = [(4, 2, 0), (6, -1, 0)]
    }
}
'''

MDL_TEXTURE_BYTES = {
    "BaseColor.png": b"fixture-mdl-base-color",
    "Normal.png": b"fixture-mdl-normal",
    "ORM.png": b"fixture-mdl-orm",
    "Emissive.png": b"fixture-mdl-emissive",
}
MDL_FIXTURE = '''mdl 1.4;
import ::OmniPBR::OmniPBR;
export material OpaqueMdl(*) = ::OmniPBR::OmniPBR(
    diffuse_color_constant: color(0.2f, 0.2f, 0.2f),
    diffuse_texture: texture_2d("./OpaqueMdl/BaseColor.png" /* asset */),
    diffuse_tint: color(0.8f, 0.7f, 0.6f),
    reflection_roughness_constant: 0.45f,
    reflectionroughness_texture: texture_2d(),
    metallic_constant: 0.25f,
    metallic_texture: texture_2d(),
    enable_ORM_texture: true,
    ORM_texture: texture_2d("./OpaqueMdl/ORM.png"),
    enable_opacity: false,
    opacity_constant: 0.f,
    enable_emission: true,
    emissive_color: color(0.1f, 0.2f, 0.3f),
    emissive_mask_texture: texture_2d("./OpaqueMdl/Emissive.png"),
    emissive_intensity: 2.f,
    bump_factor: 0.8f,
    normalmap_texture: texture_2d("./OpaqueMdl/Normal.png"),
    texture_translate: float2(0.1f, 0.2f),
    texture_rotate: 0.25f,
    texture_scale: float2(4.f, 5.f));
'''


def _write_park_fixture(source: Path, content: str = PARK_FIXTURE) -> None:
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content, encoding="utf-8")
    (source.parent / "road.png").write_bytes(TEXTURE_BYTES)
    mdl_root = source.parent / "materials"
    texture_root = mdl_root / "OpaqueMdl"
    texture_root.mkdir(parents=True)
    (mdl_root / "OpaqueMdl.mdl").write_text(MDL_FIXTURE, encoding="utf-8")
    for filename, payload in MDL_TEXTURE_BYTES.items():
        (texture_root / filename).write_bytes(payload)


def test_park_cache_builds_stream_chunks_and_box_collision_proxy(tmp_path: Path) -> None:
    source = tmp_path / "park.usda"
    _write_park_fixture(source)
    cache = tmp_path / "cache"

    manifest = build_park_cache(source, cache, "fixture-fingerprint")

    persisted = json.loads((cache / "manifest.json").read_text(encoding="utf-8"))
    assert persisted == manifest
    assert manifest["format"] == "beefoundrysim-local-scene"
    assert manifest["version"] == 3
    assert manifest["statistics"]["chunk_count"] == 1
    assert manifest["statistics"]["collision_box_count"] == 1
    chunk = cache / f"{manifest['chunks'][0]['id']}.simbin"
    header = read_geometry_bundle_header(chunk.read_bytes())
    assert len(header["geometries"]) == 2
    assert all(item.startswith("mat_") for item in header["geometries"])
    assert manifest["statistics"]["material_count"] == 2
    assert manifest["statistics"]["texture_count"] == 5
    assert manifest["statistics"]["mdl_material_count"] == 1
    assert manifest["statistics"]["mdl_source_count"] == 1
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
    assert opaque_material["source_model"] == "MDL:OmniPBR"
    assert opaque_material["base_color"][:3] == pytest.approx([0.8, 0.7, 0.6])
    assert opaque_material["roughness"] == pytest.approx(0.45)
    assert opaque_material["metalness"] == pytest.approx(0.25)
    assert opaque_material["normal_scale"] == pytest.approx(0.8)
    assert opaque_material["texture_scale"] == [4.0, 5.0]
    assert opaque_material["texture_offset"] == pytest.approx([0.1, 0.2])
    assert opaque_material["texture_rotation"] == pytest.approx(0.25)
    assert opaque_material["emissive_color"] == pytest.approx([0.1, 0.2, 0.3])
    assert opaque_material["emissive_intensity"] == pytest.approx(2.0)
    assert set(opaque_material["textures"]) == {
        "base_color",
        "emissive",
        "normal",
        "orm",
    }
    texture = manifest["textures"][texture_id]
    assert (cache / "textures" / texture["filename"]).read_bytes() == TEXTURE_BYTES
    collision = (cache / "collision.obj").read_text(encoding="utf-8")
    assert collision.count("\nv ") == 8
    assert collision.count("\nf ") == 12


def test_material_texture_recovers_pack_relative_path(tmp_path: Path) -> None:
    pack_root = tmp_path / "pack"
    source = pack_root / "Scenes" / "Assets" / "park.usda"
    _write_park_fixture(
        source,
        PARK_FIXTURE.replace("@road.png@", "@./Assets/Textures/road.png@"),
    )
    texture = pack_root / "Scenes" / "Assets" / "Textures" / "road.png"
    texture.parent.mkdir(parents=True)
    texture.write_bytes(TEXTURE_BYTES)

    manifest = build_park_cache(source, tmp_path / "cache", "fixture", pack_root)

    assert manifest["statistics"]["texture_count"] == 5
    assert manifest["statistics"]["missing_texture_count"] == 0


def test_dense_instance_prototype_lod_retains_triangle_attributes() -> None:
    vertex_count = 300
    mesh = MeshData(
        positions=[float(index) for index in range(vertex_count * 3)],
        indices=list(range(vertex_count)),
        colors=[0.1, 0.2, 0.3, 1.0] * vertex_count,
        uvs=[0.25, 0.75] * vertex_count,
    )

    simplified = _instance_lod_mesh(mesh, 100_000)

    assert simplified.vertex_count == 24
    assert simplified.triangle_count == 8
    assert len(simplified.colors) == 24 * 4
    assert len(simplified.uvs) == 24 * 2


def test_full_park_cache_preserves_filtered_content_as_gpu_instances(
    tmp_path: Path,
) -> None:
    source = tmp_path / "park.usda"
    _write_park_fixture(source)
    cache = tmp_path / "full-cache"

    manifest = build_park_cache(
        source,
        cache,
        "full-fixture",
        scene_id=FULL_PARK_SCENE_ID,
        name="Architectural Brownstone Park (Full)",
        content_profile="full",
    )

    assert manifest["scene_id"] == FULL_PARK_SCENE_ID
    assert manifest["content_profile"] == "full"
    assert manifest["statistics"]["point_instance_count"] == 2
    assert manifest["statistics"]["instance_group_count"] == 1
    headers = [
        read_geometry_bundle_header((cache / f"{chunk['id']}.simbin").read_bytes())
        for chunk in manifest["chunks"]
    ]
    instanced = [
        entry
        for header in headers
        for entry in header["geometries"].values()
        if "instances" in entry
    ]
    assert len(instanced) == 1
    assert instanced[0]["instances"][1] == 32
    assert instanced[0]["material"].startswith("mat_")


def _decode_instanced_entries(
    cache: Path, manifest: dict
) -> list[tuple[dict, list[tuple[float, float, float]]]]:
    """Decode every instanced geometry entry with its instance translations."""
    entries: list[tuple[dict, list[tuple[float, float, float]]]] = []
    for chunk in manifest["chunks"]:
        content = (cache / f"{chunk['id']}.simbin").read_bytes()
        header = read_geometry_bundle_header(content)
        header_length = int.from_bytes(content[8:12], "little")
        payload_start = (12 + header_length + 3) & ~3
        for entry in header["geometries"].values():
            if "instances" not in entry:
                continue
            offset, count = entry["instances"]
            values = struct.unpack_from(f"<{count}f", content, payload_start + offset)
            entries.append(
                (
                    entry,
                    [
                        (
                            values[index * 16 + 12],
                            values[index * 16 + 13],
                            values[index * 16 + 14],
                        )
                        for index in range(count // 16)
                    ],
                )
            )
    return entries


def test_full_park_cache_composes_nested_point_instancers(tmp_path: Path) -> None:
    source = tmp_path / "nested-park.usda"
    source.write_text(NESTED_INSTANCER_FIXTURE, encoding="utf-8")
    cache = tmp_path / "nested-full-cache"

    manifest = build_park_cache(
        source,
        cache,
        "nested-fixture",
        scene_id=FULL_PARK_SCENE_ID,
        name="Nested Instancer Park",
        content_profile="full",
    )

    assert manifest["statistics"]["point_instance_count"] == 4  # 2 trees + 2 branches
    assert manifest["statistics"]["instance_group_count"] == 2  # trunk + branch
    entries = _decode_instanced_entries(cache, manifest)
    assert len(entries) == 2

    # Trunk copies land on both painted trees.
    trunk = next(
        translations
        for entry, translations in entries
        if len(translations) == 2
    )
    assert sorted(round(x, 3) for x, _y, _z in trunk) == [4.0, 6.0]

    # Branch copies compose outer scatter, nested instancer offset, and the
    # inner instance positions: 2 outer x 2 inner copies on the painted trees.
    branch = next(
        translations
        for entry, translations in entries
        if len(translations) == 4
    )
    assert sorted(round(x, 3) for x, _y, _z in branch) == [4.4, 4.6, 6.4, 6.6]
    assert sorted(round(y, 3) for _x, y, _z in branch) == [-0.75, -0.75, 2.25, 2.25]
    assert all(round(z, 3) == 1.5 for _x, _y, z in branch)
    # No copy may remain at the authored prototype location near the origin.
    assert all(abs(x) > 1.0 or abs(y) > 1.0 for x, y, _z in branch)


def test_optimized_park_cache_composes_nested_point_instancers(tmp_path: Path) -> None:
    source = tmp_path / "nested-park.usda"
    source.write_text(NESTED_INSTANCER_FIXTURE, encoding="utf-8")

    manifest = build_park_cache(source, tmp_path / "nested-cache", "nested-fixture")

    assert manifest["statistics"]["point_instance_count"] == 4
    # Baked copies: 2 trunks + 4 branches exist only at the painted positions.
    assert manifest["bounds"]["max"][0] < 6.7
    assert manifest["bounds"]["min"][0] > -2.1


def test_local_scene_api_publishes_ready_asset_manifest_and_chunk(tmp_path: Path) -> None:
    pack_root = tmp_path / "pack"
    source = pack_root / PARK_ENTRY
    _write_park_fixture(source)
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
                    if all(  # type: ignore[union-attr]
                        scene["status"] == "ready" for scene in local_scenes
                    ):
                        break
                    await asyncio.sleep(0.02)
                assert len(local_scenes) == 2  # type: ignore[arg-type]
                assert all(  # type: ignore[union-attr]
                    scene["status"] == "ready" for scene in local_scenes
                )
                local_asset = next(
                    item for item in payload["assets"]  # type: ignore[union-attr]
                    if item["id"] == "openusd_brownstone_park_8gb"
                )
                geometry = local_asset["default_properties"]["geometry"]
                assert geometry["stream_scene_id"] == "brownstone-park"
                assert geometry["collision_mesh"].startswith("art_")
                full_asset = next(
                    item for item in payload["assets"]  # type: ignore[union-attr]
                    if item["id"] == "openusd_brownstone_park_full"
                )
                assert (
                    full_asset["default_properties"]["geometry"]["stream_scene_id"]
                    == FULL_PARK_SCENE_ID
                )

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
