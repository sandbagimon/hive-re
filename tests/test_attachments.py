from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from beefoundrysim.models.actor import Actor
from beefoundrysim.models.attachment import Attachment, DeliveryTask, VacuumGripper
from beefoundrysim.models.scene import Scene
from beefoundrysim.models.transform import Transform
from beefoundrysim.services.controller_runtime import ControllerAction
from beefoundrysim.services.mjcf_exporter import scene_to_mjcf_xml
from beefoundrysim.services.project_service import ProjectValidationError, validate_scene
from beefoundrysim.services.simulation_session import MuJoCoSimulationSession


def _actor(
    actor_id: str,
    position: list[float],
    *,
    size: list[float],
    dynamic: bool,
    mass: float = 1.0,
) -> Actor:
    return Actor(
        id=actor_id,
        name=actor_id,
        type="object",
        asset_id="primitive_box",
        transform=Transform(position=position),
        properties={
            "primitive": "box",
            "size": size,
            "rgba": [0.5, 0.6, 0.7, 1.0],
            "physics": {
                "dynamic": dynamic,
                "mass_mode": "mass",
                "mass": mass,
                "friction": [1.0, 0.005, 0.0001],
            },
        },
    )


def _attachment_scene(*, carrier_x: float = 0.0, capture_duration: float = 0.0) -> Scene:
    attachment = Attachment(
        id="attachment_payload_hook",
        parent_body_id="actor_001",
        child_body_id="actor_002",
        parent_anchor=(0.0, 0.0, -0.1),
        child_anchor=(0.0, 0.0, 0.1),
        capture_distance=0.03,
        capture_speed=0.2,
        capture_duration=capture_duration,
        require_contact=True,
        contact_probe_radius=0.025,
    )
    return Scene(
        name="Attachment Test",
        actors=[
            _actor("actor_001", [carrier_x, 0.0, 0.39], size=[0.1, 0.1, 0.1], dynamic=True),
            _actor("actor_002", [0.0, 0.0, 0.2], size=[0.15, 0.15, 0.1], dynamic=True),
            _actor("actor_003", [0.0, 0.0, -0.05], size=[2.0, 2.0, 0.05], dynamic=False),
        ],
        attachments=[attachment],
        delivery_tasks=[
            DeliveryTask(
                id="task_delivery",
                attachment_id=attachment.id,
                payload_body_id="actor_002",
                pickup_position=(0.0, 0.0, 0.2),
                dropoff_position=(1.0, 0.0, 0.2),
            )
        ],
        simulation_config={"timestep": 0.002, "duration": 2.0, "wind": [0.2, 0.0, 0.0]},
    )


def test_attachment_and_delivery_task_round_trip_and_validate() -> None:
    scene = _attachment_scene()

    restored = Scene.from_dict(scene.to_dict())
    validate_scene(restored)

    assert restored.attachments[0].parent_body_id == "actor_001"
    assert restored.delivery_tasks[0].attachment_id == "attachment_payload_hook"
    invalid = _attachment_scene()
    invalid.attachments = [
        Attachment(
            id="attachment_payload_hook",
            parent_body_id="actor_missing",
            child_body_id="actor_002",
            parent_anchor=(0, 0, 0),
            child_anchor=(0, 0, 0),
        )
    ]
    with pytest.raises(ProjectValidationError, match="unknown or static parent body"):
        validate_scene(invalid)


def test_mjcf_exports_inactive_site_connect_constraint_contact_probe_and_wind() -> None:
    root = ET.fromstring(scene_to_mjcf_xml(_attachment_scene()))
    connect = root.find("./equality/connect")

    assert root.find("./option").attrib["wind"] == "0.2 0 0"  # type: ignore[union-attr]
    assert connect is not None
    assert connect.attrib == {
        "name": "attachment_payload_hook_connect",
        "site1": "attachment_payload_hook_parent_site",
        "site2": "attachment_payload_hook_child_site",
        "active": "false",
        "solref": "0.03 1",
        "solimp": "0.9 0.95 0.001 0.5 2",
    }
    assert root.find(".//site[@name='attachment_payload_hook_parent_site']") is not None
    assert root.find(".//site[@name='attachment_payload_hook_child_site']") is not None
    assert root.find(".//geom[@name='attachment_payload_hook_contact_probe']") is not None


