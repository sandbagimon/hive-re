import pytest

from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.services.project_service import ProjectValidationError, load_scene, save_scene


def test_save_and_load_scene_json(tmp_path) -> None:
    scene = Scene(name="Saved Scene")
    scene.actors.append(
        Actor(
            id="actor_001",
            name="Box",
            type="object",
            asset_id="primitive_box",
            properties={"primitive": "box"},
        )
    )
    path = tmp_path / "scene.json"

    save_scene(path, scene)
    loaded = load_scene(path)

    assert path.read_text(encoding="utf-8").startswith("{\n  ")
    assert loaded.name == "Saved Scene"
    assert loaded.actors[0].asset_id == "primitive_box"


def test_load_rejects_duplicate_actor_ids(tmp_path) -> None:
    path = tmp_path / "scene.json"
    path.write_text(
        """
{
  "version": "1.0",
  "name": "Invalid",
  "units": "meters",
  "actors": [
    {
      "id": "actor_001",
      "name": "Box A",
      "type": "object",
      "asset_id": "primitive_box",
      "transform": {
        "position": [0, 0, 0],
        "rotation": [0, 0, 0],
        "scale": [1, 1, 1]
      },
      "properties": {}
    },
    {
      "id": "actor_001",
      "name": "Box B",
      "type": "object",
      "asset_id": "primitive_box",
      "transform": {
        "position": [0, 0, 0],
        "rotation": [0, 0, 0],
        "scale": [1, 1, 1]
      },
      "properties": {}
    }
  ],
  "simulation_config": {}
}
""",
        encoding="utf-8",
    )

    with pytest.raises(ProjectValidationError):
        load_scene(path)
