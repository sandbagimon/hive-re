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
    actors = {actor.id: actor for actor in scene.actors}
    assert actors["actor_003"].name == "Insulated Takeout Bag"
    assert (
        actors["actor_003"].properties["visual_style"]
        == "insulated_delivery_bag"
    )
    assert actors["actor_obstacle_wall"].properties["visual_style"] == "known_obstacle"
    assert actors["actor_001"].properties["visual_style"] == "cinematic_wet_asphalt"
    assert (
        actors["actor_pickup_restaurant"].properties["visual_style"]
        == "restaurant_pickup"
    )
    assert (
        actors["actor_dropoff_residence"].properties["visual_style"]
        == "residential_dropoff"
    )
    assert (
        actors["actor_dynamic_delivery_van"].properties["visual_style"]
        == "dynamic_delivery_van"
    )
    assert actors["actor_dynamic_delivery_van"].properties["physics"]["dynamic"]
    assert (
        actors["actor_dynamic_courier"].properties["visual_style"]
        == "dynamic_courier"
    )
    barrier_visual = actors["actor_obstacle_wall"].properties["visual_model"]
    assert barrier_visual["license"] == "CC0-1.0"
    assert barrier_visual["source_url"].endswith("/concrete_road_barrier_02")
    assert barrier_visual["url"].endswith("concrete_road_barrier_02_2k.gltf")
    assert [item["size"] for item in barrier_visual["instances"]] == [
        [0.5, 1.6, 1.2],
    ]
    assert actors["actor_obstacle_wall"].transform.position[2] == 1.2
    assert actors["actor_obstacle_wall"].properties["size"] == [0.25, 0.8, 1.2]
    for actor_id in (
        "actor_obstacle_pillar_west",
        "actor_obstacle_pillar_east",
    ):
        barrel_visual = actors[actor_id].properties["visual_model"]
        assert barrel_visual["license"] == "CC0-1.0"
        assert barrel_visual["source_url"].endswith("/barrel_03")
        assert len(barrel_visual["instances"]) == 2
    assert scene.simulation_config["controller_deadline"] == 0.05
    assert scene.simulation_config["controller_reset_deadline"] == 0.2
    assert scene.simulation_config["visual_environment"]["preset"] == (
        "cinematic_blue_hour_delivery"
    )
    dynamic_events = scene.simulation_config["dynamic_events"]
    assert [event["actor_id"] for event in dynamic_events] == [
        "actor_dynamic_delivery_van",
        "actor_dynamic_courier",
    ]
    assert all(len(event["keyframes"]) >= 6 for event in dynamic_events)
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
    assert len(state.dynamic_events) == 2
    assert all(event.status == "completed" for event in state.dynamic_events)
    assert 0.35 < controller.minimum_clearance < 1.2
    assert payload.position == pytest.approx([4.0, 3.0, 0.16], abs=0.25)
