from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.services.physics_materials import material_for_id
from simlab.services.primitive_geometry import (
    collider_geometry,
    euler_xyz_to_mujoco_quaternion,
)


def scene_to_mjcf_xml(scene: Scene) -> str:
    """Convert a SimLab scene into an MJCF XML string."""
    root = ET.Element("mujoco", {"model": scene.name})
    option = ET.SubElement(root, "option")
    option.set("timestep", str(scene.simulation_config.get("timestep", 0.01)))

    worldbody = ET.SubElement(root, "worldbody")
    ET.SubElement(worldbody, "light", {"name": "key_light", "pos": "0 0 4"})

    for actor in scene.actors:
        if actor.type != "object":
            continue
        collider = collider_geometry(actor)

        geom_attrs = {
            "name": f"{_xml_name(actor.id)}_geom",
            "type": collider.geom_type,
            "size": _format_vector(collider.size),
            "rgba": _format_vector(actor.properties.get("rgba", [0.7, 0.7, 0.7, 1.0])),
            "friction": _format_friction(_physics_value(actor, "friction", [0.8, 0.005, 0.0001])),
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

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode") + "\n"


def export_scene_to_mjcf(scene: Scene, path: str | Path) -> Path:
    """Write a scene as MJCF XML and return the output path."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(scene_to_mjcf_xml(scene), encoding="utf-8")
    return output_path


def _is_dynamic(actor: Actor) -> bool:
    return bool(_physics_value(actor, "dynamic", True))


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
