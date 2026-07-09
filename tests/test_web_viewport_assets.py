from pathlib import Path


def test_web_viewport_assets_are_packaged() -> None:
    root = Path("src/simlab/web_viewport")

    assert (root / "index.html").exists()
    assert (root / "viewport.js").exists()
    assert (root / "vendor" / "three.module.js").exists()
    assert (root / "vendor" / "OrbitControls.js").exists()
    assert (root / "vendor" / "TransformControls.js").exists()
    assert (root / "vendor" / "THREE_LICENSE.txt").exists()
