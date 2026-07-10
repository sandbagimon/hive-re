import json
from pathlib import Path

from PySide6.QtWidgets import QApplication, QWidget

from simlab.editor_bridge import EditorBridge
from simlab.services.project_service import load_scene


def _bridge() -> EditorBridge:
    app = QApplication.instance() or QApplication([])
    assert app is not None
    parent = QWidget()
    return EditorBridge(parent, Path.cwd())


def test_editor_bridge_returns_enriched_assets() -> None:
    bridge = _bridge()

    response = json.loads(bridge.getAssets())

    assert response["ok"] is True
    sphere = next(
        asset for asset in response["data"]["assets"] if asset["id"] == "primitive_sphere"
    )
    physics = sphere["default_properties"]["physics"]
    assert physics["material"] == "rubber"
    assert len(physics["solimp"]) == 5


def test_editor_bridge_preflight_uses_scene_snapshot() -> None:
    bridge = _bridge()
    scene = load_scene("examples/demo_project/scene.json")

    response = json.loads(bridge.preflight(json.dumps(scene.to_dict())))

    assert response["ok"] is True
    assert response["data"]["valid"] is True
    assert response["data"]["issues"] == []
