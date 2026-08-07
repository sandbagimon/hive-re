from __future__ import annotations

import heapq
import math

from examples.controllers.iris_payload_delivery import (
    ATTACHMENT_ID,
    CRUISE_HEIGHT,
    DROPOFF,
    HOOK_HEIGHT,
    IRIS_BODY_LINK,
    IRIS_ROTOR_ACTUATORS,
    PICKUP,
    IrisPayloadDeliveryController,
    _clamp,
    _euler_from_wxyz,
    _length,
    _wrap_angle,
)
from simlab.services.controller_runtime import (
    ControllerAction,
    ControllerObservation,
)

RAY_COUNT = 12
RAY_IDS = tuple(f"sensor_iris_range_{index:02d}" for index in range(RAY_COUNT))
RAY_ANGLES = tuple(2.0 * math.pi * index / RAY_COUNT for index in range(RAY_COUNT))

# Mission-map obstacles are rectangles (center_x, center_y, half_x, half_y).
# A* inflates them by the loaded vehicle/payload safety radius before planning.
MISSION_OBSTACLES = ((2.0, 1.5, 0.25, 0.8),)
MAP_BOUNDS = (-2.5, 5.0, -1.5, 4.0)
GRID_RESOLUTION = 0.2
LOADED_CLEARANCE = 0.68


def _point_blocked(
    point: tuple[float, float],
    obstacles: tuple[tuple[float, float, float, float], ...],
    clearance: float,
) -> bool:
    x, y = point
    return any(
        abs(x - center_x) <= half_x + clearance
        and abs(y - center_y) <= half_y + clearance
        for center_x, center_y, half_x, half_y in obstacles
    )


def _segment_clear(
    start: tuple[float, float],
    end: tuple[float, float],
    obstacles: tuple[tuple[float, float, float, float], ...],
    clearance: float,
) -> bool:
    distance = math.hypot(end[0] - start[0], end[1] - start[1])
    sample_count = max(1, math.ceil(distance / (GRID_RESOLUTION * 0.45)))
    return all(
        not _point_blocked(
            (
                start[0] + (end[0] - start[0]) * index / sample_count,
                start[1] + (end[1] - start[1]) * index / sample_count,
            ),
            obstacles,
            clearance,
        )
        for index in range(sample_count + 1)
    )


def plan_route(
    start: tuple[float, float],
    goal: tuple[float, float],
    *,
    obstacles: tuple[tuple[float, float, float, float], ...] = MISSION_OBSTACLES,
    clearance: float = LOADED_CLEARANCE,
) -> tuple[tuple[float, float], ...]:
    """Plan and line-of-sight simplify an eight-connected occupancy-grid route."""

    minimum_x, maximum_x, minimum_y, maximum_y = MAP_BOUNDS

    def cell(point: tuple[float, float]) -> tuple[int, int]:
        return (
            round((point[0] - minimum_x) / GRID_RESOLUTION),
            round((point[1] - minimum_y) / GRID_RESOLUTION),
        )

    def point(node: tuple[int, int]) -> tuple[float, float]:
        return (
            minimum_x + node[0] * GRID_RESOLUTION,
            minimum_y + node[1] * GRID_RESOLUTION,
        )

    maximum_cell = cell((maximum_x, maximum_y))
    start_cell = cell(start)
    goal_cell = cell(goal)
    frontier: list[tuple[float, float, tuple[int, int]]] = [(0.0, 0.0, start_cell)]
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start_cell: None}
    cost = {start_cell: 0.0}
    directions = (
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    )

    while frontier:
        _, current_cost, current = heapq.heappop(frontier)
        if current == goal_cell:
            break
        if current_cost > cost[current] + 1e-12:
            continue
        for offset_x, offset_y in directions:
            neighbor = (current[0] + offset_x, current[1] + offset_y)
            if not (0 <= neighbor[0] <= maximum_cell[0] and 0 <= neighbor[1] <= maximum_cell[1]):
                continue
            neighbor_point = point(neighbor)
            if _point_blocked(neighbor_point, obstacles, clearance):
                continue
            step_cost = math.sqrt(2.0) if offset_x and offset_y else 1.0
            candidate_cost = current_cost + step_cost
            if candidate_cost >= cost.get(neighbor, math.inf):
                continue
            cost[neighbor] = candidate_cost
            came_from[neighbor] = current
            heuristic = math.hypot(neighbor[0] - goal_cell[0], neighbor[1] - goal_cell[1])
            heapq.heappush(
                frontier,
                (candidate_cost + heuristic, candidate_cost, neighbor),
            )

    if goal_cell not in came_from:
        raise ValueError("No collision-free delivery route exists in the mission map")
    cells: list[tuple[int, int]] = []
    current: tuple[int, int] | None = goal_cell
    while current is not None:
        cells.append(current)
        current = came_from[current]
    raw_route = [start, *(point(node) for node in reversed(cells[1:-1])), goal]

    simplified = [raw_route[0]]
    anchor = 0
    while anchor < len(raw_route) - 1:
        candidate = len(raw_route) - 1
        while candidate > anchor + 1 and not _segment_clear(
            raw_route[anchor], raw_route[candidate], obstacles, clearance
        ):
            candidate -= 1
        simplified.append(raw_route[candidate])
        anchor = candidate
    return tuple(simplified)


