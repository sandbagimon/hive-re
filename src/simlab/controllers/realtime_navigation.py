from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Literal

Point2D = tuple[float, float]
GridCell = tuple[int, int]
Rectangle = tuple[float, float, float, float]
PlannerStatus = Literal["planning", "ready", "blocked"]


@dataclass(frozen=True, slots=True)
class GridSpec:
    minimum_x: float
    maximum_x: float
    minimum_y: float
    maximum_y: float
    resolution: float

    def __post_init__(self) -> None:
        values = (
            self.minimum_x,
            self.maximum_x,
            self.minimum_y,
            self.maximum_y,
            self.resolution,
        )
        if any(not math.isfinite(value) for value in values):
            raise ValueError("Grid bounds and resolution must be finite")
        if self.maximum_x <= self.minimum_x or self.maximum_y <= self.minimum_y:
            raise ValueError("Grid maximum bounds must exceed minimum bounds")
        if self.resolution <= 0:
            raise ValueError("Grid resolution must be greater than zero")

    @property
    def maximum_cell(self) -> GridCell:
        return self.cell((self.maximum_x, self.maximum_y), clamp=True)

    def cell(self, point: Point2D, *, clamp: bool = False) -> GridCell:
        cell = (
            round((point[0] - self.minimum_x) / self.resolution),
            round((point[1] - self.minimum_y) / self.resolution),
        )
        if clamp:
            maximum_x, maximum_y = (
                round((self.maximum_x - self.minimum_x) / self.resolution),
                round((self.maximum_y - self.minimum_y) / self.resolution),
            )
            return (
                max(0, min(maximum_x, cell[0])),
                max(0, min(maximum_y, cell[1])),
            )
        return cell

    def point(self, cell: GridCell) -> Point2D:
        return (
            self.minimum_x + cell[0] * self.resolution,
            self.minimum_y + cell[1] * self.resolution,
        )

    def contains(self, cell: GridCell) -> bool:
        maximum_x, maximum_y = self.maximum_cell
        return 0 <= cell[0] <= maximum_x and 0 <= cell[1] <= maximum_y


def rectangle_cells(
    spec: GridSpec,
    rectangles: tuple[Rectangle, ...],
    clearance: float,
) -> frozenset[GridCell]:
    if not math.isfinite(clearance) or clearance < 0:
        raise ValueError("Obstacle clearance must be finite and >= 0")
    result: set[GridCell] = set()
    maximum_x, maximum_y = spec.maximum_cell
    for x_index in range(maximum_x + 1):
        for y_index in range(maximum_y + 1):
            x, y = spec.point((x_index, y_index))
            if any(
                abs(x - center_x) <= half_x + clearance
                and abs(y - center_y) <= half_y + clearance
                for center_x, center_y, half_x, half_y in rectangles
            ):
                result.add((x_index, y_index))
    return frozenset(result)


def segment_is_clear(
    start: Point2D,
    end: Point2D,
    spec: GridSpec,
    blocked_cells: frozenset[GridCell],
) -> bool:
    distance = math.hypot(end[0] - start[0], end[1] - start[1])
    sample_count = max(1, math.ceil(distance / (spec.resolution * 0.4)))
    return all(
        spec.cell(
            (
                start[0] + (end[0] - start[0]) * index / sample_count,
                start[1] + (end[1] - start[1]) * index / sample_count,
            ),
            clamp=True,
        )
        not in blocked_cells
        for index in range(sample_count + 1)
    )


def route_is_clear(
    route: tuple[Point2D, ...],
    spec: GridSpec,
    blocked_cells: frozenset[GridCell],
) -> bool:
    return len(route) < 2 or all(
        segment_is_clear(start, end, spec, blocked_cells)
        for start, end in zip(route, route[1:], strict=False)
    )


