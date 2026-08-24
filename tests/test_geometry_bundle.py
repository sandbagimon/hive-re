from __future__ import annotations

from beefoundrysim.services.openusd.geometry_bundle import (
    BUNDLE_MAGIC,
    GeometryBundleMesh,
    build_geometry_bundle,
    read_geometry_bundle_header,
)
from beefoundrysim.services.openusd.mesh_extractor import MeshData


def test_geometry_bundle_packs_typed_mesh_data_and_precomputed_normals() -> None:
    mesh = MeshData(
        positions=[0, 0, 0, 1, 0, 0, 0, 1, 0],
        indices=[0, 1, 2],
        colors=[1, 0, 0, 1, 0, 1, 0, 1, 0, 0, 1, 1],
        uvs=[0, 0, 1, 0, 0, 1],
    )

    bundle = build_geometry_bundle([("visual_one", mesh)])
    header = read_geometry_bundle_header(bundle.content)
    entry = header["geometries"]["visual_one"]

    assert bundle.content.startswith(BUNDLE_MAGIC)
    assert bundle.geometry_count == 1
    assert bundle.vertex_count == 3
    assert bundle.triangle_count == 1
    assert entry["positions"][1] == 9
    assert entry["indices"][1] == 3
    assert entry["normals"][1] == 9
    assert entry["colors"][1] == 9
    assert entry["uvs"][1] == 6
    assert entry["bounds"] == {
        "min": [0, 0, 0],
        "max": [1, 1, 0],
        "sphere": [0.5, 0.5, 0.0, 2**0.5 / 2],
    }


def test_geometry_bundle_packs_gpu_instances_and_material_reference() -> None:
    mesh = MeshData(
        positions=[0, 0, 0, 1, 0, 0, 0, 1, 0],
        indices=[0, 1, 2],
    )
    matrices = [
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        0, 0, 0, 1,
        1, 0, 0, 0,
        0, 1, 0, 0,
        0, 0, 1, 0,
        4, 5, 6, 1,
    ]

    bundle = build_geometry_bundle([
        GeometryBundleMesh("grass", mesh, "mat_green", matrices)
    ])
    entry = read_geometry_bundle_header(bundle.content)["geometries"]["grass"]

    assert entry["material"] == "mat_green"
    assert entry["instances"][1] == 32
    assert bundle.vertex_count == 6
    assert bundle.triangle_count == 2


def test_geometry_bundle_is_smaller_than_the_equivalent_json_payload() -> None:
    vertex_count = 1000
    mesh = MeshData(
        positions=[float(index % 17) / 17 for index in range(vertex_count * 3)],
        indices=list(range(999)),
        colors=[0.5, 0.6, 0.7, 1.0] * vertex_count,
    )

    bundle = build_geometry_bundle([("mesh", mesh)])

    # The legacy JSON contains at least this many scalar characters plus delimiters.
    legacy_floor = sum(len(str(value)) for value in mesh.positions + mesh.colors)
    assert len(bundle.content) < legacy_floor
