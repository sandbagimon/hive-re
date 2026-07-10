import json
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QFileDialog, QWidget

from simlab.editor_bridge import EditorBridge
from simlab.services.project_service import load_scene


def _bridge(project_root: Path | None = None) -> EditorBridge:
    app = QApplication.instance() or QApplication([])
    assert app is not None
    parent = QWidget()
    return EditorBridge(parent, project_root or Path.cwd())


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


def test_editor_bridge_imports_openusd_and_serves_visual_geometry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("pxr")
    source = Path("tests/fixtures/openusd/tetrahedron.usda").resolve()
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(source), ""))
    bridge = _bridge(tmp_path)

    response = json.loads(bridge.importOpenUsd())

    assert response["ok"] is True
    asset = response["data"]["asset"]
    assert asset["source_format"] == "openusd"
    cache_path = asset["default_properties"]["geometry"]["visual_cache"]
    geometry_response = json.loads(bridge.getVisualGeometry(cache_path))
    assert geometry_response["ok"] is True
    assert len(geometry_response["data"]["positions"]) == 12