class LiveOccupancyGrid:
    """Fuse range scans into a bounded 2D occupancy grid with expiring observations."""

    def __init__(
        self,
        spec: GridSpec,
        *,
        static_obstacles: tuple[Rectangle, ...] = (),
        clearance: float,
        observation_ttl: float = 2.0,
        observed_obstacle_radius: float = 0.12,
    ) -> None:
        if not math.isfinite(observation_ttl) or observation_ttl <= 0:
            raise ValueError("Observation TTL must be finite and > 0")
        if not math.isfinite(observed_obstacle_radius) or observed_obstacle_radius < 0:
            raise ValueError("Observed obstacle radius must be finite and >= 0")
        self.spec = spec
        self.clearance = clearance
        self.observation_ttl = observation_ttl
        self.observed_obstacle_radius = observed_obstacle_radius
        self.static_cells = rectangle_cells(spec, static_obstacles, clearance)
        self._observed_at: dict[GridCell, float] = {}
        self.revision = 0

    @property
    def observed_cell_count(self) -> int:
        return len(self._observed_at)

    def reset(self) -> None:
        changed = bool(self._observed_at)
        self._observed_at.clear()
        if changed:
            self.revision += 1

    def update_scan(
        self,
        *,
        body_position: Point2D,
        yaw: float,
        beams: tuple[tuple[float, float, float, bool], ...],
        now: float,
        origin_offset: float = 0.0,
        minimum_hit_distance: float = 0.25,
    ) -> bool:
        if not math.isfinite(now) or now < 0:
            raise ValueError("Scan time must be finite and >= 0")
        previous = set(self._observed_at)
        expiry = now - self.observation_ttl
        self._observed_at = {
            cell: observed_at
            for cell, observed_at in self._observed_at.items()
            if observed_at + 1e-12 >= expiry
        }
        for local_angle, distance, max_distance, hit in beams:
            if (
                not math.isfinite(local_angle)
                or not math.isfinite(distance)
                or not math.isfinite(max_distance)
                or max_distance <= 0
            ):
                raise ValueError("Range scan contains invalid values")
            angle = yaw + local_angle
            direction = (math.cos(angle), math.sin(angle))
            origin = (
                body_position[0] + origin_offset * direction[0],
                body_position[1] + origin_offset * direction[1],
            )
            travel = max(0.0, min(distance, max_distance))
            clear_distance = max(
                0.0,
                travel - self.spec.resolution * 1.25 if hit else travel,
            )
            sample_count = max(
                1,
                math.ceil(clear_distance / (self.spec.resolution * 0.45)),
            )
            for index in range(sample_count + 1):
                amount = clear_distance * index / sample_count
                cell = self.spec.cell(
                    (
                        origin[0] + direction[0] * amount,
                        origin[1] + direction[1] * amount,
                    )
                )
                if self.spec.contains(cell) and cell not in self.static_cells:
                    self._observed_at.pop(cell, None)
            if hit and minimum_hit_distance <= travel <= max_distance:
                endpoint = (
                    origin[0] + direction[0] * travel,
                    origin[1] + direction[1] * travel,
                )
                cell = self.spec.cell(endpoint)
                if self.spec.contains(cell) and cell not in self.static_cells:
                    self._observed_at[cell] = now
        changed = previous != set(self._observed_at)
        if changed:
            self.revision += 1
        return changed

    def blocked_cells(self) -> frozenset[GridCell]:
        blocked = set(self.static_cells)
        radius = self.clearance + self.observed_obstacle_radius
        cell_radius = math.ceil(radius / self.spec.resolution)
        for occupied in self._observed_at:
            for x_offset in range(-cell_radius, cell_radius + 1):
                for y_offset in range(-cell_radius, cell_radius + 1):
                    if math.hypot(x_offset, y_offset) * self.spec.resolution > radius:
                        continue
                    candidate = (occupied[0] + x_offset, occupied[1] + y_offset)
                    if self.spec.contains(candidate):
                        blocked.add(candidate)
        return frozenset(blocked)


