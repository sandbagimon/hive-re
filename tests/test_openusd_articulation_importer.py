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
    assert elbow.initial_position == pytest.approx(-0.4)

    shoulder_drive, elbow_drive = arm.actuators
    assert shoulder_drive.joint_id == shoulder.id
    assert shoulder_drive.control_type == "position"
    assert shoulder_drive.stiffness == pytest.approx(120.0)
    assert shoulder_drive.damping == pytest.approx(12.0)
    assert shoulder_drive.max_force == pytest.approx(80.0)
    assert elbow_drive.joint_id == elbow.id


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


def test_non_articulation_stage_returns_located_error() -> None:
    with pytest.raises(OpenUsdArticulationError) as exc_info:
        import_openusd_articulations("tests/fixtures/openusd/tetrahedron.usda")

    issue = next(issue for issue in exc_info.value.report.issues if issue.severity == "error")
    assert issue.code == "usd.articulation_missing"
    assert issue.field == "apiSchemas"
