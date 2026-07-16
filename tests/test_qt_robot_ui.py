from __future__ import annotations

import json
import math
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

    _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-command=\"run\"]').click(); true",
    )
    _wait_until(
        app,
        lambda: json.loads(
            _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
        )["simulationStatus"] == "running",
    )
    home_runtime = json.loads(
        _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
    )["simulationState"]
    _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-joint-step]').value='0.5';"
        "document.querySelector('[data-joint-step]').dispatchEvent("
        "new Event('change',{bubbles:true}));"
        "document.querySelector('[data-joint-jog][data-direction=\"1\"]').click();true",
    )

    def robot_has_moved() -> bool:
        current = json.loads(
            _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
        )
        runtime = current["simulationState"]
        return bool(
            current["simulationStatus"] == "running"
            and runtime
            and runtime["controller"]["status"] == "active"
            and runtime["actuators"][0]["ctrl"] == pytest.approx(0.5)
            and runtime["joints"][0]["qpos"] > 0.1
        )

    _wait_until(app, robot_has_moved)
    running_state = json.loads(
        _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
    )
    running_runtime = running_state["simulationState"]
    assert running_state["simulationStatus"] == "running"
    assert running_state["validationIssues"] == []
    assert running_runtime["time"] > home_runtime["time"]
    child_link_id = articulation["joints"][0]["child_link_id"]
    home_link = next(item for item in home_runtime["links"] if item["id"] == child_link_id)
    moved_link = next(item for item in running_runtime["links"] if item["id"] == child_link_id)
    assert math.dist(home_link["quaternion"], moved_link["quaternion"]) > 0.01
    live_position = _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-joint-position-field]').value",
    )
    assert abs(float(live_position)) > 0.1

    _pump_events(app, 0.3)
    running_screenshot = window.web_view.grab()
    running_output = Path(
        os.environ.get(
            "SIMLAB_QT_RUNNING_SCREENSHOT",
            tmp_path / "robot-joint-running.png",
        )
    )
    assert running_screenshot.save(str(running_output))

    _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-command=\"pause\"]').click(); true",
    )
    _wait_until(
        app,
        lambda: json.loads(
            _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
        )["simulationStatus"] == "paused",
    )
    paused_time = json.loads(
        _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
    )["simulationState"]["time"]
    _pump_events(app, 0.2)
    assert json.loads(
        _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
    )["simulationState"]["time"] == pytest.approx(paused_time)

    _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-command=\"reset\"]').click(); true",
    )

    def robot_is_home() -> bool:
        current = json.loads(
            _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
        )
        runtime = current["simulationState"]
        return bool(
            current["simulationStatus"] == "paused"
            and runtime
            and runtime["time"] == 0
            and runtime["controller"]["status"] == "ready"
            and abs(runtime["joints"][0]["qpos"]) < 1e-9
        )

    _wait_until(app, robot_is_home)

    _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-joint-step]').value='0.5';"
        "document.querySelector('[data-joint-step]').dispatchEvent("
        "new Event('change',{bubbles:true}));"
        "document.querySelector('[data-joint-jog][data-direction=\"1\"]').click();true",
    )
    _wait_until(
        app,
        lambda: json.loads(
            _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
        )["simulationState"]["actuators"][0]["ctrl"]
        == pytest.approx(0.5),
    )
    _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-trajectory-name]').value='Qt Arm Motion';"
        "document.querySelector('[data-trajectory-name]').dispatchEvent("
        "new Event('change',{bubbles:true}));"
        "document.querySelector('[data-trajectory-duration]').value='0.8';"
        "document.querySelector('[data-trajectory-duration]').dispatchEvent("
        "new Event('change',{bubbles:true}));"
        "document.querySelector('[data-trajectory-command=\"load\"]').click();true",
    )

    def trajectory_is_loaded() -> bool:
        current = json.loads(
            _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
        )
        runtime = current["simulationState"]
        trajectory = runtime["trajectory"]
        return bool(
            current["simulationStatus"] == "paused"
            and trajectory["name"] == "Qt Arm Motion"
            and trajectory["status"] == "stopped"
            and trajectory["duration"] == pytest.approx(0.8)
            and trajectory["time"] == 0
            and runtime["actuators"][0]["ctrl"] == pytest.approx(0)
        )

    _wait_until(app, trajectory_is_loaded)
    _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-trajectory-command=\"play\"]').click();true",
    )

    def trajectory_is_in_progress() -> bool:
        current = json.loads(
            _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
        )
        trajectory = current["simulationState"]["trajectory"]
        return bool(
            current["simulationStatus"] == "running"
            and trajectory["status"] == "playing"
            and 0.1 < trajectory["time"] < trajectory["duration"]
        )

    _wait_until(app, trajectory_is_in_progress)
    _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-trajectory-command=\"pause\"]').click();true",
    )

    def trajectory_is_paused() -> bool:
        current = json.loads(
            _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
        )
        return bool(
            current["simulationStatus"] == "paused"
            and current["simulationState"]["trajectory"]["status"] == "paused"
        )

    _wait_until(app, trajectory_is_paused)
    paused_trajectory_state = json.loads(
        _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
    )["simulationState"]
    _pump_events(app, 0.2)
    frozen_trajectory_state = json.loads(
        _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
    )["simulationState"]
    assert frozen_trajectory_state["time"] == pytest.approx(paused_trajectory_state["time"])
    assert frozen_trajectory_state["trajectory"]["time"] == pytest.approx(
        paused_trajectory_state["trajectory"]["time"]
    )

    _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-trajectory-command=\"stop\"]').click();true",
    )
    _wait_until(app, trajectory_is_loaded)
    _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-trajectory-command=\"play\"]').click();true",
    )

    def trajectory_is_completed() -> bool:
        current = json.loads(
            _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
        )
        runtime = current["simulationState"]
        trajectory = runtime["trajectory"]
        return bool(
            current["simulationStatus"] == "paused"
            and trajectory["status"] == "completed"
            and trajectory["time"] == pytest.approx(trajectory["duration"])
            and runtime["actuators"][0]["ctrl"] == pytest.approx(0.5)
            and runtime["joints"][0]["qpos"] > 0.1
        )

    _wait_until(app, trajectory_is_completed)
    completed_state = json.loads(
        _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
    )["simulationState"]
    completed_link = next(
        item for item in completed_state["links"] if item["id"] == child_link_id
    )
    assert math.dist(home_link["quaternion"], completed_link["quaternion"]) > 0.01
    trajectory_ui = json.loads(
        _javascript(
            app,
            window.web_view.page(),
            "JSON.stringify({"
            "status:document.querySelector('#trajectory-status').textContent,"
            "time:document.querySelector('[data-trajectory-time]').textContent,"
            "progress:document.querySelector('[data-trajectory-progress]').value,"
            "max:document.querySelector('[data-trajectory-progress]').max"
            "})",
        )
    )
    assert trajectory_ui["status"] == "completed"
    assert trajectory_ui["time"] == "0.80 / 0.80 s"
    assert trajectory_ui["progress"] == pytest.approx(trajectory_ui["max"])

    _pump_events(app, 0.3)
    trajectory_screenshot = window.web_view.grab()
    trajectory_output = Path(
        os.environ.get(
            "SIMLAB_QT_TRAJECTORY_SCREENSHOT",
            tmp_path / "robot-trajectory-completed.png",
        )
    )
    assert trajectory_screenshot.save(str(trajectory_output))

    editor_history_before_keyframes = json.loads(
        _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
    )
    _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-keyframe-add]').click();true",
    )
    _wait_until(
        app,
        lambda: _javascript(
            app,
            window.web_view.page(),
            "document.querySelectorAll('[data-keyframe-id]').length",
        )
        == 3,
    )
    keyframe_time_selector = json.dumps(
        '[data-keyframe-id="keyframe-2"] [data-keyframe-time]'
    )
    _javascript(
        app,
        window.web_view.page(),
        f"(()=>{{const input=document.querySelector({keyframe_time_selector});"
        "input.value='0.4';input.dispatchEvent(new Event('change',{bubbles:true}));"
        "return true})()",
    )
    _wait_until(
        app,
        lambda: json.loads(
            _javascript(
                app,
                window.web_view.page(),
                "JSON.stringify([...document.querySelectorAll('[data-keyframe-id]')].map("
                "row=>row.dataset.keyframeId))",
            )
        )
        == ["keyframe-0", "keyframe-2", "keyframe-1"],
    )
    target_selector = json.dumps(
        f'[data-keyframe-id="keyframe-2"] [data-keyframe-target="{joint_id}"]'
    )
    _javascript(
        app,
        window.web_view.page(),
        f"const target=document.querySelector({target_selector});"
        "target.value='-0.4';target.dispatchEvent(new Event('change',{bubbles:true}));true",
    )
    keyframe_ui = json.loads(
        _javascript(
            app,
            window.web_view.page(),
            "JSON.stringify([...document.querySelectorAll('[data-keyframe-id]')].map(row=>({"
            "id:row.dataset.keyframeId,"
            "time:Number(row.querySelector('[data-keyframe-time]').value)"
            "})))",
        )
    )
    assert keyframe_ui == [
        {"id": "keyframe-0", "time": 0},
        {"id": "keyframe-2", "time": 0.4},
        {"id": "keyframe-1", "time": 0.8},
    ]
    editor_history_after_edit = json.loads(
        _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
    )
    assert editor_history_after_edit["dirty"] == editor_history_before_keyframes["dirty"]
    assert editor_history_after_edit["canUndo"] == editor_history_before_keyframes["canUndo"]
    assert editor_history_after_edit["canRedo"] == editor_history_before_keyframes["canRedo"]

    _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-trajectory-command=\"load\"]').click();true",
    )
    _wait_until(app, trajectory_is_loaded)
    _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-trajectory-command=\"play\"]').click();true",
    )

    def trajectory_crossed_middle_keyframe() -> bool:
        current = json.loads(
            _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
        )
        runtime = current["simulationState"]
        cursor = runtime["trajectory"]["time"]
        return bool(
            current["simulationStatus"] == "running"
            and 0.32 <= cursor <= 0.48
            and runtime["actuators"][0]["ctrl"] < -0.25
        )

    _wait_until(app, trajectory_crossed_middle_keyframe)
    _wait_until(app, trajectory_is_completed)
    _javascript(
        app,
        window.web_view.page(),
        "const panel=document.querySelector('#inspector-panel');"
        "panel.scrollTop=panel.scrollHeight;true",
    )
    _pump_events(app, 0.3)
    keyframe_screenshot = window.web_view.grab()
    keyframe_output = Path(
        os.environ.get(
            "SIMLAB_QT_KEYFRAME_SCREENSHOT",
            tmp_path / "robot-keyframes.png",
        )
    )
    assert keyframe_screenshot.save(str(keyframe_output))

    keyframe_delete_selector = json.dumps(
        '[data-keyframe-id="keyframe-2"] [data-keyframe-delete]'
    )
    _javascript(
        app,
        window.web_view.page(),
        f"document.querySelector({keyframe_delete_selector}).click();true",
    )
    _wait_until(
        app,
        lambda: _javascript(
            app,
            window.web_view.page(),
            "document.querySelectorAll('[data-keyframe-id]').length",
        )
        == 2,
    )
    editor_history_after_delete = json.loads(
        _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
    )
    assert editor_history_after_delete["dirty"] == editor_history_before_keyframes["dirty"]
    assert editor_history_after_delete["canUndo"] == editor_history_before_keyframes["canUndo"]
    assert editor_history_after_delete["canRedo"] == editor_history_before_keyframes["canRedo"]
    window.bridge.dirty = False
    window.close()
