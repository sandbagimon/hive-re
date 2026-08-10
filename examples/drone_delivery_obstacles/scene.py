from __future__ import annotations

import math
from pathlib import Path

from examples.controllers.iris_obstacle_delivery import LOADED_CLEARANCE, plan_route
from examples.drone_delivery.scene import (
    IRIS_BODY_LINK,
    _box,
    create_delivery_scene,
)
from simlab.models.robotics import RigidTransform, Sensor, SensorNoise, SensorNoiseChannel
from simlab.services.project_service import save_scene

RAY_COUNT = 12
RAY_ORIGIN_RADIUS = 0.32
RAY_HEIGHT = 0.03
RAY_MAX_DISTANCE = 4.0


def _horizontal_ray_sensor(index: int) -> Sensor:
    angle = 2.0 * math.pi * index / RAY_COUNT
    half_turn = math.sin(math.pi / 4.0)
    direction_x = math.cos(angle)
    direction_y = math.sin(angle)
    return Sensor(
        id=f"sensor_iris_range_{index:02d}",
        name=f"Iris Range {math.degrees(angle):.0f} deg",
        sensor_type="rangefinder",
        link_id=IRIS_BODY_LINK,
        update_rate_hz=50.0,
        local_transform=RigidTransform(
            position=[
                RAY_ORIGIN_RADIUS * direction_x,
                RAY_ORIGIN_RADIUS * direction_y,
                RAY_HEIGHT,
            ],
            # MuJoCo rangefinder rays follow site +Z. This 90-degree rotation
            # maps +Z onto the requested direction in the vehicle XY plane.
            quaternion=[
                -direction_y * half_turn,
                direction_x * half_turn,
                0.0,
                half_turn,
            ],
        ),
        max_distance=RAY_MAX_DISTANCE,
        noise=SensorNoise(
            seed=4200 + index,
            channels={
                "distance": SensorNoiseChannel(
                    bias=0.0,
                    standard_deviation=0.004,
                )
            },
        ),
    )


def create_obstacle_delivery_scene():
    scene = create_delivery_scene()
    scene.name = "Iris Obstacle-Aware Payload Delivery"
    scene.simulation_config.update(
        {
            "duration": 42.0,
            "wind": [0.1, -0.08, 0.0],
            "controller_reset_deadline": 0.2,
            "navigation": {
                "route": [
                    [x, y, 1.5] for x, y in plan_route((0.0, 0.0), (4.0, 3.0))
                ],
                "clearance": LOADED_CLEARANCE,
            },
        }
    )
    assert scene.robotics is not None
    articulation = scene.robotics.articulations[0]
    articulation.sensors.extend(_horizontal_ray_sensor(index) for index in range(RAY_COUNT))
    scene.actors.extend(
        [
            _box(
                "actor_obstacle_wall",
                "Central Flight Barrier",
                [2.0, 1.5, 1.2],
                [0.25, 0.8, 1.2],
                dynamic=False,
                rgba=[0.92, 0.32, 0.12, 1.0],
            ),
            _box(
                "actor_unmapped_pillar",
                "Unmapped Replanning Pillar",
                [2.35, 3.0, 1.2],
                [0.22, 0.22, 1.2],
                dynamic=False,
                rgba=[0.78, 0.2, 0.82, 1.0],
            ),
            _box(
                "actor_obstacle_pillar_west",
                "West Safety Pillar",
                [-1.35, 2.6, 0.9],
                [0.28, 0.28, 0.9],
                dynamic=False,
                rgba=[0.96, 0.62, 0.12, 1.0],
            ),
            _box(
                "actor_obstacle_pillar_east",
                "East Safety Pillar",
                [4.65, -0.9, 0.9],
                [0.28, 0.28, 0.9],
                dynamic=False,
                rgba=[0.96, 0.62, 0.12, 1.0],
            ),
        ]
    )
    return scene


def main() -> None:
    output = Path(__file__).with_name("scene.json")
    save_scene(output, create_obstacle_delivery_scene())
    print(output)


if __name__ == "__main__":
    main()
