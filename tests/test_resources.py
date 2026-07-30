from __future__ import annotations

from pathlib import Path

from simlab.resources import ResourceManager
from simlab.services.openusd.asset_cache import atomic_write_bytes


def test_project_seed_copy_skips_development_sources_and_is_independent(
    tmp_path: Path,
) -> None:
    seed = tmp_path / "seed"
    (seed / "imported" / "robot").mkdir(parents=True)
    (seed / "external" / "downloads").mkdir(parents=True)
    (seed / "metadata.json").write_text('{"assets": []}\n', encoding="utf-8")
    cached = seed / "imported" / "robot" / "visual.simbin"
    cached.write_bytes(b"cached geometry")
    (seed / "external" / "downloads" / "source.usd").write_bytes(b"developer source")
    manager = ResourceManager(tmp_path / "data", seed)

    project = manager.create_project()
    project_cache = project.root / "assets" / "imported" / "robot" / "visual.simbin"

    atomic_write_bytes(project_cache, b"project replacement")

    assert project_cache.is_file()
    assert project_cache.read_bytes() == b"project replacement"
    assert cached.read_bytes() == b"cached geometry"
    assert not (project.root / "assets" / "external").exists()
