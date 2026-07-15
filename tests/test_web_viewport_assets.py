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
    app = (root / "ts" / "app.ts").read_text(encoding="utf-8")
    viewport = (root / "ts" / "viewport.ts").read_text(encoding="utf-8")

    assert 'id="asset-list"' in html
    assert 'id="scene-tree"' in html
    assert 'id="property-inspector"' in html
    assert 'id="console-output"' in html
    assert 'data-command="save"' in html
    assert 'data-command="import-openusd"' in html
    assert 'data-command="run"' in html
    assert "class EditorStore" in (root / "ts" / "store.ts").read_text(encoding="utf-8")
    assert "store.undo()" in app
    assert "store.selectActor" in app
    assert "importOpenUsd" in app
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
