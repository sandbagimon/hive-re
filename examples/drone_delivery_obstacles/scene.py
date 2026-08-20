from __future__ import annotations

import math
from pathlib import Path

from examples.controllers.iris_obstacle_delivery import LOADED_CLEARANCE, plan_route
from examples.drone_delivery.scene import (
    IRIS_BODY_LINK,
    _box,
    create_delivery_scene,
)
from simlab.models.actor import Actor
from simlab.models.robotics import RigidTransform, Sensor, SensorNoise, SensorNoiseChannel
from simlab.services.project_service import save_scene

RAY_COUNT = 12
RAY_ORIGIN_RADIUS = 0.32
RAY_HEIGHT = 0.03
RAY_MAX_DISTANCE = 4.0
POLY_HAVEN_BARRIER = {
    "url": (
        "./models/polyhaven/concrete_road_barrier_02/"
        "concrete_road_barrier_02_2k.gltf"
    ),
    "source_url": "https://polyhaven.com/a/concrete_road_barrier_02",
    "license": "CC0-1.0",
    "author": "Amal Kumar",
    "resolution": "2K",
}
POLY_HAVEN_BARREL = {
    "url": "./models/polyhaven/barrel_03/barrel_03_2k.gltf",
    "source_url": "https://polyhaven.com/a/barrel_03",
    "license": "CC0-1.0",
    "author": "Serhii Khromov",
    "resolution": "2K",
}
POLY_HAVEN_CARDBOARD_BOX = {
    "url": "./models/polyhaven/cardboard_box_01/cardboard_box_01_2k.gltf",
    "source_url": "https://polyhaven.com/a/cardboard_box_01",
    "license": "CC0-1.0",
    "author": "Pacid Bhuyan",
    "resolution": "2K",
}
POLY_HAVEN_FIRE_HYDRANT = {
    "url": "./models/polyhaven/fire_hydrant/fire_hydrant_2k.gltf",
    "source_url": "https://polyhaven.com/a/fire_hydrant",
    "license": "CC0-1.0",
    "author": "Pacid Bhuyan",
    "resolution": "2K",
}
POLY_HAVEN_PLASTIC_CRATE = {
    "url": "./models/polyhaven/plastic_crate_02/plastic_crate_02_2k.gltf",
    "source_url": "https://polyhaven.com/a/plastic_crate_02",
    "license": "CC0-1.0",
    "author": "Pacid Bhuyan",
    "resolution": "2K",
}
POLY_HAVEN_JACARANDA_TREE = {
    "url": "./models/polyhaven/jacaranda_tree/jacaranda_tree_2k.gltf",
    "source_url": "https://polyhaven.com/a/jacaranda_tree",
    "license": "CC0-1.0",
    "author": "Pacid Bhuyan",
    "resolution": "2K",
}
POLY_HAVEN_WOODEN_CRATE = {
    "url": "./models/polyhaven/wooden_crate_02/wooden_crate_02_2k.gltf",
    "source_url": "https://polyhaven.com/a/wooden_crate_02",
    "license": "CC0-1.0",
    "author": "Pacid Bhuyan",
    "resolution": "2K",
}
SKETCHFAB_FORKLIFT = {
    "url": "./models/sketchfab/forklift/forklift.glb",
    "source_url": (
        "https://sketchfab.com/3d-models/"
        "forklift-truck-060f3f8bc7de4e6ca2f348d414702e9d"
    ),
    "license": "CC-BY-4.0",
    "author": "louis-muir",
    "resolution": "Objaverse Web GLB",
}
MESH2MOTION_COURIER = {
    "url": "./models/mesh2motion/courier/human-jay.glb",
    "source_url": (
        "https://github.com/Mesh2Motion/mesh2motion-app/blob/main/"
        "static/models-variation/human-jay.glb"
    ),
    "license": "CC0-1.0",
    "author": "Mesh2Motion contributors",
    "resolution": "Web GLB",
    "animation": {
        "clip_url": (
            "./models/mesh2motion/courier/human-base-animations.glb"
        ),
        "source_url": (
            "https://github.com/Mesh2Motion/mesh2motion-app/blob/main/"
            "static/animations/human-base-animations.glb"
        ),
        "license": "CC0-1.0",
        "author": "Quaternius and Mesh2Motion contributors",
        "locomotion": "walking",
        "clips": {
            "idle": "Idle_A",
            "walking": "Walk",
            # The same loader can select a seated/riding clip when a scene switches
            # locomotion to cycling. This library names that pose "Driving".
            "cycling": "Driving",
        },
        "reference_speed": 1.3,
        "stop_speed": 0.05,
        "min_playback_rate": 0.55,
        "max_playback_rate": 1.8,
    },
}


