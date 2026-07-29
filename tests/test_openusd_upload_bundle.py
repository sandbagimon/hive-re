from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from simlab.services.openusd.upload_bundle import (
    safe_relative_path,
    stage_openusd_bytes,
)
from simlab.services.openusd_importer import import_openusd_asset


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def test_upload_bundle_preserves_directory_paths(tmp_path: Path) -> None:
    fixture = Path("tests/fixtures/openusd/composite")
    files = [
        ("composite/root.usda", (fixture / "root.usda").read_bytes()),
        (
            "composite/parts/geometry.usda",
            (fixture / "parts" / "geometry.usda").read_bytes(),
        ),
    ]

    staged = stage_openusd_bytes(tmp_path, files, "composite/root.usda")

    assert staged.entry_path == staged.root / "composite" / "root.usda"
    assert (staged.root / "composite" / "parts" / "geometry.usda").is_file()
    assert staged.file_count == 2


def test_zip_package_is_safely_expanded_and_selects_shallow_entry(
    tmp_path: Path,
) -> None:
    fixture = Path("tests/fixtures/openusd/composite")
    package = _zip_bytes(
        {
            "root.usda": (fixture / "root.usda").read_bytes(),
            "parts/geometry.usda": (fixture / "parts" / "geometry.usda").read_bytes(),
        }
    )

    staged = stage_openusd_bytes(tmp_path, [("scene.zip", package)], "scene.zip")
    imported = import_openusd_asset(staged.entry_path, tmp_path)

    assert staged.entry_path == staged.root / "package" / "root.usda"
    assert (staged.root / "package" / "parts" / "geometry.usda").is_file()
    assert imported.asset["type"] == "object"


def test_zip_package_rejects_traversal_and_ambiguous_entries(tmp_path: Path) -> None:
    traversal = _zip_bytes({"../escaped.usda": b"#usda 1.0\n"})
    with pytest.raises(ValueError, match="Unsafe uploaded path"):
        stage_openusd_bytes(tmp_path, [("unsafe.zip", traversal)], "unsafe.zip")

    ambiguous = _zip_bytes(
        {
            "first.usda": b"#usda 1.0\n",
            "second.usda": b"#usda 1.0\n",
        }
    )
    with pytest.raises(ValueError, match="multiple possible entry files"):
        stage_openusd_bytes(tmp_path, [("ambiguous.zip", ambiguous)], "ambiguous.zip")


def test_self_contained_usdz_imports_without_extraction(tmp_path: Path) -> None:
    pytest.importorskip("pxr")
    from pxr import Sdf, UsdUtils

    source = Path("tests/fixtures/openusd/tetrahedron.usda").resolve()
    package = tmp_path / "tetrahedron.usdz"
    assert UsdUtils.CreateNewUsdzPackage(Sdf.AssetPath(str(source)), str(package))

    staged = stage_openusd_bytes(
        tmp_path / "project",
        [(package.name, package.read_bytes())],
        package.name,
    )
    imported = import_openusd_asset(staged.entry_path, tmp_path / "project")

    assert staged.entry_path.suffix == ".usdz"
    assert imported.asset["name"] == "tetrahedron"


@pytest.mark.parametrize("value", ["../scene.usda", "/scene.usda", "C:/scene.usda"])
def test_uploaded_paths_reject_escape(value: str) -> None:
    with pytest.raises(ValueError, match="Unsafe uploaded path"):
        safe_relative_path(value)
