"""Multi-drone swarm delivery inside the Architectural Brownstone Park.

Three cloned Iris quadcopters fly simultaneous pickup-and-delivery missions
inside the streamed Brownstone Park local scene (optimized profile). Every
airframe gets its own cloned articulation (links, joints, actuators, and
rangefinders are renamed per drone so MuJoCo IDs, attachments, and the
quadrotor propulsion bindings stay globally unique), its own payload, vacuum-
hook attachment, and delivery task. Two unmapped dynamic obstacles — a
cleaning cart and a maintenance van — cross the flight corridors during the
missions, so the swarm controller's occupancy grids and incremental A*
replanning have to route around live obstacles in addition to the park's
prior structures.
"""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any

from beefoundrysim.models.actor import Actor
from beefoundrysim.models.attachment import Attachment, DeliveryTask, VacuumGripper
from beefoundrysim.models.robotics import (
    RigidTransform,
    RoboticsModel,
    Sensor,
    SensorNoise,
    SensorNoiseChannel,
)
from beefoundrysim.models.scene import Scene
from beefoundrysim.models.transform import Transform
from beefoundrysim.services.project_service import save_scene

IRIS_ASSET_ID = "openusd_iris_09f8390b45"
PARK_ASSET_ID = "openusd_brownstone_park_8gb"
# The optimized park profile keeps every structure, tree, road, and hardscape
# (11.5 M vertices, 50 chunks) while dropping the dense painted grass/shrub
# layers. The full profile (95 M vertices, 95 chunks) takes minutes to stream
# and parse in the browser, which reads as "the scene never loads".
PARK_SCENE_ID = "brownstone-park"
PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAY_COUNT = 12
RAY_ORIGIN_RADIUS = 0.32
# Beams sit well above the airframe centre so a banking quadcopter (up to
# ~18 deg tilt) can never sweep them onto its own slung payload ~0.3 m below;
# self-reflections otherwise poison local avoidance on long legs.
RAY_HEIGHT = 0.22
RAY_MAX_DISTANCE = 4.0

# 2D navigation workspace shared by every pilot in the swarm controller.
MAP_BOUNDS = (-108.0, -86.0, -14.0, 13.0)
GRID_RESOLUTION = 0.25
LOADED_CLEARANCE = 0.68

# World-frame cruise altitude: above the raised planting beds (~0.9 m) and the
# cleaning cart (1.9 m tall hull is detected), below the 2.3 m park structures.
CRUISE_HEIGHT = 1.6

# Prior obstacles (center_x, center_y, half_x, half_y) fed to every pilot's
# occupancy grid. The two 2.3 m park structures are approximated from the
# streamed collision proxy; the two kiosks are authored scene boxes below.
# Placement keeps every planned corridor at least ~2 m wide: kiosk A blocks
# Alpha's straight leg without pinching the west corridor the Bravo leg uses,
# and kiosk B stays clear of the northern gap between it and the east park
# structure.
PARK_STRUCTURES = (
    (-96.7, 1.55, 1.35, 1.4),
    (-95.8, 3.55, 1.35, 1.4),
)
KIOSK_A = (-99.0, -4.5)
KIOSK_B = (-91.5, 6.5)
PRIOR_OBSTACLES = (
    *PARK_STRUCTURES,
    (KIOSK_A[0], KIOSK_A[1], 0.8, 0.8),
    (KIOSK_B[0], KIOSK_B[1], 0.8, 0.8),
)

# Terrain heights sampled from the park collision proxy so pads, payloads,
# hook descents, and spawn altitudes sit on the local ground instead of
# floating over or sinking into it.
TERRAIN_HEIGHTS = {
    (-106.5, -6.0): 0.05,
    (-103.5, -6.0): 0.05,
    (-89.5, 3.0): 0.32,
    (-106.5, 6.0): 0.30,
    (-103.5, 6.0): 0.30,
    (-89.5, -6.0): 0.60,
    (-95.5, -12.0): 0.82,
    (-95.5, -10.0): 0.75,
    (-95.5, 10.5): 0.00,
}


def _terrain(point: tuple[float, float]) -> float:
    return TERRAIN_HEIGHTS[point]


