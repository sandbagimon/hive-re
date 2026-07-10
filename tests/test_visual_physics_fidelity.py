import json
import shutil
import subprocess
from pathlib import Path

import pytest

from simlab.models.scene import Scene
from simlab.services.mjcf_exporter import scene_to_mjcf_xml
from simlab.services.primitive_geometry import (
    collider_geometry,
    euler_xyz_to_mujoco_quaternion,
)
from simlab.services.project_service import load_scene

mujoco = pytest.importorskip("mujoco")


def _javascript_colliders(scene: Scene) -> dict[str, dict[str, object]]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is required for the TypeScript geometry contract test")
    contract_path = Path("src/simlab/web_viewport/generated/geometry-contract.js")
    script = f"""
      import {{ colliderGeometry }} from {json.dumps(contract_path.resolve().as_uri())};
      import fs from 'node:fs';
      const actors = JSON.parse(fs.readFileSync(0, 'utf8'));
      console.log(JSON.stringify(Object.fromEntries(
        actors.map((actor) => [actor.id, colliderGeometry(actor)]),
      )));
    """
    completed = subprocess.run(
        [node, "--input-type=module", "--eval", script],
        input=json.dumps([actor.to_dict() for actor in scene.actors]),
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


def test_viewport_contract_matches_mujoco_geometry_and_pose() -> None:
    scene = load_scene("examples/demo_project/scene.json")
    javascript_colliders = _javascript_colliders(scene)
    model = mujoco.MjModel.from_xml_string(scene_to_mjcf_xml(scene))
    geom_enums = {
        "box": mujoco.mjtGeom.mjGEOM_BOX,
        "sphere": mujoco.mjtGeom.mjGEOM_SPHERE,
        "cylinder": mujoco.mjtGeom.mjGEOM_CYLINDER,
        "ellipsoid": mujoco.mjtGeom.mjGEOM_ELLIPSOID,
        "plane": mujoco.mjtGeom.mjGEOM_PLANE,
    }

    assert model.ngeom == len(scene.actors)
    for actor in scene.actors:
        python_collider = collider_geometry(actor)
        javascript_collider = javascript_colliders[actor.id]
        geom_id = mujoco.mj_name2id(
            model,
            mujoco.mjtObj.mjOBJ_GEOM,
            f"{actor.id}_geom",
        )
        assert geom_id >= 0
        assert javascript_collider["geomType"] == python_collider.geom_type
        assert javascript_collider["size"] == pytest.approx(python_collider.size)
        assert model.geom_type[geom_id] == geom_enums[python_collider.geom_type]
        assert model.geom_size[geom_id][: len(python_collider.size)] == pytest.approx(
            python_collider.size
        )

        body_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, actor.id)
        actual_position = model.body_pos[body_id] if body_id >= 0 else model.geom_pos[geom_id]
        actual_quaternion = model.body_quat[body_id] if body_id >= 0 else model.geom_quat[geom_id]
        assert actual_position == pytest.approx(actor.transform.position)
        assert actual_quaternion == pytest.approx(
            euler_xyz_to_mujoco_quaternion(actor.transform.rotation)
        )


def test_demo_ball_contacts_visible_ramp_then_visible_ground() -> None:
    scene = load_scene("examples/demo_project/scene.json")
    model = mujoco.MjModel.from_xml_string(scene_to_mjcf_xml(scene))
    data = mujoco.MjData(model)
    mujoco.mj_forward(model, data)
    sphere_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "actor_003")
    initial_position = data.xpos[sphere_body].copy()
    contact_pairs: set[frozenset[str]] = set()

    for _ in range(200):
        mujoco.mj_step(model, data)
        for contact_index in range(data.ncon):
            contact = data.contact[contact_index]
            names = (
                mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, contact.geom1),
                mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, contact.geom2),
            )
            contact_pairs.add(frozenset(name for name in names if name))

    final_position = data.xpos[sphere_body]
    assert initial_position == pytest.approx([-0.9, 0.0, 1.1])
    assert frozenset({"actor_002_geom", "actor_003_geom"}) in contact_pairs
    assert frozenset({"actor_001_geom", "actor_003_geom"}) in contact_pairs
    assert final_position[0] > initial_position[0] + 2.0
    assert 0.2 <= final_position[2] <= 0.35
