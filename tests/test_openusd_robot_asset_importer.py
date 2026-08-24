from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from beefoundrysim.models.actor import Actor
from beefoundrysim.models.scene import Scene
from beefoundrysim.services.openusd.geometry_bundle import read_geometry_bundle_header
from beefoundrysim.services.openusd_importer import OpenUsdImportError, import_openusd_asset
from beefoundrysim.services.project_service import load_scene, save_scene

pytest.importorskip("pxr")

ARM_FIXTURE = Path("tests/fixtures/openusd/robot_arm/external_two_joint_arm.usda")
MESH_COLLIDER_FIXTURE = Path("tests/fixtures/openusd/robot_arm/mesh_collider_arm.usda")


def test_formal_import_usd_path_registers_robot_asset_and_caches(tmp_path: Path) -> None:
    result = import_openusd_asset(ARM_FIXTURE, tmp_path)

    assert result.asset["type"] == "robot"
    assert result.robotics_model is not None
    assert result.report is not None
    assert result.report.has_errors is False
    properties = result.asset["default_properties"]
    assert set(properties) == {
        "source",
        "robotics_cache",
        "import_report",
        "manifest",
        "articulation_ids",
    }
    for key in ("source", "robotics_cache", "import_report", "manifest"):
        assert not Path(properties[key]).is_absolute()
        assert (tmp_path / properties[key]).is_file()

    robotics_data = json.loads(
        (tmp_path / properties["robotics_cache"]).read_text(encoding="utf-8")
    )
    assert robotics_data["version"] == "2.0"
    assert len(robotics_data["articulations"][0]["links"]) == 3
    assert robotics_data["articulations"][0]["source_uri"] == properties["source"]
    metadata = json.loads((tmp_path / "assets" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["assets"] == [result.asset]
    manifest = json.loads((tmp_path / properties["manifest"]).read_text(encoding="utf-8"))
    assert manifest["version"] == 4
    assert manifest["kinematics_contract_version"] == 2
    assert len(manifest["source_sha256"]) == 64


def test_robot_mesh_visual_gets_a_single_viewport_bundle(tmp_path: Path) -> None:
    source = tmp_path / "mesh-arm.usda"
    text = ARM_FIXTURE.read_text(encoding="utf-8")
    cube = '''        def Cube "Appearance"
        {
            color3f[] primvars:displayColor = [(0.18, 0.22, 0.28)]
            double size = 1
            float3 xformOp:scale = (0.4, 0.4, 0.2)
            double3 xformOp:translate = (0, 0, 0.1)
            uniform token[] xformOpOrder = ["xformOp:translate", "xformOp:scale"]
        }'''
    mesh = '''        def Mesh "Appearance"
        {
            color3f[] primvars:displayColor = [(0.18, 0.22, 0.28)]
            int[] faceVertexCounts = [3, 3, 3, 3]
            int[] faceVertexIndices = [0, 2, 1, 0, 1, 3, 1, 2, 3, 2, 0, 3]
            point3f[] points = [(-0.2, -0.2, 0), (0.2, -0.2, 0), (0, 0.2, 0), (0, 0, 0.4)]
            float3 xformOp:scale = (0.01, 0.01, 0.01)
            uniform token[] xformOpOrder = ["xformOp:scale"]
    }'''
    source.write_text(text.replace(cube, mesh, 1), encoding="utf-8")
    first = import_openusd_asset(source, tmp_path)
    assert first.cache_directory is not None
    legacy_cache = first.cache_directory / "visuals" / "old"
    legacy_cache.mkdir(parents=True)
    (legacy_cache / "visual.json").write_text("{}", encoding="utf-8")

    result = import_openusd_asset(source, tmp_path)
    assert result.robotics_model is not None
    visuals = [
        visual
        for articulation in result.robotics_model.articulations
        for link in articulation.links
        for visual in link.visual_geometries
        if visual.geometry_type == "mesh"
    ]
    assert visuals
    assert all(visual.visual_cache is None for visual in visuals)
    bundle_path = result.robotics_model.articulations[0].visual_bundle
    assert bundle_path is not None
    bundle = tmp_path / bundle_path
    assert bundle.suffix == ".simbin"
    header = read_geometry_bundle_header(bundle.read_bytes())
    assert set(header["geometries"]) == {visual.id for visual in visuals}
    bounds = header["geometries"][visuals[0].id]["bounds"]
    assert max(abs(float(value)) for value in bounds["min"] + bounds["max"]) <= 0.004
    assert not legacy_cache.exists()


def test_robot_mesh_collider_gets_a_mujoco_collision_cache(tmp_path: Path) -> None:
    result = import_openusd_asset(MESH_COLLIDER_FIXTURE, tmp_path)
    assert result.robotics_model is not None
    root_link = result.robotics_model.articulations[0].links[0]
    assert root_link.inertial is not None
    assert root_link.inertial.center_of_mass == [0.0, 0.0, 0.0]
    assert any(
        issue.code == "usd.center_of_mass_defaulted"
        for issue in result.report.issues
    )
    colliders = [
        collider
        for articulation in result.robotics_model.articulations
        for link in articulation.links
        for collider in link.colliders
        if collider.geometry_type == "mesh"
    ]

    assert len(colliders) == 1
    assert colliders[0].collision_mesh is not None
    collision_path = tmp_path / colliders[0].collision_mesh
    assert collision_path.name == "collision.obj"
    assert collision_path.is_file()
    assert collision_path.read_text(encoding="utf-8").startswith(
        "# Generated by BeeFoundrySim OpenUSD importer\n"
    )
    manifest = json.loads(
        (tmp_path / result.asset["default_properties"]["manifest"]).read_text(
            encoding="utf-8"
        )
    )
    assert manifest["collision_meshes"] == [colliders[0].collision_mesh]


def test_robot_scene_survives_project_directory_move(tmp_path: Path) -> None:
    project = tmp_path / "project"
    imported = import_openusd_asset(ARM_FIXTURE, project)
    assert imported.robotics_model is not None
    scene = Scene(
        name="External Arm",
        actors=[
            Actor(
                id="actor_001",
                name="External Arm",
                type="robot",
                asset_id=imported.asset["id"],
                properties=imported.asset["default_properties"],
            )
        ],
        robotics=imported.robotics_model,
    )
    save_scene(project / "scene.json", scene)
    moved = tmp_path / "moved-project"
    shutil.copytree(project, moved)

    restored = load_scene(moved / "scene.json")

    assert restored.robotics is not None
    assert len(restored.robotics.articulations[0].joints) == 2
    source = restored.robotics.articulations[0].source_uri
    assert source is not None and not Path(source).is_absolute()
    assert (moved / source).is_file()


def test_blocking_dependency_does_not_register_metadata(tmp_path: Path) -> None:
    source = tmp_path / "broken-arm.usda"
    text = ARM_FIXTURE.read_text(encoding="utf-8")
    text = text.replace(
        'def Xform "ExternalArm" (\n',
        'def Xform "ExternalArm" (\n    prepend references = @missing.usda@\n',
    )
    source.write_text(text, encoding="utf-8")
    project = tmp_path / "project"

    with pytest.raises(OpenUsdImportError) as exc_info:
        import_openusd_asset(source, project)

    assert exc_info.value.report is not None
    assert exc_info.value.report.has_errors
    assert not (project / "assets" / "metadata.json").exists()
