import copy
import json
from pathlib import Path

import pytest

from simlab.models.robotics import RoboticsModel
from simlab.models.scene import Scene
from simlab.services.project_service import validate_scene
from simlab.services.robotics_validation import (
    RoboticsValidationError,
    validate_robotics_model,
)

FIXTURE_PATH = Path("tests/fixtures/robotics/two_joint_arm.json")


def fixture_data() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def assert_validation_path(data: dict, expected_path: str) -> None:
    with pytest.raises(RoboticsValidationError) as exc_info:
        validate_robotics_model(data)
    assert any(issue.path == expected_path for issue in exc_info.value.issues)


def test_robotics_model_round_trip_preserves_two_joint_arm() -> None:
    data = fixture_data()

    restored = RoboticsModel.from_dict(data)

    assert restored.to_dict() == data
    articulation = restored.articulations[0]
    assert articulation.fixed_base is True
    assert [link.id for link in articulation.links] == [
        "link_base",
        "link_upper_arm",
        "link_forearm",
    ]
    assert [actuator.control_type for actuator in articulation.actuators] == [
        "position",
        "position",
    ]


def test_joint_state_sensor_round_trip_and_requires_joint_reference() -> None:
    data = fixture_data()
    sensor = data["articulations"][0]["sensors"][0]
    sensor["sensor_type"] = "joint_state"

    restored = RoboticsModel.from_dict(data)
    assert restored.articulations[0].sensors[0].sensor_type == "joint_state"

    sensor["joint_id"] = None
    with pytest.raises(RoboticsValidationError) as exc_info:
        RoboticsModel.from_dict(data)
    assert any(issue.code == "missing_sensor_joint" for issue in exc_info.value.issues)


def test_imu_sensor_round_trip_requires_link_and_local_transform() -> None:
    data = fixture_data()
    imu = {
        "id": "sensor_forearm_imu",
        "name": "Forearm IMU",
        "sensor_type": "imu",
        "link_id": "link_forearm",
        "joint_id": None,
        "update_rate_hz": 100.0,
        "local_transform": {
            "position": [0.0, 0.0, 0.25],
            "quaternion": [0.0, 0.0, 0.0, 1.0],
        },
        "source_prim_path": None,
    }
    data["articulations"][0]["sensors"].append(imu)

    restored = RoboticsModel.from_dict(data)

    assert restored.to_dict() == data
    restored_imu = restored.articulations[0].sensors[-1]
    assert restored_imu.local_transform is not None
    assert restored_imu.local_transform.position == [0.0, 0.0, 0.25]

    imu["link_id"] = None
    del imu["local_transform"]
    with pytest.raises(RoboticsValidationError) as exc_info:
        RoboticsModel.from_dict(data)
    assert {issue.code for issue in exc_info.value.issues}.issuperset(
        {"missing_sensor_link", "missing_sensor_transform"}
    )


def test_imu_sensor_rejects_dangling_link_and_invalid_quaternion() -> None:
    data = fixture_data()
    data["articulations"][0]["sensors"].append(
        {
            "id": "sensor_bad_imu",
            "name": "Bad IMU",
            "sensor_type": "imu",
            "link_id": "link_missing",
            "joint_id": None,
            "update_rate_hz": 50.0,
            "local_transform": {
                "position": [0.0, 0.0, 0.0],
                "quaternion": [0.0, 0.0, 0.0, 0.0],
            },
            "source_prim_path": None,
        }
    )

    with pytest.raises(RoboticsValidationError) as exc_info:
        RoboticsModel.from_dict(data)

    assert {issue.code for issue in exc_info.value.issues}.issuperset(
        {"dangling_sensor_link", "invalid_sensor_quaternion"}
    )


def test_legacy_scene_without_robotics_remains_compatible() -> None:
    legacy = {
        "version": "1.0",
        "name": "Legacy",
        "units": "meters",
        "actors": [],
        "simulation_config": {"timestep": 0.01, "duration": 1.0},
    }

    scene = Scene.from_dict(legacy)

    assert scene.robotics is None
    assert scene.trajectories == []
    assert scene.to_dict() == legacy


def test_scene_round_trip_preserves_robotics_model() -> None:
    model = RoboticsModel.from_dict(fixture_data())
    scene = Scene(name="Robot Arm", robotics=model)

    restored = Scene.from_dict(scene.to_dict())
    validate_scene(restored)

    assert restored.robotics == model


def test_schema_error_reports_field_path() -> None:
    data = fixture_data()
    del data["articulations"][0]["links"][0]["name"]

    assert_validation_path(data, "$.articulations[0].links[0]")


def test_duplicate_id_reports_second_field() -> None:
    data = fixture_data()
    data["articulations"][0]["joints"][1]["id"] = "joint_shoulder"

    assert_validation_path(data, "$.articulations[0].joints[1].id")


@pytest.mark.parametrize(
    ("field", "value", "expected_path"),
    [
        ("parent_link_id", "link_missing", "$.articulations[0].joints[0].parent_link_id"),
        ("child_link_id", "link_missing", "$.articulations[0].joints[0].child_link_id"),
    ],
)
def test_dangling_joint_link_reports_reference(
    field: str, value: str, expected_path: str
) -> None:
    data = fixture_data()
    data["articulations"][0]["joints"][0][field] = value

    assert_validation_path(data, expected_path)


def test_zero_joint_axis_is_rejected() -> None:
    data = fixture_data()
    data["articulations"][0]["joints"][0]["axis"] = [0.0, 0.0, 0.0]

    assert_validation_path(data, "$.articulations[0].joints[0].axis")


def test_reversed_joint_limits_are_rejected() -> None:
    data = fixture_data()
    limits = data["articulations"][0]["joints"][0]["limits"]
    limits["lower"], limits["upper"] = 1.0, -1.0

    assert_validation_path(data, "$.articulations[0].joints[0].limits")


def test_dangling_actuator_joint_is_rejected() -> None:
    data = fixture_data()
    data["articulations"][0]["actuators"][0]["joint_id"] = "joint_missing"

    assert_validation_path(data, "$.articulations[0].actuators[0].joint_id")


def test_scene_validation_rechecks_mutated_robotics_model() -> None:
    model = RoboticsModel.from_dict(fixture_data())
    invalid = copy.deepcopy(model)
    invalid.articulations[0].actuators[0].joint_id = "joint_missing"

    with pytest.raises(RoboticsValidationError):
        validate_scene(Scene(robotics=invalid))
