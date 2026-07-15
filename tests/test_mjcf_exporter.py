import xml.etree.ElementTree as ET

import pytest

from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.models.transform import Transform
from simlab.services.mjcf_exporter import export_scene_to_mjcf, scene_to_mjcf_xml
from simlab.services.openusd_importer import import_openusd_asset


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


def test_empty_scene_does_not_export_hidden_collision_geometry() -> None:
    root = ET.fromstring(scene_to_mjcf_xml(Scene(name="Empty")))

    assert root.findall(".//geom") == []


def test_mjcf_export_distinguishes_static_and_dynamic_actors() -> None:
    scene = Scene(name="Physics Test")
    scene.actors.extend(
        [
            Actor(
                id="actor_dynamic",
                name="Ball",
                type="object",
                asset_id="primitive_sphere",
                transform=Transform(position=[0, 0, 1]),
                properties={
                    "primitive": "sphere",
                    "size": [0.25],
                    "physics": {"dynamic": True, "mass": 2.0, "friction": [0.7, 0.004, 0.0001]},
                },
            ),
            Actor(
                id="actor_ground",
                name="Ground",
                type="object",
                asset_id="primitive_ground",
                properties={
                    "primitive": "plane",
                    "size": [4.0, 4.0, 0.1],
                    "physics": {"dynamic": False, "friction": [1.0, 0.005, 0.0001]},
                },
            ),
        ]
    )

    root = ET.fromstring(scene_to_mjcf_xml(scene))
    dynamic_body = root.find(".//body[@name='actor_dynamic']")
    static_geom = root.find(".//geom[@name='actor_ground_geom']")

    assert dynamic_body is not None
    assert dynamic_body.find("freejoint") is not None
    assert dynamic_body.find("geom").attrib["mass"] == "2.0"
    assert static_geom is not None
    assert static_geom.attrib["type"] == "plane"
    assert static_geom.attrib["friction"] == "1 0.005 0.0001"
    assert root.find(".//body[@name='actor_ground']") is None


def test_mjcf_export_bakes_scale_and_uses_quaternion_rotation() -> None:
    scene = Scene(
        actors=[
            Actor(
                id="actor_scaled",
                name="Scaled Box",
                type="object",
                asset_id="primitive_box",
                transform=Transform(rotation=[0.0, 0.0, 0.45], scale=[2.0, 3.0, 4.0]),
                properties={"primitive": "box", "size": [0.5, 1.0, 1.5]},
            ),
            Actor(
                id="actor_ellipsoid",
                name="Scaled Sphere",
                type="object",
                asset_id="primitive_sphere",
                transform=Transform(scale=[1.0, 2.0, 3.0]),
                properties={"primitive": "sphere", "size": [0.25]},
            ),
        ]
    )

    root = ET.fromstring(scene_to_mjcf_xml(scene))
    box_body = root.find(".//body[@name='actor_scaled']")
    ellipsoid = root.find(".//body[@name='actor_ellipsoid']/geom")

    assert box_body is not None
    assert [float(value) for value in box_body.attrib["quat"].split()] == pytest.approx(
        [0.9747941070689433, 0.0, 0.0, 0.22310636213174545]
    )
    assert box_body.find("geom").attrib["size"] == "1 3 6"
    assert "euler" not in box_body.attrib
    assert ellipsoid is not None
    assert ellipsoid.attrib["type"] == "ellipsoid"
    assert ellipsoid.attrib["size"] == "0.25 0.5 0.75"


