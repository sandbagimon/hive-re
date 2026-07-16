from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.models.trajectory import (
    JointTrajectory,
    JointTrajectoryKeyframe,
    SceneTrajectory,
)
from simlab.models.transform import Transform
from simlab.services.scene_service import SceneService


def test_scene_serializes_round_trip() -> None:
    scene = Scene(name="Test Scene")
    scene.actors.append(
        Actor(
            id="actor_001",
            name="Box",
            type="object",
            asset_id="primitive_box",
            transform=Transform(position=[1, 2, 3]),
            properties={"primitive": "box", "mass": 2.0},
        )
    )

    restored = Scene.from_dict(scene.to_dict())

    assert restored.name == "Test Scene"
    assert restored.actors[0].id == "actor_001"
    assert restored.actors[0].transform.position == [1.0, 2.0, 3.0]


def test_scene_trajectory_library_serializes_round_trip() -> None:
    scene = Scene(
        trajectories=[
            SceneTrajectory(
                id="trajectory_pick",
                actor_id="actor_001",
                trajectory=JointTrajectory(
                    name="Pick",
                    keyframes=[
                        JointTrajectoryKeyframe(0, {"shoulder": 0}),
                        JointTrajectoryKeyframe(1, {"shoulder": 0.5}),
                    ],
                ),
            )
        ]
    )

    restored = Scene.from_dict(scene.to_dict())

    assert restored.trajectories[0].id == "trajectory_pick"
    assert restored.trajectories[0].trajectory.duration == 1
    assert restored.trajectories[0].trajectory.keyframes[-1].targets == {
        "shoulder": 0.5
    }


def test_scene_service_adds_and_removes_actors() -> None:
    service = SceneService()

    first = service.add_actor("Box", asset_id="primitive_box")
    second = service.add_actor("Sphere", asset_id="primitive_sphere")

    assert first.id == "actor_001"
    assert second.id == "actor_002"
    assert [actor.name for actor in service.list_actors()] == ["Box", "Sphere"]

    assert service.remove_actor(first.id) is True
    assert service.get_actor(first.id) is None
    assert [actor.id for actor in service.list_actors()] == ["actor_002"]


def test_scene_service_updates_actor_state() -> None:
    service = SceneService()
    actor = service.add_actor("Box")

    service.rename_actor(actor.id, "Renamed Box")
    service.update_transform(actor.id, Transform(position=[4, 5, 6]))
    service.update_actor_properties(actor.id, {"mass": 3.0})

    updated = service.get_actor(actor.id)
    assert updated is not None
    assert updated.name == "Renamed Box"
    assert updated.transform.position == [4.0, 5.0, 6.0]
    assert updated.properties["mass"] == 3.0
