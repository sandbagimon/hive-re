from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from simlab.models.robotics import RoboticsModel, Sensor
from simlab.services.contact_sensors import (
    MAX_CONTACT_POINTS,
    ContactMeasurement,
    Vector3,
)
from simlab.services.mjcf_exporter import mujoco_name


@dataclass(frozen=True, slots=True)
class _ContactScope:
    sensor: Sensor
    geom_ids: frozenset[int]


@dataclass(frozen=True, slots=True)
class _ScopedContact:
    normal_force: float
    tangent_force: Vector3
    point: Vector3
    normal: Vector3


class MujocoContactAggregator:
    """Aggregate MuJoCo contacts into bounded world-frame sensor measurements."""

    def __init__(
        self,
        mujoco: Any,
        model: Any,
        data: Any,
        robotics: RoboticsModel | None,
        timestep: float,
    ) -> None:
        self._mujoco = mujoco
        self.model = model
        self.data = data
        self.timestep = float(timestep)
        self._scopes = self._map_scopes(robotics)

    @property
    def sensor_ids(self) -> tuple[str, ...]:
        return tuple(scope.sensor.id for scope in self._scopes)

    def measurements(self) -> dict[str, ContactMeasurement]:
        return {
            scope.sensor.id: self._measurement(scope)
            for scope in self._scopes
        }

    def _map_scopes(self, robotics: RoboticsModel | None) -> tuple[_ContactScope, ...]:
        if robotics is None:
            return ()
        result: list[_ContactScope] = []
        for articulation in robotics.articulations:
            links = {link.id: link for link in articulation.links}
            colliders = {
                collider.id: collider
                for link in articulation.links
                for collider in link.colliders
            }
            for sensor in articulation.sensors:
                if sensor.sensor_type != "contact":
                    continue
                collider_ids = (
                    [sensor.collider_id]
                    if sensor.collider_id is not None
                    else [
                        collider.id
                        for collider in links[sensor.link_id].colliders
                    ]
                    if sensor.link_id in links
                    else []
                )
                geom_ids: set[int] = set()
                for collider_id in collider_ids:
                    if collider_id is None or collider_id not in colliders:
                        raise ValueError(
                            f"Contact sensor {sensor.id} references unknown collider: "
                            f"{collider_id}"
                        )
                    geom_id = self._mujoco.mj_name2id(
                        self.model,
                        self._mujoco.mjtObj.mjOBJ_GEOM,
                        mujoco_name(collider_id),
                    )
                    if geom_id < 0:
                        raise ValueError(
                            f"MuJoCo contact geom is missing for collider: {collider_id}"
                        )
                    geom_ids.add(int(geom_id))
                if not geom_ids:
                    raise ValueError(f"Contact sensor scope has no colliders: {sensor.id}")
                result.append(_ContactScope(sensor, frozenset(geom_ids)))
        return tuple(result)

    def _measurement(self, scope: _ContactScope) -> ContactMeasurement:
        contacts: list[_ScopedContact] = []
        for contact_index in range(int(self.data.ncon)):
            contact = self.data.contact[contact_index]
            geom1_scoped = int(contact.geom1) in scope.geom_ids
            geom2_scoped = int(contact.geom2) in scope.geom_ids
            if geom1_scoped == geom2_scoped:
                continue
            force = np.zeros(6, dtype=np.float64)
            self._mujoco.mj_contactForce(
                self.model,
                self.data,
                contact_index,
                force,
            )
            frame = np.asarray(contact.frame, dtype=np.float64).reshape(3, 3)
            tangent_on_geom2 = force[1] * frame[1] + force[2] * frame[2]
            tangent = -tangent_on_geom2 if geom1_scoped else tangent_on_geom2
            normal = frame[0] if geom1_scoped else -frame[0]
            contacts.append(
                _ScopedContact(
                    normal_force=max(0.0, float(force[0])),
                    tangent_force=tuple(float(value) for value in tangent),  # type: ignore[arg-type]
                    point=tuple(float(value) for value in contact.pos),  # type: ignore[arg-type]
                    normal=tuple(float(value) for value in normal),  # type: ignore[arg-type]
                )
            )
        contacts.sort(key=lambda item: item.normal_force, reverse=True)
        retained = contacts[:MAX_CONTACT_POINTS]
        tangent_force = tuple(
            sum(contact.tangent_force[axis] for contact in contacts) for axis in range(3)
        )
        normal_force = sum(contact.normal_force for contact in contacts)
        return ContactMeasurement(
            contact_count=len(contacts),
            normal_force=normal_force,
            tangent_force=tangent_force,  # type: ignore[arg-type]
            normal_impulse=normal_force * self.timestep,
            points=tuple(contact.point for contact in retained),
            normals=tuple(contact.normal for contact in retained),
        )
