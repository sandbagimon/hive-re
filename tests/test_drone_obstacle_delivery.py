from __future__ import annotations

import math
from pathlib import Path

import pytest

from examples.controllers.iris_obstacle_delivery import (
    LOADED_CLEARANCE,
    MISSION_OBSTACLES,
    _segment_clear,
    plan_route,
)
from examples.drone_delivery_obstacles import create_obstacle_delivery_scene
from beefoundrysim.services.controller_loader import ProjectControllerLoader
from beefoundrysim.services.project_service import validate_scene
from beefoundrysim.services.simulation_session import MuJoCoSimulationSession


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
    forklift = actors["actor_dynamic_forklift"]
    assert forklift.name == "Unmapped Crossing Forklift"
    assert forklift.properties["visual_style"] == "dynamic_forklift"
    assert forklift.properties["physics"]["dynamic"]
    assert forklift.properties["physics"]["mass"] == 2_600.0
    assert forklift.properties["size"] == [0.9, 0.5, 1.0]
    assert forklift.transform.position == [1.15, -1.2, 1.0]
    assert forklift.transform.rotation == pytest.approx([0.0, 0.0, math.pi / 2.0])
    forklift_visual = forklift.properties["visual_model"]
    assert forklift_visual["license"] == "CC-BY-4.0"
    assert forklift_visual["author"] == "louis-muir"
    assert forklift_visual["source_url"].endswith(
        "/forklift-truck-060f3f8bc7de4e6ca2f348d414702e9d"
    )
    assert forklift_visual["url"].endswith("/sketchfab/forklift/forklift.glb")
    forklift_model = Path("frontend/public") / forklift_visual["url"].removeprefix(
        "./"
    )
    assert forklift_model.is_file()
    assert (
        actors["actor_dynamic_courier"].properties["visual_style"]
        == "dynamic_courier"
    )
    courier_visual = actors["actor_dynamic_courier"].properties["visual_model"]
    assert courier_visual["license"] == "CC0-1.0"
    assert courier_visual["url"].endswith("/courier/human-jay.glb")
    courier_model = Path("frontend/public") / courier_visual["url"].removeprefix("./")
    assert courier_model.is_file()
    courier_animation = courier_visual["animation"]
    assert courier_animation["locomotion"] == "walking"
    assert courier_animation["clips"] == {
        "idle": "Idle_A",
        "walking": "Walk",
        "cycling": "Driving",
    }
    animation_model = Path("frontend/public") / courier_animation[
        "clip_url"
    ].removeprefix("./")
    assert animation_model.is_file()
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
    assert scene.simulation_config["timestep"] == 0.005
    assert scene.simulation_config["controller_update_rate_hz"] == 100.0
    assert scene.simulation_config["visual_environment"]["preset"] == (
        "cinematic_blue_hour_delivery"
    )
    dynamic_events = scene.simulation_config["dynamic_events"]
    assert [event["actor_id"] for event in dynamic_events] == [
        "actor_dynamic_forklift",
        "actor_dynamic_courier",
    ]
    assert dynamic_events[0]["keyframes"][2]["position"] == [1.15, 1.45, 1.0]
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
    state = session.step(steps=9_600)

    controller = loaded.controller
    payload = next(item for item in state.actors if item.actor_id == "actor_003")
    assert state.controller.status == "active"
    assert state.controller.step_count == 4_800
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
