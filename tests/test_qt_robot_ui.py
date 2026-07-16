from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("SIMLAB_QT_WEBENGINE_E2E") != "1",
    reason="Set SIMLAB_QT_WEBENGINE_E2E=1 to run the QtWebEngine visual smoke test.",
)


def _wait_until(app: Any, predicate: Any, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Timed out waiting for QtWebEngine state")


def _javascript(app: Any, page: Any, script: str) -> Any:
    result: list[Any] = []
    page.runJavaScript(script, lambda value: result.append(value))
    _wait_until(app, lambda: bool(result))
    return result[0]


def _pump_events(app: Any, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)


def test_qt_webengine_renders_imported_robot_joint_ui(tmp_path: Path) -> None:
    pytest.importorskip("pxr")
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QApplication

    from simlab.main_window import MainWindow

    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "metadata.json").write_text('{"assets": []}\n', encoding="utf-8")
    app = QApplication.instance() or QApplication([])
    window = MainWindow(project_root=tmp_path)
    window.show()
    loaded: list[bool] = []
    window.web_view.loadFinished.connect(loaded.append)
    _wait_until(app, lambda: bool(loaded))
    assert loaded[-1] is True
    _wait_until(
        app,
        lambda: bool(_javascript(app, window.web_view.page(), "window.simlabEditorReady === true")),
    )

    source = Path(
        "tests/fixtures/openusd/robot_arm/external_two_joint_arm.usda"
    ).resolve()
    source_json = json.dumps(str(source))
    _javascript(
        app,
        window.web_view.page(),
        f"window.simlabEditor.importOpenUsdPath({source_json}).then("
        "result => document.documentElement.dataset.robotImport = JSON.stringify(result)); true",
    )
    _wait_until(
        app,
        lambda: bool(
            _javascript(
                app,
                window.web_view.page(),
                "document.documentElement.dataset.robotImport || ''",
            )
        ),
    )
    import_result = json.loads(
        _javascript(
            app,
            window.web_view.page(),
            "document.documentElement.dataset.robotImport",
        )
    )
    assert import_result["ok"] is True
    state = json.loads(
        _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
    )
    actor_id = state["scene"]["actors"][0]["id"]
    articulation = state["scene"]["robotics"]["articulations"][0]
    joint_id = articulation["joints"][0]["id"]
    assert _javascript(
        app,
        window.web_view.page(),
        f"window.simlabEditor.selectJoint({json.dumps(actor_id)}, {json.dumps(joint_id)})",
    ) is True
    app.processEvents()

    ui = json.loads(
        _javascript(
            app,
            window.web_view.page(),
            "JSON.stringify({"
            "joints:document.querySelectorAll('[data-joint-id]').length,"
            "selected:document.querySelectorAll('[data-joint-id].selected').length,"
            "inspector:document.querySelector('#property-inspector h3')?.textContent,"
            "controls:document.querySelectorAll('[data-joint-jog]').length,"
            "canvas:[document.querySelector('#viewport').width,document.querySelector('#viewport').height]"
            "})",
        )
    )
    assert ui["joints"] == 2
    assert ui["selected"] == 1
    assert ui["inspector"] == "Joint"
    assert ui["controls"] == 2
    assert ui["canvas"][0] > 300 and ui["canvas"][1] > 300

    window.web_view.update()
    window.repaint()
    _pump_events(app, 1.0)
    screenshot = window.web_view.grab()
    output = Path(os.environ.get("SIMLAB_QT_SCREENSHOT", tmp_path / "robot-joint-ui.png"))
    assert screenshot.save(str(output))
    image = screenshot.toImage()
    colors = {
        QColor(image.pixel(x, y)).rgb()
        for x in range(0, image.width(), max(image.width() // 20, 1))
        for y in range(0, image.height(), max(image.height() // 20, 1))
    }
    assert len(colors) > 10
    window.bridge.dirty = False
    window.close()
