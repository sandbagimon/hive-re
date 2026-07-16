from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

GeometryType = Literal["box", "sphere", "ellipsoid", "cylinder", "capsule", "mesh"]
JointType = Literal["fixed", "revolute", "continuous", "prismatic"]
ControlType = Literal["position", "velocity", "motor"]
ContactAggregationMode = Literal["sum"]
SensorType = Literal[
    "joint_state",
    "joint_position",
    "joint_velocity",
    "actuator_force",
    "contact",
    "imu",
]


def _float_list(value: Any, length: int, field_name: str) -> list[float]:
    result = [float(item) for item in value]
    if len(result) != length:
        msg = f"{field_name} must contain {length} values"
        raise ValueError(msg)
    return result


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


NoiseValue = float | list[float]


def _noise_value(value: Any) -> NoiseValue:
    if isinstance(value, (list, tuple)):
        return [float(item) for item in value]
    return float(value)


@dataclass(slots=True)
class SensorNoiseChannel:
    bias: NoiseValue
    standard_deviation: NoiseValue

    def __post_init__(self) -> None:
        self.bias = _noise_value(self.bias)
        self.standard_deviation = _noise_value(self.standard_deviation)

    def to_dict(self) -> dict[str, NoiseValue]:
        return {
            "bias": list(self.bias) if isinstance(self.bias, list) else self.bias,
            "standard_deviation": (
                list(self.standard_deviation)
                if isinstance(self.standard_deviation, list)
                else self.standard_deviation
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SensorNoiseChannel:
        return cls(
            bias=data["bias"],
            standard_deviation=data["standard_deviation"],
        )


@dataclass(slots=True)
class SensorNoise:
    seed: int
    channels: dict[str, SensorNoiseChannel]

    def __post_init__(self) -> None:
        self.seed = int(self.seed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "channels": {
                name: channel.to_dict() for name, channel in self.channels.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SensorNoise:
        return cls(
            seed=int(data["seed"]),
            channels={
                str(name): SensorNoiseChannel.from_dict(channel)
                for name, channel in data.get("channels", {}).items()
            },
        )


@dataclass(slots=True)
class RigidTransform:
    """A local rigid transform using an xyzw quaternion."""

    position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    quaternion: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0, 1.0])

    def __post_init__(self) -> None:
        self.position = _float_list(self.position, 3, "position")
        self.quaternion = _float_list(self.quaternion, 4, "quaternion")

    def to_dict(self) -> dict[str, list[float]]:
        return {"position": list(self.position), "quaternion": list(self.quaternion)}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> RigidTransform:
        data = data or {}
        return cls(
            position=data.get("position", [0.0, 0.0, 0.0]),
            quaternion=data.get("quaternion", [0.0, 0.0, 0.0, 1.0]),
        )


@dataclass(slots=True)
class VisualGeometry:
    id: str
    name: str
    geometry_type: GeometryType
    transform: RigidTransform = field(default_factory=RigidTransform)
    size: list[float] = field(default_factory=lambda: [1.0])
    asset_uri: str | None = None
    source_prim_path: str | None = None
    rgba: list[float] = field(default_factory=lambda: [0.7, 0.7, 0.7, 1.0])
    roughness: float | None = None
    metalness: float | None = None

    def __post_init__(self) -> None:
        self.size = [float(item) for item in self.size]
        self.rgba = _float_list(self.rgba, 4, "rgba")
        self.roughness = _optional_float(self.roughness)
        self.metalness = _optional_float(self.metalness)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "geometry_type": self.geometry_type,
            "transform": self.transform.to_dict(),
            "size": list(self.size),
            "asset_uri": self.asset_uri,
            "source_prim_path": self.source_prim_path,
            "rgba": list(self.rgba),
            "roughness": self.roughness,
            "metalness": self.metalness,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VisualGeometry:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            geometry_type=data["geometry_type"],
            transform=RigidTransform.from_dict(data.get("transform")),
            size=list(data.get("size", [1.0])),
            asset_uri=data.get("asset_uri"),
            source_prim_path=data.get("source_prim_path"),
            rgba=list(data.get("rgba", [0.7, 0.7, 0.7, 1.0])),
            roughness=data.get("roughness"),
            metalness=data.get("metalness"),
        )


@dataclass(slots=True)
class Collider:
    id: str
    name: str
    geometry_type: GeometryType
    transform: RigidTransform = field(default_factory=RigidTransform)
    size: list[float] = field(default_factory=lambda: [1.0])
    asset_uri: str | None = None
    source_prim_path: str | None = None
    friction: list[float] = field(default_factory=lambda: [1.0, 0.005, 0.0001])
    restitution: float = 0.0

    def __post_init__(self) -> None:
        self.size = [float(item) for item in self.size]
        self.friction = _float_list(self.friction, 3, "friction")
        self.restitution = float(self.restitution)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "geometry_type": self.geometry_type,
            "transform": self.transform.to_dict(),
            "size": list(self.size),
            "asset_uri": self.asset_uri,
            "source_prim_path": self.source_prim_path,
            "friction": list(self.friction),
            "restitution": self.restitution,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Collider:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            geometry_type=data["geometry_type"],
            transform=RigidTransform.from_dict(data.get("transform")),
            size=list(data.get("size", [1.0])),
            asset_uri=data.get("asset_uri"),
            source_prim_path=data.get("source_prim_path"),
            friction=list(data.get("friction", [1.0, 0.005, 0.0001])),
            restitution=float(data.get("restitution", 0.0)),
        )


