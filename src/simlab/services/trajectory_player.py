from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from simlab.models.trajectory import JointTrajectory
from simlab.services.trajectory_validation import validate_joint_trajectory

TrajectoryPlaybackStatus = Literal["stopped", "playing", "paused", "completed"]


@dataclass(frozen=True, slots=True)
class TrajectoryPlaybackState:
    status: TrajectoryPlaybackStatus
    time: float
    duration: float
    name: str | None

    def to_dict(self) -> dict[str, float | str | None]:
        return {
            "status": self.status,
            "time": self.time,
            "duration": self.duration,
            "name": self.name,
        }


class JointTrajectoryPlayer:
    """Deterministic linear interpolation over stable joint target IDs."""

    def __init__(self) -> None:
        self.trajectory: JointTrajectory | None = None
        self.status: TrajectoryPlaybackStatus = "stopped"
        self._position = 0.0
        self._started_at = 0.0

    def load(
        self,
        trajectory: JointTrajectory,
        *,
        allowed_joint_ids: set[str] | None = None,
    ) -> TrajectoryPlaybackState:
        validate_joint_trajectory(
            trajectory,
            allowed_joint_ids=allowed_joint_ids,
        )
        self.trajectory = trajectory
        self.status = "stopped"
        self._position = 0.0
        self._started_at = 0.0
        return self.state()

    def play(self, simulation_time: float) -> TrajectoryPlaybackState:
        self._require_trajectory()
        if self.status == "completed":
            self._position = 0.0
        self._started_at = simulation_time - self._position
        self.status = "playing"
        return self.state(simulation_time)

    def pause(self, simulation_time: float) -> TrajectoryPlaybackState:
        self._require_trajectory()
        if self.status == "playing":
            self._position = self._playback_position(simulation_time)
            self.status = "paused"
        return self.state()

    def stop(self) -> TrajectoryPlaybackState:
        self._require_trajectory()
        self.status = "stopped"
        self._position = 0.0
        self._started_at = 0.0
        return self.state()

    def sample(self, simulation_time: float) -> dict[str, float] | None:
        trajectory = self.trajectory
        if trajectory is None:
            return None
        position = self._playback_position(simulation_time)
        self._position = position
        return self._sample_at(position)

    def state(self, simulation_time: float | None = None) -> TrajectoryPlaybackState:
        trajectory = self.trajectory
        if trajectory is None:
            return TrajectoryPlaybackState("stopped", 0.0, 0.0, None)
        position = self._position
        if simulation_time is not None and self.status == "playing":
            position = self._playback_position(simulation_time)
        return TrajectoryPlaybackState(
            status=self.status,
            time=position,
            duration=trajectory.duration,
            name=trajectory.name,
        )

    def _playback_position(self, simulation_time: float) -> float:
        trajectory = self._require_trajectory()
        if self.status != "playing":
            return self._position
        elapsed = max(0.0, simulation_time - self._started_at)
        if trajectory.loop:
            return elapsed % trajectory.duration
        if elapsed >= trajectory.duration:
            self.status = "completed"
            return trajectory.duration
        return elapsed

    def _sample_at(self, time_value: float) -> dict[str, float]:
        trajectory = self._require_trajectory()
        if time_value <= 0:
            return dict(trajectory.keyframes[0].targets)
        if time_value >= trajectory.duration:
            return dict(trajectory.keyframes[-1].targets)
        for left, right in zip(
            trajectory.keyframes,
            trajectory.keyframes[1:],
            strict=True,
        ):
            if time_value > right.time:
                continue
            ratio = (time_value - left.time) / (right.time - left.time)
            return {
                joint_id: left.targets[joint_id]
                + (right.targets[joint_id] - left.targets[joint_id]) * ratio
                for joint_id in left.targets
            }
        return dict(trajectory.keyframes[-1].targets)

    def _require_trajectory(self) -> JointTrajectory:
        if self.trajectory is None:
            raise RuntimeError("No joint trajectory is loaded")
        return self.trajectory
