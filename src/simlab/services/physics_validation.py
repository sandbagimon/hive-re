from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from simlab.models.actor import Actor
from simlab.models.scene import Scene
from simlab.services.mjcf_exporter import scene_to_mjcf_xml
from simlab.services.physics_materials import PHYSICS_MATERIALS, material_for_id
from simlab.services.primitive_geometry import (
    GeometryContractError,
    collider_geometry,
    source_geom_type,
)

ValidationSeverity = Literal["error", "warning"]
ModelLoader = Callable[[str], object]


@dataclass(frozen=True, slots=True)
class PhysicsValidationIssue:
    severity: ValidationSeverity
    code: str
    message: str
    actor_id: str | None = None
    actor_name: str | None = None
    field: str | None = None

    def format(self) -> str:
        location = self.actor_name or self.actor_id or "Scene"
        if self.actor_name and self.actor_id:
            location = f"{self.actor_name} ({self.actor_id})"
        if self.field:
            location = f"{location} / {self.field}"
        return f"[{self.severity.upper()}] {self.code}: {location}: {self.message}"


@dataclass(slots=True)
class PhysicsPreflightReport:
    issues: list[PhysicsValidationIssue] = field(default_factory=list)
    mjcf_xml: str | None = None
    mjcf_loaded: bool = False

    @property
    def errors(self) -> list[PhysicsValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "error"]

    @property
    def warnings(self) -> list[PhysicsValidationIssue]:
        return [issue for issue in self.issues if issue.severity == "warning"]

    @property
    def is_valid(self) -> bool:
        return not self.errors and self.mjcf_loaded

    def detailed_text(self) -> str:
        return "\n".join(issue.format() for issue in self.issues)


def run_physics_preflight(
    scene: Scene,
    *,
    model_loader: ModelLoader | None = None,
) -> PhysicsPreflightReport:
    """Validate physics properties, generate MJCF, and compile it with MuJoCo."""
    report = PhysicsPreflightReport()
    _validate_actor_ids(scene, report)

    physics_actor_count = 0
    for actor in scene.actors:
        if actor.type != "object":
            continue
        physics_actor_count += 1
        _validate_actor(actor, report)

    if physics_actor_count == 0:
        report.issues.append(
            PhysicsValidationIssue(
                severity="warning",
                code="NO_PHYSICS_ACTORS",
                message="The scene has no object actors to simulate.",
            )
        )

    if report.errors:
        return report

    try:
        report.mjcf_xml = scene_to_mjcf_xml(scene)
    except (TypeError, ValueError, IndexError) as exc:
        report.issues.append(
            PhysicsValidationIssue(
                severity="error",
                code="MJCF_GENERATION_FAILED",
                message=f"Could not generate MJCF: {exc}",
            )
        )
        return report

    if model_loader is None:
        try:
            import mujoco
        except ImportError:
            report.issues.append(
                PhysicsValidationIssue(
                    severity="error",
                    code="MUJOCO_NOT_INSTALLED",
                    message="MuJoCo is required to validate and run exported MJCF.",
                )
            )
            return report
        model_loader = mujoco.MjModel.from_xml_string

    try:
        model_loader(report.mjcf_xml)
    except Exception as exc:  # MuJoCo exposes several parser/compiler exception types.
        report.issues.append(
            PhysicsValidationIssue(
                severity="error",
                code="MJCF_LOAD_FAILED",
                message=f"MuJoCo rejected the generated model: {exc}",
            )
        )
        return report

    report.mjcf_loaded = True
    return report


def _validate_actor_ids(scene: Scene, report: PhysicsPreflightReport) -> None:
    seen: set[str] = set()
    for actor in scene.actors:
        if actor.id in seen:
            report.issues.append(
                _actor_issue(
                    actor,
                    "error",
                    "DUPLICATE_ACTOR_ID",
                    "Actor ids must be unique for MuJoCo body mapping.",
                    "id",
                )
            )
        seen.add(actor.id)


