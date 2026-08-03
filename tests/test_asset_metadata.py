import json
from pathlib import Path

import pytest


def test_physics_playground_assets_are_declared() -> None:
    metadata = json.loads(Path("assets/metadata.json").read_text(encoding="utf-8"))
    assets = {asset["id"]: asset for asset in metadata["assets"]}

    assert {"primitive_ground", "primitive_table", "primitive_ramp"}.issubset(assets)
    assert assets["primitive_ground"]["default_properties"]["physics"]["dynamic"] is False
    assert assets["primitive_ground"]["primitive"] == "box"
    assert assets["primitive_ground"]["default_transform"]["position"] == [0.0, 0.0, -0.05]
    assert assets["primitive_table"]["default_properties"]["physics"]["dynamic"] is False
    assert assets["primitive_ramp"]["default_transform"]["rotation"] == [0.0, 0.45, 0.0]
    assert assets["primitive_sphere"]["default_properties"]["physics"]["dynamic"] is True
    assert assets["primitive_sphere"]["default_properties"]["physics"]["material"] == "rubber"
    assert assets["primitive_box"]["default_properties"]["physics"]["mass_mode"] == "density"


def test_complete_openusd_robot_arm_is_declared() -> None:
    metadata = json.loads(Path("assets/metadata.json").read_text(encoding="utf-8"))
    robots = {asset["id"]: asset for asset in metadata["assets"] if asset["type"] == "robot"}

    robot = robots["openusd_external_two_joint_arm_b6c7a81772"]
    assert robot["name"] == "Two-Joint Robot Arm"
    assert robot["source_format"] == "openusd"
    properties = robot["default_properties"]
    assert properties["articulation_ids"]
    assert (Path(properties["source"])).is_file()
    assert (Path(properties["robotics_cache"])).is_file()
    assert (Path(properties["import_report"])).is_file()


def test_high_quality_franka_robot_is_declared() -> None:
    metadata = json.loads(Path("assets/metadata.json").read_text(encoding="utf-8"))
    robots = {asset["id"]: asset for asset in metadata["assets"] if asset["type"] == "robot"}

    robot = robots["openusd_franka_quality_4b35c27245"]
    assert robot["name"] == "Franka Panda (High Quality)"
    properties = robot["default_properties"]
    robotics = json.loads(Path(properties["robotics_cache"]).read_text(encoding="utf-8"))
    articulation = robotics["articulations"][0]
    assert len(articulation["links"]) == 11
    assert len(articulation["joints"]) == 10
    assert articulation["visual_bundle"].endswith(".simbin")
    assert Path(articulation["visual_bundle"]).is_file()
    assert sum(
        bool(visual.get("visual_cache"))
        for link in articulation["links"]
        for visual in link["visual_geometries"]
    ) == 0
    assert sum(
        bool(collider.get("collision_mesh"))
        for link in articulation["links"]
        for collider in link["colliders"]
    ) == 12


def test_pegasus_iris_quadcopter_is_declared() -> None:
    metadata = json.loads(Path("assets/metadata.json").read_text(encoding="utf-8"))
    robots = {asset["id"]: asset for asset in metadata["assets"] if asset["type"] == "robot"}

    robot = robots["openusd_iris_09f8390b45"]
    assert robot["name"] == "Pegasus Iris Quadcopter"
    assert robot["license"] == "BSD-3-Clause"
    assert robot["source_url"].startswith("https://github.com/PegasusSimulator/")
    assert robot["default_transform"]["position"] == [0.0, 0.0, 0.07]

    properties = robot["default_properties"]
    for key in ("source", "robotics_cache", "import_report", "manifest"):
        assert Path(properties[key]).is_file()
    robotics = json.loads(Path(properties["robotics_cache"]).read_text(encoding="utf-8"))
    articulation = robotics["articulations"][0]
    assert len(articulation["links"]) == 5
    assert len(articulation["joints"]) == 4
    assert len(articulation["actuators"]) == 4
    assert {item["control_type"] for item in articulation["actuators"]} == {"velocity"}
    assert all(
        item["inertial"]["mass"] == pytest.approx(0.005)
        for item in articulation["links"]
        if item["name"].startswith("rotor")
    )
    propulsion = properties["propulsion"]
    assert propulsion["type"] == "quadrotor"
    assert len(propulsion["rotors"]) == 4
    assert articulation["visual_bundle"].endswith(".simbin")
    assert Path(articulation["visual_bundle"]).is_file()
