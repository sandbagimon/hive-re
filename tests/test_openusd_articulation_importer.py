from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from simlab.models.robotics import RoboticsModel
from simlab.services.openusd import (
    OpenUsdArticulationError,
    import_openusd_articulations,
)

pytest.importorskip("pxr")

ARM_FIXTURE = Path("tests/fixtures/openusd/robot_arm/external_two_joint_arm.usda")


def test_external_usd_arm_maps_to_robotics_model() -> None:
    result = import_openusd_articulations(ARM_FIXTURE)

    assert result.report.has_errors is False
    assert result.report.issues == []
    assert result.model.version == "2.0"
    assert len(result.model.articulations) == 1
    arm = result.model.articulations[0]
    assert arm.fixed_base is True
    assert arm.source_prim_path == "/ExternalArm"
    assert len(arm.links) == 3
    assert len(arm.joints) == 2
    assert len(arm.actuators) == 2
    assert arm.root_link_id == next(link.id for link in arm.links if link.name == "Pedestal")

    upper = next(link for link in arm.links if link.name == "FirstSegment")
    forearm = next(link for link in arm.links if link.name == "SecondSegment")
    assert upper.parent_link_id == arm.root_link_id
    assert forearm.parent_link_id == upper.id
    assert upper.inertial is not None
    assert upper.inertial.mass == pytest.approx(2.0)
    assert upper.inertial.center_of_mass == pytest.approx([0.0, 0.0, 0.3])
    assert upper.inertial.diagonal_inertia == pytest.approx([0.065, 0.065, 0.008])
    assert len(upper.visual_geometries) == 1
    assert len(upper.colliders) == 1
    assert upper.visual_geometries[0].source_prim_path.endswith("/Appearance")
    assert upper.colliders[0].source_prim_path.endswith("/ContactShape")
    assert upper.visual_geometries[0].size == pytest.approx([0.06, 0.06, 0.3])

    shoulder, elbow = arm.joints
    assert shoulder.axis == [0.0, 1.0, 0.0]
    assert shoulder.limits is not None
    assert shoulder.limits.lower == pytest.approx(-math.pi / 2)
    assert shoulder.limits.upper == pytest.approx(math.pi / 2)
    assert shoulder.parent_frame is not None
    assert shoulder.child_frame is not None
    assert shoulder.parent_frame.position == pytest.approx([0.0, 0.0, 0.2])
    assert elbow.initial_position == pytest.approx(0.0)

    shoulder_drive, elbow_drive = arm.actuators
    assert shoulder_drive.joint_id == shoulder.id
    assert shoulder_drive.control_type == "position"
    assert shoulder_drive.stiffness == pytest.approx(120.0)
    assert shoulder_drive.damping == pytest.approx(12.0)
    assert shoulder_drive.max_force == pytest.approx(80.0)
    assert elbow_drive.joint_id == elbow.id
    assert elbow_drive.target_position == pytest.approx(-0.4)


def test_imported_robotics_model_round_trips() -> None:
    model = import_openusd_articulations(ARM_FIXTURE).model

    restored = RoboticsModel.from_dict(json.loads(json.dumps(model.to_dict())))

    assert restored == model


def test_importer_uses_usd_relationships_instead_of_known_names(tmp_path: Path) -> None:
    renamed = tmp_path / "renamed-manipulator.usda"
    text = ARM_FIXTURE.read_text(encoding="utf-8")
    for old, new in (
        ("ExternalArm", "ImportedManipulator"),
        ("Pedestal", "RootPiece"),
        ("FirstSegment", "LinkOne"),
        ("SecondSegment", "LinkTwo"),
        ("Constraints", "Connections"),
        ("AxisA", "JointOne"),
        ("AxisB", "JointTwo"),
        ("Appearance", "RenderPart"),
        ("ContactShape", "CollisionPart"),
    ):
        text = text.replace(old, new)
    renamed.write_text(text, encoding="utf-8")

    arm = import_openusd_articulations(renamed).model.articulations[0]

    assert arm.name == "ImportedManipulator"
    assert {link.name for link in arm.links} == {"RootPiece", "LinkOne", "LinkTwo"}
    assert {joint.name for joint in arm.joints} == {"JointOne", "JointTwo"}
    assert len(arm.actuators) == 2
    assert all(joint.parent_link_id != joint.child_link_id for joint in arm.joints)