def _validate_actor(actor: Actor, report: PhysicsPreflightReport) -> None:
    try:
        collider_geometry(actor)
    except GeometryContractError as exc:
        report.issues.append(
            _actor_issue(
                actor,
                "error",
                exc.code,
                str(exc),
                exc.field,
            )
        )
        return
    geom_type = source_geom_type(actor)

    physics = actor.properties.get("physics", {})
    if not isinstance(physics, dict):
        report.issues.append(
            _actor_issue(
                actor,
                "error",
                "INVALID_PHYSICS_BLOCK",
                "Physics must be an object containing dynamic, mass, and friction.",
                "properties.physics",
            )
        )
        return

    dynamic = physics.get("dynamic", actor.properties.get("dynamic", True))
    if not isinstance(dynamic, bool):
        report.issues.append(
            _actor_issue(
                actor,
                "error",
                "INVALID_DYNAMIC",
                "Dynamic must be true or false.",
                "physics.dynamic",
            )
        )

    if dynamic is True and geom_type == "plane":
        report.issues.append(
            _actor_issue(
                actor,
                "error",
                "DYNAMIC_PLANE",
                "Plane geoms must be static. Disable Dynamic or use a thin box.",
                "physics.dynamic",
            )
        )

    material_id = str(physics.get("material", "default"))
    if material_id not in PHYSICS_MATERIALS:
        report.issues.append(
            _actor_issue(
                actor,
                "error",
                "UNKNOWN_PHYSICS_MATERIAL",
                f"Unknown physics material: {material_id}.",
                "physics.material",
            )
        )
    preset = material_for_id(material_id)

    mass_mode = physics.get("mass_mode", "mass")
    if mass_mode not in {"mass", "density"}:
        report.issues.append(
            _actor_issue(
                actor,
                "error",
                "INVALID_MASS_MODE",
                "Mass mode must be 'mass' or 'density'.",
                "physics.mass_mode",
            )
        )

    mass_is_explicit = "mass" in physics or "mass" in actor.properties
    mass = physics.get("mass", actor.properties.get("mass", 1.0))
    if dynamic is True:
        if mass_mode == "density":
            density = physics.get("density", preset.density)
            if not _is_finite_number(density) or float(density) <= 0:
                report.issues.append(
                    _actor_issue(
                        actor,
                        "error",
                        "INVALID_DENSITY",
                        "Material density must be a finite number greater than zero.",
                        "physics.density",
                    )
                )
        elif mass_mode == "mass" and (not _is_finite_number(mass) or float(mass) <= 0):
            report.issues.append(
                _actor_issue(
                    actor,
                    "error",
                    "INVALID_MASS",
                    "Dynamic actor mass must be a finite number greater than zero.",
                    "physics.mass",
                )
            )
    elif dynamic is False and mass_is_explicit:
        report.issues.append(
            _actor_issue(
                actor,
                "warning",
                "STATIC_MASS_IGNORED",
                "Mass is ignored because this actor is static.",
                "physics.mass",
            )
        )

    friction = physics.get("friction", actor.properties.get("friction", preset.friction))
    friction_values = _friction_values(friction)
    if friction_values is None:
        report.issues.append(
            _actor_issue(
                actor,
                "error",
                "INVALID_FRICTION",
                "Friction must be a finite non-negative number or a three-number array.",
                "physics.friction",
            )
        )
    elif any(value < 0 for value in friction_values):
        report.issues.append(
            _actor_issue(
                actor,
                "error",
                "NEGATIVE_FRICTION",
                "Friction values cannot be negative.",
                "physics.friction",
            )
        )

    _validate_contact_vector(actor, report, physics.get("solref", preset.solref), "solref", 2)
    _validate_contact_vector(actor, report, physics.get("solimp", preset.solimp), "solimp", 5)


def _friction_values(value: Any) -> list[float] | None:
    if _is_finite_number(value):
        return [float(value)]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) == 3:
        if all(_is_finite_number(item) for item in value):
            return [float(item) for item in value]
    return None


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _validate_contact_vector(
    actor: Actor,
    report: PhysicsPreflightReport,
    value: Any,
    field_name: str,
    length: int,
) -> None:
    valid = (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and len(value) == length
        and all(_is_finite_number(item) for item in value)
    )
    if valid:
        return
    report.issues.append(
        _actor_issue(
            actor,
            "error",
            f"INVALID_{field_name.upper()}",
            f"{field_name} must contain exactly {length} finite numbers.",
            f"physics.{field_name}",
        )
    )


def _actor_issue(
    actor: Actor,
    severity: ValidationSeverity,
    code: str,
    message: str,
    field_name: str,
) -> PhysicsValidationIssue:
    return PhysicsValidationIssue(
        severity=severity,
        code=code,
        message=message,
        actor_id=actor.id,
        actor_name=actor.name,
        field=field_name,
    )
