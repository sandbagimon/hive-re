from __future__ import annotations

import math

from beefoundrysim.services.controller_runtime import ControllerAction, ControllerObservation

IRIS_BODY_LINK = "link_c46480014a33"
PAYLOAD_BODY = "actor_003"
ATTACHMENT_ID = "attachment_iris_payload_hook"
IRIS_ROTOR_ACTUATORS = tuple(f"actuator_iris_rotor_{index}" for index in range(4))

PICKUP = (0.0, 0.0)
DROPOFF = (4.0, 3.0)
HOME = (-2.0, 0.0)
CRUISE_HEIGHT = 1.5
HOOK_HEIGHT = 0.39
AIRFRAME_MASS = 1.52
PAYLOAD_MASS = 0.35
THRUST_COEFFICIENT = 8.54858e-6
MAX_ROTOR_SPEED = 1100.0

# Maps [total thrust, roll torque, pitch torque, yaw torque] to four rotor thrusts.
# It is the inverse of the Iris rotor-arm/yaw geometry declared in assets/metadata.json.
MIXER_INVERSE = (
    (0.23543522, -1.17605586, -1.90281642, -2.21932953),
    (0.26456478, 1.17605586, 1.90281642, -2.05496047),
    (0.23943767, 1.17509143, -1.90376242, 2.20941092),
    (0.26056233, -1.17509143, 1.90376242, 2.06487908),
)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _length(values: tuple[float, ...]) -> float:
    return math.sqrt(sum(value * value for value in values))


def _euler_from_wxyz(
    quaternion: tuple[float, float, float, float],
) -> tuple[float, float, float]:
    w, x, y, z = quaternion
    roll = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
    pitch_sine = _clamp(2.0 * (w * y - z * x), -1.0, 1.0)
    pitch = math.asin(pitch_sine)
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    return roll, pitch, yaw


def _wrap_angle(value: float) -> float:
    return (value + math.pi) % (2.0 * math.pi) - math.pi


