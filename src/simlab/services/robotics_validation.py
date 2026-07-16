from __future__ import annotations

import json
import math
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from jsonschema import Draft202012Validator

from simlab.models.robotics import Articulation, RoboticsModel


class _Identified(Protocol):
    id: str


@dataclass(frozen=True, slots=True)
class RoboticsValidationIssue:
    code: str
    path: str
    message: str


class RoboticsValidationError(ValueError):
    """Raised when a robotics model violates structural or semantic constraints."""

    def __init__(self, issues: list[RoboticsValidationIssue]) -> None:
        self.issues = issues
        summary = "; ".join(f"{issue.path}: {issue.message}" for issue in issues)
        super().__init__(summary)


def _schema_path() -> Path:
    source_path = (
        Path(__file__).resolve().parents[3]
        / "shared"
        / "schemas"
        / "robotics.schema.json"
    )
    installed_path = Path(sys.prefix) / "share" / "simlab" / "schemas" / "robotics.schema.json"
    for candidate in (source_path, installed_path):
        if candidate.is_file():
            return candidate
    msg = "Unable to locate shared/schemas/robotics.schema.json"
    raise RuntimeError(msg)


def _json_path(parts: Any) -> str:
    path = "$"
    for part in parts:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path


def _schema_issues(data: dict[str, Any]) -> list[RoboticsValidationIssue]:
    schema = json.loads(_schema_path().read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    return [
        RoboticsValidationIssue(
            code=f"schema.{error.validator}",
            path=_json_path(error.absolute_path),
            message=error.message,
        )
        for error in sorted(validator.iter_errors(data), key=lambda item: list(item.absolute_path))
    ]


def _add_duplicate_issue(
    issues: list[RoboticsValidationIssue],
    seen: set[str],
    identifier: str,
    path: str,
) -> None:
    if identifier in seen:
        issues.append(
            RoboticsValidationIssue("duplicate_id", path, f"Duplicate id: {identifier}")
        )
    seen.add(identifier)


def _validate_link_tree(
    articulation: Articulation,
    articulation_path: str,
    issues: list[RoboticsValidationIssue],
) -> None:
    link_ids = {link.id for link in articulation.links}
    root = next((link for link in articulation.links if link.id == articulation.root_link_id), None)
    if root is None:
        issues.append(
            RoboticsValidationIssue(
                "missing_root_link",
                f"{articulation_path}.root_link_id",
                f"Unknown root link: {articulation.root_link_id}",
            )
        )
    elif root.parent_link_id is not None:
        issues.append(
            RoboticsValidationIssue(
                "root_has_parent",
                f"{articulation_path}.links[{articulation.links.index(root)}].parent_link_id",
                "The root link cannot have a parent",
            )
        )

    parents = {link.id: link.parent_link_id for link in articulation.links}
    for index, link in enumerate(articulation.links):
        if link.parent_link_id is not None and link.parent_link_id not in link_ids:
            issues.append(
                RoboticsValidationIssue(
                    "dangling_parent_link",
                    f"{articulation_path}.links[{index}].parent_link_id",
                    f"Unknown parent link: {link.parent_link_id}",
                )
            )
        visited: set[str] = set()
        current: str | None = link.id
        while current is not None and current in parents:
            if current in visited:
                issues.append(
                    RoboticsValidationIssue(
                        "link_cycle",
                        f"{articulation_path}.links[{index}].parent_link_id",
                        f"Link hierarchy contains a cycle at {current}",
                    )
                )
                break
            visited.add(current)
            current = parents[current]


def _validate_articulation(
    articulation: Articulation,
    index: int,
) -> list[RoboticsValidationIssue]:
    path = f"$.articulations[{index}]"
    issues: list[RoboticsValidationIssue] = []
    seen_ids: set[str] = set()
    _add_duplicate_issue(issues, seen_ids, articulation.id, f"{path}.id")

    def register_ids(collection_name: str, values: Iterable[_Identified]) -> None:
        for item_index, item in enumerate(values):
            _add_duplicate_issue(
                issues,
                seen_ids,
                item.id,
                f"{path}.{collection_name}[{item_index}].id",
            )

    register_ids("links", articulation.links)
    register_ids("joints", articulation.joints)
    register_ids("actuators", articulation.actuators)
    register_ids("sensors", articulation.sensors)
    for link_index, link in enumerate(articulation.links):
        register_ids(f"links[{link_index}].visual_geometries", link.visual_geometries)
        register_ids(f"links[{link_index}].colliders", link.colliders)

    _validate_link_tree(articulation, path, issues)
    link_ids = {link.id for link in articulation.links}
    joint_ids = {joint.id for joint in articulation.joints}
    link_parents = {link.id: link.parent_link_id for link in articulation.links}

    for joint_index, joint in enumerate(articulation.joints):
        joint_path = f"{path}.joints[{joint_index}]"
        if joint.parent_link_id not in link_ids:
            issues.append(
                RoboticsValidationIssue(
                    "dangling_joint_parent",
                    f"{joint_path}.parent_link_id",
                    f"Unknown parent link: {joint.parent_link_id}",
                )
            )
        if joint.child_link_id not in link_ids:
            issues.append(
                RoboticsValidationIssue(
                    "dangling_joint_child",
                    f"{joint_path}.child_link_id",
                    f"Unknown child link: {joint.child_link_id}",
                )
            )
        elif link_parents[joint.child_link_id] != joint.parent_link_id:
            issues.append(
                RoboticsValidationIssue(
                    "joint_hierarchy_mismatch",
                    f"{joint_path}.child_link_id",
                    "Joint parent/child does not match the link hierarchy",
                )
            )
        if joint.parent_link_id == joint.child_link_id:
            issues.append(
                RoboticsValidationIssue(
                    "self_joint",
                    f"{joint_path}.child_link_id",
                    "A joint cannot join a link to itself",
                )
            )
        if joint.type != "fixed" and math.isclose(
            math.sqrt(sum(component * component for component in joint.axis)), 0.0, abs_tol=1e-9
        ):
            issues.append(
                RoboticsValidationIssue(
                    "invalid_joint_axis",
                    f"{joint_path}.axis",
                    "A movable joint axis must be non-zero",
                )
            )
        limits = joint.limits
        if limits is not None:
            if (limits.lower is None) != (limits.upper is None):
                issues.append(
                    RoboticsValidationIssue(
                        "incomplete_joint_range",
                        f"{joint_path}.limits",
                        "Joint lower and upper limits must be set together",
                    )
                )
            elif limits.lower is not None and limits.upper is not None:
                if limits.lower > limits.upper:
                    issues.append(
                        RoboticsValidationIssue(
                            "invalid_joint_range",
                            f"{joint_path}.limits",
                            "Joint lower limit must not exceed upper limit",
                        )
                    )
                elif not limits.lower <= joint.initial_position <= limits.upper:
                    issues.append(
                        RoboticsValidationIssue(
                            "initial_position_out_of_range",
                            f"{joint_path}.initial_position",
                            "Initial position is outside the joint limits",
                        )
                    )

    for actuator_index, actuator in enumerate(articulation.actuators):
        actuator_path = f"{path}.actuators[{actuator_index}]"
        if actuator.joint_id not in joint_ids:
            issues.append(
                RoboticsValidationIssue(
                    "dangling_actuator_joint",
                    f"{actuator_path}.joint_id",
                    f"Unknown joint: {actuator.joint_id}",
                )
            )
        if actuator.control_range[0] > actuator.control_range[1]:
            issues.append(
                RoboticsValidationIssue(
                    "invalid_control_range",
                    f"{actuator_path}.control_range",
                    "Actuator control range minimum must not exceed maximum",
                )
            )

    for sensor_index, sensor in enumerate(articulation.sensors):
        sensor_path = f"{path}.sensors[{sensor_index}]"
        if sensor.sensor_type in {"joint_state", "joint_position", "joint_velocity"}:
            if sensor.joint_id is None:
                issues.append(
                    RoboticsValidationIssue(
                        "missing_sensor_joint",
                        f"{sensor_path}.joint_id",
                        f"{sensor.sensor_type} sensor requires a joint",
                    )
                )
        if sensor.sensor_type == "imu":
            if sensor.link_id is None:
                issues.append(
                    RoboticsValidationIssue(
                        "missing_sensor_link",
                        f"{sensor_path}.link_id",
                        "imu sensor requires a link",
                    )
                )
            if sensor.local_transform is None:
                issues.append(
                    RoboticsValidationIssue(
                        "missing_sensor_transform",
                        f"{sensor_path}.local_transform",
                        "imu sensor requires a local transform",
                    )
                )
            elif not math.isclose(
                math.sqrt(
                    sum(value * value for value in sensor.local_transform.quaternion)
                ),
                1.0,
                rel_tol=0.0,
                abs_tol=1e-6,
            ):
                issues.append(
                    RoboticsValidationIssue(
                        "invalid_sensor_quaternion",
                        f"{sensor_path}.local_transform.quaternion",
                        "imu sensor local quaternion must be normalized",
                    )
                )
        if sensor.link_id is not None and sensor.link_id not in link_ids:
            issues.append(
                RoboticsValidationIssue(
                    "dangling_sensor_link",
                    f"{sensor_path}.link_id",
                    f"Unknown link: {sensor.link_id}",
                )
            )
        if sensor.joint_id is not None and sensor.joint_id not in joint_ids:
            issues.append(
                RoboticsValidationIssue(
                    "dangling_sensor_joint",
                    f"{sensor_path}.joint_id",
                    f"Unknown joint: {sensor.joint_id}",
                )
            )
    return issues


def validate_robotics_model(value: RoboticsModel | dict[str, Any]) -> None:
    """Validate the shared schema and cross-reference invariants."""
    data = value.to_dict() if isinstance(value, RoboticsModel) else value
    issues = _schema_issues(data)
    if issues:
        raise RoboticsValidationError(issues)

    model = (
        value
        if isinstance(value, RoboticsModel)
        else RoboticsModel.from_dict(data, validate=False)
    )
    seen_articulation_ids: set[str] = set()
    for index, articulation in enumerate(model.articulations):
        if articulation.id in seen_articulation_ids:
            issues.append(
                RoboticsValidationIssue(
                    "duplicate_articulation_id",
                    f"$.articulations[{index}].id",
                    f"Duplicate articulation id: {articulation.id}",
                )
            )
        seen_articulation_ids.add(articulation.id)
        issues.extend(_validate_articulation(articulation, index))
    if issues:
        raise RoboticsValidationError(issues)