# One mission per drone: codename, home pad, pickup, and dropoff points.
MISSIONS = (
    ("alpha", (-106.5, -6.0), (-103.5, -6.0), (-89.5, 3.0)),
    ("bravo", (-106.5, 6.0), (-103.5, 6.0), (-89.5, -6.0)),
    ("charlie", (-95.5, -12.0), (-95.5, -10.0), (-95.5, 10.5)),
)


def _box(
    actor_id: str,
    name: str,
    position: list[float],
    size: list[float],
    *,
    dynamic: bool,
    mass: float = 1.0,
    rgba: list[float] | None = None,
    visual_style: str | None = None,
    physics_material: str | None = None,
) -> Actor:
    properties: dict[str, Any] = {
        "primitive": "box",
        "size": size,
        "rgba": rgba or [0.5, 0.55, 0.6, 1.0],
        "physics": {
            "dynamic": dynamic,
            "material": physics_material or ("wood" if dynamic else "default"),
            "mass_mode": "mass",
            "mass": mass,
            "friction": (
                [0.72, 0.008, 0.0002]
                if dynamic
                else [1.0, 0.005, 0.0001]
            ),
            "solref": [0.025, 1.0],
            "solimp": [0.92, 0.97, 0.001, 0.5, 2.0],
        },
    }
    if visual_style is not None:
        properties["visual_style"] = visual_style
    return Actor(
        id=actor_id,
        name=name,
        type="object",
        asset_id="primitive_box",
        transform=Transform(position=position),
        properties=properties,
    )


def _clone_articulation(raw: dict[str, Any], suffix: str) -> dict[str, Any]:
    """Deep-copy one articulation, renaming every stable ID with ``suffix``.

    Cloned vehicles must not share link/joint/actuator/collider IDs: MuJoCo
    resolves those IDs by name once per model, the quadrotor propulsion layer
    claims rotor links/actuators exclusively, and attachments address bodies
    by ID. Only reference fields pointing at renamed IDs are rewritten.
    """
    clone = copy.deepcopy(raw)
    clone["id"] = f"{clone['id']}_{suffix}"
    if clone.get("root_link_id"):
        clone["root_link_id"] = f"{clone['root_link_id']}_{suffix}"
    for link in clone["links"]:
        link["id"] = f"{link['id']}_{suffix}"
        if link.get("parent_link_id"):
            link["parent_link_id"] = f"{link['parent_link_id']}_{suffix}"
        for visual in link.get("visual_geometries", []):
            visual["id"] = f"{visual['id']}_{suffix}"
        for collider in link.get("colliders", []):
            collider["id"] = f"{collider['id']}_{suffix}"
    for joint in clone["joints"]:
        joint["id"] = f"{joint['id']}_{suffix}"
        if joint.get("parent_link_id"):
            joint["parent_link_id"] = f"{joint['parent_link_id']}_{suffix}"
        if joint.get("child_link_id"):
            joint["child_link_id"] = f"{joint['child_link_id']}_{suffix}"
    for actuator in clone["actuators"]:
        actuator["id"] = f"{actuator['id']}_{suffix}"
        if actuator.get("joint_id"):
            actuator["joint_id"] = f"{actuator['joint_id']}_{suffix}"
    for sensor in clone.get("sensors", []):
        sensor["id"] = f"{sensor['id']}_{suffix}"
        if sensor.get("link_id"):
            sensor["link_id"] = f"{sensor['link_id']}_{suffix}"
    return clone


def _horizontal_ray_sensor(index: int, body_link_id: str, seed_base: int) -> Sensor:
    angle = 2.0 * math.pi * index / RAY_COUNT
    half_turn = math.sin(math.pi / 4.0)
    direction_x = math.cos(angle)
    direction_y = math.sin(angle)
    return Sensor(
        id=f"sensor_iris_range_{index:02d}_{body_link_id.rsplit('_', 1)[-1]}",
        name=f"Iris Range {math.degrees(angle):.0f} deg",
        sensor_type="rangefinder",
        link_id=body_link_id,
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
            seed=seed_base + index,
            channels={
                "distance": SensorNoiseChannel(
                    bias=0.0,
                    standard_deviation=0.004,
                )
            },
        ),
    )


