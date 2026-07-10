from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from simlab.models.actor import Actor
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
