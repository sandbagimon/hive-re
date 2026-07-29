from __future__ import annotations

from pathlib import Path

import pytest

from simlab.services.openusd import OpenUsdStageError, load_openusd_stage

pxr = pytest.importorskip("pxr")
from pxr import UsdPhysics  # noqa: E402

ARM_FIXTURE = Path("tests/fixtures/openusd/robot_arm/external_two_joint_arm.usda")


def test_external_robot_arm_stage_loads_with_physics_articulation() -> None:
    result = load_openusd_stage(ARM_FIXTURE)

    assert result.report.has_errors is False
    assert result.report.unresolved_dependencies == []
    assert str(result.stage.GetDefaultPrim().GetPath()) == "/ExternalArm"

    prims = list(result.stage.Traverse())
    rigid_bodies = [
        prim for prim in prims if "PhysicsRigidBodyAPI" in prim.GetAppliedSchemas()
    ]
    revolute_joints = [prim for prim in prims if prim.IsA(UsdPhysics.RevoluteJoint)]
    collision_prims = [
        prim for prim in prims if "PhysicsCollisionAPI" in prim.GetAppliedSchemas()
    ]

    assert len(rigid_bodies) == 3
    assert len(revolute_joints) == 2
    assert len(collision_prims) == 3
    assert all(
        UsdPhysics.DriveAPI.Get(joint, "angular").GetPrim().IsValid()
        for joint in revolute_joints
    )


def test_import_report_serializes_stable_issue_contract(tmp_path: Path) -> None:
    broken = tmp_path / "broken.usda"
    broken.write_text(
        '''#usda 1.0
(
    defaultPrim = "Broken"
)
def Xform "Broken" (
    prepend references = @missing_link.usda@
)
{
}
''',
        encoding="utf-8",
    )

    result = load_openusd_stage(broken)
    payload = result.report.to_dict()

    assert payload["has_errors"] is True
    assert any(path.endswith("missing_link.usda") for path in payload["unresolved_dependencies"])
    missing = next(
        issue for issue in payload["issues"] if issue["code"] == "usd.missing_dependency"
    )
    assert missing["severity"] == "error"
    assert missing["prim_path"] == "/Broken"
    assert missing["field"] == "references"
    assert missing["fallback"] is None


def test_stage_loader_rejects_missing_source_with_report(tmp_path: Path) -> None:
    source = tmp_path / "missing.usda"

    with pytest.raises(OpenUsdStageError) as exc_info:
        load_openusd_stage(source)

    issue = exc_info.value.report.issues[0]
    assert issue.code == "usd.source_missing"
    assert issue.field == "source_path"


def test_stage_loader_rejects_unsupported_extension(tmp_path: Path) -> None:
    source = tmp_path / "robot.obj"
    source.write_text("", encoding="utf-8")

    with pytest.raises(OpenUsdStageError) as exc_info:
        load_openusd_stage(source)

    assert exc_info.value.report.issues[0].code == "usd.unsupported_extension"


def test_missing_material_texture_is_warning_but_missing_usd_is_blocking(
    tmp_path: Path,
) -> None:
    material_only = tmp_path / "material-only.usda"
    material_only.write_text(
        '''#usda 1.0
def Xform "Asset"
{
    def Mesh "Triangle"
    {
        int[] faceVertexCounts = [3]
        int[] faceVertexIndices = [0, 1, 2]
        point3f[] points = [(0, 0, 0), (1, 0, 0), (0, 1, 0)]
    }
}
def Shader "Texture"
{
    uniform token info:id = "UsdUVTexture"
    asset inputs:file = @missing.png@
}
''',
        encoding="utf-8",
    )
    missing_layer = tmp_path / "missing-layer.usda"
    missing_layer.write_text(
        '''#usda 1.0
(
    subLayers = [@missing.usda@]
)
''',
        encoding="utf-8",
    )

    material_result = load_openusd_stage(material_only)
    layer_result = load_openusd_stage(missing_layer)

    texture_issue = next(
        issue
        for issue in material_result.report.issues
        if issue.code == "usd.missing_dependency"
    )
    layer_issue = next(
        issue
        for issue in layer_result.report.issues
        if issue.code == "usd.missing_dependency"
    )
    assert texture_issue.severity == "warning"
    assert texture_issue.field == "inputs:file"
    assert texture_issue.fallback is not None
    assert material_result.report.has_errors is False
    assert layer_issue.severity == "error"
    assert layer_issue.field == "sublayers"
    assert layer_result.report.has_errors is True
