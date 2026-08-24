from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from itertools import combinations
from pathlib import Path
from typing import Any

from beefoundrysim.models.actor import Actor
from beefoundrysim.models.robotics import Articulation, Collider, Link, Sensor
from beefoundrysim.models.scene import Scene
from beefoundrysim.services.openusd_importer import resolve_imported_asset_path
from beefoundrysim.services.physics_materials import material_for_id
from beefoundrysim.services.primitive_geometry import (
    collider_geometry,
    euler_xyz_to_mujoco_quaternion,
)


def scene_to_mjcf_xml(scene: Scene, *, asset_root: str | Path | None = None) -> str:
    """Convert a BeeFoundrySim scene into an MJCF XML string."""
    root = ET.Element("mujoco", {"model": scene.name})
    ET.SubElement(root, "compiler", {"angle": "radian"})
    option = ET.SubElement(root, "option")
    option.set("timestep", str(scene.simulation_config.get("timestep", 0.01)))
    option.set(
        "integrator",
        str(scene.simulation_config.get("integrator", "implicitfast")),
    )
    wind = scene.simulation_config.get("wind")
    if wind is not None:
        option.set("wind", _format_vector(wind))
        option.set("density", str(scene.simulation_config.get("air_density", 1.225)))
        option.set("viscosity", str(scene.simulation_config.get("air_viscosity", 1.8e-5)))

    mesh_assets = ET.SubElement(root, "asset")
    mesh_names: dict[str, str] = {}
    robot_mesh_names: dict[str, str] = {}
    for actor in scene.actors:
        mesh_path = _collision_mesh_path(actor)
        if mesh_path is None:
            continue
        if asset_root is None:
            raise ValueError("Imported mesh assets require an asset_root when generating MJCF.")
        resolved = resolve_imported_asset_path(mesh_path, asset_root)
        if not resolved.is_file():
            raise ValueError(f"Imported collision mesh is missing: {mesh_path}")
        asset_mesh_name = f"{_xml_name(actor.id)}_mesh"
        mesh_names[actor.id] = asset_mesh_name
        ET.SubElement(
            mesh_assets,
            "mesh",
            {
                "name": asset_mesh_name,
                "file": str(resolved),
                "scale": _format_vector(actor.transform.scale),
            },
        )
    if scene.robotics is not None:
        for articulation in scene.robotics.articulations:
            for link in articulation.links:
                for robot_collider in link.colliders:
                    if robot_collider.geometry_type != "mesh":
                        continue
                    if not robot_collider.collision_mesh:
                        raise ValueError(
                            "Robot mesh collider has no collision cache: "
                            f"{robot_collider.id}"
                        )
                    if asset_root is None:
                        raise ValueError(
                            "Robot mesh colliders require an asset_root when generating MJCF."
                        )
                    resolved = resolve_imported_asset_path(
                        robot_collider.collision_mesh,
                        asset_root,
                    )
                    if not resolved.is_file():
                        raise ValueError(
                            "Robot collision mesh is missing: "
                            f"{robot_collider.collision_mesh}"
                        )
                    if robot_collider.id in robot_mesh_names:
                        continue
                    asset_mesh_name = f"{_xml_name(robot_collider.id)}_mesh"
                    robot_mesh_names[robot_collider.id] = asset_mesh_name
                    ET.SubElement(
                        mesh_assets,
                        "mesh",
                        {"name": asset_mesh_name, "file": str(resolved)},
                    )
    if not mesh_names and not robot_mesh_names:
        root.remove(mesh_assets)

    worldbody = ET.SubElement(root, "worldbody")
    ET.SubElement(worldbody, "light", {"name": "key_light", "pos": "0 0 4"})
    robot_actuators: list[tuple[str, Any, float]] = []
    robot_imu_sensors: list[tuple[Sensor, str]] = []
    robot_rangefinder_sensors: list[tuple[Sensor, str]] = []
    robot_contact_excludes: list[tuple[str, str]] = []
    home_positions: list[float] = []
    home_velocities: list[float] = []

    for actor in scene.actors:
        if actor.type != "object":
            continue
        mesh_name = mesh_names.get(actor.id)
        rgba = _format_vector(actor.properties.get("rgba", [0.7, 0.7, 0.7, 1.0]))
        friction = _format_friction(
            _physics_value(actor, "friction", [0.8, 0.005, 0.0001])
        )
        if mesh_name:
            geom_attrs = {
                "name": f"{_xml_name(actor.id)}_geom",
                "type": "mesh",
                "mesh": mesh_name,
                "rgba": rgba,
                "friction": friction,
            }
        else:
            primitive_collider = collider_geometry(actor)
            geom_attrs = {
                "name": f"{_xml_name(actor.id)}_geom",
                "type": primitive_collider.geom_type,
                "size": _format_vector(primitive_collider.size),
                "rgba": rgba,
                "friction": friction,
            }
        solref = _physics_value(actor, "solref", None)
        solimp = _physics_value(actor, "solimp", None)
        if solref is not None:
            geom_attrs["solref"] = _format_vector(solref)
        if solimp is not None:
            geom_attrs["solimp"] = _format_vector(solimp)
        if _is_dynamic(actor):
            body = ET.SubElement(
                worldbody,
                "body",
                {
                    "name": _xml_name(actor.id),
                    "pos": _format_vector(actor.transform.position),
                    "quat": _format_vector(
                        euler_xyz_to_mujoco_quaternion(actor.transform.rotation)
                    ),
                },
            )
            ET.SubElement(body, "freejoint")
            home_positions.extend(actor.transform.position)
            home_positions.extend(
                euler_xyz_to_mujoco_quaternion(actor.transform.rotation)
            )
            home_velocities.extend([0.0] * 6)
            if _physics_value(actor, "mass_mode", "mass") == "density":
                geom_attrs["density"] = str(_physics_value(actor, "density", 1000.0))
            else:
                mass = _physics_value(actor, "mass", actor.properties.get("mass", 1.0))
                geom_attrs["mass"] = str(mass)
            ET.SubElement(body, "geom", geom_attrs)
        else:
            geom_attrs["pos"] = _format_vector(actor.transform.position)
            geom_attrs["quat"] = _format_vector(
                euler_xyz_to_mujoco_quaternion(actor.transform.rotation)
            )
            ET.SubElement(worldbody, "geom", geom_attrs)

    if scene.robotics is not None:
        articulations = {item.id: item for item in scene.robotics.articulations}
        for actor in scene.actors:
            if actor.type != "robot":
                continue
            ids = actor.properties.get("articulation_ids", [])
            for articulation_id in ids:
                selected_articulation = articulations.get(str(articulation_id))
                if selected_articulation is None:
                    continue
                wrapper = ET.SubElement(
                    worldbody,
                    "body",
                    {
                        "name": _xml_name(actor.id),
                        "pos": _format_vector(actor.transform.position),
                        "quat": _format_vector(
                            euler_xyz_to_mujoco_quaternion(actor.transform.rotation)
                        ),
                    },
                )
                if not selected_articulation.fixed_base:
                    ET.SubElement(wrapper, "freejoint")
                    home_positions.extend(actor.transform.position)
                    home_positions.extend(
                        euler_xyz_to_mujoco_quaternion(actor.transform.rotation)
                    )
                    home_velocities.extend([0.0] * 6)
                _append_articulation(
                    wrapper,
                    selected_articulation,
                    robot_actuators,
                    robot_imu_sensors,
                    robot_rangefinder_sensors,
                    robot_contact_excludes,
                    home_positions,
                    home_velocities,
                    robot_mesh_names,
                )

    if scene.attachments:
        bodies_by_name = {
            body.get("name"): body
            for body in worldbody.iter("body")
            if body.get("name")
        }
        equality_element = ET.SubElement(root, "equality")
        for attachment in scene.attachments:
            parent_body = bodies_by_name.get(_xml_name(attachment.parent_body_id))
            child_body = bodies_by_name.get(_xml_name(attachment.child_body_id))
            if parent_body is None or child_body is None:
                raise ValueError(
                    f"Attachment {attachment.id} references a body that was not exported"
                )
            parent_site_name, child_site_name = attachment_site_names(attachment.id)
            ET.SubElement(
                parent_body,
                "site",
                {
                    "name": parent_site_name,
                    "type": "sphere",
                    "size": "0.008",
                    "pos": _format_vector(attachment.parent_anchor),
                    "rgba": "1 0.7 0.1 1",
                },
            )
            ET.SubElement(
                child_body,
                "site",
                {
                    "name": child_site_name,
                    "type": "sphere",
                    "size": "0.008",
                    "pos": _format_vector(attachment.child_anchor),
                    "rgba": "0.2 0.9 0.5 1",
                },
            )
            if attachment.gripper is not None:
                gripper = attachment.gripper
                cup_x, cup_y = gripper.cup_offset
                for index, (offset_x, offset_y) in enumerate(
                    ((cup_x, cup_y), (cup_x, -cup_y), (-cup_x, cup_y), (-cup_x, -cup_y))
                ):
                    cup_position = [
                        attachment.parent_anchor[0] + offset_x,
                        attachment.parent_anchor[1] + offset_y,
                        attachment.parent_anchor[2] + gripper.cup_height * 0.5,
                    ]
                    ET.SubElement(
                        parent_body,
                        "geom",
                        {
                            "name": attachment_gripper_cup_geom_name(
                                attachment.id, index
                            ),
                            "type": "cylinder",
                            "size": _format_vector(
                                [gripper.cup_radius, gripper.cup_height * 0.5]
                            ),
                            "pos": _format_vector(cup_position),
                            "mass": "0",
                            "friction": "1.2 0.01 0.0002",
                            "condim": "4",
                            "rgba": "0.08 0.1 0.12 1",
                        },
                    )
                plate_position = [
                    attachment.parent_anchor[0],
                    attachment.parent_anchor[1],
                    attachment.parent_anchor[2]
                    + gripper.cup_height
                    + gripper.plate_half_extents[2],
                ]
                ET.SubElement(
                    parent_body,
                    "geom",
                    {
                        "name": attachment_gripper_plate_geom_name(attachment.id),
                        "type": "box",
                        "size": _format_vector(gripper.plate_half_extents),
                        "pos": _format_vector(plate_position),
                        "mass": "0",
                        "friction": "0.8 0.005 0.0001",
                        "rgba": "0.12 0.16 0.2 1",
                    },
                )
                mount_position = [
                    attachment.parent_anchor[0],
                    attachment.parent_anchor[1],
                    attachment.parent_anchor[2]
                    + gripper.cup_height
                    + gripper.plate_half_extents[2] * 2
                    + gripper.mount_length * 0.5,
                ]
                ET.SubElement(
                    parent_body,
                    "geom",
                    {
                        "name": attachment_gripper_mount_geom_name(attachment.id),
                        "type": "cylinder",
                        "size": _format_vector(
                            [gripper.mount_radius, gripper.mount_length * 0.5]
                        ),
                        "pos": _format_vector(mount_position),
                        "mass": "0",
                        "friction": "0.8 0.005 0.0001",
                        "rgba": "0.25 0.3 0.34 1",
                    },
                )
            elif attachment.require_contact:
                probe_position = list(attachment.parent_anchor)
                probe_position[2] += attachment.contact_probe_radius
                ET.SubElement(
                    parent_body,
                    "geom",
                    {
                        "name": attachment_probe_geom_name(attachment.id),
                        "type": "sphere",
                        "size": str(attachment.contact_probe_radius),
                        "pos": _format_vector(probe_position),
                        "mass": "0",
                        "friction": "1 0.005 0.0001",
                        "rgba": "0.95 0.65 0.08 1",
                    },
                )
            ET.SubElement(
                equality_element,
                attachment.constraint_type,
                {
                    "name": attachment_constraint_name(attachment.id),
                    "site1": parent_site_name,
                    "site2": child_site_name,
                    "active": "true" if attachment.initially_active else "false",
                    "solref": _format_vector(attachment.solref),
                    "solimp": _format_vector(attachment.solimp),
                },
            )

    if robot_contact_excludes:
        contact_element = ET.SubElement(root, "contact")
        for parent_name, child_name in robot_contact_excludes:
            ET.SubElement(
                contact_element,
                "exclude",
                {"body1": parent_name, "body2": child_name},
            )

    if robot_actuators:
        actuator_element = ET.SubElement(root, "actuator")
        for joint_name, actuator, _ in robot_actuators:
            attrs = {
                "name": _xml_name(actuator.id),
                "joint": joint_name,
                "ctrlrange": _format_vector(actuator.control_range),
                "ctrllimited": "true",
            }
            if actuator.max_force is not None:
                attrs.update(
                    {
                        "forcerange": _format_vector(
                            [-actuator.max_force, actuator.max_force]
                        ),
                        "forcelimited": "true",
                    }
                )
            if actuator.control_type == "position":
                attrs["kp"] = str(actuator.stiffness)
                if actuator.damping > 0:
                    attrs["kv"] = str(actuator.damping)
                ET.SubElement(actuator_element, "position", attrs)
            elif actuator.control_type == "velocity":
                attrs["kv"] = str(actuator.damping)
                ET.SubElement(actuator_element, "velocity", attrs)
            else:
                ET.SubElement(actuator_element, "motor", attrs)
    if robot_imu_sensors or robot_rangefinder_sensors:
        sensor_element = ET.SubElement(root, "sensor")
        for sensor, site_name in robot_imu_sensors:
            orientation_name, angular_velocity_name, linear_acceleration_name = (
                imu_sensor_channel_names(sensor.id)
            )
            ET.SubElement(
                sensor_element,
                "framequat",
                {
                    "name": orientation_name,
                    "objtype": "site",
                    "objname": site_name,
                },
            )
            ET.SubElement(
                sensor_element,
                "gyro",
                {"name": angular_velocity_name, "site": site_name},
            )
            ET.SubElement(
                sensor_element,
                "accelerometer",
                {"name": linear_acceleration_name, "site": site_name},
            )
        for sensor, site_name in robot_rangefinder_sensors:
            ET.SubElement(
                sensor_element,
                "rangefinder",
                {"name": rangefinder_sensor_name(sensor.id), "site": site_name},
            )
    if home_positions:
        keyframe = ET.SubElement(root, "keyframe")
        home_controls = [target for _, _, target in robot_actuators]
        key_attrs = {"name": "home", "qpos": _format_vector(home_positions)}
        if any(value != 0.0 for value in home_velocities):
            key_attrs["qvel"] = _format_vector(home_velocities)
        if home_controls:
            key_attrs["ctrl"] = _format_vector(home_controls)
        ET.SubElement(
            keyframe,
            "key",
            key_attrs,
        )

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode") + "\n"


