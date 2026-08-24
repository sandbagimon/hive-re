"""Parameterized obstacle-aware delivery pilot for Iris quadcopters.

:class:`ObstacleDeliveryPilot` layers an online navigation stack on top of the
parameterized :class:`IrisPayloadDeliveryController` mission FSM: rangefinder
sweeps build a live occupancy grid, an incremental A* planner replans around
obstacles detected on the route, and a reactive repulsion + wall-following
layer handles last-moment avoidance between planner updates. Every stable ID,
mission point, and navigation parameter can be overridden per instance, so a
multi-drone scene can run one pilot per airframe (each with its own sensors,
prior map, and delivery leg) inside a single controller. Optional ``intruders``
positions let a swarm wrapper deconflict airframes through the same occupancy
grid and repulsion layer.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from beefoundrysim.controllers.iris_payload_delivery import (
    IrisPayloadDeliveryController,
    _clamp,
    _euler_from_wxyz,
    _length,
    _wrap_angle,
)
from beefoundrysim.controllers.realtime_navigation import (
    GridSpec,
    IncrementalAStarPlanner,
    LiveOccupancyGrid,
    Point2D,
    Rectangle,
    rectangle_cells,
    route_is_clear,
)
from beefoundrysim.controllers.realtime_navigation import (
    plan_route as plan_grid_route,
)
from beefoundrysim.services.controller_runtime import (
    ControllerAction,
    ControllerObservation,
    NavigationUpdate,
)

# Default scan geometry and navigation cadence (see the obstacle demo scene):
# beams originate 0.32 m from the body center, and the occupancy grid is
# refreshed every 40 ms of simulated time.
DEFAULT_RAY_ORIGIN_RADIUS = 0.32
DEFAULT_MAP_UPDATE_PERIOD = 0.04
DEFAULT_ROUTE_CHECK_PERIOD = 0.04

# Default replanning budget and hysteresis: the A* planner spreads its node
# expansions across steps; replans are rate-limited and blocked routes are
# retried on a timer so a transient obstacle does not thrash the route.
DEFAULT_PLANNER_EXPANSIONS_PER_STEP = 48
DEFAULT_REPLAN_COOLDOWN = 0.25
DEFAULT_REPLAN_RETRY_PERIOD = 0.5

# Default progress watchdog: flying toward the goal must improve by
# MINIMUM_PROGRESS at least once per STALL_TIMEOUT, otherwise the route is
# assumed blocked.
DEFAULT_STALL_TIMEOUT = 1.5
DEFAULT_MINIMUM_PROGRESS = 0.12

# Ground clutter would poison the occupancy grid, so scans only count once the
# vehicle has climbed above this altitude.
DEFAULT_MAPPING_MINIMUM_ALTITUDE = 0.75

# Intruder deconfliction: neighbouring airframes are injected into the grid and
# repelled from within this radius during local avoidance.
INTRUDER_INFLUENCE_DISTANCE = 1.8


def plan_pilot_route(
    spec: GridSpec,
    start: Point2D,
    goal: Point2D,
    *,
    obstacles: tuple[Rectangle, ...],
    clearance: float,
) -> tuple[Point2D, ...]:
    """Plan and line-of-sight simplify an eight-connected occupancy-grid route."""
    blocked_cells = rectangle_cells(spec, obstacles, clearance)
    return plan_grid_route(spec, start, goal, blocked_cells)


class ObstacleDeliveryPilot(IrisPayloadDeliveryController):
    """One airframe's online mapping and incremental replanning delivery pilot."""

    def __init__(
        self,
        *,
        ray_ids: Sequence[str],
        ray_angles: Sequence[float],
        grid_spec: GridSpec,
        prior_obstacles: tuple[Rectangle, ...],
        clearance: float,
        observation_ttl: float = 2.0,
        ray_origin_radius: float = DEFAULT_RAY_ORIGIN_RADIUS,
        map_update_period: float = DEFAULT_MAP_UPDATE_PERIOD,
        route_check_period: float = DEFAULT_ROUTE_CHECK_PERIOD,
        expansions_per_step: int = DEFAULT_PLANNER_EXPANSIONS_PER_STEP,
        replan_cooldown: float = DEFAULT_REPLAN_COOLDOWN,
        replan_retry_period: float = DEFAULT_REPLAN_RETRY_PERIOD,
        stall_timeout: float = DEFAULT_STALL_TIMEOUT,
        minimum_progress: float = DEFAULT_MINIMUM_PROGRESS,
        mapping_minimum_altitude: float = DEFAULT_MAPPING_MINIMUM_ALTITUDE,
        minimum_hit_distance: float = 0.25,
        **base_kwargs: object,
    ) -> None:
        if len(ray_ids) != len(ray_angles):
            raise ValueError("ray_ids and ray_angles must have the same length")
        super().__init__(**base_kwargs)  # type: ignore[arg-type]
        self.ray_ids = tuple(ray_ids)
        self.ray_angles = tuple(ray_angles)
        self.grid_spec = grid_spec
        self.prior_obstacles = tuple(prior_obstacles)
        self.clearance = clearance
        self.observation_ttl = observation_ttl
        self.ray_origin_radius = ray_origin_radius
        self.map_update_period = map_update_period
        self.route_check_period = route_check_period
        self.expansions_per_step = expansions_per_step
        self.replan_cooldown = replan_cooldown
        self.replan_retry_period = replan_retry_period
        self.stall_timeout = stall_timeout
        self.minimum_progress = minimum_progress
        self.mapping_minimum_altitude = mapping_minimum_altitude
        # Rangefinder hits closer than this are treated as self-reflections.
        # A slung payload swinging under the airframe (and rotor-downwash
        # turbulence) can otherwise seed ghost obstacle cells right around the
        # vehicle that poison route checks and replanning.
        self.minimum_hit_distance = minimum_hit_distance
        self._init_navigation_state()

    def _init_navigation_state(self) -> None:
        """(Re)initialise every navigation field against a fresh episode."""
        # Initial route from the static prior map; replaced by replans once the
        # live occupancy grid disagrees with it.
        self.route = plan_pilot_route(
            self.grid_spec,
            self.pickup,
            self.dropoff,
            obstacles=self.prior_obstacles,
            clearance=self.clearance,
        )
        self.route_index = 0
        # Telemetry counters surfaced through NavigationUpdate.
        self.avoidance_events = 0
        self.minimum_clearance = math.inf
        self.occupancy = LiveOccupancyGrid(
            self.grid_spec,
            static_obstacles=self.prior_obstacles,
            clearance=self.clearance,
            observation_ttl=self.observation_ttl,
        )
        # Active incremental planner between _request_replan and adoption; the
        # pilot hovers while it advances over successive steps.
        self.planner: IncrementalAStarPlanner | None = None
        self.navigation_status = "ready"
        self.navigation_message: str | None = None
        self.route_revision = 1
        self.replan_count = 0
        self.last_replan_time: float | None = None
        self.next_map_update = 0.0
        self.next_route_check = 0.0
        self.last_replan_request = -math.inf
        self.next_replan_retry = 0.0
        # Progress watchdog state (see stall_timeout / minimum_progress).
        self.best_goal_distance = math.inf
        self.last_progress_time = 0.0
        # NavigationUpdate is only emitted when something actually changed.
        self.telemetry_dirty = True

    def reset(self, observation: ControllerObservation) -> None:
        # Re-run the navigation initialisation against the new episode's clock
        # so time-based thresholds stay valid, then validate the sensors.
        super().reset(observation)
        missing = sorted(set(self.ray_ids) - set(observation.rangefinders))
        if missing:
            raise ValueError("Iris rangefinders are missing: " + ", ".join(missing))
        self._init_navigation_state()
        self.next_map_update = observation.time
        self.next_route_check = observation.time
        self.next_replan_retry = observation.time
        self.last_progress_time = observation.time

    def step(
        self,
        observation: ControllerObservation,
        intruders: tuple[Point2D, ...] = (),
    ) -> ControllerAction:
        # Pipeline per step: advance the delivery FSM and obstacle mission,
        # refresh the live map / replanner, then mix the nominal trajectory
        # with reactive avoidance before the base PID/mixer produces rotor speeds.
        body = observation.bodies[self.body_link_id]
        attachment = observation.attachments[self.attachment_id]
        self._advance_obstacle_mission(observation, attachment.active)
        self._update_realtime_navigation(
            observation,
            attachment.active,
            intruders=intruders,
        )
        target_position, target_velocity = self._trajectory_target(observation.time)
        if self.phase.startswith("navigate_"):
            target_position, target_velocity = self._apply_local_avoidance(
                observation,
                target_position,
                target_velocity,
                intruders=intruders,
            )
        controls = self._flight_controls(
            body.position,
            body.quaternion,
            body.linear_velocity,
            body.angular_velocity,
            target_position,
            target_velocity,
            carrying=attachment.active,
            payload_mass=self.payload_mass,
        )
        navigation = self._navigation_update() if self.telemetry_dirty else None
        self.telemetry_dirty = False
        return ControllerAction(
            actuator_controls=dict(
                zip(self.rotor_actuators, controls, strict=True)
            ),
            attachment_commands={self.attachment_id: self.hold_payload},
            navigation=navigation,
        )

    def navigation_update(self) -> NavigationUpdate:
        """Snapshot the navigation state for the frontend Sensors/Navigation panel."""
        return NavigationUpdate(
            status=self.navigation_status,
            route=tuple(
                (x, y, self.cruise_height) for x, y in self.route
            ),
            route_revision=self.route_revision,
            map_revision=self.occupancy.revision,
            replan_count=self.replan_count,
            occupied_cell_count=self.occupancy.observed_cell_count,
            last_replan_time=self.last_replan_time,
            message=self.navigation_message,
        )

    # Retained alias matching the historic private helper name.
    _navigation_update = navigation_update

    def _update_realtime_navigation(
        self,
        observation: ControllerObservation,
        attached: bool,
        *,
        intruders: tuple[Point2D, ...] = (),
    ) -> None:
        """Update the occupancy grid and drive replanning during loaded flight.

        Three duties per step, in order:
        1. fold the latest rangefinder sweep (and intruder reports) into the
           occupancy grid,
        2. advance an in-flight incremental planner and adopt its route,
        3. otherwise check the current route against the live grid and the
           progress watchdog, requesting a replan when either trips.
        """
        body = observation.bodies[self.body_link_id]
        # Mapping only runs above the clutter altitude and on a fixed cadence;
        # yaw rotates the body-frame beam angles into the map frame.
        if (
            body.position[2] >= self.mapping_minimum_altitude
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
                for sensor_id, local_angle in zip(
                    self.ray_ids, self.ray_angles, strict=True
                )
            )
            changed = self.occupancy.update_scan(
                body_position=(body.position[0], body.position[1]),
                yaw=yaw,
                beams=beams,
                now=observation.time,
                origin_offset=self.ray_origin_radius,
                minimum_hit_distance=self.minimum_hit_distance,
            )
            # Swarm deconfliction: neighbouring airframes are transient map
            # obstacles too, so planners route around them with the same TTL.
            for intruder in intruders:
                if math.hypot(
                    intruder[0] - body.position[0],
                    intruder[1] - body.position[1],
                ) < INTRUDER_INFLUENCE_DISTANCE:
                    changed = (
                        self.occupancy.add_transient_obstacle(
                            intruder, observation.time
                        )
                        or changed
                    )
            if changed:
                self.telemetry_dirty = True
            self.next_map_update = observation.time + self.map_update_period

        # Navigation decisions only matter once the payload is captured and the
        # vehicle is flying the loaded leg; everything else just reports status.
        navigation_active = attached and (
            self.phase == "lift_payload" or self.phase.startswith("navigate_")
        )
        if not navigation_active:
            if self.phase == "complete" and self.navigation_status != "complete":
                self.navigation_status = "complete"
                self.navigation_message = None
                self.telemetry_dirty = True
            return

        # A planner is already running: spend this step's expansion budget and
        # adopt (or reject) its result — no new replans may be requested here.
        if self.planner is not None:
            status = self.planner.advance(self.expansions_per_step)
            if status == "ready":
                self._adopt_replanned_route(observation)
            elif status == "blocked":
                self._enter_navigation_blocked(observation)
            return

        # Previous search failed: wait out the retry period before trying again.
        if self.phase == "navigate_blocked":
            if observation.time + 1e-12 >= self.next_replan_retry:
                self._request_replan(observation, "retry_after_blocked")
            return
        if not self.phase.startswith("navigate_loaded"):
            return

        # The route can only become newly blocked after a map update. Checking
        # it at the map cadence avoids resampling every segment at 100 Hz while
        # the reactive rangefinder layer continues to run on every control tick.
        if observation.time + 1e-12 < self.next_route_check:
            return
        self.next_route_check = observation.time + self.route_check_period

        # Trigger check 1: any observed obstacle cell now blocks the remaining route.
        position = (body.position[0], body.position[1])
        remaining_route = (position, *self.route[self.route_index :])
        blocked_cells = self.occupancy.blocked_cells()
        if not route_is_clear(remaining_route, self.grid_spec, blocked_cells):
            self._request_replan(observation, "live_obstacle_on_route")
            return

        # Trigger check 2: progress watchdog — no meaningful goal progress lately.
        goal_distance = math.hypot(
            self.dropoff[0] - body.position[0],
            self.dropoff[1] - body.position[1],
        )
        if goal_distance <= self.best_goal_distance - self.minimum_progress:
            self.best_goal_distance = goal_distance
            self.last_progress_time = observation.time
        elif observation.time - self.last_progress_time >= self.stall_timeout:
            self._request_replan(observation, "navigation_progress_stalled")

    def _request_replan(
        self,
        observation: ControllerObservation,
        reason: str,
    ) -> None:
        """Start an incremental A* replan from the current position to the dropoff.

        The vehicle switches to a hover segment while the planner spreads its
        search over subsequent steps. Rate-limited by replan_cooldown.
        """
        if observation.time - self.last_replan_request < self.replan_cooldown:
            return
        body = observation.bodies[self.body_link_id]
        start = (body.position[0], body.position[1])
        self.planner = IncrementalAStarPlanner(
            self.grid_spec,
            start,
            self.dropoff,
            self.occupancy.blocked_cells(),
        )
        self.last_replan_request = observation.time
        self.navigation_status = "planning"
        self.navigation_message = reason
        self._hold_for_navigation(observation, "navigate_replanning")
        self.telemetry_dirty = True

    def _adopt_replanned_route(self, observation: ControllerObservation) -> None:
        """Swap in the finished planner route and resume loaded navigation."""
        planner = self.planner
        if planner is None or planner.route is None:
            self._enter_navigation_blocked(observation)
            return
        self.route = planner.route
        # route_index 0 is the planner's start cell, i.e. the current position.
        self.route_index = 1
        self.planner = None
        self.navigation_status = "following"
        self.navigation_message = None
        self.route_revision += 1
        self.replan_count += 1
        self.last_replan_time = observation.time
        body = observation.bodies[self.body_link_id]
        # Reset the progress watchdog baseline for the new route.
        self.best_goal_distance = math.hypot(
            self.dropoff[0] - body.position[0],
            self.dropoff[1] - body.position[1],
        )
        self.last_progress_time = observation.time
        if len(self.route) < 2:
            # Already at the goal cell: skip navigation and start the dropoff descent.
            self._start_segment(
                "descend_dropoff",
                (*self.dropoff, self.dropoff_hook_height),
                3.0,
                observation,
            )
        else:
            self._start_route_segment(observation)
        self.telemetry_dirty = True

    def _enter_navigation_blocked(self, observation: ControllerObservation) -> None:
        """Mark the search failed and hover until replan_retry_period elapses."""
        self.planner = None
        self.navigation_status = "blocked"
        self.navigation_message = "no_collision_free_route"
        self.next_replan_retry = observation.time + self.replan_retry_period
        self._hold_for_navigation(observation, "navigate_blocked")
        self.telemetry_dirty = True

    def _hold_for_navigation(
        self,
        observation: ControllerObservation,
        phase: str,
    ) -> None:
        """Interrupt the current segment and hover in place at cruise height."""
        body = observation.bodies[self.body_link_id]
        position = body.position
        self.phase = phase
        self.phase_started_at = observation.time
        self.segment_start = position
        self.segment_target = (position[0], position[1], self.cruise_height)
        self.segment_duration = 0.5

    def _advance_obstacle_mission(
        self,
        observation: ControllerObservation,
        attached: bool,
    ) -> None:
        """Delivery mission FSM: pickup -> loaded route following -> dropoff.

        Same skeleton as the base controller, but the loaded leg follows the
        (possibly replanned) waypoint route instead of a single straight
        segment, and resets the navigation watchdog when the leg starts.
        """
        body = observation.bodies[self.body_link_id]
        elapsed = observation.time - self.phase_started_at
        position_error = _length(
            tuple(self.segment_target[index] - body.position[index] for index in range(3))
        )
        speed = _length(body.linear_velocity)
        segment_reached = (
            elapsed >= self.segment_duration and position_error < 0.2 and speed < 0.34
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
            self.hold_payload = True
        elif self.phase == "descend_pickup" and segment_reached:
            self._hold_phase("capture", observation)
        elif self.phase == "capture" and attached:
            self._start_segment(
                "lift_payload", (*self.pickup, self.cruise_height), 3.0, observation
            )
        elif self.phase == "lift_payload" and segment_reached:
            # Entering the loaded leg: arm the route follower and watchdog.
            self.route_index = 1
            self.navigation_status = "following"
            self.navigation_message = None
            self.best_goal_distance = math.hypot(
                self.dropoff[0] - body.position[0],
                self.dropoff[1] - body.position[1],
            )
            self.last_progress_time = observation.time
            self.telemetry_dirty = True
            self._start_route_segment(observation)
        elif self.phase.startswith("navigate_loaded") and segment_reached:
            # Waypoint reached; advance to the next one or start the dropoff descent.
            self.route_index += 1
            if self.route_index < len(self.route):
                self._start_route_segment(observation)
            else:
                self.navigation_status = "arrived"
                self.navigation_message = None
                self.telemetry_dirty = True
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
            self.navigation_status = "complete"
            self.navigation_message = None
            self.telemetry_dirty = True

    def _start_route_segment(self, observation: ControllerObservation) -> None:
        """Fly to the current waypoint at ~0.72 m/s, blending from the live target."""
        waypoint = self.route[self.route_index]
        current_target, _ = self._trajectory_target(observation.time)
        distance = math.hypot(
            waypoint[0] - current_target[0],
            waypoint[1] - current_target[1],
        )
        self._start_segment(
            f"navigate_loaded_{self.route_index}",
            (waypoint[0], waypoint[1], self.cruise_height),
            max(1.2, distance / 0.72),
            observation,
        )

    def _apply_local_avoidance(
        self,
        observation: ControllerObservation,
        nominal_position: tuple[float, float, float],
        nominal_velocity: tuple[float, float, float],
        *,
        intruders: tuple[Point2D, ...] = (),
    ) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        """Reactive avoidance layered on the nominal trajectory.

        Combines an inverse-square-style repulsion field from nearby ray hits
        (and neighbouring airframes) with deterministic clockwise wall following
        when an obstacle sits ahead; inside 0.35 m the commanded motion
        collapses to pure retreat.
        """
        body = observation.bodies[self.body_link_id]
        yaw = _euler_from_wxyz(body.quaternion)[2]
        repulsion_x = 0.0
        repulsion_y = 0.0
        closest_angle = 0.0
        closest_distance = math.inf
        # Obstacles only push back within this radius; strength grows quadratically
        # as the hit distance shrinks.
        influence_distance = 1.2

        for sensor_id, local_angle in zip(self.ray_ids, self.ray_angles, strict=True):
            sample = observation.rangefinders[sensor_id]
            if not sample.hit:
                continue
            # Apply the same self-reflection floor as the occupancy grid: a
            # slung payload swinging under the airframe would otherwise fire
            # the repulsion layer on every step and stall long legs.
            if sample.distance < self.minimum_hit_distance:
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

        # Neighbouring airframes repel exactly like a ray hit in the map frame.
        for intruder in intruders:
            delta_x = intruder[0] - body.position[0]
            delta_y = intruder[1] - body.position[1]
            distance = math.hypot(delta_x, delta_y)
            if distance >= INTRUDER_INFLUENCE_DISTANCE or distance < 1e-6:
                continue
            strength = 1.3 * (1.0 - distance / INTRUDER_INFLUENCE_DISTANCE) ** 2
            repulsion_x -= delta_x / distance * strength
            repulsion_y -= delta_y / distance * strength
            if distance < closest_distance:
                closest_distance = distance
                closest_angle = math.atan2(delta_y, delta_x)

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

        # Mix repulsion + tangent into the nominal velocity, capped for stability.
        velocity_x = nominal_velocity[0] + repulsion_x + tangent_x
        velocity_y = nominal_velocity[1] + repulsion_y + tangent_y
        speed = math.hypot(velocity_x, velocity_y)
        if speed > 0.9:
            velocity_x *= 0.9 / speed
            velocity_y *= 0.9 / speed

        if closest_distance < 0.35:
            # Emergency zone: ignore the nominal command and back straight off.
            target_x = body.position[0] + _clamp(repulsion_x, -0.45, 0.45)
            target_y = body.position[1] + _clamp(repulsion_y, -0.45, 0.45)
            velocity_x = _clamp(repulsion_x, -0.5, 0.5)
            velocity_y = _clamp(repulsion_y, -0.5, 0.5)
        else:
            # Far enough away: nudge the position target slightly off the nominal.
            target_x = nominal_position[0] + 0.18 * repulsion_x
            target_y = nominal_position[1] + 0.18 * repulsion_y

        return (
            (target_x, target_y, nominal_position[2]),
            (velocity_x, velocity_y, nominal_velocity[2]),
        )
