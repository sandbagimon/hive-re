from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PhysicsMaterial:
    id: str
    label: str
    density: float
    friction: tuple[float, float, float]
    solref: tuple[float, float]
    solimp: tuple[float, float, float, float, float]
    roughness: float
    metalness: float

    def property_values(self) -> dict[str, object]:
        return {
            "material": self.id,
            "density": self.density,
            "friction": list(self.friction),
            "solref": list(self.solref),
            "solimp": list(self.solimp),
            "roughness": self.roughness,
            "metalness": self.metalness,
        }


PHYSICS_MATERIALS = {
    material.id: material
    for material in (
        PhysicsMaterial(
            "default",
            "Default",
            1000.0,
            (0.8, 0.005, 0.0001),
            (0.02, 1.0),
            (0.9, 0.95, 0.001, 0.5, 2.0),
            0.55,
            0.04,
        ),
        PhysicsMaterial(
            "rubber",
            "Rubber",
            1100.0,
            (1.2, 0.01, 0.0002),
            (0.03, 1.0),
            (0.88, 0.96, 0.002, 0.5, 2.0),
            0.86,
            0.0,
        ),
        PhysicsMaterial(
            "wood",
            "Wood",
            700.0,
            (0.6, 0.004, 0.0001),
            (0.015, 1.0),
            (0.9, 0.95, 0.001, 0.5, 2.0),
            0.72,
            0.0,
        ),
        PhysicsMaterial(
            "metal",
            "Metal",
            7800.0,
            (0.35, 0.003, 0.0001),
            (0.008, 1.0),
            (0.92, 0.97, 0.0005, 0.5, 2.0),
            0.24,
            0.82,
        ),
        PhysicsMaterial(
            "ice",
            "Ice",
            917.0,
            (0.03, 0.001, 0.00005),
            (0.01, 1.0),
            (0.92, 0.98, 0.0005, 0.5, 2.0),
            0.12,
            0.08,
        ),
    )
}

DEFAULT_MATERIAL_ID = "default"


def material_for_id(material_id: object) -> PhysicsMaterial:
    return PHYSICS_MATERIALS.get(str(material_id), PHYSICS_MATERIALS[DEFAULT_MATERIAL_ID])