def export_scene_to_mjcf(
    scene: Scene,
    path: str | Path,
    *,
    asset_root: str | Path | None = None,
) -> Path:
    """Write a scene as MJCF XML and return the output path."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(scene_to_mjcf_xml(scene, asset_root=asset_root), encoding="utf-8")
    return output_path


def _is_dynamic(actor: Actor) -> bool:
    return bool(_physics_value(actor, "dynamic", True))


def _mujoco_quaternion(value: list[float]) -> list[float]:
    x, y, z, w = value
    return [w, x, y, z]


def _rotate_vector(quaternion: list[float], vector: list[float]) -> list[float]:
    x, y, z, w = quaternion
    length = math.sqrt(x * x + y * y + z * z + w * w)
    if math.isclose(length, 0.0, abs_tol=1e-12):
        return list(vector)
    x, y, z, w = x / length, y / length, z / length, w / length
    vx, vy, vz = vector
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return [
        vx + w * tx + (y * tz - z * ty),
        vy + w * ty + (z * tx - x * tz),
        vz + w * tz + (x * ty - y * tx),
    ]


def _append_collider(
    body: Any,
    collider: Collider,
    mesh_names: dict[str, str],
    *,
    mass: float | None = None,
) -> None:
    geom_type = collider.geometry_type
    attrs = {
        "name": _xml_name(collider.id),
        "type": geom_type,
        "pos": _format_vector(collider.transform.position),
        "quat": _format_vector(_mujoco_quaternion(collider.transform.quaternion)),
        "friction": _format_vector(collider.friction),
        "rgba": "0.55 0.62 0.7 1",
    }
    if mass is not None:
        attrs["mass"] = str(mass)
    if geom_type == "mesh":
        mesh_name = mesh_names.get(collider.id)
        if mesh_name is None:
            raise ValueError(f"Robot mesh collider was not registered: {collider.id}")
        attrs["mesh"] = mesh_name
    else:
        attrs["size"] = _format_vector(collider.size)
    ET.SubElement(body, "geom", attrs)


def _append_articulation(
    parent: Any,
    articulation: Articulation,
    exported_actuators: list[tuple[str, Any, float]],
    exported_imu_sensors: list[tuple[Sensor, str]],
    exported_rangefinder_sensors: list[tuple[Sensor, str]],
    contact_excludes: list[tuple[str, str]],
    home_positions: list[float],
    home_velocities: list[float],
    mesh_names: dict[str, str],
) -> None:
    links = {link.id: link for link in articulation.links}
    joints_by_child = {joint.child_link_id: joint for joint in articulation.joints}
    children: dict[str, list[Link]] = {link.id: [] for link in articulation.links}
    for link in articulation.links:
        if link.parent_link_id in children:
            children[link.parent_link_id].append(link)
    contact_excludes.extend(
        (_xml_name(first.id), _xml_name(second.id))
        for first, second in combinations(articulation.links, 2)
    )

    joint_names: dict[str, str] = {}
    imu_sensors_by_link: dict[str, list[Sensor]] = {}
    rangefinder_sensors_by_link: dict[str, list[Sensor]] = {}
    for sensor in articulation.sensors:
        if sensor.sensor_type == "imu" and sensor.link_id is not None:
            imu_sensors_by_link.setdefault(sensor.link_id, []).append(sensor)
        elif sensor.sensor_type == "rangefinder" and sensor.link_id is not None:
            rangefinder_sensors_by_link.setdefault(sensor.link_id, []).append(sensor)

    def append_link(parent_body: Any, link: Link) -> None:
        body = ET.SubElement(
            parent_body,
            "body",
            {
                "name": _xml_name(link.id),
                "pos": _format_vector(link.transform.position),
                "quat": _format_vector(_mujoco_quaternion(link.transform.quaternion)),
            },
        )
        joint = joints_by_child.get(link.id)
        if joint is not None and joint.type != "fixed":
            joint_name = _xml_name(joint.id)
            axis = joint.axis
            attrs = {
                "name": joint_name,
                "type": "hinge" if joint.type in {"revolute", "continuous"} else "slide",
                "axis": _format_vector(axis),
            }
            if joint.child_frame is not None:
                attrs["pos"] = _format_vector(joint.child_frame.position)
                attrs["axis"] = _format_vector(
                    _rotate_vector(joint.child_frame.quaternion, axis)
                )
            if joint.limits and joint.limits.lower is not None and joint.limits.upper is not None:
                attrs["range"] = _format_vector([joint.limits.lower, joint.limits.upper])
                attrs["limited"] = "true"
            ET.SubElement(body, "joint", attrs)
            joint_names[joint.id] = joint_name
            home_positions.append(joint.initial_position)
            home_velocities.append(joint.initial_velocity)
        infer_inertia_from_colliders = bool(
            link.inertial is not None
            and link.inertial.diagonal_inertia is None
            and link.inertial.full_inertia is None
            and link.colliders
        )
        if link.inertial is not None and not infer_inertia_from_colliders:
            inertial_attrs = {
                "mass": str(link.inertial.mass),
                "pos": _format_vector(link.inertial.center_of_mass),
            }
            if link.inertial.diagonal_inertia is not None:
                inertial_attrs["diaginertia"] = _format_vector(
                    link.inertial.diagonal_inertia
                )
            elif link.inertial.full_inertia is not None:
                inertial_attrs["fullinertia"] = _format_vector(
                    link.inertial.full_inertia
                )
            ET.SubElement(body, "inertial", inertial_attrs)
        inferred_collider_mass = (
            link.inertial.mass / len(link.colliders)
            if infer_inertia_from_colliders and link.inertial is not None
            else None
        )
        for collider in link.colliders:
            _append_collider(
                body,
                collider,
                mesh_names,
                mass=inferred_collider_mass,
            )
        for sensor in imu_sensors_by_link.get(link.id, []):
            if sensor.local_transform is None:
                raise ValueError(f"IMU sensor requires local_transform: {sensor.id}")
            site_name = f"{_xml_name(sensor.id)}_site"
            ET.SubElement(
                body,
                "site",
                {
                    "name": site_name,
                    "pos": _format_vector(sensor.local_transform.position),
                    "quat": _format_vector(
                        _mujoco_quaternion(sensor.local_transform.quaternion)
                    ),
                    "type": "sphere",
                    "size": "0.005",
                    "rgba": "0.2 0.85 0.65 0.8",
                },
            )
            exported_imu_sensors.append((sensor, site_name))
        for sensor in rangefinder_sensors_by_link.get(link.id, []):
            if sensor.local_transform is None:
                raise ValueError(f"Rangefinder sensor requires local_transform: {sensor.id}")
            site_name = f"{_xml_name(sensor.id)}_site"
            ET.SubElement(
                body,
                "site",
                {
                    "name": site_name,
                    "pos": _format_vector(sensor.local_transform.position),
                    "quat": _format_vector(
                        _mujoco_quaternion(sensor.local_transform.quaternion)
                    ),
                    "type": "sphere",
                    "size": "0.004",
                    "rgba": "0.95 0.65 0.15 0.8",
                },
            )
            exported_rangefinder_sensors.append((sensor, site_name))
        for child in children[link.id]:
            append_link(body, child)

    append_link(parent, links[articulation.root_link_id])
    for actuator in articulation.actuators:
        joint_name = joint_names.get(actuator.joint_id)
        if joint_name is not None:
            joint = next(
                joint
                for joint in articulation.joints
                if joint.id == actuator.joint_id
            )
            if actuator.control_type == "position":
                target = (
                    actuator.target_position
                    if actuator.target_position is not None
                    else joint.initial_position
                )
            elif actuator.control_type == "velocity":
                target = actuator.target_velocity or 0.0
            else:
                target = 0.0
            exported_actuators.append((joint_name, actuator, target))


def _physics_value(actor: Actor, key: str, default: Any) -> Any:
    physics = actor.properties.get("physics")
    if isinstance(physics, dict) and key in physics:
        return physics[key]
    if key in actor.properties:
        return actor.properties[key]
    if isinstance(physics, dict) and "material" in physics:
        material = material_for_id(physics.get("material"))
        material_values = material.property_values()
        if key in material_values:
            return material_values[key]
    return default


def _collision_mesh_path(actor: Actor) -> str | None:
    geometry = actor.properties.get("geometry")
    if not isinstance(geometry, dict) or geometry.get("kind") != "mesh":
        return None
    value = geometry.get("collision_mesh")
    return str(value) if value else None


def _format_vector(value: Any) -> str:
    return " ".join(f"{float(item):.15g}" for item in value)


def _format_friction(value: Any) -> str:
    if isinstance(value, (int, float)):
        values = [float(value), 0.005, 0.0001]
    else:
        values = [float(item) for item in value]
    return _format_vector((values + [0.8, 0.005, 0.0001])[:3])


def imu_sensor_channel_names(sensor_id: str) -> tuple[str, str, str]:
    sensor_name = _xml_name(sensor_id)
    return (
        f"{sensor_name}_orientation",
        f"{sensor_name}_angular_velocity",
        f"{sensor_name}_linear_acceleration",
    )


def rangefinder_sensor_name(sensor_id: str) -> str:
    return f"{_xml_name(sensor_id)}_distance"


def attachment_constraint_name(attachment_id: str) -> str:
    return f"{_xml_name(attachment_id)}_connect"


def attachment_site_names(attachment_id: str) -> tuple[str, str]:
    name = _xml_name(attachment_id)
    return f"{name}_parent_site", f"{name}_child_site"


def attachment_probe_geom_name(attachment_id: str) -> str:
    return f"{_xml_name(attachment_id)}_contact_probe"


def attachment_gripper_cup_geom_name(attachment_id: str, index: int) -> str:
    name = _xml_name(attachment_id)
    return f"{name}_vacuum_cup_{index}"


def attachment_gripper_plate_geom_name(attachment_id: str) -> str:
    return f"{_xml_name(attachment_id)}_gripper_plate"


def attachment_gripper_mount_geom_name(attachment_id: str) -> str:
    return f"{_xml_name(attachment_id)}_gripper_mount"


def mujoco_name(value: str) -> str:
    """Return the deterministic XML-safe name used for stable BeeFoundrySim IDs."""
    return _xml_name(value)


def _xml_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "_-" else "_" for char in value.strip())
    return cleaned or "actor"
