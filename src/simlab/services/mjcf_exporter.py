from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from simlab.models.actor import Actor
from simlab.models.scene import Scene

PRIMITIVE_GEOMS = {
    "primitive_box": "box",
    "primitive_sphere": "sphere",
    "primitive_cylinder": "cylinder",
    "box": "box",
    "sphere": "sphere",
    "cylinder": "cylinder",
}


def scene_to_mjcf_xml(scene: Scene) -> str:
    """Convert a SimLab scene into an MJCF XML string."""
    root = ET.Element("mujoco", {"model": scene.name})
    option = ET.SubElement(root, "option")
    option.set("timestep", str(scene.simulation_config.get("timestep", 0.01)))

    worldbody = ET.SubElement(root, "worldbody")
    ET.SubElement(worldbody, "light", {"name": "key_light", "pos": "0 0 4"})
    ET.SubElement(worldbody, "geom", {"name": "ground", "type": "plane", "size": "5 5 0.1"})

    for actor in scene.actors:
        if actor.type != "object":
            continue
        geom_type = _geom_type_for(actor)
        if geom_type is None:
            continue

        body = ET.SubElement(
            worldbody,
            "body",
            {"name": _xml_name(actor.name), "pos": _format_vector(actor.transform.position)},
        )
        geom_attrs = {
            "name": f"{_xml_name(actor.name)}_geom",
            "type": geom_type,
            "size": _format_size(actor.properties.get("size"), geom_type),
            "mass": str(actor.properties.get("mass", 1.0)),
            "rgba": _format_vector(actor.properties.get("rgba", [0.7, 0.7, 0.7, 1.0])),
        }
        ET.SubElement(body, "geom", geom_attrs)

    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode") + "\n"


def export_scene_to_mjcf(scene: Scene, path: str | Path) -> Path:
    """Write a scene as MJCF XML and return the output path."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(scene_to_mjcf_xml(scene), encoding="utf-8")
    return output_path


def _geom_type_for(actor: Actor) -> str | None:
    primitive = actor.properties.get("primitive")
    return PRIMITIVE_GEOMS.get(str(primitive), PRIMITIVE_GEOMS.get(actor.asset_id))


def _format_vector(value: Any) -> str:
    return " ".join(f"{float(item):g}" for item in value)


def _format_size(value: Any, geom_type: str) -> str:
    if value is None:
        value = [0.5, 0.5, 0.5] if geom_type == "box" else [0.5]
    values = [float(item) for item in value]
    if geom_type == "box":
        return _format_vector((values + [0.5, 0.5, 0.5])[:3])
    if geom_type == "cylinder":
        return _format_vector((values + [0.5, 1.0])[:2])
    return _format_vector((values + [0.5])[:1])


def _xml_name(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "_-" else "_" for char in value.strip())
    return cleaned or "actor"
