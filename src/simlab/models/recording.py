from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True, slots=True)
class RecordingManifest:
    engine_version: str
    timestep: float
    scene_version: str
    engine: str = "mujoco"

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "engine_version": self.engine_version,
            "timestep": self.timestep,
            "scene_version": self.scene_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecordingManifest:
        return cls(
            engine=str(data.get("engine", "mujoco")),
            engine_version=str(data["engine_version"]),
            timestep=float(data["timestep"]),
            scene_version=str(data["scene_version"]),
        )


@dataclass(frozen=True, slots=True)
class JointRecordingState:
    qpos: float
    qvel: float

    def to_dict(self) -> dict[str, float]:
        return {"qpos": self.qpos, "qvel": self.qvel}


@dataclass(frozen=True, slots=True)
class ActuatorRecordingState:
    ctrl: float
    force: float

    def to_dict(self) -> dict[str, float]:
        return {"ctrl": self.ctrl, "force": self.force}


@dataclass(frozen=True, slots=True)
class SensorRecordingState:
    joint_id: str
    time: float
    sequence: int
    qpos: float
    qvel: float

    def to_dict(self) -> dict[str, str | int | float]:
        return {
            "sensor_type": "joint_state",
            "joint_id": self.joint_id,
            "time": self.time,
            "sequence": self.sequence,
            "qpos": self.qpos,
            "qvel": self.qvel,
        }


@dataclass(frozen=True, slots=True)
class ImuRecordingState:
    link_id: str
    time: float
    sequence: int
    orientation: tuple[float, float, float, float]
    angular_velocity: tuple[float, float, float]
    linear_acceleration: tuple[float, float, float]

    def to_dict(self) -> dict[str, str | int | float | list[float]]:
        return {
            "sensor_type": "imu",
            "link_id": self.link_id,
            "time": self.time,
            "sequence": self.sequence,
            "orientation": list(self.orientation),
            "angular_velocity": list(self.angular_velocity),
            "linear_acceleration": list(self.linear_acceleration),
        }


RecordingSensorType = Literal["joint_state", "imu"]
TypedSensorRecordingState = SensorRecordingState | ImuRecordingState


def _sensor_state_from_dict(data: dict[str, Any]) -> TypedSensorRecordingState:
    sensor_type = str(data.get("sensor_type", "joint_state"))
    if sensor_type == "imu":
        return ImuRecordingState(
            link_id=str(data["link_id"]),
            time=float(data["time"]),
            sequence=int(data["sequence"]),
            orientation=tuple(float(value) for value in data["orientation"]),  # type: ignore[arg-type]
            angular_velocity=tuple(  # type: ignore[arg-type]
                float(value) for value in data["angular_velocity"]
            ),
            linear_acceleration=tuple(  # type: ignore[arg-type]
                float(value) for value in data["linear_acceleration"]
            ),
        )
    if sensor_type != "joint_state":
        raise ValueError(f"Unsupported recording sensor type: {sensor_type}")
    return SensorRecordingState(
        joint_id=str(data["joint_id"]),
        time=float(data["time"]),
        sequence=int(data["sequence"]),
        qpos=float(data["qpos"]),
        qvel=float(data["qvel"]),
    )