def _delivery_attachment(
    attachment_id: str, parent_body_id: str, child_body_id: str
) -> Attachment:
    return Attachment(
        id=attachment_id,
        parent_body_id=parent_body_id,
        child_body_id=child_body_id,
        parent_anchor=(0.0, 0.0, -0.12),
        child_anchor=(0.0, 0.0, 0.11),
        constraint_type="weld",
        gripper=VacuumGripper(
            plate_half_extents=(0.075, 0.055, 0.009),
            cup_offset=(0.05, 0.032),
            cup_radius=0.016,
            cup_height=0.018,
            mount_radius=0.011,
            mount_length=0.078,
        ),
        capture_distance=0.035,
        capture_speed=0.14,
        capture_duration=0.25,
        require_contact=True,
        contact_probe_radius=0.016,
        solref=(0.04, 1.0),
    )


def _load_iris_template() -> dict[str, Any]:
    metadata = json.loads(
        (PROJECT_ROOT / "assets/metadata.json").read_text(encoding="utf-8")
    )
    iris_asset = next(item for item in metadata["assets"] if item["id"] == IRIS_ASSET_ID)
    properties = iris_asset["default_properties"]
    raw = json.loads(
        (PROJECT_ROOT / properties["robotics_cache"]).read_text(encoding="utf-8")
    )
    return properties, raw


def _park_actor() -> Actor:
    # The viewport renders this actor purely from the streamed local-scene
    # chunks (stream_scene_id short-circuits primitive rendering), while MuJoCo
    # sees only the invisible workspace floor slab below: the full park OBJ
    # cannot be used as one mesh collider because MuJoCo collides meshes as
    # convex hulls, which would cap the entire park under an invisible shell.
    # Mission-relevant obstacles (the three 2.3 m park structures and the two
    # kiosks) are explicit primitive colliders instead.
    return Actor(
        id="actor_park_full",
        name="Architectural Brownstone Park",
        type="object",
        asset_id=PARK_ASSET_ID,
        transform=Transform(position=[-97.0, -0.5, -0.1]),
        properties={
            "primitive": "box",
            "size": [23.0, 28.0, 0.1],
            "rgba": [0.28, 0.34, 0.25, 1.0],
            "visual_style": "park_stream_floor",
            "physics": {"dynamic": False},
            "geometry": {
                "source_format": "openusd",
                "source": f"local-scene:{PARK_SCENE_ID}",
                "stream_scene_id": PARK_SCENE_ID,
                "bounds": {
                    "min": [-138.7, -53.3, -19.8],
                    "max": [-54.9, 75.3, 8.1],
                },
            },
        },
    )


# The 2.3 m park structures inside the workspace, lifted from the streamed
# collision proxy as world-aligned boxes. They block the 1.6 m cruise altitude
# so every pilot's prior map and A* detours match the physical world.
PARK_STRUCTURE_BOXES = (
    ("actor_park_structure_west", (-96.7, 1.55), (2.6, 2.7, 2.33)),
    ("actor_park_structure_center", (-95.8, 3.55), (2.6, 2.7, 2.33)),
    ("actor_park_structure_east", (-91.1, 14.05), (2.6, 2.7, 2.33)),
)


def _park_structure_actors() -> list[Actor]:
    return [
        _box(
            actor_id,
            f"Park Structure {actor_id.rsplit('_', 1)[-1].title()}",
            [center[0], center[1], size[2] / 2.0],
            list(size),
            dynamic=False,
            rgba=[0.35, 0.38, 0.33, 1.0],
            visual_style="known_obstacle",
        )
        for actor_id, center, size in PARK_STRUCTURE_BOXES
    ]


def _kiosk(actor_id: str, name: str, center: tuple[float, float], rgba: list[float]) -> Actor:
    return _box(
        actor_id,
        name,
        [center[0], center[1], 1.0],
        [1.6, 1.6, 2.0],
        dynamic=False,
        rgba=rgba,
        visual_style="known_obstacle",
    )


