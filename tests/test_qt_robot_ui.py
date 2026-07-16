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


def _write_qt_controller(
    path: Path,
    shoulder_id: str,
    elbow_id: str,
    *,
    shoulder_target: float = 0.3,
    elbow_target: float = -0.7,
    fault: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    step_body = (
        "        raise RuntimeError('Qt controller fault')\n"
        if fault
        else (
            "        return ControllerAction("
            f"{{{shoulder_id!r}: {shoulder_target!r}, "
            f"{elbow_id!r}: {elbow_target!r}}})\n"
        )
    )
    path.write_text(
        "from simlab.services.controller_runtime import ControllerAction\n"
        "class QtController:\n"
        "    name = 'Qt Project Controller'\n"
        "    def reset(self, observation): pass\n"
        "    def step(self, observation):\n"
        + step_body
        + "def create_controller(): return QtController()\n",
        encoding="utf-8",
    )


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
    persisted_time_selector = json.dumps(
        '[data-keyframe-id="keyframe-3"] [data-keyframe-time]'
    )
    _javascript(
        app,
        window.web_view.page(),
        f"(()=>{{const input=document.querySelector({persisted_time_selector});"
        "input.value='0.4';input.dispatchEvent(new Event('change',{bubbles:true}));"
        "return true})()",
    )
    persisted_target_selector = json.dumps(
        f'[data-keyframe-id="keyframe-3"] [data-keyframe-target="{joint_id}"]'
    )
    _javascript(
        app,
        window.web_view.page(),
        f"(()=>{{const input=document.querySelector({persisted_target_selector});"
        "input.value='-0.4';input.dispatchEvent(new Event('change',{bubbles:true}));"
        "return true})()",
    )
    _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-trajectory-save]').click();true",
    )

    def trajectory_clip_is_saved() -> bool:
        current = json.loads(
            _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
        )
        clips = current["scene"].get("trajectories", [])
        return bool(
            len(clips) == 1
            and clips[0]["id"] == "trajectory_001"
            and [item["time"] for item in clips[0]["trajectory"]["keyframes"]]
            == [0, 0.4, 0.8]
            and clips[0]["trajectory"]["keyframes"][1]["targets"][joint_id]
            == pytest.approx(-0.4)
        )

    _wait_until(app, trajectory_clip_is_saved)
    _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-command=\"undo\"]').click();true",
    )
    _wait_until(
        app,
        lambda: "trajectories"
        not in json.loads(
            _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
        )["scene"],
    )
    _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-command=\"redo\"]').click();true",
    )
    _wait_until(app, trajectory_clip_is_saved)
    _wait_until(
        app,
        lambda: _javascript(
            app,
            window.web_view.page(),
            "document.querySelectorAll('[data-keyframe-id]').length",
        )
        == 3,
    )

    saved_scene_path = tmp_path / "saved-robot-scene.json"
    saved_scene_json = json.dumps(str(saved_scene_path))
    _javascript(
        app,
        window.web_view.page(),
        f"window.simlabEditor.saveProjectPath({saved_scene_json}).then("
        "result=>document.documentElement.dataset.projectSave=JSON.stringify(result));true",
    )
    _wait_until(
        app,
        lambda: bool(
            _javascript(
                app,
                window.web_view.page(),
                "document.documentElement.dataset.projectSave || ''",
            )
        ),
    )
    save_result = json.loads(
        _javascript(
            app,
            window.web_view.page(),
            "document.documentElement.dataset.projectSave",
        )
    )
    assert save_result["ok"] is True
    saved_data = json.loads(saved_scene_path.read_text(encoding="utf-8"))
    assert saved_data["trajectories"][0]["trajectory"]["name"] == "Qt Arm Motion"
    saved_editor_state = json.loads(
        _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
    )
    assert saved_editor_state["dirty"] is False
    assert saved_editor_state["currentPath"] == str(saved_scene_path)

    window.bridge.dirty = False
    window.close()

    reopened_window = MainWindow(project_root=tmp_path)
    reopened_loaded: list[bool] = []
    reopened_window.web_view.loadFinished.connect(reopened_loaded.append)
    reopened_window.show()
    _wait_until(app, lambda: bool(reopened_loaded))
    assert reopened_loaded[-1] is True
    _wait_until(
        app,
        lambda: bool(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "window.simlabEditorReady === true",
            )
        ),
    )
    _javascript(
        app,
        reopened_window.web_view.page(),
        f"window.simlabEditor.openProjectPath({saved_scene_json}).then("
        "result=>document.documentElement.dataset.projectOpen=JSON.stringify(result));true",
    )
    _wait_until(
        app,
        lambda: bool(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "document.documentElement.dataset.projectOpen || ''",
            )
        ),
    )
    open_result = json.loads(
        _javascript(
            app,
            reopened_window.web_view.page(),
            "document.documentElement.dataset.projectOpen",
        )
    )
    assert open_result["ok"] is True
    reopened_state = json.loads(
        _javascript(
            app,
            reopened_window.web_view.page(),
            "window.simlabEditor.getStateJson()",
        )
    )
    reopened_actor_id = reopened_state["scene"]["actors"][0]["id"]
    reopened_articulation = reopened_state["scene"]["robotics"]["articulations"][0]
    reopened_joint_id = reopened_articulation["joints"][0]["id"]
    assert _javascript(
        app,
        reopened_window.web_view.page(),
        "window.simlabEditor.selectJoint("
        f"{json.dumps(reopened_actor_id)},{json.dumps(reopened_joint_id)})",
    ) is True
    _wait_until(
        app,
        lambda: _javascript(
            app,
            reopened_window.web_view.page(),
            "document.querySelector('[data-trajectory-clip]').value",
        )
        == "trajectory_001",
    )
    reopened_keyframes = json.loads(
        _javascript(
            app,
            reopened_window.web_view.page(),
            "JSON.stringify([...document.querySelectorAll('[data-keyframe-id]')].map(row=>({"
            "time:Number(row.querySelector('[data-keyframe-time]').value),"
            "target:Number(row.querySelector('[data-keyframe-target]').value)"
            "})))",
        )
    )
    assert [item["time"] for item in reopened_keyframes] == [0, 0.4, 0.8]
    assert reopened_keyframes[1]["target"] == pytest.approx(-0.4)

    _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-trajectory-command=\"load\"]').click();true",
    )

    def reopened_trajectory_is_loaded() -> bool:
        current = json.loads(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "window.simlabEditor.getStateJson()",
            )
        )
        runtime = current["simulationState"]
        return bool(
            current["simulationStatus"] == "paused"
            and runtime
            and runtime["trajectory"]["status"] == "stopped"
            and runtime["trajectory"]["duration"] == pytest.approx(0.8)
        )

    _wait_until(app, reopened_trajectory_is_loaded)
    reopened_wall_time = [200.0]
    reopened_window.bridge.simulation_service.clock = lambda: reopened_wall_time[0]
    controller_elbow_id = reopened_articulation["joints"][1]["id"]
    controller_path = tmp_path / "controllers" / "qt_controller.py"
    _write_qt_controller(controller_path, reopened_joint_id, controller_elbow_id)
    controller_path_json = json.dumps(str(controller_path))
    _javascript(
        app,
        reopened_window.web_view.page(),
        f"window.simlabEditor.loadControllerPath({controller_path_json}).then("
        "result=>document.documentElement.dataset.controllerLoad=JSON.stringify(result));true",
    )
    _wait_until(
        app,
        lambda: bool(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "document.documentElement.dataset.controllerLoad || ''",
            )
        ),
    )
    controller_load = json.loads(
        _javascript(
            app,
            reopened_window.web_view.page(),
            "document.documentElement.dataset.controllerLoad",
        )
    )
    assert controller_load["ok"] is True
    assert controller_load["data"]["controller"] == {
        "path": str(controller_path.resolve()),
        "name": "Qt Project Controller",
    }

    def reopened_controller_status(status: str) -> bool:
        current = json.loads(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "window.simlabEditor.getStateJson()",
            )
        )
        runtime = current["simulationState"]
        return bool(
            current["simulationStatus"] in {"paused", "running"}
            and runtime
            and runtime["controller"]["mode"] == "python"
            and runtime["controller"]["status"] == status
        )

    _wait_until(app, lambda: reopened_controller_status("ready"))
    controller_ui = json.loads(
        _javascript(
            app,
            reopened_window.web_view.page(),
            "JSON.stringify({"
            "name:document.querySelector('[data-controller-name]').textContent,"
            "path:document.querySelector('[data-controller-path]').textContent,"
            "jogDisabled:[...document.querySelectorAll('[data-joint-jog]')].every(x=>x.disabled),"
            "playDisabled:document.querySelector('[data-trajectory-command=\"play\"]').disabled"
            "})",
        )
    )
    assert controller_ui == {
        "name": "Qt Project Controller",
        "path": str(controller_path.resolve()),
        "jogDisabled": True,
        "playDisabled": True,
    }
    _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-command=\"run\"]').click();true",
    )
    _wait_until(
        app,
        lambda: json.loads(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "window.simlabEditor.getStateJson()",
            )
        )["simulationStatus"]
        == "running",
    )
    reopened_window.bridge.simulation_timer.stop()
    reopened_wall_time[0] += 0.08
    reopened_window.bridge._advance_simulation()
    app.processEvents()
    controller_running = json.loads(
        _javascript(
            app,
            reopened_window.web_view.page(),
            "window.simlabEditor.getStateJson()",
        )
    )["simulationState"]
    assert controller_running["time"] == pytest.approx(0.08)
    assert controller_running["controller"]["step_count"] == 8
    assert controller_running["controller"]["last_duration"] >= 0
    assert [item["ctrl"] for item in controller_running["actuators"]] == pytest.approx(
        [0.3, -0.7]
    )
    assert _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-controller-steps]').textContent",
    ) == "8 Steps"

    _write_qt_controller(
        controller_path,
        reopened_joint_id,
        controller_elbow_id,
        shoulder_target=0.6,
        elbow_target=-1.0,
    )
    _javascript(
        app,
        reopened_window.web_view.page(),
        "window.confirm=()=>true;"
        "document.querySelector('[data-controller-command=\"reload\"]').click();true",
    )
    _wait_until(
        app,
        lambda: reopened_controller_status("ready")
        and json.loads(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "window.simlabEditor.getStateJson()",
            )
        )["simulationStatus"]
        == "paused",
    )
    _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-command=\"run\"]').click();true",
    )
    _wait_until(
        app,
        lambda: json.loads(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "window.simlabEditor.getStateJson()",
            )
        )["simulationStatus"]
        == "running",
    )
    reopened_window.bridge.simulation_timer.stop()
    reopened_wall_time[0] += 0.08
    reopened_window.bridge._advance_simulation()
    app.processEvents()
    controller_reloaded = json.loads(
        _javascript(
            app,
            reopened_window.web_view.page(),
            "window.simlabEditor.getStateJson()",
        )
    )["simulationState"]
    assert controller_reloaded["time"] == pytest.approx(0.16)
    assert [item["ctrl"] for item in controller_reloaded["actuators"]] == pytest.approx(
        [0.6, -1.0]
    )

    _write_qt_controller(
        controller_path,
        reopened_joint_id,
        controller_elbow_id,
        fault=True,
    )
    _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-controller-command=\"reload\"]').click();true",
    )
    _wait_until(app, lambda: reopened_controller_status("ready"))
    _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-command=\"run\"]').click();true",
    )
    _wait_until(
        app,
        lambda: json.loads(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "window.simlabEditor.getStateJson()",
            )
        )["simulationStatus"]
        == "running",
    )
    reopened_window.bridge.simulation_timer.stop()
    reopened_wall_time[0] += 0.02
    reopened_window.bridge._advance_simulation()
    app.processEvents()
    controller_fault = json.loads(
        _javascript(
            app,
            reopened_window.web_view.page(),
            "window.simlabEditor.getStateJson()",
        )
    )
    assert controller_fault["simulationStatus"] == "running"
    assert controller_fault["simulationState"]["time"] == pytest.approx(0.18)
    assert controller_fault["simulationState"]["controller"]["status"] == "fault"
    assert "Qt controller fault" in controller_fault["simulationState"]["controller"]["message"]
    assert _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('#controller-panel-status').textContent",
    ) == "fault"

    _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-controller-command=\"detach\"]').click();true",
    )
    _wait_until(
        app,
        lambda: json.loads(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "window.simlabEditor.getStateJson()",
            )
        )["simulationState"]["controller"]["mode"]
        == "manual",
    )
    detached_ui = json.loads(
        _javascript(
            app,
            reopened_window.web_view.page(),
            "JSON.stringify({"
            "status:window.simlabEditor.getStateJson(),"
            "jogEnabled:[...document.querySelectorAll('[data-joint-jog]')].every(x=>!x.disabled),"
            "playEnabled:!document.querySelector('[data-trajectory-command=\"play\"]').disabled"
            "})",
        )
    )
    assert json.loads(detached_ui["status"])["simulationStatus"] == "paused"
    assert detached_ui["jogEnabled"] is True
    assert detached_ui["playEnabled"] is True
    _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-command=\"reset\"]').click();true",
    )
    _wait_until(
        app,
        lambda: json.loads(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "window.simlabEditor.getStateJson()",
            )
        )["simulationState"]["time"]
        == 0,
    )
    _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-simulation-speed=\"0.5\"]').click();true",
    )

    def reopened_speed_is(factor: float) -> bool:
        current = json.loads(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "window.simlabEditor.getStateJson()",
            )
        )
        runtime = current["simulationState"]
        return bool(
            runtime
            and runtime["clock"]["target_rtf"] == factor
            and _javascript(
                app,
                reopened_window.web_view.page(),
                f"document.querySelector('[data-simulation-speed=\"{factor:g}\"]')"
                ".getAttribute('aria-pressed')",
            )
            == "true"
        )

    _wait_until(app, lambda: reopened_speed_is(0.5))
    _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-recording-command=\"start\"]').click();true",
    )
    _wait_until(
        app,
        lambda: json.loads(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "window.simlabEditor.getStateJson()",
            )
        )["simulationState"]["recording"]["sample_count"]
        == 1,
    )
    _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-trajectory-command=\"play\"]').click();true",
    )
    _wait_until(
        app,
        lambda: json.loads(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "window.simlabEditor.getStateJson()",
            )
        )["simulationStatus"]
        == "running",
    )
    reopened_window.bridge.simulation_timer.stop()
    reopened_wall_time[0] += 0.04
    reopened_window.bridge._advance_simulation()
    app.processEvents()
    half_speed_state = json.loads(
        _javascript(
            app,
            reopened_window.web_view.page(),
            "window.simlabEditor.getStateJson()",
        )
    )["simulationState"]
    assert half_speed_state["time"] == pytest.approx(0.02)
    assert half_speed_state["trajectory"]["time"] == pytest.approx(0.02)
    assert half_speed_state["clock"] == pytest.approx(
        {"target_rtf": 0.5, "actual_rtf": 0.5, "timestep": 0.01}
    )
    assert half_speed_state["recording"]["sample_count"] == 3

    _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-simulation-speed=\"2\"]').click();true",
    )
    _wait_until(app, lambda: reopened_speed_is(2.0))
    reopened_wall_time[0] += 0.04
    reopened_window.bridge._advance_simulation()
    app.processEvents()
    double_speed_state = json.loads(
        _javascript(
            app,
            reopened_window.web_view.page(),
            "window.simlabEditor.getStateJson()",
        )
    )["simulationState"]
    assert double_speed_state["time"] == pytest.approx(0.10)
    assert double_speed_state["trajectory"]["time"] == pytest.approx(0.10)
    assert double_speed_state["clock"] == pytest.approx(
        {"target_rtf": 2.0, "actual_rtf": 2.0, "timestep": 0.01}
    )
    assert double_speed_state["recording"]["sample_count"] == 11
    assert _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('#rtf-readout').textContent",
    ) == "2.00x"

    _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-recording-command=\"stop\"]').click();true",
    )
    _wait_until(
        app,
        lambda: json.loads(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "window.simlabEditor.getStateJson()",
            )
        )["simulationState"]["recording"]["active"]
        is False,
    )
    _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-trajectory-command=\"pause\"]').click();true",
    )
    _wait_until(
        app,
        lambda: json.loads(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "window.simlabEditor.getStateJson()",
            )
        )["simulationStatus"]
        == "paused",
    )
    speed_recording = reopened_window.bridge.simulation_service.get_joint_recording()
    speed_times = [sample.time for sample in speed_recording.samples]
    assert speed_times == pytest.approx([index * 0.01 for index in range(11)])

    reopened_window.bridge.simulation_service.clock = time.monotonic
    _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-simulation-speed=\"1\"]').click();true",
    )
    _wait_until(app, lambda: reopened_speed_is(1.0))
    _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-command=\"reset\"]').click();true",
    )
    _wait_until(
        app,
        lambda: json.loads(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "window.simlabEditor.getStateJson()",
            )
        )["simulationState"]["time"]
        == 0,
    )
    _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-trajectory-command=\"load\"]').click();true",
    )
    _wait_until(
        app,
        reopened_trajectory_is_loaded,
    )
    second_joint_id = reopened_articulation["joints"][1]["id"]
    second_joint_selector = json.dumps(
        f'[data-recording-joint="{second_joint_id}"]'
    )
    _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-recording-name]').value='Qt Physics Samples';"
        "document.querySelector('[data-recording-name]').dispatchEvent("
        "new Event('change',{bubbles:true}));"
        f"document.querySelector({second_joint_selector}).click();"
        "document.querySelector('[data-recording-command=\"start\"]').click();true",
    )

    def reopened_recording_is_active() -> bool:
        current = json.loads(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "window.simlabEditor.getStateJson()",
            )
        )
        runtime = current["simulationState"]
        return bool(
            current["simulationStatus"] == "paused"
            and runtime
            and runtime["recording"]["active"] is True
            and runtime["recording"]["sample_count"] == 1
            and runtime["recording"]["name"] == "Qt Physics Samples"
        )

    _wait_until(app, reopened_recording_is_active)
    _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-trajectory-command=\"play\"]').click();true",
    )

    def reopened_trajectory_is_completed() -> bool:
        current = json.loads(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "window.simlabEditor.getStateJson()",
            )
        )
        runtime = current["simulationState"]
        return bool(
            current["simulationStatus"] == "paused"
            and runtime
            and runtime["trajectory"]["status"] == "completed"
            and runtime["actuators"][0]["ctrl"] == pytest.approx(0.5)
        )

    try:
        _wait_until(app, reopened_trajectory_is_completed)
    except AssertionError as exc:
        failed_state = json.loads(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "window.simlabEditor.getStateJson()",
            )
        )
        raise AssertionError(
            "Reopened recording trajectory did not complete: "
            + json.dumps(
                {
                    "status": failed_state["simulationStatus"],
                    "runtime": failed_state["simulationState"],
                    "logs": failed_state["logs"][-8:],
                }
            )
        ) from exc
    completed_recording_state = json.loads(
        _javascript(
            app,
            reopened_window.web_view.page(),
            "window.simlabEditor.getStateJson()",
        )
    )["simulationState"]["recording"]
    assert completed_recording_state["active"] is True
    assert completed_recording_state["sample_count"] >= 81
    _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('[data-recording-command=\"stop\"]').click();true",
    )

    def reopened_recording_is_stopped() -> bool:
        current = json.loads(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "window.simlabEditor.getStateJson()",
            )
        )
        recording = current["simulationState"]["recording"]
        return bool(
            recording["active"] is False
            and recording["sample_count"]
            == completed_recording_state["sample_count"]
        )

    _wait_until(app, reopened_recording_is_stopped)
    _javascript(
        app,
        reopened_window.web_view.page(),
        "window.simlabEditor.getRecording().then("
        "result=>document.documentElement.dataset.recording=JSON.stringify(result));true",
    )
    _wait_until(
        app,
        lambda: bool(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "document.documentElement.dataset.recording || ''",
            )
        ),
    )
    recording_result = json.loads(
        _javascript(
            app,
            reopened_window.web_view.page(),
            "document.documentElement.dataset.recording",
        )
    )
    assert recording_result["ok"] is True
    recording = recording_result["data"]["recording"]
    assert recording["name"] == "Qt Physics Samples"
    assert recording["joint_ids"] == [reopened_joint_id]
    assert recording["actuator_ids"] == [reopened_articulation["actuators"][0]["id"]]
    assert len(recording["samples"]) == completed_recording_state["sample_count"]
    times = [sample["time"] for sample in recording["samples"]]
    assert times[0] == 0
    assert 0.8 <= times[-1] <= 0.84
    assert all(
        right - left == pytest.approx(0.01)
        for left, right in zip(times, times[1:], strict=False)
    )
    assert all(
        math.isfinite(sample["joints"][reopened_joint_id]["qpos"])
        for sample in recording["samples"]
    )

    recording_json_path = tmp_path / "recordings" / "qt-physics.json"
    recording_csv_path = tmp_path / "recordings" / "qt-physics.csv"
    recording_json_path_json = json.dumps(str(recording_json_path))
    recording_csv_path_json = json.dumps(str(recording_csv_path))
    _javascript(
        app,
        reopened_window.web_view.page(),
        "Promise.all(["
        f"window.simlabEditor.exportRecordingPath({recording_json_path_json},'json'),"
        f"window.simlabEditor.exportRecordingPath({recording_csv_path_json},'csv')"
        "]).then(result=>document.documentElement.dataset.recordingExport="
        "JSON.stringify(result));true",
    )
    _wait_until(
        app,
        lambda: bool(
            _javascript(
                app,
                reopened_window.web_view.page(),
                "document.documentElement.dataset.recordingExport || ''",
            )
        ),
    )
    export_results = json.loads(
        _javascript(
            app,
            reopened_window.web_view.page(),
            "document.documentElement.dataset.recordingExport",
        )
    )
    assert all(result["ok"] for result in export_results)
    assert json.loads(recording_json_path.read_text(encoding="utf-8")) == recording
    csv_lines = recording_csv_path.read_text(encoding="utf-8").splitlines()
    assert len(csv_lines) == len(recording["samples"]) + 1
    assert csv_lines[0].startswith(f"time,joint.{reopened_joint_id}.qpos")
    recording_status_text = _javascript(
        app,
        reopened_window.web_view.page(),
        "document.querySelector('#recording-status').textContent",
    )
    assert recording_status_text == f"{len(recording['samples'])} Samples"
    _javascript(
        app,
        reopened_window.web_view.page(),
        "const panel=document.querySelector('#inspector-panel');"
        "panel.scrollTop=panel.scrollHeight;true",
    )
    _pump_events(app, 0.3)
    reopened_screenshot = reopened_window.web_view.grab()
    reopened_output = Path(
        os.environ.get(
            "SIMLAB_QT_REOPENED_SCREENSHOT",
            tmp_path / "robot-trajectory-reopened.png",
        )
    )
    assert reopened_screenshot.save(str(reopened_output))
    reopened_window.bridge.dirty = False
    reopened_window.close()