@dataclass(slots=True)
class Inertial:
    mass: float
    center_of_mass: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    diagonal_inertia: list[float] | None = None
    full_inertia: list[float] | None = None

    def __post_init__(self) -> None:
        self.mass = float(self.mass)
        self.center_of_mass = _float_list(self.center_of_mass, 3, "center_of_mass")
        if self.diagonal_inertia is not None:
            self.diagonal_inertia = _float_list(
                self.diagonal_inertia, 3, "diagonal_inertia"
            )
        if self.full_inertia is not None:
            self.full_inertia = _float_list(self.full_inertia, 6, "full_inertia")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mass": self.mass,
            "center_of_mass": list(self.center_of_mass),
            "diagonal_inertia": (
                list(self.diagonal_inertia) if self.diagonal_inertia is not None else None
            ),
            "full_inertia": list(self.full_inertia) if self.full_inertia is not None else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Inertial:
        return cls(
            mass=float(data["mass"]),
            center_of_mass=list(data.get("center_of_mass", [0.0, 0.0, 0.0])),
            diagonal_inertia=(
                list(data["diagonal_inertia"])
                if data.get("diagonal_inertia") is not None
                else None
            ),
            full_inertia=(
                list(data["full_inertia"])
                if data.get("full_inertia") is not None
                else None
            ),
        )


@dataclass(slots=True)
class Link:
    id: str
    name: str
    parent_link_id: str | None = None
    transform: RigidTransform = field(default_factory=RigidTransform)
    visual_geometries: list[VisualGeometry] = field(default_factory=list)
    colliders: list[Collider] = field(default_factory=list)
    inertial: Inertial | None = None
    source_prim_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "parent_link_id": self.parent_link_id,
            "transform": self.transform.to_dict(),
            "visual_geometries": [geometry.to_dict() for geometry in self.visual_geometries],
            "colliders": [collider.to_dict() for collider in self.colliders],
            "inertial": self.inertial.to_dict() if self.inertial is not None else None,
            "source_prim_path": self.source_prim_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Link:
        inertial = data.get("inertial")
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            parent_link_id=data.get("parent_link_id"),
            transform=RigidTransform.from_dict(data.get("transform")),
            visual_geometries=[
                VisualGeometry.from_dict(item) for item in data.get("visual_geometries", [])
            ],
            colliders=[Collider.from_dict(item) for item in data.get("colliders", [])],
            inertial=Inertial.from_dict(inertial) if inertial is not None else None,
            source_prim_path=data.get("source_prim_path"),
        )


@dataclass(slots=True)
class JointLimits:
    lower: float | None = None
    upper: float | None = None
    effort: float | None = None
    velocity: float | None = None

    def __post_init__(self) -> None:
        self.lower = _optional_float(self.lower)
        self.upper = _optional_float(self.upper)
        self.effort = _optional_float(self.effort)
        self.velocity = _optional_float(self.velocity)

    def to_dict(self) -> dict[str, float | None]:
        return {
            "lower": self.lower,
            "upper": self.upper,
            "effort": self.effort,
            "velocity": self.velocity,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JointLimits:
        return cls(
            lower=data.get("lower"),
            upper=data.get("upper"),
            effort=data.get("effort"),
            velocity=data.get("velocity"),
        )


@dataclass(slots=True)
class Joint:
    id: str
    name: str
    type: JointType
    parent_link_id: str
    child_link_id: str
    origin: RigidTransform = field(default_factory=RigidTransform)
    axis: list[float] = field(default_factory=lambda: [0.0, 0.0, 1.0])
    limits: JointLimits | None = None
    initial_position: float = 0.0
    source_prim_path: str | None = None

    def __post_init__(self) -> None:
        self.axis = _float_list(self.axis, 3, "axis")
        self.initial_position = float(self.initial_position)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "parent_link_id": self.parent_link_id,
            "child_link_id": self.child_link_id,
            "origin": self.origin.to_dict(),
            "axis": list(self.axis),
            "limits": self.limits.to_dict() if self.limits is not None else None,
            "initial_position": self.initial_position,
            "source_prim_path": self.source_prim_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Joint:
        limits = data.get("limits")
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            type=data["type"],
            parent_link_id=str(data["parent_link_id"]),
            child_link_id=str(data["child_link_id"]),
            origin=RigidTransform.from_dict(data.get("origin")),
            axis=list(data.get("axis", [0.0, 0.0, 1.0])),
            limits=JointLimits.from_dict(limits) if limits is not None else None,
            initial_position=float(data.get("initial_position", 0.0)),
            source_prim_path=data.get("source_prim_path"),
        )


