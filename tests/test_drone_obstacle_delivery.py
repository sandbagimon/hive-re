from __future__ import annotations

from pathlib import Path

import pytest

from examples.controllers.iris_obstacle_delivery import (
    LOADED_CLEARANCE,
    MISSION_OBSTACLES,
    _segment_clear,
    plan_route,
)
from examples.drone_delivery_obstacles import create_obstacle_delivery_scene
from simlab.services.controller_loader import ProjectControllerLoader
from simlab.services.project_service import validate_scene
from simlab.services.simulation_session import MuJoCoSimulationSession


def test_a_star_route_avoids_inflated_delivery_obstacles() -> None:
    route = plan_route((0.0, 0.0), (4.0, 3.0))

    assert route[0] == (0.0, 0.0)
    assert route[-1] == (4.0, 3.0)
    assert len(route) >= 3
    assert not _segment_clear(
        route[0], route[-1], MISSION_OBSTACLES, LOADED_CLEARANCE
    )
    assert all(
        _segment_clear(start, end, MISSION_OBSTACLES, LOADED_CLEARANCE)
        for start, end in zip(route, route[1:], strict=False)
    )


def test_obstacle_delivery_uses_range_data_and_completes(tmp_path: Path) -> None:
    pytest.importorskip("mujoco")
    scene = create_obstacle_delivery_scene()
    validate_scene(scene)
    sensors = scene.robotics.articulations[0].sensors
    rangefinders = [sensor for sensor in sensors if sensor.sensor_type == "rangefinder"]
    assert len(rangefinders) == 12
    assert all(sensor.max_distance == 4.0 for sensor in rangefinders)
    assert any(actor.id == "actor_unmapped_pillar" for actor in scene.actors)
    assert scene.simulation_config["controller_deadline"] == 0.02
    assert scene.simulation_config["controller_reset_deadline"] == 0.2
    assert scene.simulation_config["navigation"]["route"] == [
        [x, y, 1.5] for x, y in plan_route((0.0, 0.0), (4.0, 3.0))
    ]

    loaded = ProjectControllerLoader(Path.cwd()).load(
        Path("examples/controllers/iris_obstacle_delivery.py")
    )
    session = MuJoCoSimulationSession(
        scene,
        tmp_path / "obstacle-delivery" / "scene.xml",
        asset_root=Path.cwd(),
    )
    attached = session.attach_controller(loaded.controller, name=loaded.name)

    assert len(
        [sample for sample in attached.sensors if sample.to_dict()["sensor_type"] == "rangefinder"]
    ) == 12
    assert len(session._controller_observation().rangefinders) == 12
    state = session.step(steps=21_000)

    controller = loaded.controller
    payload = next(item for item in state.actors if item.actor_id == "actor_003")
    assert state.controller.status == "active"
    assert state.delivery_tasks[0].status == "completed"
    assert controller.phase == "complete"
    assert controller.avoidance_events > 0
    assert controller.replan_count > 0
    assert state.navigation.route_revision > 1
    assert state.navigation.status == "complete"
    assert 0.35 < controller.minimum_clearance < 1.2
    assert payload.position == pytest.approx([4.0, 3.0, 0.16], abs=0.25)