class IrisPayloadDeliveryController:
    """Smooth A-to-B pickup mission with a contact-gated compliant payload hook.

    The mission identifiers default to the single-drone delivery demo, but every
    stable Scene ID and mission point can be overridden so one controller can
    drive a cloned vehicle (multi-drone scenes rename links, actuators,
    attachments, and sensors per airframe).
    """

    name = "Iris Physical Payload Delivery"

    def __init__(
        self,
        *,
        body_link_id: str = IRIS_BODY_LINK,
        payload_body_id: str = PAYLOAD_BODY,
        attachment_id: str = ATTACHMENT_ID,
        rotor_actuators: tuple[str, ...] = IRIS_ROTOR_ACTUATORS,
        pickup: tuple[float, float] = PICKUP,
        dropoff: tuple[float, float] = DROPOFF,
        home: tuple[float, float] = HOME,
        cruise_height: float = CRUISE_HEIGHT,
        hook_height: float = HOOK_HEIGHT,
        dropoff_hook_height: float | None = None,
        payload_mass: float = PAYLOAD_MASS,
    ) -> None:
        self.body_link_id = body_link_id
        self.payload_body_id = payload_body_id
        self.attachment_id = attachment_id
        self.rotor_actuators = tuple(rotor_actuators)
        self.pickup = pickup
        self.dropoff = dropoff
        self.home = home
        self.cruise_height = cruise_height
        self.hook_height = hook_height
        # Pickup and dropoff pads may sit on different terrain heights; the
        # release descent defaults to the pickup hook height when unset.
        self.dropoff_hook_height = (
            hook_height if dropoff_hook_height is None else dropoff_hook_height
        )
        self.payload_mass = payload_mass
        self.phase = "spool"
        self.phase_started_at = 0.0
        self.segment_start = (0.0, 0.0, 0.0)
        self.segment_target = (0.0, 0.0, 0.0)
        self.segment_duration = 0.5
        self.hold_payload = False

    def reset(self, observation: ControllerObservation) -> None:
        missing = sorted(set(self.rotor_actuators) - set(observation.actuators))
        if missing:
            raise ValueError("Iris rotor actuators are missing: " + ", ".join(missing))
        if self.body_link_id not in observation.bodies:
            raise ValueError(f"Iris body observation is missing: {self.body_link_id}")
        if self.payload_body_id not in observation.bodies:
            raise ValueError(
                f"Payload body observation is missing: {self.payload_body_id}"
            )
        if self.attachment_id not in observation.attachments:
            raise ValueError(f"Payload attachment is missing: {self.attachment_id}")
        position = observation.bodies[self.body_link_id].position
        self.phase = "spool"
        self.phase_started_at = observation.time
        self.segment_start = position
        self.segment_target = position
        self.segment_duration = 0.5
        self.hold_payload = False

    def step(self, observation: ControllerObservation) -> ControllerAction:
        body = observation.bodies[self.body_link_id]
        attachment = observation.attachments[self.attachment_id]
        self._advance_mission(observation, attachment.active)
        target_position, target_velocity = self._trajectory_target(observation.time)
        controls = self._flight_controls(
            body.position,
            body.quaternion,
            body.linear_velocity,
            body.angular_velocity,
            target_position,
            target_velocity,
            carrying=attachment.active,
        )
        return ControllerAction(
            actuator_controls=dict(
                zip(self.rotor_actuators, controls, strict=True)
            ),
            attachment_commands={self.attachment_id: self.hold_payload},
        )

    def _advance_mission(
        self,
        observation: ControllerObservation,
        attached: bool,
    ) -> None:
        body = observation.bodies[self.body_link_id]
        elapsed = observation.time - self.phase_started_at
        position_error = _length(
            tuple(
                self.segment_target[index] - body.position[index]
                for index in range(3)
            )
        )
        speed = _length(body.linear_velocity)
        segment_reached = (
            elapsed >= self.segment_duration and position_error < 0.18 and speed < 0.3
        )

        if self.phase == "spool" and elapsed >= self.segment_duration:
            self._start_segment(
                "takeoff", (*self.home, self.cruise_height), 2.5, observation
            )
        elif self.phase == "takeoff" and segment_reached:
            self._start_segment(
                "to_pickup", (*self.pickup, self.cruise_height), 3.0, observation
            )
        elif self.phase == "to_pickup" and segment_reached:
            self._start_segment(
                "descend_pickup", (*self.pickup, self.hook_height), 3.0, observation
            )
            # Pre-arm the vacuum during final approach. The runtime still requires
            # sustained four-cup contact, low relative speed, and anchor proximity.
            self.hold_payload = True
        elif self.phase == "descend_pickup" and segment_reached:
            self._hold_phase("capture", observation)
        elif self.phase == "capture" and attached:
            self._start_segment(
                "lift_payload", (*self.pickup, self.cruise_height), 3.0, observation
            )
        elif self.phase == "lift_payload" and segment_reached:
            self._start_segment(
                "to_dropoff", (*self.dropoff, self.cruise_height), 5.0, observation
            )
        elif self.phase == "to_dropoff" and segment_reached:
            self._start_segment(
                "descend_dropoff",
                (*self.dropoff, self.dropoff_hook_height),
                3.0,
                observation,
            )
        elif self.phase == "descend_dropoff" and segment_reached:
            self._hold_phase("release", observation)
            self.hold_payload = False
        elif self.phase == "release" and not attached and elapsed >= 0.35:
            self._start_segment(
                "retreat", (*self.dropoff, self.cruise_height), 3.0, observation
            )
        elif self.phase == "retreat" and segment_reached:
            self._hold_phase("complete", observation)

    def _start_segment(
        self,
        phase: str,
        target: tuple[float, float, float],
        duration: float,
        observation: ControllerObservation,
    ) -> None:
        current_target, _ = self._trajectory_target(observation.time)
        self.phase = phase
        self.phase_started_at = observation.time
        self.segment_start = current_target
        self.segment_target = target
        self.segment_duration = duration

    def _hold_phase(self, phase: str, observation: ControllerObservation) -> None:
        target = self.segment_target
        self.phase = phase
        self.phase_started_at = observation.time
        self.segment_start = target
        self.segment_target = target
        self.segment_duration = 1.0

    def _trajectory_target(
        self, time: float
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        progress = _clamp(
            (time - self.phase_started_at) / self.segment_duration, 0.0, 1.0
        )
        blend = progress**3 * (10.0 - 15.0 * progress + 6.0 * progress**2)
        blend_rate = (
            30.0 * progress**2 * (1.0 - progress) ** 2 / self.segment_duration
            if progress < 1.0
            else 0.0
        )
        delta = tuple(
            self.segment_target[index] - self.segment_start[index]
            for index in range(3)
        )
        return (
            tuple(
                self.segment_start[index] + delta[index] * blend
                for index in range(3)
            ),
            tuple(delta[index] * blend_rate for index in range(3)),
        )  # type: ignore[return-value]

    @staticmethod
    def _flight_controls(
        position: tuple[float, float, float],
        quaternion: tuple[float, float, float, float],
        linear_velocity: tuple[float, float, float],
        angular_velocity: tuple[float, float, float],
        target_position: tuple[float, float, float],
        target_velocity: tuple[float, float, float],
        *,
        carrying: bool,
        payload_mass: float = PAYLOAD_MASS,
    ) -> tuple[float, float, float, float]:
        acceleration = [
            2.0 * (target_position[0] - position[0])
            + 2.8 * (target_velocity[0] - linear_velocity[0]),
            2.0 * (target_position[1] - position[1])
            + 2.8 * (target_velocity[1] - linear_velocity[1]),
            6.5 * (target_position[2] - position[2])
            + 4.5 * (target_velocity[2] - linear_velocity[2]),
        ]
        acceleration[0] = _clamp(acceleration[0], -3.0, 3.0)
        acceleration[1] = _clamp(acceleration[1], -3.0, 3.0)
        acceleration[2] = _clamp(acceleration[2], -5.0, 5.0)

        roll, pitch, yaw = _euler_from_wxyz(quaternion)
        desired_roll = _clamp(-acceleration[1] / 9.81, -0.32, 0.32)
        desired_pitch = _clamp(acceleration[0] / 9.81, -0.32, 0.32)
        desired_yaw = 0.0
        torque = (
            1.1 * _wrap_angle(desired_roll - roll) - 0.18 * angular_velocity[0],
            1.1 * _wrap_angle(desired_pitch - pitch) - 0.18 * angular_velocity[1],
            0.55 * _wrap_angle(desired_yaw - yaw) - 0.12 * angular_velocity[2],
        )
        mass = AIRFRAME_MASS + (payload_mass if carrying else 0.0)
        tilt_compensation = max(0.72, math.cos(roll) * math.cos(pitch))
        total_thrust = mass * (9.81 + acceleration[2]) / tilt_compensation
        wrench = (total_thrust, *torque)
        maximum_force = THRUST_COEFFICIENT * MAX_ROTOR_SPEED**2
        rotor_speeds = []
        for row in MIXER_INVERSE:
            force = sum(row[index] * wrench[index] for index in range(4))
            force = _clamp(force, 0.0, maximum_force)
            rotor_speeds.append(math.sqrt(force / THRUST_COEFFICIENT))
        return tuple(rotor_speeds)  # type: ignore[return-value]
