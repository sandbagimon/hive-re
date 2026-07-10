from simlab.services.physics_materials import PHYSICS_MATERIALS, material_for_id


def test_requested_physics_material_presets_are_available() -> None:
    assert {"rubber", "wood", "metal", "ice"}.issubset(PHYSICS_MATERIALS)

    for material_id in ("rubber", "wood", "metal", "ice"):
        material = material_for_id(material_id)
        assert material.density > 0
        assert len(material.friction) == 3
        assert len(material.solref) == 2
        assert len(material.solimp) == 5
        assert 0 <= material.roughness <= 1
        assert 0 <= material.metalness <= 1
