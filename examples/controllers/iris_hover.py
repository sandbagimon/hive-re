from __future__ import annotations

import math

from beefoundrysim.services.controller_runtime import (
    ControllerAction,
    ControllerObservation,
)

IRIS_ROTOR_ACTUATORS = (
    "actuator_iris_rotor_0",
    "actuator_iris_rotor_1",
    "actuator_iris_rotor_2",
    "actuator_iris_rotor_3",
)
IRIS_BODY_LINK = "link_c46480014a33"

# Static trim for the bundled 1.52 kg Iris profile. The rotor mounts and the
# assembled center of mass are slightly asymmetric, so equal speeds create a
# persistent roll/pitch moment even when their total thrust equals gravity.
IRIS_HOVER_TRIM = (
    641.132187,
    679.039297,
    646.466695,
    673.962654,
)


class IrisHoverController:
    """Smooth takeoff followed by altitude hold for the bundled Iris asset."""

    name = "Iris Takeoff and Hover"

    def __init__(
        self,
        *,
        takeoff_height: float = 1.0,
        spool_duration: float = 0.5,
        takeoff_duration: float = 2.0,
        altitude_kp: float = 8.0,
        vertical_velocity_kd: float = 5.0,
    ) -> None:
        values = (
            takeoff_height,
            spool_duration,
            takeoff_duration,
            altitude_kp,
            vertical_velocity_kd,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in values):
            raise ValueError("Iris takeoff parameters must be finite and greater than zero")
        self.takeoff_height = takeoff_height
        self.spool_duration = spool_duration
        self.takeoff_duration = takeoff_duration
        self.altitude_kp = altitude_kp
        self.vertical_velocity_kd = vertical_velocity_kd
        self._start_time = 0.0
        self._start_height = 0.0

    def reset(self, observation: ControllerObservation) -> None:
        missing = sorted(set(IRIS_ROTOR_ACTUATORS) - set(observation.actuators))
        if missing:
            raise ValueError(
                "Iris rotor actuators were not found; load the Pegasus Iris asset first: "
                + ", ".join(missing)
            )
        body = observation.bodies.get(IRIS_BODY_LINK)
        if body is None:
            raise ValueError("Iris body observation was not found")
        self._start_time = observation.time
        self._start_height = body.position[2]

    def step(self, observation: ControllerObservation) -> ControllerAction:
        body = observation.bodies[IRIS_BODY_LINK]
        elapsed = max(0.0, observation.time - self._start_time - self.spool_duration)
        progress = min(elapsed / self.takeoff_duration, 1.0)
        smooth_progress = progress * progress * (3.0 - 2.0 * progress)
        progress_rate = (
            6.0 * progress * (1.0 - progress) / self.takeoff_duration if progress < 1.0 else 0.0
        )
        target_height = self._start_height + self.takeoff_height * smooth_progress
        target_velocity = self.takeoff_height * progress_rate
        vertical_acceleration = self.altitude_kp * (
            target_height - body.position[2]
        ) + self.vertical_velocity_kd * (target_velocity - body.linear_velocity[2])
        thrust_scale = max(0.5, min(1.5, (9.81 + vertical_acceleration) / 9.81))
        angular_velocities = tuple(
            angular_velocity * math.sqrt(thrust_scale) for angular_velocity in IRIS_HOVER_TRIM
        )
        return ControllerAction(
            actuator_controls={
                actuator_id: angular_velocity
                for actuator_id, angular_velocity in zip(
                    IRIS_ROTOR_ACTUATORS,
                    angular_velocities,
                    strict=True,
                )
            }
        )


def create_controller() -> IrisHoverController:
    return IrisHoverController()
