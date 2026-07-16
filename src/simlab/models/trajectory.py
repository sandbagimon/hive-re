from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class JointTrajectoryKeyframe:
    time: float
    targets: dict[str, float]

    def __post_init__(self) -> None:
        self.time = float(self.time)
        self.targets = {str(key): float(value) for key, value in self.targets.items()}

    def to_dict(self) -> dict[str, Any]:
        return {"time": self.time, "targets": dict(self.targets)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JointTrajectoryKeyframe:
        targets = data.get("targets")
        if not isinstance(targets, dict):
            raise ValueError("Trajectory keyframe targets must be an object")
        return cls(time=float(data["time"]), targets=targets)


@dataclass(slots=True)
class JointTrajectory:
    name: str
    keyframes: list[JointTrajectoryKeyframe] = field(default_factory=list)
    loop: bool = False
    version: str = "1.0"

    @property
    def duration(self) -> float:
        return self.keyframes[-1].time if self.keyframes else 0.0

    @property
    def joint_ids(self) -> set[str]:
        return set(self.keyframes[0].targets) if self.keyframes else set()

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "name": self.name,
            "loop": self.loop,
            "keyframes": [keyframe.to_dict() for keyframe in self.keyframes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JointTrajectory:
        keyframes = data.get("keyframes")
        if not isinstance(keyframes, list):
            raise ValueError("Trajectory keyframes must be an array")
        return cls(
            version=str(data.get("version", "1.0")),
            name=str(data.get("name", "Joint Trajectory")),
            loop=bool(data.get("loop", False)),
            keyframes=[JointTrajectoryKeyframe.from_dict(item) for item in keyframes],
        )