@dataclass(slots=True)
class Actuator:
    id: str
    name: str
    joint_id: str
    control_type: ControlType
    control_range: list[float]
    stiffness: float = 0.0
    damping: float = 0.0
    max_force: float | None = None
    source_prim_path: str | None = None

    def __post_init__(self) -> None:
        self.control_range = _float_list(self.control_range, 2, "control_range")
        self.stiffness = float(self.stiffness)
        self.damping = float(self.damping)
        self.max_force = _optional_float(self.max_force)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "joint_id": self.joint_id,
            "control_type": self.control_type,
            "control_range": list(self.control_range),
            "stiffness": self.stiffness,
            "damping": self.damping,
            "max_force": self.max_force,
            "source_prim_path": self.source_prim_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Actuator:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            joint_id=str(data["joint_id"]),
            control_type=data["control_type"],
            control_range=list(data["control_range"]),
            stiffness=float(data.get("stiffness", 0.0)),
            damping=float(data.get("damping", 0.0)),
            max_force=data.get("max_force"),
            source_prim_path=data.get("source_prim_path"),
        )


@dataclass(slots=True)
class Sensor:
    id: str
    name: str
    sensor_type: SensorType
    link_id: str | None = None
    joint_id: str | None = None
    collider_id: str | None = None
    aggregation_mode: ContactAggregationMode | None = None
    update_rate_hz: float | None = None
    local_transform: RigidTransform | None = None
    noise: SensorNoise | None = None
    source_prim_path: str | None = None

    def __post_init__(self) -> None:
        self.update_rate_hz = _optional_float(self.update_rate_hz)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "sensor_type": self.sensor_type,
            "link_id": self.link_id,
            "joint_id": self.joint_id,
            "update_rate_hz": self.update_rate_hz,
            "source_prim_path": self.source_prim_path,
        }
        if self.local_transform is not None:
            data["local_transform"] = self.local_transform.to_dict()
        if self.collider_id is not None:
            data["collider_id"] = self.collider_id
        if self.aggregation_mode is not None:
            data["aggregation_mode"] = self.aggregation_mode
        if self.noise is not None:
            data["noise"] = self.noise.to_dict()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Sensor:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            sensor_type=data["sensor_type"],
            link_id=data.get("link_id"),
            joint_id=data.get("joint_id"),
            collider_id=data.get("collider_id"),
            aggregation_mode=data.get("aggregation_mode"),
            update_rate_hz=data.get("update_rate_hz"),
            local_transform=(
                RigidTransform.from_dict(data["local_transform"])
                if data.get("local_transform") is not None
                else None
            ),
            noise=(
                SensorNoise.from_dict(data["noise"])
                if data.get("noise") is not None
                else None
            ),
            source_prim_path=data.get("source_prim_path"),
        )


@dataclass(slots=True)
class Articulation:
    id: str
    name: str
    root_link_id: str
    fixed_base: bool
    links: list[Link]
    joints: list[Joint] = field(default_factory=list)
    actuators: list[Actuator] = field(default_factory=list)
    sensors: list[Sensor] = field(default_factory=list)
    source_uri: str | None = None
    source_prim_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "root_link_id": self.root_link_id,
            "fixed_base": self.fixed_base,
            "source_uri": self.source_uri,
            "source_prim_path": self.source_prim_path,
            "links": [link.to_dict() for link in self.links],
            "joints": [joint.to_dict() for joint in self.joints],
            "actuators": [actuator.to_dict() for actuator in self.actuators],
            "sensors": [sensor.to_dict() for sensor in self.sensors],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Articulation:
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            root_link_id=str(data["root_link_id"]),
            fixed_base=bool(data["fixed_base"]),
            source_uri=data.get("source_uri"),
            source_prim_path=data.get("source_prim_path"),
            links=[Link.from_dict(item) for item in data.get("links", [])],
            joints=[Joint.from_dict(item) for item in data.get("joints", [])],
            actuators=[Actuator.from_dict(item) for item in data.get("actuators", [])],
            sensors=[Sensor.from_dict(item) for item in data.get("sensors", [])],
        )


@dataclass(slots=True)
class RoboticsModel:
    version: str = "1.0"
    articulations: list[Articulation] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "articulations": [item.to_dict() for item in self.articulations],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, validate: bool = True) -> RoboticsModel:
        model = cls(
            version=str(data["version"]),
            articulations=[
                Articulation.from_dict(item) for item in data.get("articulations", [])
            ],
        )
        if validate:
            from simlab.services.robotics_validation import validate_robotics_model

            validate_robotics_model(model)
        return model
