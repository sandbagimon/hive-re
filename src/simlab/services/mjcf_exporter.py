from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from simlab.models.actor import Actor
from simlab.models.robotics import Articulation, Collider, Link
from simlab.models.scene import Scene
from simlab.services.openusd_importer import resolve_imported_asset_path
from simlab.services.physics_materials import material_for_id
from simlab.services.primitive_geometry import (
    collider_geometry,
    euler_xyz_to_mujoco_quaternion,
)


def scene_to_mjcf_xml(scene: Scene, *, asset_root: str | Path | None = None) -> str:
    """Convert a SimLab scene into an MJCF XML string."""
    root = ET.Element("mujoco", {"model": scene.name})
    ET.SubElement(root, "compiler", {"angle": "radian"})
    option = ET.SubElement(root, "option")
    option.set("timestep", str(scene.simulation_config.get("timestep", 0.01)))

    mesh_assets = ET.SubElement(root, "asset")
    mesh_names: dict[str, str] = {}
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
    if not mesh_names:
        root.remove(mesh_assets)

    worldbody = ET.SubElement(root, "worldbody")
    ET.SubElement(worldbody, "light", {"name": "key_light", "pos": "0 0 4"})
    robot_actuators: list[tuple[str, Any, float]] = []
    robot_contact_excludes: list[tuple[str, str]] = []
    home_positions: list[float] = []

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
            collider = collider_geometry(actor)
            geom_attrs = {
                "name": f"{_xml_name(actor.id)}_geom",
                "type": collider.geom_type,
                "size": _format_vector(collider.size),
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
                articulation = articulations.get(str(articulation_id))
                if articulation is None:
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
                _append_articulation(
                    wrapper,
                    articulation,
                    robot_actuators,
                    robot_contact_excludes,
                    home_positions,
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
    if home_positions:
        keyframe = ET.SubElement(root, "keyframe")
        home_controls = [initial for _, _, initial in robot_actuators]
        key_attrs = {"name": "home", "qpos": _format_vector(home_positions)}
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


def _append_collider(body: Any, collider: Collider) -> None:
    geom_type = collider.geometry_type
    attrs = {
        "name": _xml_name(collider.id),
        "type": geom_type if geom_type != "capsule" else "capsule",
        "size": _format_vector(collider.size),
        "pos": _format_vector(collider.transform.position),
        "quat": _format_vector(_mujoco_quaternion(collider.transform.quaternion)),
        "friction": _format_vector(collider.friction),
        "rgba": "0.55 0.62 0.7 1",
    }
    ET.SubElement(body, "geom", attrs)


def _append_articulation(
    parent: Any,
    articulation: Articulation,
    exported_actuators: list[tuple[str, Any, float]],
    contact_excludes: list[tuple[str, str]],
    home_positions: list[float],
) -> None:
    links = {link.id: link for link in articulation.links}
    joints_by_child = {joint.child_link_id: joint for joint in articulation.joints}
    children: dict[str, list[Link]] = {link.id: [] for link in articulation.links}
    for link in articulation.links:
        if link.parent_link_id in children:
            children[link.parent_link_id].append(link)

    joint_names: dict[str, str] = {}

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
            attrs = {
                "name": joint_name,
                "type": "hinge" if joint.type in {"revolute", "continuous"} else "slide",
                "axis": _format_vector(joint.axis),
            }
            if joint.limits and joint.limits.lower is not None and joint.limits.upper is not None:
                attrs["range"] = _format_vector([joint.limits.lower, joint.limits.upper])
                attrs["limited"] = "true"
            ET.SubElement(body, "joint", attrs)
            joint_names[joint.id] = joint_name
            home_positions.append(joint.initial_position)
        if link.parent_link_id is not None:
            contact_excludes.append(
                (_xml_name(link.parent_link_id), _xml_name(link.id))
            )
        if link.inertial is not None:
            inertial_attrs = {
                "mass": str(link.inertial.mass),
                "pos": _format_vector(link.inertial.center_of_mass),
            }
            if link.inertial.diagonal_inertia is not None:
                inertial_attrs["diaginertia"] = _format_vector(
                    link.inertial.diagonal_inertia
                )
            ET.SubElement(body, "inertial", inertial_attrs)
        for collider in link.colliders:
            _append_collider(body, collider)
        for child in children[link.id]:
            append_link(body, child)

    append_link(parent, links[articulation.root_link_id])
    for actuator in articulation.actuators:
        joint_name = joint_names.get(actuator.joint_id)
        if joint_name is not None:
            initial = next(
                joint.initial_position
                for joint in articulation.joints
                if joint.id == actuator.joint_id
            )
            exported_actuators.append((joint_name, actuator, initial))


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


def _xml_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "_-" else "_" for char in value.strip())
    return cleaned or "actor"