@dataclass(frozen=True, slots=True)
class JointStateSample:
    time: float
    joints: dict[str, JointRecordingState]
    actuators: dict[str, ActuatorRecordingState]
    sensors: dict[str, TypedSensorRecordingState] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "time": self.time,
            "joints": {key: value.to_dict() for key, value in self.joints.items()},
            "actuators": {
                key: value.to_dict() for key, value in self.actuators.items()
            },
            "sensors": {key: value.to_dict() for key, value in self.sensors.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JointStateSample:
        return cls(
            time=float(data["time"]),
            joints={
                str(key): JointRecordingState(
                    qpos=float(value["qpos"]),
                    qvel=float(value["qvel"]),
                )
                for key, value in data.get("joints", {}).items()
            },
            actuators={
                str(key): ActuatorRecordingState(
                    ctrl=float(value["ctrl"]),
                    force=float(value["force"]),
                )
                for key, value in data.get("actuators", {}).items()
            },
            sensors={
                str(key): _sensor_state_from_dict(value)
                for key, value in data.get("sensors", {}).items()
            },
        )


@dataclass(slots=True)
class JointStateRecording:
    name: str
    manifest: RecordingManifest
    joint_ids: list[str]
    actuator_ids: list[str]
    sensor_ids: list[str] = field(default_factory=list)
    sensor_types: dict[str, RecordingSensorType] = field(default_factory=dict)
    samples: list[JointStateSample] = field(default_factory=list)
    limit_reached: bool = False
    version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "manifest": self.manifest.to_dict(),
            "joint_ids": list(self.joint_ids),
            "actuator_ids": list(self.actuator_ids),
            "sensor_ids": list(self.sensor_ids),
            "sensor_types": dict(self.sensor_types),
            "limit_reached": self.limit_reached,
            "samples": [sample.to_dict() for sample in self.samples],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JointStateRecording:
        sensor_ids = [str(value) for value in data.get("sensor_ids", [])]
        sensor_types = {
            str(key): value for key, value in data.get("sensor_types", {}).items()
        }
        for sensor_id in sensor_ids:
            if sensor_id in sensor_types:
                continue
            sensor_types[sensor_id] = next(
                (
                    str(sample["sensors"][sensor_id].get("sensor_type", "joint_state"))
                    for sample in data.get("samples", [])
                    if sensor_id in sample.get("sensors", {})
                ),
                "joint_state",
            )
        return cls(
            version=str(data.get("version", "1.0")),
            name=str(data["name"]),
            manifest=RecordingManifest.from_dict(data["manifest"]),
            joint_ids=[str(value) for value in data.get("joint_ids", [])],
            actuator_ids=[str(value) for value in data.get("actuator_ids", [])],
            sensor_ids=sensor_ids,
            sensor_types=sensor_types,  # type: ignore[arg-type]
            limit_reached=bool(data.get("limit_reached", False)),
            samples=[JointStateSample.from_dict(item) for item in data.get("samples", [])],
        )

    def to_csv(self) -> str:
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\n")
        header = ["time"]
        for joint_id in self.joint_ids:
            header.extend([f"joint.{joint_id}.qpos", f"joint.{joint_id}.qvel"])
        for actuator_id in self.actuator_ids:
            header.extend(
                [f"actuator.{actuator_id}.ctrl", f"actuator.{actuator_id}.force"]
            )
        for sensor_id in self.sensor_ids:
            if self.sensor_types.get(sensor_id, "joint_state") == "imu":
                header.extend(_imu_csv_columns(sensor_id))
            else:
                header.extend(_joint_sensor_csv_columns(sensor_id))
        writer.writerow(header)
        for sample in self.samples:
            row: list[str | int | float] = [sample.time]
            for joint_id in self.joint_ids:
                joint_state = sample.joints[joint_id]
                row.extend([joint_state.qpos, joint_state.qvel])
            for actuator_id in self.actuator_ids:
                actuator_state = sample.actuators[actuator_id]
                row.extend([actuator_state.ctrl, actuator_state.force])
            for sensor_id in self.sensor_ids:
                sensor_state = sample.sensors.get(sensor_id)
                sensor_type = self.sensor_types.get(sensor_id, "joint_state")
                if sensor_state is None:
                    column_count = 13 if sensor_type == "imu" else 5
                    row.extend([""] * column_count)
                    continue
                if sensor_type == "imu" and isinstance(sensor_state, ImuRecordingState):
                    row.extend(
                        [
                            sensor_state.link_id,
                            sensor_state.time,
                            sensor_state.sequence,
                            *sensor_state.orientation,
                            *sensor_state.angular_velocity,
                            *sensor_state.linear_acceleration,
                        ]
                    )
                elif sensor_type == "joint_state" and isinstance(
                    sensor_state, SensorRecordingState
                ):
                    row.extend(
                        [
                            sensor_state.joint_id,
                            sensor_state.time,
                            sensor_state.sequence,
                            sensor_state.qpos,
                            sensor_state.qvel,
                        ]
                    )
                else:
                    raise ValueError(f"Recording sensor type mismatch: {sensor_id}")
            writer.writerow(row)
        return output.getvalue()


def _joint_sensor_csv_columns(sensor_id: str) -> list[str]:
    return [
        f"sensor.{sensor_id}.joint_id",
        f"sensor.{sensor_id}.time",
        f"sensor.{sensor_id}.sequence",
        f"sensor.{sensor_id}.qpos",
        f"sensor.{sensor_id}.qvel",
    ]


def _imu_csv_columns(sensor_id: str) -> list[str]:
    prefix = f"sensor.{sensor_id}"
    return [
        f"{prefix}.link_id",
        f"{prefix}.time",
        f"{prefix}.sequence",
        f"{prefix}.orientation.x",
        f"{prefix}.orientation.y",
        f"{prefix}.orientation.z",
        f"{prefix}.orientation.w",
        f"{prefix}.angular_velocity.x",
        f"{prefix}.angular_velocity.y",
        f"{prefix}.angular_velocity.z",
        f"{prefix}.linear_acceleration.x",
        f"{prefix}.linear_acceleration.y",
        f"{prefix}.linear_acceleration.z",
    ]