def _dynamic_events(duration: float) -> list[dict[str, Any]]:
    def keyframes(points: list[tuple[float, tuple[float, float, float]]]) -> list[dict[str, Any]]:
        return [
            {"time": time, "position": list(position), "rotation": [0.0, 0.0, 0.0]}
            for time, position in points
        ]

    # Both obstacles park on the workspace fringe while idle and only enter
    # the flight corridors during their activation window, so the parked hull
    # never permanently blocks a planned route.
    return [
        {
            "id": "event_cart_crosses_alpha_route",
            "type": "kinematic_actor",
            "actor_id": "actor_dynamic_cart",
            "label": "Cleaning cart crossing the west plaza",
            "activation_time": 14.0,
            "completion_time": 24.0,
            "interpolation": "smoothstep",
            "keyframes": keyframes(
                [
                    (0.0, (-101.5, -12.5, 0.95)),
                    (14.0, (-101.5, -12.5, 0.95)),
                    (17.0, (-101.5, 0.0, 0.95)),
                    (19.0, (-91.5, 0.0, 0.95)),
                    (24.0, (-101.5, -12.5, 0.95)),
                    (duration, (-101.5, -12.5, 0.95)),
                ]
            ),
        },
        {
            "id": "event_van_crosses_final_approach",
            "type": "kinematic_actor",
            "actor_id": "actor_dynamic_van",
            "label": "Maintenance van crossing the east corridor",
            "activation_time": 30.0,
            "completion_time": 42.0,
            "interpolation": "smoothstep",
            "keyframes": keyframes(
                [
                    (0.0, (-85.8, -12.0, 1.05)),
                    (30.0, (-85.8, -12.0, 1.05)),
                    (33.0, (-93.0, -7.0, 1.05)),
                    (37.0, (-93.0, 7.0, 1.05)),
                    (42.0, (-85.8, -12.0, 1.05)),
                    (duration, (-85.8, -12.0, 1.05)),
                ]
            ),
        },
    ]


