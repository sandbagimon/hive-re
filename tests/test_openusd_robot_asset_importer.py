from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.services.openusd_importer import OpenUsdImportError, import_openusd_asset
from simlab.services.project_service import load_scene, save_scene

pytest.importorskip("pxr")

ARM_FIXTURE = Path("tests/fixtures/openusd/robot_arm/external_two_joint_arm.usda")


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
    assert len(robotics_data["articulations"][0]["links"]) == 3
    assert robotics_data["articulations"][0]["source_uri"] == properties["source"]
    metadata = json.loads((tmp_path / "assets" / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["assets"] == [result.asset]


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
