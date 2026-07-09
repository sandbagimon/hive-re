import xml.etree.ElementTree as ET

import pytest

from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.models.transform import Transform
from simlab.services.mjcf_exporter import export_scene_to_mjcf, scene_to_mjcf_xml


def _scene_with_primitives() -> Scene:
    scene = Scene(name="MJCF Test")
    scene.actors.extend(
        [
            Actor(
                id="actor_001",
                name="Box",
                type="object",
                asset_id="primitive_box",
                transform=Transform(position=[1, 0, 0]),
                properties={
                    "primitive": "box",
                    "size": [0.5, 0.5, 0.5],
                    "mass": 1.0,
                    "rgba": [0.2, 0.5, 0.9, 1.0],
                },
            ),
            Actor(
                id="actor_002",
                name="Sphere",
                type="object",
                asset_id="primitive_sphere",
                properties={"primitive": "sphere", "size": [0.25]},
            ),
            Actor(
                id="actor_003",
                name="Cylinder",
                type="object",
                asset_id="primitive_cylinder",
                properties={"primitive": "cylinder", "size": [0.25, 0.75]},
            ),
        ]
    )
    return scene


def test_mjcf_export_contains_expected_geoms() -> None:
    xml = scene_to_mjcf_xml(_scene_with_primitives())
    root = ET.fromstring(xml)
    geom_types = [geom.attrib.get("type") for geom in root.findall(".//geom")]
    body_names = [body.attrib.get("name") for body in root.findall(".//body")]

    assert root.tag == "mujoco"
    assert "box" in geom_types
    assert "sphere" in geom_types
    assert "cylinder" in geom_types
    assert "actor_001" in body_names
    assert len(root.findall(".//freejoint")) == 3


def test_export_writes_scene_xml(tmp_path) -> None:
    output = export_scene_to_mjcf(_scene_with_primitives(), tmp_path / "scene.xml")

    assert output.exists()
    assert '<geom name="Box_geom" type="box"' in output.read_text(encoding="utf-8")


def test_exported_mjcf_can_load_with_mujoco_when_installed(tmp_path) -> None:
    mujoco = pytest.importorskip("mujoco")
    output = export_scene_to_mjcf(_scene_with_primitives(), tmp_path / "scene.xml")

    model = mujoco.MjModel.from_xml_path(str(output))

    assert model.nbody >= 4
