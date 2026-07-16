from __future__ import annotations

import math

from simlab.models.trajectory import JointTrajectory


class TrajectoryValidationError(ValueError):
    """Raised when a joint trajectory violates playback invariants."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = issues
        super().__init__("; ".join(issues))


def validate_joint_trajectory(
    trajectory: JointTrajectory,
    *,
    allowed_joint_ids: set[str] | None = None,
) -> None:
    issues: list[str] = []
    if trajectory.version != "1.0":
        issues.append("Trajectory version must be '1.0'")
    if not trajectory.name.strip():
        issues.append("Trajectory name cannot be empty")
    if len(trajectory.keyframes) < 2:
        issues.append("Trajectory must contain at least two keyframes")
    if issues:
        raise TrajectoryValidationError(issues)

    expected_joint_ids = set(trajectory.keyframes[0].targets)
    if not expected_joint_ids:
        issues.append("Trajectory keyframes must contain at least one joint target")
    previous_time: float | None = None
    for index, keyframe in enumerate(trajectory.keyframes):
        if not math.isfinite(keyframe.time) or keyframe.time < 0:
            issues.append(f"Keyframe {index} time must be finite and >= 0")
        if index == 0 and keyframe.time != 0:
            issues.append("The first trajectory keyframe must start at time 0")
        if previous_time is not None and keyframe.time <= previous_time:
            issues.append(f"Keyframe {index} time must be strictly increasing")
        previous_time = keyframe.time
        if set(keyframe.targets) != expected_joint_ids:
            issues.append(f"Keyframe {index} must target the same joint IDs as keyframe 0")
        for joint_id, target in keyframe.targets.items():
            if not joint_id:
                issues.append(f"Keyframe {index} contains an empty joint ID")
            if not math.isfinite(target):
                issues.append(
                    f"Keyframe {index} target for {joint_id or '<empty>'} must be finite"
                )
    if allowed_joint_ids is not None:
        unknown = sorted(expected_joint_ids - allowed_joint_ids)
        if unknown:
            issues.append(f"Trajectory targets unknown position joint(s): {', '.join(unknown)}")
    if issues:
        raise TrajectoryValidationError(issues)