class IrisObstacleDeliveryController(IrisPayloadDeliveryController):
    """A* delivery controller with rangefinder-based local collision protection."""

    name = "Iris Obstacle-Aware Payload Delivery"

    def __init__(self) -> None:
        super().__init__()
        self.route = plan_route(PICKUP, DROPOFF)
        self.route_index = 0
        self.avoidance_events = 0
        self.minimum_clearance = math.inf

    def reset(self, observation: ControllerObservation) -> None:
        super().reset(observation)
        missing = sorted(set(RAY_IDS) - set(observation.rangefinders))
        if missing:
            raise ValueError("Iris rangefinders are missing: " + ", ".join(missing))
        self.route = plan_route(PICKUP, DROPOFF)
        self.route_index = 0
        self.avoidance_events = 0
        self.minimum_clearance = math.inf

    def step(self, observation: ControllerObservation) -> ControllerAction:
        body = observation.bodies[IRIS_BODY_LINK]
        attachment = observation.attachments[ATTACHMENT_ID]
        self._advance_obstacle_mission(observation, attachment.active)
        target_position, target_velocity = self._trajectory_target(observation.time)
        if self.phase.startswith("navigate_loaded"):
            target_position, target_velocity = self._apply_local_avoidance(
                observation,
                target_position,
                target_velocity,
            )
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
            actuator_controls=dict(zip(IRIS_ROTOR_ACTUATORS, controls, strict=True)),
            attachment_commands={ATTACHMENT_ID: self.hold_payload},
        )

    def _advance_obstacle_mission(
        self,
        observation: ControllerObservation,
        attached: bool,
    ) -> None:
        body = observation.bodies[IRIS_BODY_LINK]
        elapsed = observation.time - self.phase_started_at
        position_error = _length(
            tuple(self.segment_target[index] - body.position[index] for index in range(3))
        )
        speed = _length(body.linear_velocity)
        segment_reached = (
            elapsed >= self.segment_duration and position_error < 0.2 and speed < 0.34
        )

        if self.phase == "spool" and elapsed >= self.segment_duration:
            self._start_segment("takeoff", (-2.0, 0.0, CRUISE_HEIGHT), 2.5, observation)
        elif self.phase == "takeoff" and segment_reached:
            self._start_segment("to_pickup", (*PICKUP, CRUISE_HEIGHT), 3.0, observation)
        elif self.phase == "to_pickup" and segment_reached:
            self._start_segment("descend_pickup", (*PICKUP, HOOK_HEIGHT), 3.0, observation)
            self.hold_payload = True
        elif self.phase == "descend_pickup" and segment_reached:
            self._hold_phase("capture", observation)
        elif self.phase == "capture" and attached:
            self._start_segment("lift_payload", (*PICKUP, CRUISE_HEIGHT), 3.0, observation)
        elif self.phase == "lift_payload" and segment_reached:
            self.route_index = 1
            self._start_route_segment(observation)
        elif self.phase.startswith("navigate_loaded") and segment_reached:
            self.route_index += 1
            if self.route_index < len(self.route):
                self._start_route_segment(observation)
            else:
                self._start_segment(
                    "descend_dropoff",
                    (*DROPOFF, HOOK_HEIGHT),
                    3.0,
                    observation,
                )
        elif self.phase == "descend_dropoff" and segment_reached:
            self._hold_phase("release", observation)
            self.hold_payload = False
        elif self.phase == "release" and not attached and elapsed >= 0.35:
            self._start_segment("retreat", (*DROPOFF, CRUISE_HEIGHT), 3.0, observation)
        elif self.phase == "retreat" and segment_reached:
            self._hold_phase("complete", observation)

    def _start_route_segment(self, observation: ControllerObservation) -> None:
        waypoint = self.route[self.route_index]
        current_target, _ = self._trajectory_target(observation.time)
        distance = math.hypot(
            waypoint[0] - current_target[0],
            waypoint[1] - current_target[1],
        )
        self._start_segment(
            f"navigate_loaded_{self.route_index}",
            (waypoint[0], waypoint[1], CRUISE_HEIGHT),
            max(1.2, distance / 0.72),
            observation,
        )

    def _apply_local_avoidance(
        self,
        observation: ControllerObservation,
        nominal_position: tuple[float, float, float],
        nominal_velocity: tuple[float, float, float],
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        body = observation.bodies[IRIS_BODY_LINK]
        yaw = _euler_from_wxyz(body.quaternion)[2]
        repulsion_x = 0.0
        repulsion_y = 0.0
        closest_angle = 0.0
        closest_distance = math.inf
        influence_distance = 1.2

        for sensor_id, local_angle in zip(RAY_IDS, RAY_ANGLES, strict=True):
            sample = observation.rangefinders[sensor_id]
            if not sample.hit:
                continue
            self.minimum_clearance = min(self.minimum_clearance, sample.distance)
            if sample.distance >= influence_distance:
                continue
            ray_angle = yaw + local_angle
            strength = 1.15 * (1.0 - sample.distance / influence_distance) ** 2
            repulsion_x -= math.cos(ray_angle) * strength
            repulsion_y -= math.sin(ray_angle) * strength
            if sample.distance < closest_distance:
                closest_distance = sample.distance
                closest_angle = ray_angle

        if closest_distance == math.inf:
            return nominal_position, nominal_velocity

        self.avoidance_events += 1
        nominal_heading = math.atan2(nominal_velocity[1], nominal_velocity[0])
        obstacle_ahead = abs(_wrap_angle(closest_angle - nominal_heading)) < math.radians(75)
        tangent_x = 0.0
        tangent_y = 0.0
        if obstacle_ahead and closest_distance < 0.9:
            # Deterministic clockwise wall following avoids oscillation at a flat wall.
            tangent_strength = 0.7 * (1.0 - closest_distance / 0.9)
            tangent_x = math.sin(closest_angle) * tangent_strength
            tangent_y = -math.cos(closest_angle) * tangent_strength

        velocity_x = nominal_velocity[0] + repulsion_x + tangent_x
        velocity_y = nominal_velocity[1] + repulsion_y + tangent_y
        speed = math.hypot(velocity_x, velocity_y)
        if speed > 0.9:
            velocity_x *= 0.9 / speed
            velocity_y *= 0.9 / speed

        if closest_distance < 0.35:
            target_x = body.position[0] + _clamp(repulsion_x, -0.45, 0.45)
            target_y = body.position[1] + _clamp(repulsion_y, -0.45, 0.45)
            velocity_x = _clamp(repulsion_x, -0.5, 0.5)
            velocity_y = _clamp(repulsion_y, -0.5, 0.5)
        else:
            target_x = nominal_position[0] + 0.18 * repulsion_x
            target_y = nominal_position[1] + 0.18 * repulsion_y

        return (
            (target_x, target_y, nominal_position[2]),
            (velocity_x, velocity_y, nominal_velocity[2]),
        )


def create_controller() -> IrisObstacleDeliveryController:
    return IrisObstacleDeliveryController()
