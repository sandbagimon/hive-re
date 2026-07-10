import json
from pathlib import Path


def test_shared_scene_physics_and_bridge_schemas_are_declared() -> None:
    root = Path("shared/schemas")
    scene = json.loads((root / "scene.schema.json").read_text(encoding="utf-8"))
    physics = json.loads((root / "physics.schema.json").read_text(encoding="utf-8"))
    bridge = json.loads((root / "bridge-protocol.schema.json").read_text(encoding="utf-8"))

    assert scene["title"] == "SimLabScene"
    assert "physics" in scene["$defs"]["actor"]["properties"]["properties"]["properties"]
    assert {"rubber", "wood", "metal", "ice"}.issubset(
        physics["properties"]["material"]["enum"]
    )
    assert "runSimulation" in bridge["properties"]["rpc_methods"]["const"]
    assert "importOpenUsd" in bridge["properties"]["rpc_methods"]["const"]
    assert "getVisualGeometry" in bridge["properties"]["rpc_methods"]["const"]
    assert "simulationStateChanged" in bridge["properties"]["events"]["const"]
    assert "meshGeometry" in scene["$defs"]
