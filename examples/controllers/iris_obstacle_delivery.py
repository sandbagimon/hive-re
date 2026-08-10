from __future__ import annotations

import math

from simlab.controllers.iris_payload_delivery import (
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
from simlab.controllers.realtime_navigation import (
    GridSpec,
    IncrementalAStarPlanner,
    LiveOccupancyGrid,
    rectangle_cells,
    route_is_clear,
)
from simlab.controllers.realtime_navigation import (
    plan_route as plan_grid_route,
)
from simlab.services.controller_runtime import (
    ControllerAction,
    ControllerObservation,
    NavigationUpdate,
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
GRID_SPEC = GridSpec(*MAP_BOUNDS, GRID_RESOLUTION)
RAY_ORIGIN_RADIUS = 0.32
MAP_UPDATE_PERIOD = 0.02
PLANNER_EXPANSIONS_PER_STEP = 48
REPLAN_COOLDOWN = 0.25
REPLAN_RETRY_PERIOD = 0.5
STALL_TIMEOUT = 1.5
MINIMUM_PROGRESS = 0.12
MAPPING_MINIMUM_ALTITUDE = 0.75


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
    blocked_cells = rectangle_cells(GRID_SPEC, obstacles, clearance)
    return plan_grid_route(GRID_SPEC, start, goal, blocked_cells)


class IrisObstacleDeliveryController(IrisPayloadDeliveryController):
    """Online mapping and incremental replanning for physical payload delivery."""

    name = "Iris Obstacle-Aware Payload Delivery"

    def __init__(self) -> None:
        super().__init__()
        self.route = plan_route(PICKUP, DROPOFF)
        self.route_index = 0
        self.avoidance_events = 0
        self.minimum_clearance = math.inf
        self.occupancy = self._new_occupancy_grid()
        self.planner: IncrementalAStarPlanner | None = None
        self.navigation_status = "ready"
        self.navigation_message: str | None = None
        self.route_revision = 1
        self.replan_count = 0
        self.last_replan_time: float | None = None
        self.next_map_update = 0.0
        self.last_replan_request = -math.inf
        self.next_replan_retry = 0.0
        self.best_goal_distance = math.inf
        self.last_progress_time = 0.0
        self.telemetry_dirty = True

    def reset(self, observation: ControllerObservation) -> None:
        super().reset(observation)
        missing = sorted(set(RAY_IDS) - set(observation.rangefinders))
        if missing:
            raise ValueError("Iris rangefinders are missing: " + ", ".join(missing))
        self.route = plan_route(PICKUP, DROPOFF)
        self.route_index = 0
        self.avoidance_events = 0
        self.minimum_clearance = math.inf
        self.occupancy = self._new_occupancy_grid()
        self.planner = None
        self.navigation_status = "ready"
        self.navigation_message = None
        self.route_revision = 1
        self.replan_count = 0
        self.last_replan_time = None
        self.next_map_update = observation.time
        self.last_replan_request = -math.inf
        self.next_replan_retry = observation.time
        self.best_goal_distance = math.inf
        self.last_progress_time = observation.time
        self.telemetry_dirty = True

    def step(self, observation: ControllerObservation) -> ControllerAction:
        body = observation.bodies[IRIS_BODY_LINK]
        attachment = observation.attachments[ATTACHMENT_ID]
        self._advance_obstacle_mission(observation, attachment.active)
        self._update_realtime_navigation(observation, attachment.active)
        target_position, target_velocity = self._trajectory_target(observation.time)
        if self.phase.startswith("navigate_"):
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
        navigation = self._navigation_update() if self.telemetry_dirty else None
        self.telemetry_dirty = False
        return ControllerAction(
            actuator_controls=dict(zip(IRIS_ROTOR_ACTUATORS, controls, strict=True)),
            attachment_commands={ATTACHMENT_ID: self.hold_payload},
            navigation=navigation,
        )

    @staticmethod
    def _new_occupancy_grid() -> LiveOccupancyGrid:
        return LiveOccupancyGrid(
            GRID_SPEC,
            static_obstacles=MISSION_OBSTACLES,
            clearance=LOADED_CLEARANCE,
            observation_ttl=2.0,
            observed_obstacle_radius=0.12,
        )

    def _navigation_update(self) -> NavigationUpdate:
        return NavigationUpdate(
            status=self.navigation_status,
            route=tuple((x, y, CRUISE_HEIGHT) for x, y in self.route),
            route_revision=self.route_revision,
            map_revision=self.occupancy.revision,
            replan_count=self.replan_count,
            occupied_cell_count=self.occupancy.observed_cell_count,
            last_replan_time=self.last_replan_time,
            message=self.navigation_message,
        )

    def _update_realtime_navigation(
        self,
        observation: ControllerObservation,
        attached: bool,
    ) -> None:
        body = observation.bodies[IRIS_BODY_LINK]
        if (
            body.position[2] >= MAPPING_MINIMUM_ALTITUDE
            and observation.time + 1e-12 >= self.next_map_update
        ):
            yaw = _euler_from_wxyz(body.quaternion)[2]
            beams = tuple(
                (
                    local_angle,
                    observation.rangefinders[sensor_id].distance,
                    observation.rangefinders[sensor_id].max_distance,
                    observation.rangefinders[sensor_id].hit,
                )
                for sensor_id, local_angle in zip(RAY_IDS, RAY_ANGLES, strict=True)
            )
            if self.occupancy.update_scan(
                body_position=(body.position[0], body.position[1]),
                yaw=yaw,
                beams=beams,
                now=observation.time,
                origin_offset=RAY_ORIGIN_RADIUS,
            ):
                self.telemetry_dirty = True
            self.next_map_update = observation.time + MAP_UPDATE_PERIOD

        navigation_active = attached and (
            self.phase == "lift_payload" or self.phase.startswith("navigate_")
        )
        if not navigation_active:
            if self.phase == "complete" and self.navigation_status != "complete":
                self.navigation_status = "complete"
                self.navigation_message = None
                self.telemetry_dirty = True
            return

        if self.planner is not None:
            status = self.planner.advance(PLANNER_EXPANSIONS_PER_STEP)
            if status == "ready":
                self._adopt_replanned_route(observation)
            elif status == "blocked":
                self._enter_navigation_blocked(observation)
            return

        if self.phase == "navigate_blocked":
            if observation.time + 1e-12 >= self.next_replan_retry:
                self._request_replan(observation, "retry_after_blocked")
            return
        if not self.phase.startswith("navigate_loaded"):
            return

        position = (body.position[0], body.position[1])
        remaining_route = (position, *self.route[self.route_index :])
        blocked_cells = self.occupancy.blocked_cells()
        if not route_is_clear(remaining_route, GRID_SPEC, blocked_cells):
            self._request_replan(observation, "live_obstacle_on_route")
            return

        goal_distance = math.hypot(
            DROPOFF[0] - body.position[0],
            DROPOFF[1] - body.position[1],
        )
        if goal_distance <= self.best_goal_distance - MINIMUM_PROGRESS:
            self.best_goal_distance = goal_distance
            self.last_progress_time = observation.time
        elif observation.time - self.last_progress_time >= STALL_TIMEOUT:
            self._request_replan(observation, "navigation_progress_stalled")

    def _request_replan(
        self,
        observation: ControllerObservation,
        reason: str,
    ) -> None:
        if observation.time - self.last_replan_request < REPLAN_COOLDOWN:
            return
        body = observation.bodies[IRIS_BODY_LINK]
        start = (body.position[0], body.position[1])
        self.planner = IncrementalAStarPlanner(
            GRID_SPEC,
            start,
            DROPOFF,
            self.occupancy.blocked_cells(),
        )
        self.last_replan_request = observation.time
        self.navigation_status = "planning"
        self.navigation_message = reason
        self._hold_for_navigation(observation, "navigate_replanning")
        self.telemetry_dirty = True

    def _adopt_replanned_route(self, observation: ControllerObservation) -> None:
        planner = self.planner
        if planner is None or planner.route is None:
            self._enter_navigation_blocked(observation)
            return
        self.route = planner.route
        self.route_index = 1
        self.planner = None
        self.navigation_status = "following"
        self.navigation_message = None
        self.route_revision += 1
        self.replan_count += 1
        self.last_replan_time = observation.time
        body = observation.bodies[IRIS_BODY_LINK]
        self.best_goal_distance = math.hypot(
            DROPOFF[0] - body.position[0],
            DROPOFF[1] - body.position[1],
        )
        self.last_progress_time = observation.time
        if len(self.route) < 2:
            self._start_segment(
                "descend_dropoff",
                (*DROPOFF, HOOK_HEIGHT),
                3.0,
                observation,
            )
        else:
            self._start_route_segment(observation)
        self.telemetry_dirty = True

    def _enter_navigation_blocked(self, observation: ControllerObservation) -> None:
        self.planner = None
        self.navigation_status = "blocked"
        self.navigation_message = "no_collision_free_route"
        self.next_replan_retry = observation.time + REPLAN_RETRY_PERIOD
        self._hold_for_navigation(observation, "navigate_blocked")
        self.telemetry_dirty = True

    def _hold_for_navigation(
        self,
        observation: ControllerObservation,
        phase: str,
    ) -> None:
        body = observation.bodies[IRIS_BODY_LINK]
        position = body.position
        self.phase = phase
        self.phase_started_at = observation.time
        self.segment_start = position
        self.segment_target = (position[0], position[1], CRUISE_HEIGHT)
        self.segment_duration = 0.5

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
            self.navigation_status = "following"
            self.navigation_message = None
            self.best_goal_distance = math.hypot(
                DROPOFF[0] - body.position[0],
                DROPOFF[1] - body.position[1],
            )
            self.last_progress_time = observation.time
            self.telemetry_dirty = True
            self._start_route_segment(observation)
        elif self.phase.startswith("navigate_loaded") and segment_reached:
            self.route_index += 1
            if self.route_index < len(self.route):
                self._start_route_segment(observation)
            else:
                self.navigation_status = "arrived"
                self.navigation_message = None
                self.telemetry_dirty = True
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
            self.navigation_status = "complete"
            self.navigation_message = None
            self.telemetry_dirty = True

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