def _with_visual_model(
    actor: Actor,
    model: dict[str, object],
    *,
    instance_size: list[float],
    instance_heights: tuple[float, ...],
    rotation: list[float],
) -> Actor:
    actor.properties["visual_model"] = {
        **model,
        "instances": [
            {
                "position": [0.0, 0.0, height],
                "rotation": rotation,
                "size": instance_size,
            }
            for height in instance_heights
        ],
    }
    return actor


def _with_rotation(actor: Actor, rotation: list[float]) -> Actor:
    actor.transform.rotation = rotation
    return actor


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
    scene.name = "Blue-Hour Autonomous Food Delivery"
    ground = next(actor for actor in scene.actors if actor.id == "actor_001")
    ground.name = "Rain-darkened Urban Delivery Street"
    ground.properties["visual_style"] = "cinematic_wet_asphalt"
    ground.properties["size"] = [6.5, 5.5, 0.05]
    ground.properties["rgba"] = [0.12, 0.15, 0.18, 1.0]
    scene.simulation_config.update(
        {
            # 200 Hz physics is stable for this controller while avoiding the
            # unnecessary 500 Hz Python/visual synchronization cost of the base demo.
            "timestep": 0.005,
            # Hold each Python action for two physics steps. Local avoidance still
            # runs at 100 Hz, well above the 50 Hz rangefinder publication rate.
            "controller_update_rate_hz": 100.0,
            "duration": 48.0,
            "wind": [0.1, -0.08, 0.0],
            # Incremental planning normally completes far below this budget. The extra margin
            # prevents a busy remote development host from turning one scheduling spike into a
            # permanently disabled flight controller.
            "controller_deadline": 0.05,
            "controller_reset_deadline": 0.2,
            "visual_environment": {
                "preset": "cinematic_blue_hour_delivery",
                "exposure": 0.92,
                "fog_color": "#17232f",
                "fog_near": 18.0,
                "fog_far": 58.0,
            },
            "navigation": {
                "route": [
                    [x, y, 1.5] for x, y in plan_route((0.0, 0.0), (4.0, 3.0))
                ],
                "clearance": LOADED_CLEARANCE,
            },
            "dynamic_events": [
                {
                    "id": "event_forklift_blocks_pickup_exit",
                    "type": "kinematic_actor",
                    "actor_id": "actor_dynamic_forklift",
                    "label": "Forklift crossing the live route",
                    "activation_time": 11.0,
                    "completion_time": 19.0,
                    "interpolation": "smoothstep",
                    "keyframes": [
                        {
                            "time": 0.0,
                            "position": [1.15, -1.2, 1.0],
                            "rotation": [0.0, 0.0, math.pi / 2.0],
                        },
                        {
                            "time": 11.0,
                            "position": [1.15, -1.2, 1.0],
                            "rotation": [0.0, 0.0, math.pi / 2.0],
                        },
                        {
                            "time": 13.0,
                            "position": [1.15, 1.45, 1.0],
                            "rotation": [0.0, 0.0, math.pi / 2.0],
                        },
                        {
                            "time": 17.0,
                            "position": [1.15, 1.45, 1.0],
                            "rotation": [0.0, 0.0, math.pi / 2.0],
                        },
                        {
                            "time": 19.0,
                            "position": [1.15, -1.2, 1.0],
                            "rotation": [0.0, 0.0, math.pi / 2.0],
                        },
                        {
                            "time": 48.0,
                            "position": [1.15, -1.2, 1.0],
                            "rotation": [0.0, 0.0, math.pi / 2.0],
                        },
                    ],
                },
                {
                    "id": "event_courier_crosses_final_leg",
                    "type": "kinematic_actor",
                    "actor_id": "actor_dynamic_courier",
                    "label": "Courier entering the final approach",
                    "activation_time": 20.0,
                    "completion_time": 28.0,
                    "interpolation": "smoothstep",
                    "keyframes": [
                        {
                            "time": 0.0,
                            "position": [5.35, -2.0, 0.82],
                            "rotation": [0.0, 0.0, math.pi / 2.0],
                        },
                        {
                            "time": 20.0,
                            "position": [5.35, -2.0, 0.82],
                            "rotation": [0.0, 0.0, math.pi / 2.0],
                        },
                        {
                            "time": 22.0,
                            "position": [2.75, -2.0, 0.82],
                            "rotation": [0.0, 0.0, math.pi / 2.0],
                        },
                        {
                            "time": 26.0,
                            "position": [2.75, -2.0, 0.82],
                            "rotation": [0.0, 0.0, -math.pi / 2.0],
                        },
                        {
                            "time": 28.0,
                            "position": [5.35, -2.0, 0.82],
                            "rotation": [0.0, 0.0, -math.pi / 2.0],
                        },
                        {
                            "time": 48.0,
                            "position": [5.35, -2.0, 0.82],
                            "rotation": [0.0, 0.0, -math.pi / 2.0],
                        },
                    ],
                },
            ],
        }
    )
    assert scene.robotics is not None
    articulation = scene.robotics.articulations[0]
    articulation.sensors.extend(_horizontal_ray_sensor(index) for index in range(RAY_COUNT))
    scene.actors.extend(
        [
            _with_visual_model(
                _box(
                    "actor_obstacle_wall",
                    "Central Flight Barrier",
                    [2.0, 1.5, 1.2],
                    [0.25, 0.8, 1.2],
                    dynamic=False,
                    rgba=[0.92, 0.32, 0.12, 1.0],
                    visual_style="known_obstacle",
                ),
                POLY_HAVEN_BARRIER,
                instance_size=[0.5, 1.6, 1.2],
                instance_heights=(-0.6,),
                rotation=[math.pi / 2.0, 0.0, math.pi / 2.0],
            ),
            _with_visual_model(
                _box(
                    "actor_obstacle_pillar_west",
                    "West Safety Pillar",
                    [-1.35, 2.6, 0.9],
                    [0.28, 0.28, 0.9],
                    dynamic=False,
                    rgba=[0.96, 0.62, 0.12, 1.0],
                    visual_style="safety_pillar",
                ),
                POLY_HAVEN_BARREL,
                instance_size=[0.56, 0.56, 0.9],
                instance_heights=(-0.45, 0.45),
                rotation=[math.pi / 2.0, 0.0, 0.0],
            ),
            _with_visual_model(
                _box(
                    "actor_obstacle_pillar_east",
                    "East Safety Pillar",
                    [4.65, -0.9, 0.9],
                    [0.28, 0.28, 0.9],
                    dynamic=False,
                    rgba=[0.96, 0.62, 0.12, 1.0],
                    visual_style="safety_pillar",
                ),
                POLY_HAVEN_BARREL,
                instance_size=[0.56, 0.56, 0.9],
                instance_heights=(-0.45, 0.45),
                rotation=[math.pi / 2.0, 0.0, 0.0],
            ),
            _with_rotation(
                _box(
                    "actor_pickup_restaurant",
                    "Neon Pickup Kitchen",
                    [-2.72, 0.0, 1.35],
                    [1.5, 0.22, 1.35],
                    dynamic=False,
                    rgba=[0.12, 0.15, 0.17, 1.0],
                    visual_style="restaurant_pickup",
                    physics_material="default",
                ),
                [0.0, 0.0, -math.pi / 2.0],
            ),
            _box(
                "actor_dropoff_residence",
                "Warm Residential Dropoff",
                [4.0, 4.15, 1.7],
                [1.45, 0.24, 1.7],
                dynamic=False,
                rgba=[0.2, 0.22, 0.24, 1.0],
                visual_style="residential_dropoff",
                physics_material="default",
            ),
            _with_rotation(
                _with_visual_model(
                    _box(
                        "actor_dynamic_forklift",
                        "Unmapped Crossing Forklift",
                        [1.15, -1.2, 1.0],
                        # Approximate the solid chassis rather than treating the open
                        # space between the full-length forks as a filled box.
                        [0.9, 0.5, 1.0],
                        dynamic=True,
                        mass=2_600.0,
                        rgba=[0.88, 0.62, 0.08, 1.0],
                        visual_style="dynamic_forklift",
                        physics_material="rubber",
                    ),
                    SKETCHFAB_FORKLIFT,
                    instance_size=[2.9, 1.1, 2.0],
                    instance_heights=(0.0,),
                    rotation=[math.pi / 2.0, 0.0, 0.0],
                ),
                [0.0, 0.0, math.pi / 2.0],
            ),
            _with_rotation(
                _with_visual_model(
                    _box(
                        "actor_dynamic_courier",
                        "Unmapped Crossing Courier",
                        # Keep the pedestrian in the south service lane so the
                        # forklift remains the obstacle that crosses the flight path.
                        [5.35, -2.0, 0.82],
                        [0.25, 0.22, 0.82],
                        dynamic=True,
                        mass=82.0,
                        rgba=[0.08, 0.23, 0.34, 1.0],
                        visual_style="dynamic_courier",
                        physics_material="rubber",
                    ),
                    MESH2MOTION_COURIER,
                    instance_size=[0.48, 0.4, 1.62],
                    instance_heights=(0.0,),
                    rotation=[math.pi / 2.0, 0.0, 0.0],
                ),
                [0.0, 0.0, math.pi / 2.0],
            ),
            # Cinematic street-furniture props with PBR glTF models
            _with_visual_model(
                _box(
                    "actor_prop_cardboard_boxes",
                    "Stacked Cardboard Boxes",
                    [-1.0, -0.8, 0.18],
                    [0.36, 0.28, 0.18],
                    dynamic=False,
                    rgba=[0.55, 0.38, 0.22, 1.0],
                    visual_style="known_obstacle",
                ),
                POLY_HAVEN_CARDBOARD_BOX,
                instance_size=[0.42, 0.32, 0.3],
                instance_heights=(0.0, 0.32),
                rotation=[math.pi / 2.0, 0.0, 0.0],
            ),
            _with_visual_model(
                _box(
                    "actor_prop_fire_hydrant",
                    "Street Fire Hydrant",
                    [-0.8, 2.0, 0.38],
                    [0.22, 0.22, 0.38],
                    dynamic=False,
                    rgba=[0.72, 0.12, 0.08, 1.0],
                    visual_style="known_obstacle",
                ),
                POLY_HAVEN_FIRE_HYDRANT,
                instance_size=[0.35, 0.35, 0.62],
                instance_heights=(0.0,),
                rotation=[math.pi / 2.0, 0.0, 0.0],
            ),
            _with_visual_model(
                _box(
                    "actor_prop_plastic_crates",
                    "Stacked Plastic Crates",
                    [3.5, 3.8, 0.22],
                    [0.4, 0.3, 0.22],
                    dynamic=False,
                    rgba=[0.18, 0.35, 0.48, 1.0],
                    visual_style="known_obstacle",
                ),
                POLY_HAVEN_PLASTIC_CRATE,
                instance_size=[0.5, 0.36, 0.3],
                instance_heights=(0.0, 0.32),
                rotation=[math.pi / 2.0, 0.0, 0.0],
            ),
            _with_visual_model(
                _box(
                    "actor_prop_wooden_crate",
                    "Wooden Cargo Crate",
                    [2.6, -0.7, 0.3],
                    [0.5, 0.36, 0.3],
                    dynamic=False,
                    rgba=[0.42, 0.28, 0.16, 1.0],
                    visual_style="known_obstacle",
                ),
                POLY_HAVEN_WOODEN_CRATE,
                instance_size=[0.6, 0.42, 0.42],
                instance_heights=(0.0,),
                rotation=[math.pi / 2.0, 0.0, 0.0],
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