def test_articulation_converts_stage_units_and_y_up_basis(tmp_path: Path) -> None:
    converted = tmp_path / "centimeter-y-up-arm.usda"
    text = ARM_FIXTURE.read_text(encoding="utf-8")
    text = text.replace("metersPerUnit = 1", "metersPerUnit = 0.01")
    text = text.replace('upAxis = "Z"', 'upAxis = "Y"')
    converted.write_text(text, encoding="utf-8")

    arm = import_openusd_articulations(converted).model.articulations[0]
    upper = next(link for link in arm.links if link.name == "FirstSegment")

    assert upper.transform.position == pytest.approx([0.0, -0.002, 0.0])
    assert upper.visual_geometries[0].size == pytest.approx([0.0006, 0.0006, 0.003])
    assert upper.inertial is not None
    assert upper.inertial.center_of_mass == pytest.approx([0.0, -0.003, 0.0])
    assert upper.inertial.diagonal_inertia == pytest.approx(
        [0.065e-4, 0.008e-4, 0.065e-4]
    )


def test_prismatic_joint_uses_linear_units_and_drive(tmp_path: Path) -> None:
    source = tmp_path / "prismatic-arm.usda"
    text = ARM_FIXTURE.read_text(encoding="utf-8")
    prefix, axis_b = text.split('def PhysicsRevoluteJoint "AxisB"', 1)
    axis_b = axis_b.replace("PhysicsDriveAPI:angular", "PhysicsDriveAPI:linear")
    axis_b = axis_b.replace("drive:angular:", "drive:linear:")
    axis_b = axis_b.replace("targetPosition = -22.918312", "targetPosition = 0.025")
    axis_b = axis_b.replace("lowerLimit = -126.05071", "lowerLimit = -0.02")
    axis_b = axis_b.replace("upperLimit = 11.459156", "upperLimit = 0.08")
    source.write_text(prefix + 'def PhysicsPrismaticJoint "AxisB"' + axis_b, encoding="utf-8")

    arm = import_openusd_articulations(source).model.articulations[0]
    joint = next(item for item in arm.joints if item.name == "AxisB")
    actuator = next(item for item in arm.actuators if item.joint_id == joint.id)

    assert joint.type == "prismatic"
    assert joint.limits is not None
    assert joint.limits.lower == pytest.approx(-0.02)
    assert joint.limits.upper == pytest.approx(0.08)
    assert joint.initial_position == pytest.approx(0.0)
    assert actuator.target_position == pytest.approx(0.025)
    assert actuator.source_prim_path.endswith(".drive:linear")


def test_joint_state_is_distinct_from_drive_target(tmp_path: Path) -> None:
    source = tmp_path / "stateful-arm.usda"
    text = ARM_FIXTURE.read_text(encoding="utf-8").replace(
        "float drive:angular:physics:targetPosition = -22.918312",
        "float drive:angular:physics:targetPosition = -22.918312\n"
        "            float state:angular:physics:position = -10\n"
        "            float state:angular:physics:velocity = 5",
    )
    source.write_text(text, encoding="utf-8")

    arm = import_openusd_articulations(source).model.articulations[0]
    joint = next(item for item in arm.joints if item.name == "AxisB")
    actuator = next(item for item in arm.actuators if item.joint_id == joint.id)

    assert joint.initial_position == pytest.approx(math.radians(-10))
    assert joint.initial_velocity == pytest.approx(math.radians(5))
    assert actuator.target_position == pytest.approx(-0.4)


def test_dual_joint_frames_define_zero_pose_and_joint_frame_axis(
    tmp_path: Path,
) -> None:
    source = tmp_path / "rotated-child-frame.usda"
    text = ARM_FIXTURE.read_text(encoding="utf-8").replace(
        "point3f physics:localPos1 = (0, 0, 0)",
        "point3f physics:localPos1 = (0.1, 0, 0)\n"
        "            quatf physics:localRot1 = (0.70710678, 0.70710678, 0, 0)",
        1,
    )
    source.write_text(text, encoding="utf-8")

    arm = import_openusd_articulations(source).model.articulations[0]
    shoulder = next(item for item in arm.joints if item.name == "AxisA")
    upper = next(item for item in arm.links if item.id == shoulder.child_link_id)

    assert shoulder.axis == pytest.approx([0.0, 1.0, 0.0])
    assert shoulder.child_frame is not None
    assert shoulder.child_frame.position == pytest.approx([0.1, 0.0, 0.0])
    assert upper.transform.position == pytest.approx([-0.1, 0.0, 0.2])


def test_non_articulation_stage_returns_located_error() -> None:
    with pytest.raises(OpenUsdArticulationError) as exc_info:
        import_openusd_articulations("tests/fixtures/openusd/tetrahedron.usda")

    issue = next(issue for issue in exc_info.value.report.issues if issue.severity == "error")
    assert issue.code == "usd.articulation_missing"
    assert issue.field == "apiSchemas"