class IncrementalAStarPlanner:
    """A* planner whose node expansion can be budgeted across control frames."""

    _DIRECTIONS = (
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    )

    def __init__(
        self,
        spec: GridSpec,
        start: Point2D,
        goal: Point2D,
        blocked_cells: frozenset[GridCell],
    ) -> None:
        self.spec = spec
        self.start = start
        self.goal = goal
        self.start_cell = spec.cell(start, clamp=True)
        self.goal_cell = spec.cell(goal, clamp=True)
        self.blocked_cells = frozenset(
            cell
            for cell in blocked_cells
            if cell not in {self.start_cell, self.goal_cell}
        )
        self.status: PlannerStatus = "planning"
        self.route: tuple[Point2D, ...] | None = None
        self.expansion_count = 0
        self._frontier: list[tuple[float, float, GridCell]] = [
            (self._heuristic(self.start_cell), 0.0, self.start_cell)
        ]
        self._came_from: dict[GridCell, GridCell | None] = {self.start_cell: None}
        self._cost = {self.start_cell: 0.0}

    def advance(self, max_expansions: int) -> PlannerStatus:
        if max_expansions < 1:
            raise ValueError("A* expansion budget must be >= 1")
        if self.status != "planning":
            return self.status
        expanded = 0
        while self._frontier and expanded < max_expansions:
            _, current_cost, current = heapq.heappop(self._frontier)
            if current_cost > self._cost[current] + 1e-12:
                continue
            expanded += 1
            self.expansion_count += 1
            if current == self.goal_cell:
                self.route = self._build_route()
                self.status = "ready"
                return self.status
            self._expand(current, current_cost)
        if not self._frontier:
            self.status = "blocked"
        return self.status

    def _expand(self, current: GridCell, current_cost: float) -> None:
        for offset_x, offset_y in self._DIRECTIONS:
            neighbor = (current[0] + offset_x, current[1] + offset_y)
            if not self.spec.contains(neighbor) or neighbor in self.blocked_cells:
                continue
            if offset_x and offset_y:
                adjacent_x = (current[0] + offset_x, current[1])
                adjacent_y = (current[0], current[1] + offset_y)
                if (
                    adjacent_x in self.blocked_cells
                    or adjacent_y in self.blocked_cells
                ):
                    continue
            step_cost = math.sqrt(2.0) if offset_x and offset_y else 1.0
            candidate_cost = current_cost + step_cost
            if candidate_cost >= self._cost.get(neighbor, math.inf):
                continue
            self._cost[neighbor] = candidate_cost
            self._came_from[neighbor] = current
            priority = candidate_cost + self._heuristic(neighbor)
            heapq.heappush(self._frontier, (priority, candidate_cost, neighbor))

    def _heuristic(self, cell: GridCell) -> float:
        return math.hypot(cell[0] - self.goal_cell[0], cell[1] - self.goal_cell[1])

    def _build_route(self) -> tuple[Point2D, ...]:
        cells: list[GridCell] = []
        current: GridCell | None = self.goal_cell
        while current is not None:
            cells.append(current)
            current = self._came_from[current]
        raw_route = [
            self.start,
            *(self.spec.point(cell) for cell in reversed(cells[1:-1])),
            self.goal,
        ]
        simplified = [raw_route[0]]
        anchor = 0
        while anchor < len(raw_route) - 1:
            candidate = len(raw_route) - 1
            while candidate > anchor + 1 and not segment_is_clear(
                raw_route[anchor],
                raw_route[candidate],
                self.spec,
                self.blocked_cells,
            ):
                candidate -= 1
            simplified.append(raw_route[candidate])
            anchor = candidate
        return tuple(simplified)


def plan_route(
    spec: GridSpec,
    start: Point2D,
    goal: Point2D,
    blocked_cells: frozenset[GridCell],
) -> tuple[Point2D, ...]:
    planner = IncrementalAStarPlanner(spec, start, goal, blocked_cells)
    while planner.advance(512) == "planning":
        pass
    if planner.route is None:
        raise ValueError("No collision-free route exists in the occupancy grid")
    return planner.route
