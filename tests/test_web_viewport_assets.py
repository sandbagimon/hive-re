from pathlib import Path


def test_web_viewport_assets_are_packaged() -> None:
    root = Path("src/simlab/web_viewport")

    assert (root / "index.html").exists()
    assert (root / "viewport.js").exists()
    assert (root / "vendor" / "three.module.js").exists()
    assert (root / "vendor" / "OrbitControls.js").exists()
    assert (root / "vendor" / "TransformControls.js").exists()
    assert (root / "vendor" / "THREE_LICENSE.txt").exists()


def test_web_viewport_editing_tools_are_declared() -> None:
    root = Path("src/simlab/web_viewport")
    html = (root / "index.html").read_text(encoding="utf-8")
    script = (root / "viewport.js").read_text(encoding="utf-8")

    assert 'data-tool="translate"' in html
    assert 'data-tool="rotate"' in html
    assert 'data-tool="scale"' in html
    assert 'data-action="frame"' in html
    assert 'data-camera="front"' in html
    assert "setTransformMode(mode)" in script
    assert "frameSelected()" in script
    assert "setCameraView(viewName)" in script
    assert "selectionOutline" in script
    assert "window.QWebChannel" in script
