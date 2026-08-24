from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal


def _vector3(value: object, field_name: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{field_name} must contain xyz")
    try:
        result = tuple(float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must contain numeric values") from exc
    if any(not math.isfinite(item) for item in result):
        raise ValueError(f"{field_name} values must be finite")
    return result  # type: ignore[return-value]


def _vector2(value: object, field_name: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{field_name} must contain xy")
    try:
        result = tuple(float(item) for item in value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must contain numeric values") from exc
    if any(not math.isfinite(item) for item in result):
        raise ValueError(f"{field_name} values must be finite")
    return result  # type: ignore[return-value]


@dataclass(frozen=True, slots=True)
class VacuumGripper:
    """A four-cup vacuum head fixed to the attachment parent body."""

    type: Literal["four_cup_vacuum"] = "four_cup_vacuum"
    plate_half_extents: tuple[float, float, float] = (0.08, 0.06, 0.01)
    cup_offset: tuple[float, float] = (0.05, 0.035)
    cup_radius: float = 0.018
    cup_height: float = 0.02
    mount_radius: float = 0.012
    mount_length: float = 0.08

    def __post_init__(self) -> None:
        if self.type != "four_cup_vacuum":
            raise ValueError(f"Unsupported gripper type: {self.type}")
        object.__setattr__(
            self,
            "plate_half_extents",
            _vector3(self.plate_half_extents, "plate_half_extents"),
        )
        object.__setattr__(self, "cup_offset", _vector2(self.cup_offset, "cup_offset"))
        for name in ("cup_radius", "cup_height", "mount_radius", "mount_length"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"Vacuum gripper {name} must be finite and > 0")
            object.__setattr__(self, name, value)
        if any(value <= 0 for value in self.plate_half_extents):
            raise ValueError("Vacuum gripper plate half extents must be positive")
        if any(value <= 0 for value in self.cup_offset):
            raise ValueError("Vacuum gripper cup offsets must be positive")
        if (
            self.cup_offset[0] + self.cup_radius > self.plate_half_extents[0]
            or self.cup_offset[1] + self.cup_radius > self.plate_half_extents[1]
        ):
            raise ValueError("Vacuum cups must fit below the gripper plate")

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "plate_half_extents": list(self.plate_half_extents),
            "cup_offset": list(self.cup_offset),
            "cup_radius": self.cup_radius,
            "cup_height": self.cup_height,
            "mount_radius": self.mount_radius,
            "mount_length": self.mount_length,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VacuumGripper:
        return cls(
            type=str(data.get("type", "four_cup_vacuum")),  # type: ignore[arg-type]
            plate_half_extents=_vector3(
                data.get("plate_half_extents", [0.08, 0.06, 0.01]),
                "plate_half_extents",
            ),
            cup_offset=_vector2(data.get("cup_offset", [0.05, 0.035]), "cup_offset"),
            cup_radius=float(data.get("cup_radius", 0.018)),
            cup_height=float(data.get("cup_height", 0.02)),
            mount_radius=float(data.get("mount_radius", 0.012)),
            mount_length=float(data.get("mount_length", 0.08)),
        )


@dataclass(frozen=True, slots=True)
class Attachment:
    """A runtime-switchable point connection between two physics bodies."""

    id: str
    parent_body_id: str
    child_body_id: str
    parent_anchor: tuple[float, float, float]
    child_anchor: tuple[float, float, float]
    constraint_type: Literal["connect", "weld"] = "connect"
    gripper: VacuumGripper | None = None
    initially_active: bool = False
    capture_distance: float = 0.05
    capture_speed: float = 0.15
    capture_duration: float = 0.2
    require_contact: bool = True
    contact_probe_radius: float = 0.025
    solref: tuple[float, float] = (0.03, 1.0)
    solimp: tuple[float, float, float, float, float] = (
        0.9,
        0.95,
        0.001,
        0.5,
        2.0,
    )

    def __post_init__(self) -> None:
        if not self.id or not self.parent_body_id or not self.child_body_id:
            raise ValueError("Attachment and body IDs must not be empty")
        if self.parent_body_id == self.child_body_id:
            raise ValueError(f"Attachment {self.id} must connect two different bodies")
        if self.constraint_type not in {"connect", "weld"}:
            raise ValueError(f"Unsupported attachment type: {self.constraint_type}")
        object.__setattr__(self, "parent_anchor", _vector3(self.parent_anchor, "parent_anchor"))
        object.__setattr__(self, "child_anchor", _vector3(self.child_anchor, "child_anchor"))
        numeric = {
            "capture_distance": self.capture_distance,
            "capture_speed": self.capture_speed,
            "capture_duration": self.capture_duration,
            "contact_probe_radius": self.contact_probe_radius,
        }
        for name, raw in numeric.items():
            value = float(raw)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"Attachment {name} must be finite and >= 0")
            object.__setattr__(self, name, value)
        if self.capture_distance <= 0 or self.capture_speed <= 0:
            raise ValueError("Attachment capture distance and speed must be greater than zero")
        if self.require_contact and self.contact_probe_radius <= 0:
            raise ValueError("Contact-gated attachments require a positive probe radius")
        solref = tuple(float(item) for item in self.solref)
        solimp = tuple(float(item) for item in self.solimp)
        if len(solref) != 2 or len(solimp) != 5:
            raise ValueError("Attachment solref/solimp dimensions are invalid")
        if any(not math.isfinite(item) for item in (*solref, *solimp)):
            raise ValueError("Attachment solver values must be finite")
        object.__setattr__(self, "solref", solref)
        object.__setattr__(self, "solimp", solimp)

    def to_dict(self) -> dict[str, Any]:
        data = {
            "id": self.id,
            "type": self.constraint_type,
            "parent_body_id": self.parent_body_id,
            "child_body_id": self.child_body_id,
            "parent_anchor": list(self.parent_anchor),
            "child_anchor": list(self.child_anchor),
            "initially_active": self.initially_active,
            "capture_distance": self.capture_distance,
            "capture_speed": self.capture_speed,
            "capture_duration": self.capture_duration,
            "require_contact": self.require_contact,
            "contact_probe_radius": self.contact_probe_radius,
            "solref": list(self.solref),
            "solimp": list(self.solimp),
        }
        if self.gripper is not None:
            data["gripper"] = self.gripper.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Attachment:
        attachment_type = str(data.get("type", "connect"))
        gripper = data.get("gripper")
        return cls(
            id=str(data["id"]),
            parent_body_id=str(data["parent_body_id"]),
            child_body_id=str(data["child_body_id"]),
            parent_anchor=_vector3(data.get("parent_anchor", [0, 0, 0]), "parent_anchor"),
            child_anchor=_vector3(data.get("child_anchor", [0, 0, 0]), "child_anchor"),
            constraint_type=attachment_type,  # type: ignore[arg-type]
            gripper=VacuumGripper.from_dict(gripper) if gripper is not None else None,
            initially_active=bool(data.get("initially_active", False)),
            capture_distance=float(data.get("capture_distance", 0.05)),
            capture_speed=float(data.get("capture_speed", 0.15)),
            capture_duration=float(data.get("capture_duration", 0.2)),
            require_contact=bool(data.get("require_contact", True)),
            contact_probe_radius=float(data.get("contact_probe_radius", 0.025)),
            solref=tuple(data.get("solref", [0.03, 1.0])),  # type: ignore[arg-type]
            solimp=tuple(data.get("solimp", [0.9, 0.95, 0.001, 0.5, 2.0])),  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class DeliveryTask:
    """Success criteria for transporting one attached payload to a drop point."""

    id: str
    attachment_id: str
    payload_body_id: str
    pickup_position: tuple[float, float, float]
    dropoff_position: tuple[float, float, float]
    position_tolerance: float = 0.35
    settle_speed: float = 0.15
    settle_duration: float = 0.5

    def __post_init__(self) -> None:
        if not self.id or not self.attachment_id or not self.payload_body_id:
            raise ValueError("Delivery task IDs must not be empty")
        object.__setattr__(
            self, "pickup_position", _vector3(self.pickup_position, "pickup_position")
        )
        object.__setattr__(
            self, "dropoff_position", _vector3(self.dropoff_position, "dropoff_position")
        )
        for name in ("position_tolerance", "settle_speed", "settle_duration"):
            value = float(getattr(self, name))
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"Delivery task {name} must be finite and > 0")
            object.__setattr__(self, name, value)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": "aerial_delivery",
            "attachment_id": self.attachment_id,
            "payload_body_id": self.payload_body_id,
            "pickup_position": list(self.pickup_position),
            "dropoff_position": list(self.dropoff_position),
            "position_tolerance": self.position_tolerance,
            "settle_speed": self.settle_speed,
            "settle_duration": self.settle_duration,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeliveryTask:
        task_type = str(data.get("type", "aerial_delivery"))
        if task_type != "aerial_delivery":
            raise ValueError(f"Unsupported task type: {task_type}")
        return cls(
            id=str(data["id"]),
            attachment_id=str(data["attachment_id"]),
            payload_body_id=str(data["payload_body_id"]),
            pickup_position=_vector3(data["pickup_position"], "pickup_position"),
            dropoff_position=_vector3(data["dropoff_position"], "dropoff_position"),
            position_tolerance=float(data.get("position_tolerance", 0.35)),
            settle_speed=float(data.get("settle_speed", 0.15)),
            settle_duration=float(data.get("settle_duration", 0.5)),
        )
