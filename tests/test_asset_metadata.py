import json
from pathlib import Path


def test_physics_playground_assets_are_declared() -> None:
    metadata = json.loads(Path("assets/metadata.json").read_text(encoding="utf-8"))
    assets = {asset["id"]: asset for asset in metadata["assets"]}

    assert {"primitive_ground", "primitive_table", "primitive_ramp"}.issubset(assets)
    assert assets["primitive_ground"]["default_properties"]["physics"]["dynamic"] is False
    assert assets["primitive_ground"]["primitive"] == "box"
    assert assets["primitive_ground"]["default_transform"]["position"] == [0.0, 0.0, -0.05]
    assert assets["primitive_table"]["default_properties"]["physics"]["dynamic"] is False
    assert assets["primitive_ramp"]["default_transform"]["rotation"] == [0.0, 0.45, 0.0]
    assert assets["primitive_sphere"]["default_properties"]["physics"]["dynamic"] is True
    assert assets["primitive_sphere"]["default_properties"]["physics"]["material"] == "rubber"
    assert assets["primitive_box"]["default_properties"]["physics"]["mass_mode"] == "density"
