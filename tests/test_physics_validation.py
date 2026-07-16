import json
from pathlib import Path

from simlab.models.actor import Actor
from simlab.models.robotics import RoboticsModel
from simlab.models.scene import Scene
from simlab.services.physics_validation import run_physics_preflight


def _actor(
    actor_id: str = "actor_001",
    *,
    primitive: str = "box",
    physics: object | None = None,
) -> Actor:
    properties: dict[str, object] = {"primitive": primitive, "size": [0.5, 0.5, 0.5]}
    if physics is not None:
        properties["physics"] = physics
    return Actor(
        id=actor_id,
        name="Test Actor",
        type="object",
        asset_id=f"primitive_{primitive}",
        properties=properties,
    )


def test_preflight_loads_valid_generated_mjcf() -> None:
    loaded_xml: list[str] = []
    scene = Scene(
        actors=[
            _actor(
                physics={
                    "dynamic": True,
                    "mass": 1.5,
                    "friction": [0.8, 0.005, 0.0001],
                }
            )
        ]
    )

    report = run_physics_preflight(scene, model_loader=loaded_xml.append)

    assert report.is_valid
    assert report.mjcf_loaded
    assert loaded_xml == [report.mjcf_xml]


def test_preflight_reports_actor_physics_errors_before_mjcf_load() -> None:
    load_calls = 0

    def loader(_xml: str) -> object:
        nonlocal load_calls
        load_calls += 1
        return object()

    scene = Scene(
        actors=[
            _actor(
                "actor_mass",
                physics={
                    "dynamic": True,
                    "mass": 0,
                    "friction": [0.8, -0.1, 0.0001],
                },
            ),
            _actor("actor_plane", primitive="plane", physics={"dynamic": True, "mass": 1}),
        ]
    )

    report = run_physics_preflight(scene, model_loader=loader)
    codes = {issue.code for issue in report.errors}

    assert not report.is_valid
    assert {"INVALID_MASS", "NEGATIVE_FRICTION", "DYNAMIC_PLANE"} <= codes
    assert load_calls == 0
    assert "actor_mass" in report.detailed_text()


def test_preflight_reports_invalid_dynamic_and_friction_types() -> None:
    scene = Scene(
        actors=[
            _actor(
                physics={
                    "dynamic": "yes",
                    "mass": 1,
                    "friction": [0.8],
                }
            )
        ]
    )

    report = run_physics_preflight(scene, model_loader=lambda _xml: object())

    assert [issue.code for issue in report.errors] == ["INVALID_DYNAMIC", "INVALID_FRICTION"]


def test_preflight_warns_when_static_mass_is_ignored() -> None:
    scene = Scene(
        actors=[
            _actor(
                physics={
                    "dynamic": False,
                    "mass": 3.0,
                    "friction": [0.8, 0.005, 0.0001],
                }
            )
        ]
    )

    report = run_physics_preflight(scene, model_loader=lambda _xml: object())

    assert report.is_valid
    assert [issue.code for issue in report.warnings] == ["STATIC_MASS_IGNORED"]


def test_preflight_surfaces_mujoco_compile_error() -> None:
    def rejected(_xml: str) -> object:
        raise ValueError("duplicate name 'actor_001'")

    scene = Scene(actors=[_actor()])

    report = run_physics_preflight(scene, model_loader=rejected)

    assert not report.is_valid
    assert report.errors[0].code == "MJCF_LOAD_FAILED"
    assert "duplicate name" in report.errors[0].message


def test_preflight_accepts_robot_only_scene_without_no_actor_warning() -> None:
    robotics = RoboticsModel.from_dict(
        json.loads(
            Path("tests/fixtures/robotics/two_joint_arm.json").read_text(
                encoding="utf-8"
            )
        )
    )
    scene = Scene(
        actors=[
            Actor(
                id="actor_arm",
                name="Arm",
                type="robot",
                asset_id="external_arm",
                properties={"articulation_ids": ["arm_demo"]},
            )
        ],
        robotics=robotics,
    )

    report = run_physics_preflight(scene, model_loader=lambda _xml: object())

    assert report.is_valid
    assert "NO_PHYSICS_ACTORS" not in {issue.code for issue in report.issues}


def test_preflight_rejects_robot_actor_with_unknown_articulation() -> None:
    scene = Scene(
        actors=[
            Actor(
                id="actor_arm",
                name="Arm",
                type="robot",
                asset_id="external_arm",
                properties={"articulation_ids": ["arm_missing"]},
            )
        ]
    )

    report = run_physics_preflight(scene, model_loader=lambda _xml: object())

    assert not report.is_valid
    assert "UNKNOWN_ARTICULATION" in {issue.code for issue in report.errors}
