from __future__ import annotations

from pathlib import Path

import pytest

from examples.drone_delivery import create_delivery_scene
from simlab.services.controller_loader import ProjectControllerLoader
from simlab.services.project_service import validate_scene
from simlab.services.simulation_session import MuJoCoSimulationSession


def test_delivery_scene_is_valid_and_controller_completes_physical_transport(tmp_path) -> None:
    pytest.importorskip("mujoco")
    scene = create_delivery_scene()
    validate_scene(scene)
    payload = next(item for item in scene.actors if item.id == "actor_003")
    attachment = scene.attachments[0]
    assert payload.properties["visual_style"] == "shipping_package"
    assert payload.properties["physics"]["mass"] == pytest.approx(0.35)
    assert attachment.constraint_type == "weld"
    assert attachment.gripper is not None
    loaded = ProjectControllerLoader(Path.cwd()).load(
        Path("examples/controllers/iris_payload_delivery.py")
    )
    session = MuJoCoSimulationSession(
        scene,
        tmp_path / "delivery" / "scene.xml",
        asset_root=Path.cwd(),
    )

    session.attach_controller(loaded.controller, name=loaded.name)
    state = session.step(steps=15_000)

    payload_state = next(item for item in state.actors if item.actor_id == "actor_003")
    assert state.controller.status == "active"
    assert state.attachments[0].active is False
    assert state.delivery_tasks[0].status == "completed"
    assert payload_state.position == pytest.approx([4.0, 3.0, 0.16], abs=0.25)
