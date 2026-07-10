import math

import pytest

from simlab.models.actor import Actor
from simlab.models.transform import Transform
from simlab.services.primitive_geometry import (
    GeometryContractError,
    collider_geometry,
    euler_xyz_to_mujoco_quaternion,
)


def _actor(primitive: str, size: list[float], scale: list[float]) -> Actor:
    return Actor(
        id="actor_001",
        name="Primitive",
        type="object",
        asset_id=f"primitive_{primitive}",
        transform=Transform(scale=scale),
        properties={"primitive": primitive, "size": size},
    )


def test_box_half_extents_are_scaled_per_axis() -> None:
    geometry = collider_geometry(_actor("box", [0.5, 1.0, 1.5], [2.0, 3.0, 4.0]))

    assert geometry.geom_type == "box"
    assert geometry.size == [1.0, 3.0, 6.0]


def test_non_uniform_sphere_scale_becomes_ellipsoid() -> None:
    geometry = collider_geometry(_actor("sphere", [0.5], [1.0, 2.0, 3.0]))

    assert geometry.geom_type == "ellipsoid"
    assert geometry.size == [0.5, 1.0, 1.5]


def test_cylinder_uses_radius_and_half_height_with_z_axis_scale() -> None:
    geometry = collider_geometry(_actor("cylinder", [0.35, 0.8], [2.0, 2.0, 0.5]))

    assert geometry.geom_type == "cylinder"
    assert geometry.size == [0.7, 0.4]


def test_cylinder_rejects_non_uniform_radial_scale() -> None:
    with pytest.raises(GeometryContractError, match="X and Y scale must match") as exc_info:
        collider_geometry(_actor("cylinder", [0.35, 0.8], [1.0, 2.0, 1.0]))

    assert exc_info.value.code == "NON_UNIFORM_CYLINDER_RADIUS"


def test_xyz_euler_radians_convert_to_wxyz_quaternion() -> None:
    quaternion = euler_xyz_to_mujoco_quaternion([0.0, 0.0, 0.45])

    assert quaternion == pytest.approx(
        [math.cos(0.225), 0.0, 0.0, math.sin(0.225)],
    )
