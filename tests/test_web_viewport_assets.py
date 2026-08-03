from pathlib import Path


def test_typescript_editor_assets_are_an_independent_frontend() -> None:
    root = Path("frontend/src")
    generated = Path("frontend/generated")

    assert (root / "index.html").exists()
    assert (root / "style.css").exists()
    assert (root / "ts" / "app.ts").exists()
    assert (root / "ts" / "store.ts").exists()
    assert (root / "ts" / "bridge.ts").exists()
    assert (root / "ts" / "viewport.ts").exists()
    assert (root / "ts" / "geometry-contract.ts").exists()
    assert (root / "ts" / "geometry-bundle.ts").exists()
    assert (generated / "app.js").exists()
    assert (generated / "viewport.js").exists()
    assert Path("frontend/public/simlab-config.json").exists()
    assert (root / "vendor" / "three.module.js").exists()
    assert (root / "vendor" / "THREE_LICENSE.txt").exists()


def test_editor_ui_and_bridge_commands_are_declared() -> None:
    root = Path("frontend/src")
    html = (root / "index.html").read_text(encoding="utf-8")
    style = (root / "style.css").read_text(encoding="utf-8")
    app = (root / "ts" / "app.ts").read_text(encoding="utf-8")
    bridge = (root / "ts" / "bridge.ts").read_text(encoding="utf-8")
    types = (root / "ts" / "types.ts").read_text(encoding="utf-8")
    viewport = (root / "ts" / "viewport.ts").read_text(encoding="utf-8")

    assert 'id="asset-list"' in html
    assert 'id="scene-tree"' in html
    assert 'id="property-inspector"' in html
    assert 'id="console-output"' in html
    assert 'data-command="save"' in html
    assert 'data-command="import-openusd"' in html
    assert 'data-command="import-openusd-folder"' in html
    assert 'data-command="run"' in html
    assert 'data-simulation-speed="0.25"' in html
    assert 'id="rtf-readout"' in html
    assert "class EditorStore" in (root / "ts" / "store.ts").read_text(encoding="utf-8")
    assert "store.undo()" in app
    assert "store.selectActor" in app
    assert "importOpenUsd" in app
    assert "importOpenUsdFolder" in bridge
    assert "new FormData()" in bridge
    assert "webkitdirectory" in bridge
    assert "/api/v1/projects" in bridge
    assert "/api/v1/simulations" in bridge
    assert "simlab-config.json" in bridge
    assert "after_sequence" in bridge
    assert "QWebChannel" not in bridge
    assert "/api/rpc" not in bridge
    assert "openProjectPath" not in bridge
    assert "saveProjectPath" not in bridge
    assert "startRecording" in bridge
    assert "recordings/${formatName}/artifact" in bridge
    assert "getVisualGeometry" in app
    assert "getVisualGeometryBundle" in app
    assert "decodeGeometryBundle" in viewport
    assert "new THREE.WireframeGeometry(mesh.geometry)" in viewport
    assert "onActorTransformChanged" in viewport
    assert "addRobotActor" in viewport
    assert "link.visual_geometries" in viewport
    assert "scene.robotics?.articulations" in app
    assert "tree-subitem joint" in app
    assert "for (const linkState of state.links)" in viewport
    assert "parent.worldToLocal" in viewport
    assert "data-joint-target" in app
    assert "setJointTargets" in app
    assert "data-rotor-control" in app
    assert "data-rotor-stop" in app
    assert "setActuatorControls" in app
    assert "/actuator-controls" in bridge
    assert "data-controller-status" in app
    assert 'data-status="fault"' in style
    assert "result.data?.state" in app
    assert "data-joint-jog" in app
    assert "updateRuntimeInspector" in app
    assert "store.selectJoint" in app
    assert "store.selectSensor" in app
    assert "data-sensor-id" in app
    assert "data-runtime-sensor-id" in app
    assert "linear_acceleration" in app
    assert "angular_velocity" in app
    assert "sensor.sensor_type === 'imu'" in app
    assert "sensor.sensor_type === 'contact'" in app
    assert 'data-sensor-field="normal_force"' in app
    assert 'data-sensor-field="first_point"' in app
    assert (
        "export type SensorSample = JointStateSensorSample | ImuSensorSample "
        "| ContactSensorSample"
    ) in types
    assert "selectViewportLink" in app
    assert "selectedLinkId" in viewport
    assert "window.simlabEditor" in app
    assert "simlabEditorReady" in app
    assert "simulationStatus === 'running' ? 'running' : 'paused'" in app
    assert "loadTrajectory" in bridge
    assert "TrajectorySimulationState" in types
    assert 'id="trajectory-panel"' in html
    assert "data-keyframe-add" in app
    assert "data-keyframe-target" in app
    assert "trajectoryFromDraft" in app
    assert "data-trajectory-clip" in app
    assert "data-trajectory-save" in app
    assert "store.upsertTrajectory" in app
    assert 'id="recording-panel"' in html
    assert 'id="controller-panel"' in html
    assert "data-recording-joint" in app
    assert "data-recording-sensor" in app
    assert "['joint_state', 'imu', 'contact']" in app
    assert "sensor_ids: sensorIds" in app
    assert "data-recording-command" in app
    assert "updateRecordingRuntime" in app
    assert "renderControllerPanel" in app
    assert "loadProjectController" in app
    assert "updateControllerRuntime" in app
    assert "updateSimulationClock" in app
    assert "setSimulationSpeed" in app
    assert "exportRecordingPath" not in app
    assert "handleTrajectoryCommand" in app
    assert "updateTrajectoryRuntime" in app


def test_optional_qt_shell_is_only_an_http_client() -> None:
    source = Path("src/simlab/main_window.py").read_text(encoding="utf-8")

    assert "QWebEngineView" in source
    assert "SIMLAB_FRONTEND_URL" in source
    assert 'parsed.scheme() not in {"http", "https"}' in source
    assert "EditorBridge" not in source
    assert "QWebChannel" not in source
    assert "project_root" not in source
