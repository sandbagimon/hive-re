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
    assert (root / "ts" / "procedural-materials.ts").exists()
    assert (root / "ts" / "pbr-model-loader.ts").exists()
    assert (root / "ts" / "photographic-environment.ts").exists()
    assert (generated / "app.js").exists()
    assert (generated / "viewport.js").exists()
    assert (generated / "procedural-materials.js").exists()
    assert (generated / "pbr-model-loader.js").exists()
    assert (generated / "photographic-environment.js").exists()
    assert Path("frontend/public/beefoundrysim-config.json").exists()
    assert Path("frontend/public/docs/viewport-controls.html").exists()
    assert Path("frontend/public/textures/delivery-bag-oxford-albedo.png").exists()
    assert Path(
        "frontend/public/textures/cinematic-delivery/wet-asphalt-albedo.png"
    ).exists()
    assert Path(
        "frontend/public/models/polyhaven/concrete_road_barrier_02/"
        "concrete_road_barrier_02_2k.gltf"
    ).exists()
    assert Path(
        "frontend/public/models/polyhaven/barrel_03/barrel_03_2k.gltf"
    ).exists()
    assert Path(
        "frontend/public/environments/polyhaven/"
        "abandoned_hopper_terminal_03_1k.hdr"
    ).exists()
    assert (root / "vendor" / "three.module.js").exists()
    assert (root / "vendor" / "THREE_LICENSE.txt").exists()