def create_park_swarm_scene() -> Scene:
    template_properties, robotics_raw = _load_iris_template()
    template_articulation = robotics_raw["articulations"][0]

    actors: list[Actor] = [_park_actor(), *_park_structure_actors()]
    attachments: list[Attachment] = []
    tasks: list[DeliveryTask] = []
    articulations: list[dict[str, Any]] = []

    for index, (codename, home, pickup, dropoff) in enumerate(MISSIONS):
        suffix = codename
        body_link = f"{template_articulation['links'][0]['id']}_{suffix}"
        clone = _clone_articulation(template_articulation, suffix)
        clone["name"] = f"Iris Quadcopter {codename.title()}"
        clone["sensors"] = [
            _horizontal_ray_sensor(ray, body_link, seed_base=5100 + index * 100).to_dict()
            for ray in range(RAY_COUNT)
        ]
        articulations.append(clone)

        properties = copy.deepcopy(template_properties)
        properties["articulation_ids"] = [clone["id"]]
        propulsion = properties["propulsion"]
        propulsion["body_link_id"] = f"{propulsion['body_link_id']}_{suffix}"
        for rotor_index, rotor in enumerate(propulsion["rotors"]):
            rotor["id"] = f"iris_rotor_{rotor_index}_{suffix}"
            rotor["link_id"] = f"{rotor['link_id']}_{suffix}"
            rotor["actuator_id"] = f"{rotor['actuator_id']}_{suffix}"

        pickup_terrain = _terrain(pickup)
        dropoff_terrain = _terrain(dropoff)
        pad_top_pickup = pickup_terrain + 0.05
        pad_top_dropoff = dropoff_terrain + 0.05
        payload_z = pad_top_pickup + 0.11

        actors.extend(
            [
                Actor(
                    id=f"actor_iris_{suffix}",
                    name=f"Pegasus Iris {codename.title()}",
                    type="robot",
                    asset_id=IRIS_ASSET_ID,
                    transform=Transform(
                        position=[home[0], home[1], _terrain(home) + 0.12]
                    ),
                    properties=properties,
                ),
                _box(
                    f"actor_payload_{suffix}",
                    f"Insulated Delivery Bag {codename.title()}",
                    [pickup[0], pickup[1], payload_z],
                    [0.18, 0.14, 0.11],
                    dynamic=True,
                    mass=0.35,
                    rgba=[0.13, 0.14, 0.15, 1.0],
                    visual_style="insulated_delivery_bag",
                    physics_material="rubber",
                ),
                _box(
                    f"actor_pickup_pad_{suffix}",
                    f"Pickup {codename.title()}",
                    [pickup[0], pickup[1], pickup_terrain + 0.025],
                    [1.5, 1.5, 0.05],
                    dynamic=False,
                    rgba=[0.18, 0.55, 0.9, 1.0],
                    visual_style="landing_pad_pickup",
                ),
                _box(
                    f"actor_dropoff_pad_{suffix}",
                    f"Dropoff {codename.title()}",
                    [dropoff[0], dropoff[1], dropoff_terrain + 0.025],
                    [1.5, 1.5, 0.05],
                    dynamic=False,
                    rgba=[0.2, 0.75, 0.35, 1.0],
                    visual_style="landing_pad_dropoff",
                ),
            ]
        )
        attachment = _delivery_attachment(
            f"attachment_iris_hook_{suffix}",
            body_link,
            f"actor_payload_{suffix}",
        )
        attachments.append(attachment)
        tasks.append(
            DeliveryTask(
                id=f"task_delivery_{suffix}",
                attachment_id=attachment.id,
                payload_body_id=f"actor_payload_{suffix}",
                pickup_position=(pickup[0], pickup[1], payload_z),
                dropoff_position=(dropoff[0], dropoff[1], pad_top_dropoff + 0.11),
                position_tolerance=0.35,
                settle_speed=0.15,
                settle_duration=0.5,
            )
        )

    actors.extend(
        [
            _kiosk(
                "actor_kiosk_west",
                "West Plaza Kiosk",
                KIOSK_A,
                [0.92, 0.42, 0.16, 1.0],
            ),
            _kiosk(
                "actor_kiosk_east",
                "East Meadow Kiosk",
                KIOSK_B,
                [0.16, 0.55, 0.9, 1.0],
            ),
            _box(
                "actor_dynamic_cart",
                "Unmapped Crossing Cleaning Cart",
                [-101.5, -12.5, 0.95],
                [0.9, 0.5, 0.9],
                dynamic=True,
                mass=90.0,
                rgba=[0.25, 0.7, 0.4, 1.0],
                visual_style="dynamic_event",
                physics_material="rubber",
            ),
            _box(
                "actor_dynamic_van",
                "Unmapped Crossing Maintenance Van",
                [-85.8, -12.0, 1.05],
                [1.1, 2.2, 1.0],
                dynamic=True,
                mass=2_400.0,
                rgba=[0.88, 0.62, 0.08, 1.0],
                visual_style="dynamic_event",
                physics_material="rubber",
            ),
        ]
    )

    duration = 200.0
    return Scene(
        name="Brownstone Park Swarm Delivery",
        actors=actors,
        robotics=RoboticsModel.from_dict(
            {"version": robotics_raw["version"], "articulations": articulations}
        ),
        attachments=attachments,
        delivery_tasks=tasks,
        simulation_config={
            # 200 Hz physics keeps three airframes plus the park mesh stable
            # without the cost of the single-drone demo's 500 Hz clock.
            "timestep": 0.005,
            # Each Python action holds for two physics steps; every pilot's
            # local avoidance still runs at 100 Hz.
            "controller_update_rate_hz": 100.0,
            "duration": duration,
            "wind": [0.12, -0.08, 0.0],
            "controller_deadline": 0.05,
            # Three pilots each plan an initial A* route over the shared park
            # grid during reset; the pooled budget needs more headroom than the
            # single-drone demo's 200 ms.
            "controller_reset_deadline": 0.8,
            "dynamic_events": _dynamic_events(duration),
        },
    )


def main() -> None:
    output = Path(__file__).with_name("scene.json")
    save_scene(output, create_park_swarm_scene())
    print(output)


if __name__ == "__main__":
    main()
