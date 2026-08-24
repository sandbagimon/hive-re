from __future__ import annotations

from pathlib import Path

import pytest

from examples.controllers.iris_swarm_delivery import (
    GRID_SPEC,
    MISSIONS,
    PRIOR_OBSTACLES,
    IrisSwarmDeliveryController,
)
from examples.drone_delivery_park.scene import create_park_swarm_scene
from beefoundrysim.controllers.iris_obstacle_navigation import plan_pilot_route
from beefoundrysim.controllers.realtime_navigation import rectangle_cells, route_is_clear
from beefoundrysim.services.controller_loader import ProjectControllerLoader
from beefoundrysim.services.project_service import validate_scene
from beefoundrysim.services.simulation_session import MuJoCoSimulationSession


def test_park_swarm_scene_has_unique_cloned_robotics_ids() -> None:
    scene = create_park_swarm_scene()
    validate_scene(scene)

    link_ids = [
        link.id
        for articulation in scene.robotics.articulations
        for link in articulation.links
    ]
    actuator_ids = [
        actuator.id
        for articulation in scene.robotics.articulations
        for actuator in articulation.actuators
    ]
    sensor_ids = [
        sensor.id
        for articulation in scene.robotics.articulations
        for sensor in articulation.sensors
    ]
    assert len(link_ids) == len(set(link_ids)) == 15
    assert len(actuator_ids) == len(set(actuator_ids)) == 12
    assert len(sensor_ids) == len(set(sensor_ids)) == 36

    park = next(actor for actor in scene.actors if actor.id == "actor_park_full")
    geometry = park.properties["geometry"]
    # The viewport streams the optimized park profile visually (the full
    # profile's 95 M vertices take minutes to load in the browser); physics
    # uses the invisible floor slab plus explicit structure colliders instead
    # of one convex-hull mesh.
    assert geometry["stream_scene_id"] == "brownstone-park"
    assert park.properties["primitive"] == "box"
    structures = [
        actor for actor in scene.actors if actor.id.startswith("actor_park_structure_")
    ]
    assert len(structures) == 3
    assert all(actor.properties["size"][2] > 1.6 for actor in structures)


def test_swarm_routes_avoid_prior_park_obstacles() -> None:
    clearance = 0.68
    blocked_cells = rectangle_cells(GRID_SPEC, PRIOR_OBSTACLES, clearance)
    for _, _, pickup, dropoff, _, _ in MISSIONS:
        route = plan_pilot_route(
            GRID_SPEC,
            pickup,
            dropoff,
            obstacles=PRIOR_OBSTACLES,
            clearance=clearance,
        )
        assert route[0] == pickup
        assert route[-1] == dropoff
        # Every leg is multi-waypoint: the prior park structures/kiosks force
        # a detour instead of the straight pickup -> dropoff line.
        assert len(route) >= 3
        assert not route_is_clear((pickup, dropoff), GRID_SPEC, blocked_cells)
        assert route_is_clear(route, GRID_SPEC, blocked_cells)


def test_park_swarm_delivery_completes_all_missions(tmp_path: Path) -> None:
    pytest.importorskip("mujoco")
    scene = create_park_swarm_scene()
    validate_scene(scene)

    loader = ProjectControllerLoader(Path.cwd())
    loaded = loader.load(Path("examples/controllers/iris_swarm_delivery.py"))
    session = MuJoCoSimulationSession(
        scene, tmp_path / "exports" / "scene.xml", asset_root=Path.cwd()
    )
    session.attach_controller(loaded.controller, name=loaded.name)

    state = session.step(steps=1)
    mission_deadline = 190.0
    while state.delivery_tasks and not all(
        task.status == "completed" for task in state.delivery_tasks
    ):
        if state.time >= mission_deadline or session.state().time >= mission_deadline:
            break
        remaining = int((mission_deadline - state.time) / 0.005)
        state = session.step(steps=min(600, max(1, remaining)))
        if state.controller.status == "fault":
            pytest.fail(f"Controller fault: {state.controller.message}")

    assert state.controller.status == "active"
    statuses = {task.task_id: task.status for task in state.delivery_tasks}
    assert statuses == {
        "task_delivery_alpha": "completed",
        "task_delivery_bravo": "completed",
        "task_delivery_charlie": "completed",
    }
    dropoffs = {task.id: task.dropoff_position for task in scene.delivery_tasks}
    for task in state.delivery_tasks:
        payload = next(
            item for item in state.actors if item.actor_id == task.payload_body_id
        )
        expected = dropoffs[task.task_id]
        assert payload.position == pytest.approx(
            [expected[0], expected[1], expected[2]],
            abs=0.35,
        )


def test_swarm_controller_rejects_missing_pilot_resources() -> None:
    from beefoundrysim.services.controller_runtime import ControllerObservation

    controller = IrisSwarmDeliveryController()
    observation = ControllerObservation(
        time=0.0,
        timestep=0.005,
        joints={},
        actuators={},
        bodies={},
        attachments={},
        rangefinders={},
    )
    with pytest.raises(ValueError, match="missing"):
        controller.reset(observation)