def test_agent_conversation_window_is_declared() -> None:
    html = Path("frontend/src/index.html").read_text(encoding="utf-8")

    assert 'data-panel="agent"' in html
    assert 'id="agent-conversation"' in html
    assert 'aria-label="Agent message composer"' in html
    assert 'data-panel-title="Agent"' in html


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
    assert 'data-menu-command="save"' in html
    assert 'data-command="import-openusd"' in html
    assert 'data-command="import-openusd-folder"' in html
    assert 'data-command="run"' in html
    assert 'data-documentation="viewport-controls"' in html
    assert 'href="./docs/viewport-controls.html"' in html
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
    assert "beefoundrysim-config.json" in bridge
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
    assert "normal_texture_url" in types
    assert "roughness_texture_url" in types
    assert "metallic_texture_url" in types
    assert "textureArtifactUrl" in bridge
    assert "'normalMap'" in viewport
    assert "'roughnessMap'" in viewport
    assert "'metalnessMap'" in viewport
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
    assert "setAttachmentCommands" in bridge
    assert "/attachments" in bridge
    assert "data-controller-status" in app
    assert "data-status='fault'" in style
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
    assert "export type SensorSample" in types
    for sensor_state in (
        "JointStateSensorSample",
        "ImuSensorSample",
        "ContactSensorSample",
        "RangefinderSensorSample",
    ):
        assert sensor_state in types
    assert "selectViewportLink" in app
    assert "selectedLinkId" in viewport
    assert "window.beefoundrysimEditor" in app
    assert "beefoundrysimEditorReady" in app
    assert "simulationStatus === 'running' ? 'running' : 'paused'" in app
    assert "loadTrajectory" in bridge
    assert "TrajectorySimulationState" in types
    assert 'data-panel="trajectory-editor"' in html
    assert "data-keyframe-add" in app
    assert "data-keyframe-target" in app
    assert "trajectoryFromDraft" in app
    assert "data-trajectory-clip" in app
    assert "data-trajectory-save" in app
    assert "store.upsertTrajectory" in app
    assert 'data-panel="recording"' in html
    assert 'data-panel="controller"' in html
    assert "data-recording-joint" in app
    assert "data-recording-sensor" in app
    assert "['joint_state', 'imu', 'contact', 'rangefinder']" in app
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
    assert "actorRenderSignatures" in viewport
    assert "actorLoadRevisions" in viewport
    assert "removeActorObject" in viewport
    assert "actorLoadIsCurrent" in viewport
    assert "syncAttachmentVisuals" in viewport
    assert "updateAttachmentVisuals" in viewport
    assert "addShippingPackageDetails" in viewport
    assert "four_cup_vacuum" in types
    assert "TorusGeometry" in viewport
    assert "delivery_tasks" in viewport
    assert "navigationRouteRevision" in viewport
    assert "replan_count" in types
    assert "renderer.shadowMap.enabled = true" in viewport
    assert "THREE.PCFSoftShadowMap" in viewport
    assert "addActorVisualDetails" in viewport
    assert "addInsulatedDeliveryBagDetails" in viewport
    assert "delivery-bag-oxford-albedo.png" in viewport
    assert "roundedRectangleGeometry" in viewport
    assert "new THREE.TubeGeometry" in viewport
    assert "landingPadTexture" in viewport
    assert "operationsDeckTexture" in viewport
    assert "navigationPulse" in viewport
    assert "ActorVisualStyle" in types
    assert "createProceduralEnvironmentTexture" in viewport
    assert "applyProceduralSurface" in viewport
    assert "new THREE.MeshPhysicalMaterial" in viewport
    assert "createFittedPbrVisual" in viewport
    assert "addConstructionFenceExtension" in viewport
    assert "loadPhotographicEnvironment" in viewport
    assert "photorealObstacleStatus" in viewport
    assert "photographicEnvironment" in viewport
    assert "cinematic_blue_hour_delivery" in viewport
    assert "addCinematicWetAsphaltDetails" in viewport
    assert "addRestaurantPickupDetails" in viewport
    assert "addResidentialDropoffDetails" in viewport
    assert "addDynamicDeliveryVanDetails" in viewport
    assert "addDynamicForkliftDetails" in viewport
    assert "dynamic_forklift" in types
    assert "addDynamicCourierDetails" in viewport
    assert "dynamic_events" in types
    assert "visual_model" in types
    assert "ActorVisualAnimation" in types
    assert "walking" in types
    assert "cycling" in types
    pbr_model_loader = (root / "ts" / "pbr-model-loader.ts").read_text(
        encoding="utf-8"
    )
    assert "GLTFLoader" in pbr_model_loader
    assert "gltfCache" in pbr_model_loader
    assert "SkeletonUtils" in pbr_model_loader
    assert "AnimationMixer" in pbr_model_loader
    assert "clip_url" in pbr_model_loader
    assert "instance.size" in pbr_model_loader
    assert "playbackRateForSpeed" in viewport
    assert "advanceActorVisualAnimations" in viewport
    assert "gltfAnimationStatus" in viewport
    photographic_environment = (
        root / "ts" / "photographic-environment.ts"
    ).read_text(encoding="utf-8")
    assert "RGBELoader" in photographic_environment
    assert "EquirectangularReflectionMapping" in photographic_environment
    procedural_materials = (root / "ts" / "procedural-materials.ts").read_text(
        encoding="utf-8"
    )
    assert "ProceduralSurfaceKind" in procedural_materials
    assert "material.bumpMap" in procedural_materials
    assert "material.roughnessMap" in procedural_materials
    assert "THREE.EquirectangularReflectionMapping" in procedural_materials
    assert "function clearActors" not in viewport
    assert "sceneRevision" not in viewport


def test_viewport_controls_document_covers_implemented_shortcuts() -> None:
    document = Path("frontend/public/docs/viewport-controls.html").read_text(encoding="utf-8")

    assert "Viewport 操作与快捷键" in document
    assert 'href="../"' in document
    for key in ("W", "E", "R", "F", "C", "0", "1", "3", "7"):
        assert f"<kbd>{key}</kbd>" in document
    assert "Ctrl" in document
    assert "Shift" in document
    assert "大型场景建议" in document


def test_optional_qt_shell_is_only_an_http_client() -> None:
    source = Path("src/beefoundrysim/main_window.py").read_text(encoding="utf-8")

    assert "QWebEngineView" in source
    assert "BEEFOUNDRYSIM_FRONTEND_URL" in source
    assert 'parsed.scheme() not in {"http", "https"}' in source
    assert "EditorBridge" not in source
    assert "QWebChannel" not in source
    assert "project_root" not in source
