from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("SIMLAB_QT_WEBENGINE_E2E") != "1",
    reason="Set SIMLAB_QT_WEBENGINE_E2E=1 to run the QtWebEngine sensor test.",
)


def _wait_until(app: Any, predicate: Any, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Timed out waiting for QtWebEngine sensor state")


def _javascript(app: Any, page: Any, script: str) -> Any:
    result: list[Any] = []
    page.runJavaScript(script, result.append)
    _wait_until(app, lambda: bool(result))
    return result[0]


def test_qt_webengine_displays_live_joint_state_sensor(tmp_path: Path) -> None:
    pytest.importorskip("mujoco")
    pytest.importorskip("pxr")
    pytest.importorskip("PySide6.QtWebEngineWidgets")
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QApplication

    from simlab.main_window import MainWindow
    from simlab.models.actor import Actor
    from simlab.models.robotics import RigidTransform, Sensor
    from simlab.models.scene import Scene
    from simlab.services.openusd_importer import import_openusd_asset
    from simlab.services.project_service import save_scene

    imported = import_openusd_asset(
        "tests/fixtures/openusd/robot_arm/external_two_joint_arm.usda", tmp_path
    )
    articulation = imported.robotics_model.articulations[0]
    shoulder = articulation.joints[0]
    sensor = Sensor(
        id="sensor_qt_shoulder",
        name="Shoulder State",
        sensor_type="joint_state",
        joint_id=shoulder.id,
        update_rate_hz=50.0,
    )
    articulation.sensors.append(sensor)
    forearm = articulation.links[-1]
    imu = Sensor(
        id="sensor_qt_forearm_imu",
        name="Forearm IMU",
        sensor_type="imu",
        link_id=forearm.id,
        update_rate_hz=50.0,
        local_transform=RigidTransform(position=[0.0, 0.0, 0.2]),
    )
    articulation.sensors.append(imu)
    scene = Scene(
        name="Qt Sensor Scene",
        actors=[
            Actor(
                id="actor_arm",
                name="External Arm",
                type="robot",
                asset_id=imported.asset["id"],
                properties=imported.asset["default_properties"],
            )
        ],
        robotics=imported.robotics_model,
        simulation_config={"timestep": 0.01, "max_catch_up_steps": 8},
    )
    scene_path = tmp_path / "sensor-scene.json"
    save_scene(scene_path, scene)

    app = QApplication.instance() or QApplication([])
    window = MainWindow(project_root=tmp_path)
    window.show()
    loaded: list[bool] = []
    window.web_view.loadFinished.connect(loaded.append)
    _wait_until(app, lambda: bool(loaded) and loaded[-1])
    _wait_until(
        app,
        lambda: bool(
            _javascript(app, window.web_view.page(), "window.simlabEditorReady === true")
        ),
    )
    _javascript(
        app,
        window.web_view.page(),
        f"window.simlabEditor.openProjectPath({json.dumps(str(scene_path))}).then("
        "result=>document.documentElement.dataset.sensorOpen=JSON.stringify(result));true",
    )
    _wait_until(
        app,
        lambda: bool(
            _javascript(
                app,
                window.web_view.page(),
                "document.documentElement.dataset.sensorOpen || ''",
            )
        ),
    )
    assert _javascript(
        app,
        window.web_view.page(),
        "window.simlabEditor.selectSensor('actor_arm','sensor_qt_shoulder')",
    ) is True
    initial_ui = json.loads(
        _javascript(
            app,
            window.web_view.page(),
            "JSON.stringify({"
            "rows:document.querySelectorAll('[data-sensor-id]').length,"
            "selected:document.querySelectorAll('[data-sensor-id].selected').length,"
            "heading:document.querySelector('#property-inspector h3').textContent,"
            "rate:[...document.querySelectorAll('#property-inspector .property-row')]"
            ".find(row=>row.querySelector('label').textContent==='Rate').querySelector('input').value"
            "})",
        )
    )
    assert initial_ui == {
        "rows": 2,
        "selected": 1,
        "heading": "Sensor",
        "rate": "50 Hz",
    }
    recording_sources = json.loads(
        _javascript(
            app,
            window.web_view.page(),
            "JSON.stringify({"
            "count:document.querySelectorAll('[data-recording-sensor]').length,"
            "checked:document.querySelector('[data-recording-sensor]').checked"
            "})",
        )
    )
    assert recording_sources == {"count": 2, "checked": False}
    _javascript(
        app,
        window.web_view.page(),
        "document.querySelectorAll('[data-recording-sensor]').forEach(sensor=>sensor.click());"
        "document.querySelector('[data-recording-command=\"start\"]').click();true",
    )

    def recording_is_active() -> bool:
        current = json.loads(
            _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
        )["simulationState"]
        return bool(
            current
            and current["recording"]["active"] is True
            and current["recording"]["sample_count"] == 1
            and current["recording"]["sensor_event_count"] == 2
        )

    _wait_until(app, recording_is_active)

    _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-command=\"run\"]').click();true",
    )

    def sensor_has_samples() -> bool:
        current = json.loads(
            _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
        )
        return bool(
            current["simulationStatus"] == "running"
            and current["simulationState"]
            and current["simulationState"]["sensors"][0]["sequence"] >= 4
        )

    _wait_until(app, sensor_has_samples)
    _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-command=\"pause\"]').click();true",
    )
    _wait_until(
        app,
        lambda: json.loads(
            _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
        )["simulationStatus"]
        == "paused",
    )
    _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('[data-recording-command=\"stop\"]').click();true",
    )
    _wait_until(
        app,
        lambda: json.loads(
            _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
        )["simulationState"]["recording"]["active"]
        is False,
    )
    state = json.loads(
        _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
    )["simulationState"]
    sample = state["sensors"][0]
    live_ui = json.loads(
        _javascript(
            app,
            window.web_view.page(),
            "JSON.stringify(Object.fromEntries("
            "[...document.querySelectorAll('[data-sensor-field]')]"
            ".map(input=>[input.dataset.sensorField,input.value])))",
        )
    )
    assert int(live_ui["sequence"]) == sample["sequence"]
    assert float(live_ui["time"]) == pytest.approx(sample["time"], abs=0.001)
    assert float(live_ui["qpos"]) == pytest.approx(sample["qpos"], abs=0.001)
    assert float(live_ui["qvel"]) == pytest.approx(sample["qvel"], abs=0.001)
    assert sample["time"] <= state["time"]

    _javascript(
        app,
        window.web_view.page(),
        "window.simlabEditor.getRecording().then("
        "result=>document.documentElement.dataset.sensorRecording=JSON.stringify(result));true",
    )
    _wait_until(
        app,
        lambda: bool(
            _javascript(
                app,
                window.web_view.page(),
                "document.documentElement.dataset.sensorRecording || ''",
            )
        ),
    )
    recording_result = json.loads(
        _javascript(
            app,
            window.web_view.page(),
            "document.documentElement.dataset.sensorRecording",
        )
    )
    assert recording_result["ok"] is True
    recording = recording_result["data"]["recording"]
    assert recording["sensor_ids"] == [sensor.id, imu.id]
    assert recording["sensor_types"] == {sensor.id: "joint_state", imu.id: "imu"}
    events = [
        sample["sensors"][sensor.id]
        for sample in recording["samples"]
        if sensor.id in sample["sensors"]
    ]
    assert [event["sequence"] for event in events] == list(range(len(events)))
    assert all(
        right["time"] - left["time"] == pytest.approx(0.02)
        for left, right in zip(events, events[1:], strict=False)
    )
    assert any(not sample["sensors"] for sample in recording["samples"][1:])
    imu_events = [
        sample["sensors"][imu.id]
        for sample in recording["samples"]
        if imu.id in sample["sensors"]
    ]
    assert [event["sequence"] for event in imu_events] == list(range(len(imu_events)))
    assert all(
        right["time"] - left["time"] == pytest.approx(0.02)
        for left, right in zip(imu_events, imu_events[1:], strict=False)
    )
    assert all(event["sensor_type"] == "imu" for event in imu_events)
    assert state["recording"]["sensor_event_count"] == len(events) + len(imu_events)

    json_path = tmp_path / "recordings" / "sensor.json"
    csv_path = tmp_path / "recordings" / "sensor.csv"
    _javascript(
        app,
        window.web_view.page(),
        "Promise.all(["
        f"window.simlabEditor.exportRecordingPath({json.dumps(str(json_path))},'json'),"
        f"window.simlabEditor.exportRecordingPath({json.dumps(str(csv_path))},'csv')"
        "]).then(result=>document.documentElement.dataset.sensorExport="
        "JSON.stringify(result));true",
    )
    _wait_until(
        app,
        lambda: bool(
            _javascript(
                app,
                window.web_view.page(),
                "document.documentElement.dataset.sensorExport || ''",
            )
        ),
    )
    export_result = json.loads(
        _javascript(
            app,
            window.web_view.page(),
            "document.documentElement.dataset.sensorExport",
        )
    )
    assert all(item["ok"] for item in export_result)
    assert json.loads(json_path.read_text(encoding="utf-8")) == recording
    rows = list(csv.reader(csv_path.read_text(encoding="utf-8").splitlines()))
    sequence_column = rows[0].index(f"sensor.{sensor.id}.sequence")
    assert any(row[sequence_column] == "" for row in rows[1:])
    assert [
        int(row[sequence_column]) for row in rows[1:] if row[sequence_column]
    ] == list(range(len(events)))
    imu_sequence_column = rows[0].index(f"sensor.{imu.id}.sequence")
    assert f"sensor.{imu.id}.orientation.w" in rows[0]
    assert f"sensor.{imu.id}.linear_acceleration.z" in rows[0]
    assert [
        int(row[imu_sequence_column]) for row in rows[1:] if row[imu_sequence_column]
    ] == list(range(len(imu_events)))
    recording_status = _javascript(
        app,
        window.web_view.page(),
        "document.querySelector('#recording-status').textContent",
    )
    assert recording_status == (
        f"{len(recording['samples'])} Rows · {len(events) + len(imu_events)} Events"
    )

    assert _javascript(
        app,
        window.web_view.page(),
        "window.simlabEditor.selectSensor('actor_arm','sensor_qt_forearm_imu')",
    ) is True
    imu_sample = next(item for item in state["sensors"] if item["sensor_type"] == "imu")
    imu_ui = json.loads(
        _javascript(
            app,
            window.web_view.page(),
            "JSON.stringify({"
            "mount:[...document.querySelectorAll('#property-inspector .property-row')]"
            ".find(row=>row.querySelector('label').textContent==='Link').querySelector('input').value,"
            "fields:Object.fromEntries([...document.querySelectorAll('[data-sensor-field]')]"
            ".map(input=>[input.dataset.sensorField,input.value]))"
            "})",
        )
    )
    assert imu_ui["mount"] == forearm.name
    assert int(imu_ui["fields"]["sequence"]) == imu_sample["sequence"]
    assert float(imu_ui["fields"]["time"]) == pytest.approx(imu_sample["time"], abs=0.001)
    assert imu_ui["fields"]["orientation"] == ", ".join(
        f"{value:.3f}" for value in imu_sample["orientation"]
    )
    assert imu_ui["fields"]["angular_velocity"] == ", ".join(
        f"{value:.3f}" for value in imu_sample["angular_velocity"]
    )
    assert imu_ui["fields"]["linear_acceleration"] == ", ".join(
        f"{value:.3f}" for value in imu_sample["linear_acceleration"]
    )
    assert any(abs(value) > 0.01 for value in imu_sample["angular_velocity"])

    # QtWebEngine updates the DOM synchronously but composites offscreen a frame later.
    window.web_view.update()
    paint_deadline = time.monotonic() + 0.75
    while time.monotonic() < paint_deadline:
        app.processEvents()
        time.sleep(0.02)
    screenshot = window.web_view.grab()
    output = Path(
        os.environ.get("SIMLAB_QT_SENSOR_SCREENSHOT", tmp_path / "joint-sensor-ui.png")
    )
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
        "document.querySelector('[data-command=\"reset\"]').click();true",
    )

    def imu_is_reset() -> bool:
        current = json.loads(
            _javascript(app, window.web_view.page(), "window.simlabEditor.getStateJson()")
        )
        reset_imu = next(
            item
            for item in current["simulationState"]["sensors"]
            if item["sensor_type"] == "imu"
        )
        return bool(
            current["simulationStatus"] == "paused"
            and reset_imu["sequence"] == 0
            and reset_imu["time"] == 0.0
        )

    _wait_until(app, imu_is_reset)

    window.bridge.dirty = False
    window.close()
    app.processEvents()
