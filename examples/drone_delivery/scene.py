from __future__ import annotations

import json
from pathlib import Path

from simlab.models.actor import Actor
from simlab.models.attachment import Attachment, DeliveryTask, VacuumGripper
from simlab.models.robotics import RoboticsModel
from simlab.models.scene import Scene
from simlab.models.transform import Transform
from simlab.services.project_service import save_scene

IRIS_ASSET_ID = "openusd_iris_09f8390b45"
IRIS_BODY_LINK = "link_c46480014a33"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


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
    properties = {
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


def create_delivery_scene() -> Scene:
    metadata = json.loads((PROJECT_ROOT / "assets/metadata.json").read_text(encoding="utf-8"))
    iris_asset = next(item for item in metadata["assets"] if item["id"] == IRIS_ASSET_ID)
    properties = iris_asset["default_properties"]
    robotics = RoboticsModel.from_dict(
        json.loads((PROJECT_ROOT / properties["robotics_cache"]).read_text(encoding="utf-8"))
    )
    attachment = Attachment(
        id="attachment_iris_payload_hook",
        parent_body_id=IRIS_BODY_LINK,
        child_body_id="actor_003",
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
    return Scene(
        name="Iris A-to-B Physical Delivery",
        actors=[
            _box(
                "actor_001",
                "Ground",
                [1.0, 1.0, -0.05],
                [4.25, 3.25, 0.05],
                dynamic=False,
                rgba=[0.27, 0.34, 0.38, 1.0],
                visual_style="operations_ground",
            ),
            Actor(
                id="actor_002",
                name="Pegasus Iris Quadcopter",
                type="robot",
                asset_id=IRIS_ASSET_ID,
                transform=Transform(position=[-2.0, 0.0, 0.12]),
                properties=properties,
            ),
            _box(
                "actor_003",
                "Insulated Takeout Bag",
                [0.0, 0.0, 0.16],
                [0.18, 0.14, 0.11],
                dynamic=True,
                mass=0.35,
                rgba=[0.13, 0.14, 0.15, 1.0],
                visual_style="insulated_delivery_bag",
                physics_material="rubber",
            ),
            _box(
                "actor_004",
                "Pickup A",
                [0.0, 0.0, 0.025],
                [0.75, 0.75, 0.025],
                dynamic=False,
                rgba=[0.18, 0.55, 0.9, 1.0],
                visual_style="landing_pad_pickup",
            ),
            _box(
                "actor_005",
                "Dropoff B",
                [4.0, 3.0, 0.025],
                [0.75, 0.75, 0.025],
                dynamic=False,
                rgba=[0.2, 0.75, 0.35, 1.0],
                visual_style="landing_pad_dropoff",
            ),
        ],
        robotics=robotics,
        attachments=[attachment],
        delivery_tasks=[
            DeliveryTask(
                id="task_iris_delivery",
                attachment_id=attachment.id,
                payload_body_id="actor_003",
                pickup_position=(0.0, 0.0, 0.16),
                dropoff_position=(4.0, 3.0, 0.16),
                position_tolerance=0.35,
                settle_speed=0.15,
                settle_duration=0.5,
            )
        ],
        simulation_config={
            "timestep": 0.002,
            "duration": 30.0,
            "integrator": "implicitfast",
            "wind": [0.15, -0.1, 0.0],
            "air_density": 1.225,
            "air_viscosity": 1.8e-5,
            "controller_deadline": 0.02,
            "max_catch_up_steps": 32,
        },
    )


def main() -> None:
    output = Path(__file__).with_name("scene.json")
    save_scene(output, create_delivery_scene())
    print(output)


if __name__ == "__main__":
    main()