def test_mjcf_exports_four_cup_vacuum_gripper_and_rigid_weld() -> None:
    scene = _attachment_scene()
    scene.attachments = [
        Attachment(
            id="attachment_payload_hook",
            parent_body_id="actor_001",
            child_body_id="actor_002",
            parent_anchor=(0.0, 0.0, -0.1),
            child_anchor=(0.0, 0.0, 0.1),
            constraint_type="weld",
            gripper=VacuumGripper(),
            capture_distance=0.03,
            capture_speed=0.2,
            capture_duration=0.0,
            require_contact=True,
            contact_probe_radius=0.018,
        )
    ]

    restored = Scene.from_dict(scene.to_dict())
    root = ET.fromstring(scene_to_mjcf_xml(restored))
    weld = root.find("./equality/weld")

    assert restored.attachments[0].constraint_type == "weld"
    assert restored.attachments[0].gripper == VacuumGripper()
    assert weld is not None
    assert weld.attrib["site1"] == "attachment_payload_hook_parent_site"
    assert weld.attrib["site2"] == "attachment_payload_hook_child_site"
    assert root.find("./equality/connect") is None
    assert len(root.findall(".//geom[@type='cylinder']")) == 5
    for index in range(4):
        assert (
            root.find(
                f".//geom[@name='attachment_payload_hook_vacuum_cup_{index}']"
            )
            is not None
        )
    assert root.find(".//geom[@name='attachment_payload_hook_gripper_plate']") is not None
    assert root.find(".//geom[@name='attachment_payload_hook_gripper_mount']") is not None


def test_controller_action_attachment_commands_are_typed_and_immutable() -> None:
    action = ControllerAction(attachment_commands={"attachment_payload_hook": True})

    assert action.attachment_commands == {"attachment_payload_hook": True}
    with pytest.raises(TypeError):
        action.attachment_commands["attachment_payload_hook"] = False  # type: ignore[index]
    with pytest.raises(ValueError, match="must be boolean"):
        ControllerAction(attachment_commands={"attachment_payload_hook": 1})  # type: ignore[dict-item]


def test_runtime_attachment_requires_proximity_and_contact(tmp_path) -> None:
    pytest.importorskip("mujoco")
    session = MuJoCoSimulationSession(
        _attachment_scene(carrier_x=0.5), tmp_path / "far" / "scene.xml"
    )

    state = session.set_attachment_commands({"attachment_payload_hook": True})

    assert state.attachments[0].status == "pending"
    assert state.attachments[0].active is False
    assert state.attachments[0].eligible is False
    assert state.attachments[0].contact is False


def test_runtime_attachment_connects_and_releases_without_teleporting(tmp_path) -> None:
    pytest.importorskip("mujoco")
    session = MuJoCoSimulationSession(_attachment_scene(), tmp_path / "near" / "scene.xml")
    before = session.state()

    attached = session.set_attachment_commands({"attachment_payload_hook": True})
    binding = session._attachment_bindings["attachment_payload_hook"]
    session.data.qvel[2] = 0.5
    carried = session.step(steps=20)
    session.set_attachment_commands({"attachment_payload_hook": False})
    released = session.step(steps=50)

    assert before.attachments[0].contact is True
    assert attached.attachments[0].active is True
    assert bool(session.data.eq_active[binding.equality_id]) is False
    assert carried.attachments[0].distance < 0.005
    assert released.attachments[0].status == "inactive"
    carrier = next(item for item in released.actors if item.actor_id == "actor_001")
    payload = next(item for item in released.actors if item.actor_id == "actor_002")
    assert carrier.position[2] - payload.position[2] > 0.2
