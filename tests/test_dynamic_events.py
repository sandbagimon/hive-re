from __future__ import annotations

import pytest

from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.models.transform import Transform
from simlab.services.dynamic_events import KinematicActorEventScheduler
from simlab.services.simulation_session import MuJoCoSimulationSession
from simlab.simulation.runtime import EngineCapability, required_engine_capabilities


def _dynamic_event_scene() -> Scene:
    return Scene(
        name="Kinematic street event",
        actors=[
            Actor(
                id="actor_crossing_vehicle",
                name="Crossing vehicle",
                type="object",
                asset_id="primitive_box",
                transform=Transform(position=[-1.0, 0.0, 0.5]),
                properties={
                    "primitive": "box",
                    "size": [0.4, 0.7, 0.5],
                    "physics": {"dynamic": True, "mass": 80.0},
                },
            )
        ],
        simulation_config={
            "timestep": 0.1,
            "duration": 2.0,
            "dynamic_events": [
                {
                    "id": "event_vehicle_crossing",
                    "type": "kinematic_actor",
                    "actor_id": "actor_crossing_vehicle",
                    "label": "Delivery van crossing route",
                    "activation_time": 0.25,
                    "completion_time": 1.0,
                    "interpolation": "linear",
                    "keyframes": [
                        {"time": 0.0, "position": [-1.0, 0.0, 0.5]},
                        {"time": 1.0, "position": [1.0, 0.0, 0.5]},
                        {"time": 2.0, "position": [1.0, 0.0, 0.5]},
                    ],
                }
            ],
        },
    )


def test_dynamic_event_scheduler_interpolates_pose_and_publishes_state() -> None:
    scheduler = KinematicActorEventScheduler.from_scene(_dynamic_event_scene())

    sample = scheduler.sample("actor_crossing_vehicle", 0.5)

    assert sample.position == pytest.approx((0.0, 0.0, 0.5))
    assert sample.linear_velocity == pytest.approx((2.0, 0.0, 0.0))
    assert scheduler.states(0.1)[0].status == "scheduled"
    assert scheduler.states(0.5)[0].status == "active"
    assert scheduler.states(1.5)[0].status == "completed"
    assert EngineCapability.KINEMATIC_ACTOR in required_engine_capabilities(
        _dynamic_event_scene()
    )


def test_mujoco_session_applies_dynamic_actor_timeline_and_resets(tmp_path) -> None:
    pytest.importorskip("mujoco")
    session = MuJoCoSimulationSession(_dynamic_event_scene(), tmp_path / "scene.xml")

    initial = session.state()
    moving = session.step(steps=5)
    reset = session.reset()

    assert initial.actors[0].position == pytest.approx([-1.0, 0.0, 0.5])
    assert moving.time == pytest.approx(0.5)
    assert moving.actors[0].position == pytest.approx([0.0, 0.0, 0.5])
    assert moving.dynamic_events[0].status == "active"
    assert moving.to_dict()["dynamic_events"][0]["id"] == "event_vehicle_crossing"
    assert reset.time == pytest.approx(0.0)
    assert reset.actors[0].position == pytest.approx([-1.0, 0.0, 0.5])


def test_dynamic_event_rejects_static_or_unknown_actors(tmp_path) -> None:
    pytest.importorskip("mujoco")
    scene = _dynamic_event_scene()
    scene.actors[0].properties["physics"]["dynamic"] = False
    with pytest.raises(ValueError, match="must be dynamic"):
        MuJoCoSimulationSession(scene, tmp_path / "static.xml")

    scene = _dynamic_event_scene()
    scene.simulation_config["dynamic_events"][0]["actor_id"] = "missing"
    with pytest.raises(ValueError, match="unknown actor"):
        KinematicActorEventScheduler.from_scene(scene)


def test_dynamic_event_rejects_duplicate_actor_timelines() -> None:
    scene = _dynamic_event_scene()
    duplicate = dict(scene.simulation_config["dynamic_events"][0])
    duplicate["id"] = "event_duplicate"
    scene.simulation_config["dynamic_events"].append(duplicate)

    with pytest.raises(ValueError, match="one timeline per actor"):
        KinematicActorEventScheduler.from_scene(scene)