def test_mjcf_export_applies_density_and_material_contact_parameters() -> None:
    scene = Scene(
        actors=[
            Actor(
                id="actor_rubber",
                name="Rubber Ball",
                type="object",
                asset_id="primitive_sphere",
                properties={
                    "primitive": "sphere",
                    "size": [0.25],
                    "physics": {
                        "dynamic": True,
                        "material": "rubber",
                        "mass_mode": "density",
                    },
                },
            )
        ]
    )

    root = ET.fromstring(scene_to_mjcf_xml(scene))
    geom = root.find(".//body[@name='actor_rubber']/geom")

    assert geom is not None
    assert geom.attrib["density"] == "1100.0"
    assert "mass" not in geom.attrib
    assert geom.attrib["friction"] == "1.2 0.01 0.0002"
    assert geom.attrib["solref"] == "0.03 1"
    assert len(geom.attrib["solimp"].split()) == 5


def test_export_writes_scene_xml(tmp_path) -> None:
    output = export_scene_to_mjcf(_scene_with_primitives(), tmp_path / "scene.xml")

    assert output.exists()
    assert '<geom name="actor_001_geom" type="box"' in output.read_text(encoding="utf-8")


def test_exported_mjcf_can_load_with_mujoco_when_installed(tmp_path) -> None:
    mujoco = pytest.importorskip("mujoco")
    output = export_scene_to_mjcf(_scene_with_primitives(), tmp_path / "scene.xml")

    model = mujoco.MjModel.from_xml_path(str(output))

    assert model.nbody >= 4


def test_external_usd_robot_exports_compilable_articulation(tmp_path) -> None:
    mujoco = pytest.importorskip("mujoco")
    imported = import_openusd_asset(
        "tests/fixtures/openusd/robot_arm/external_two_joint_arm.usda", tmp_path
    )
    assert imported.robotics_model is not None
    scene = Scene(
        name="External Arm Physics",
        actors=[
            Actor(
                id="actor_arm",
                name="Arm",
                type="robot",
                asset_id=imported.asset["id"],
                properties=imported.asset["default_properties"],
            )
        ],
        robotics=imported.robotics_model,
    )

    xml = scene_to_mjcf_xml(scene, asset_root=tmp_path)
    root = ET.fromstring(xml)
    joints = root.findall(".//joint")
    actuators = root.findall("./actuator/position")

    assert len(joints) == 2
    assert len(root.findall(".//freejoint")) == 0
    assert joints[0].attrib["type"] == "hinge"
    assert [float(value) for value in joints[0].attrib["range"].split()] == pytest.approx(
        [-1.57079632679, 1.57079632679]
    )
    assert len(actuators) == 2
    assert actuators[0].attrib["kp"] == "120.0"
    assert [float(value) for value in actuators[0].attrib["ctrlrange"].split()] == pytest.approx(
        [-1.5707963267948966, 1.5707963267948966]
    )
    model = mujoco.MjModel.from_xml_string(xml)
    assert model.njnt == 2
    assert model.nu == 2
    assert model.nbody == 5
    assert model.key_qpos[0, 1] == pytest.approx(-0.4)


def test_robot_and_free_body_home_keyframe_has_complete_qpos(tmp_path) -> None:
    mujoco = pytest.importorskip("mujoco")
    imported = import_openusd_asset(
        "tests/fixtures/openusd/robot_arm/external_two_joint_arm.usda", tmp_path
    )
    scene = Scene(
        actors=[
            Actor(
                id="actor_ball",
                name="Ball",
                type="object",
                asset_id="primitive_sphere",
                transform=Transform(position=[1, 2, 3]),
                properties={"primitive": "sphere", "size": [0.2]},
            ),
            Actor(
                id="actor_arm",
                name="Arm",
                type="robot",
                asset_id=imported.asset["id"],
                properties=imported.asset["default_properties"],
            ),
        ],
        robotics=imported.robotics_model,
    )

    model = mujoco.MjModel.from_xml_string(scene_to_mjcf_xml(scene, asset_root=tmp_path))

    assert model.nq == 9
    assert model.key_qpos.shape == (1, 9)
    assert model.key_qpos[0, :3] == pytest.approx([1, 2, 3])
    assert model.key_qpos[0, -1] == pytest.approx(-0.4)
