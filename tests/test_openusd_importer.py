from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.models.transform import Transform
from simlab.services.mjcf_exporter import scene_to_mjcf_xml
from simlab.services.openusd_importer import import_openusd_asset, load_visual_geometry
from simlab.services.physics_validation import run_physics_preflight
from simlab.services.simulation_session import MuJoCoSimulationSession

pytest.importorskip("pxr")
FIXTURE = Path("tests/fixtures/openusd/tetrahedron.usda")


def test_import_openusd_creates_project_asset_and_mesh_caches(tmp_path: Path) -> None:
    result = import_openusd_asset(FIXTURE, tmp_path)

    asset = result.asset
    assert result.report is not None
    assert result.report.has_errors is False
    properties = asset["default_properties"]
    geometry = properties["geometry"]
    physics = properties["physics"]
    assert asset["id"].startswith("openusd_tetrahedron_")
    assert asset["source_format"] == "openusd"
    assert physics["dynamic"] is True
    assert physics["mass_mode"] == "mass"
    assert physics["mass"] == pytest.approx(2.5)
    assert physics["friction"][0] == pytest.approx(0.42)
    assert properties["rgba"] == pytest.approx([0.2, 0.65, 0.85, 1.0])
    assert (tmp_path / geometry["source"]).is_file()
    assert (tmp_path / geometry["visual_cache"]).is_file()
    assert (tmp_path / geometry["collision_mesh"]).is_file()

    visual = load_visual_geometry(geometry["visual_cache"], tmp_path)
    assert len(visual["positions"]) == 12
    assert len(visual["indices"]) == 12
    assert max(visual["positions"]) == pytest.approx(1.0)

    metadata = json.loads((tmp_path / "assets" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["assets"][0]["id"] == asset["id"]


def test_imported_openusd_mesh_exports_and_compiles_with_mujoco(tmp_path: Path) -> None:
    mujoco = pytest.importorskip("mujoco")
    asset = import_openusd_asset(FIXTURE, tmp_path).asset
    actor = Actor(
        id="actor_001",
        name="USD Tetrahedron",
        type="object",
        asset_id=asset["id"],
        transform=Transform(position=[0.0, 0.0, 1.0]),
        properties=asset["default_properties"],
    )
    scene = Scene(name="OpenUSD Physics", actors=[actor])

    xml = scene_to_mjcf_xml(scene, asset_root=tmp_path)
    root = ET.fromstring(xml)
    mesh = root.find("./asset/mesh")
    geom = root.find(".//body[@name='actor_001']/geom")
    assert mesh is not None
    assert mesh.attrib["file"].endswith("collision.obj")
    assert geom is not None
    assert geom.attrib["type"] == "mesh"
    assert geom.attrib["mesh"] == "actor_001_mesh"
    assert geom.attrib["mass"] == "2.5"

    model = mujoco.MjModel.from_xml_string(xml)
    assert model.nbody == 2
    report = run_physics_preflight(scene, asset_root=tmp_path)
    assert report.is_valid

    session = MuJoCoSimulationSession(
        scene,
        tmp_path / "exports" / "scene.xml",
        asset_root=tmp_path,
    )
    initial = session.state()
    stepped = session.step(steps=5)
    assert stepped.time > initial.time
    assert stepped.actors[0].position[2] < initial.actors[0].position[2]


def test_import_expands_native_primitives_instances_material_and_collision(
    tmp_path: Path,
) -> None:
    source = tmp_path / "composed.usda"
    source.write_text(
        '''#usda 1.0
(
    defaultPrim = "World"
    metersPerUnit = 1
    upAxis = "Z"
)
def Xform "World"
{
    def Cube "ColoredCube"
    {
        double size = 2
        rel material:binding = </Looks/Blue>
    }
    def Scope "Prototypes"
    {
        def Sphere "Ball"
        {
            double radius = 0.25
        }
    }
    def PointInstancer "Balls"
    {
        rel prototypes = [</World/Prototypes/Ball>]
        int[] protoIndices = [0, 0]
        point3f[] positions = [(3, 0, 0), (4, 0, 0)]
    }
    def Cube "Collider" (
        prepend apiSchemas = ["PhysicsCollisionAPI"]
    )
    {
        double size = 1
        token visibility = "invisible"
    }
}
def Scope "Looks"
{
    def Material "Blue"
    {
        token outputs:surface.connect = </Looks/Blue/Shader.outputs:surface>
        def Shader "Shader"
        {
            uniform token info:id = "UsdPreviewSurface"
            color3f inputs:diffuseColor = (0.1, 0.2, 0.8)
            float inputs:opacity = 0.75
            token outputs:surface
        }
    }
}
''',
        encoding="utf-8",
    )

    result = import_openusd_asset(source, tmp_path / "project")
    properties = result.asset["default_properties"]
    visual = load_visual_geometry(properties["geometry"]["visual_cache"], tmp_path / "project")
    manifest = json.loads(
        (result.cache_directory / "manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["point_instance_count"] == 2
    assert manifest["native_primitive_count"] >= 4
    assert manifest["dedicated_collision"] is True
    assert manifest["collision_vertex_count"] == 8
    assert manifest["collision_triangle_count"] == 12
    assert len(visual["positions"]) > 8 * 3
    assert visual["colors"][:4] == pytest.approx([0.1, 0.2, 0.8, 0.75])
    assert properties["rgba"] == pytest.approx([0.1, 0.2, 0.8, 0.75])


def test_import_preserves_preview_surface_texture_and_vertex_uvs(tmp_path: Path) -> None:
    source = tmp_path / "textured.usda"
    texture = tmp_path / "albedo.png"
    texture.write_bytes(b"simlab-test-texture")
    source.write_text(
        '''#usda 1.0
(
    defaultPrim = "Asset"
)
def Xform "Asset"
{
    def Mesh "Triangle"
    {
        int[] faceVertexCounts = [3]
        int[] faceVertexIndices = [0, 1, 2]
        point3f[] points = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
        texCoord2f[] primvars:st = [(0, 0), (1, 0), (0, 1)] (
            interpolation = "vertex"
        )
        rel material:binding = </Looks/Textured>
    }
}
def Scope "Looks"
{
    def Material "Textured"
    {
        token outputs:surface.connect = </Looks/Textured/Preview.outputs:surface>
        def Shader "Preview"
        {
            uniform token info:id = "UsdPreviewSurface"
            color3f inputs:diffuseColor.connect = </Looks/Textured/Texture.outputs:rgb>
            token outputs:surface
        }
        def Shader "Texture"
        {
            uniform token info:id = "UsdUVTexture"
            asset inputs:file = @albedo.png@
            float3 outputs:rgb
        }
    }
}
''',
        encoding="utf-8",
    )
    project = tmp_path / "project"

    result = import_openusd_asset(source, project)
    geometry = result.asset["default_properties"]["geometry"]
    visual = load_visual_geometry(geometry["visual_cache"], project)

    assert visual["uvs"] == pytest.approx([0, 0, 1, 0, 0, 1])
    assert visual["base_color_texture"].endswith("source/albedo.png")
    assert (project / visual["base_color_texture"]).read_bytes() == texture.read_bytes()
