from pathlib import Path


def test_typescript_editor_assets_are_packaged() -> None:
    root = Path("src/simlab/web_viewport")

    assert (root / "index.html").exists()
    assert (root / "style.css").exists()
    assert (root / "ts" / "app.ts").exists()
    assert (root / "ts" / "store.ts").exists()
    assert (root / "ts" / "bridge.ts").exists()
    assert (root / "ts" / "viewport.ts").exists()
    assert (root / "ts" / "geometry-contract.ts").exists()
    assert (root / "generated" / "app.js").exists()
    assert (root / "generated" / "viewport.js").exists()
    assert (root / "vendor" / "three.module.js").exists()
    assert (root / "vendor" / "THREE_LICENSE.txt").exists()


def test_editor_ui_and_bridge_commands_are_declared() -> None:
    root = Path("src/simlab/web_viewport")
    html = (root / "index.html").read_text(encoding="utf-8")
    style = (root / "style.css").read_text(encoding="utf-8")
    app = (root / "ts" / "app.ts").read_text(encoding="utf-8")
    viewport = (root / "ts" / "viewport.ts").read_text(encoding="utf-8")

    assert 'id="asset-list"' in html
    assert 'id="scene-tree"' in html
    assert 'id="property-inspector"' in html
    assert 'id="console-output"' in html
    assert 'data-command="save"' in html
    assert 'data-command="import-openusd"' in html
    assert 'data-command="run"' in html
    assert 'data-simulation-speed="0.25"' in html
    assert 'id="rtf-readout"' in html
    assert "class EditorStore" in (root / "ts" / "store.ts").read_text(encoding="utf-8")
    assert "store.undo()" in app
    assert "store.selectActor" in app
    assert "importOpenUsd" in app
    assert "importOpenUsdPath" in (root / "ts" / "types.ts").read_text(encoding="utf-8")
    assert "openProjectPath" in (root / "ts" / "types.ts").read_text(encoding="utf-8")
    assert "saveProjectPath" in (root / "ts" / "types.ts").read_text(encoding="utf-8")
    assert "startRecording" in (root / "ts" / "types.ts").read_text(encoding="utf-8")
    assert "exportRecording" in (root / "ts" / "types.ts").read_text(encoding="utf-8")
    assert "getVisualGeometry" in app
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
    assert "data-controller-status" in app
    assert 'data-status="fault"' in style
    assert "result.data?.state" in app
    assert "data-joint-jog" in app
    assert "updateRuntimeInspector" in app
    assert "store.selectJoint" in app
    assert "selectViewportLink" in app
    assert "selectedLinkId" in viewport
    assert "window.simlabEditor" in app
    assert "simlabEditorReady" in app
    assert "simulationStatus === 'running' ? 'running' : 'paused'" in app
    types = (root / "ts" / "types.ts").read_text(encoding="utf-8")
    assert "loadTrajectory" in types
    assert "TrajectorySimulationState" in types
    assert 'id="trajectory-panel"' in html
    assert "data-keyframe-add" in app
    assert "data-keyframe-target" in app
    assert "trajectoryFromDraft" in app
    assert "data-trajectory-clip" in app
    assert "data-trajectory-save" in app
    assert "store.upsertTrajectory" in app
    assert 'id="recording-panel"' in html
    assert "data-recording-joint" in app
    assert "data-recording-command" in app
    assert "updateRecordingRuntime" in app
    assert "updateSimulationClock" in app
    assert "setSimulationSpeed" in app
    assert "exportRecordingPath" in app
    assert "handleTrajectoryCommand" in app
    assert "updateTrajectoryRuntime" in app
