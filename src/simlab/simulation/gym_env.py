from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from simlab.simulation.backend import (
    BackendState,
    ResetOptions,
    SceneBundle,
    SimulationBackend,
    SimulationBackendSession,
)
from simlab.simulation.task import BoundEnvironmentTask, EnvironmentTask

try:  # Gymnasium is an optional algorithm integration dependency.
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:  # pragma: no cover - exercised by projects without algorithm extras
    gym = None  # type: ignore[assignment]
    spaces = None  # type: ignore[assignment]


_GymBase = gym.Env if gym is not None else object


class SimLabEnv(_GymBase):  # type: ignore[misc,valid-type]
    """Gymnasium adapter over the engine-neutral atomic simulation contract."""

    metadata = {"render_modes": ["state"], "render_fps": 0}

    def __init__(
        self,
        *,
        backend: SimulationBackend,
        scene_bundle: SceneBundle,
        task: EnvironmentTask,
        frame_skip: int = 1,
        render_mode: str | None = None,
    ) -> None:
        if gym is None or spaces is None:
            raise RuntimeError(
                "Gymnasium is not installed. Install SimLab with: pip install -e '.[algorithm]'"
            )
        if isinstance(frame_skip, bool) or frame_skip < 1:
            raise ValueError("frame_skip must be an integer >= 1")
        if render_mode not in {None, "state"}:
            raise ValueError("SimLabEnv render_mode must be None or 'state'")
        self._session: SimulationBackendSession | None = backend.create_session(scene_bundle)
        self._task: BoundEnvironmentTask = task.bind(self._session.model_description)
        self._frame_skip = int(frame_skip)
        self.render_mode = render_mode
        self._episode_step = 0
        self._state: BackendState | None = None
        action = self._task.action_spec
        observation = self._task.observation_spec
        self.action_space = spaces.Box(
            low=np.asarray(action.minimum, dtype=action.dtype).reshape(action.shape),
            high=np.asarray(action.maximum, dtype=action.dtype).reshape(action.shape),
            shape=action.shape,
            dtype=np.float32,
        )
        self.observation_space = spaces.Box(
            low=np.asarray(observation.minimum, dtype=observation.dtype).reshape(observation.shape),
            high=np.asarray(observation.maximum, dtype=observation.dtype).reshape(
                observation.shape
            ),
            shape=observation.shape,
            dtype=np.float32,
        )
        self.metadata = {
            **type(self).metadata,
            "render_fps": round(
                1.0 / (self._session.model_description.timestep * self._frame_skip)
            ),
        }

    @property
    def model_description(self):
        return self._require_session().model_description

    def reset(
        self,
        *,
        seed: int | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        self._episode_step = 0
        self._state = self._require_session().reset(
            seed=seed,
            options=ResetOptions.from_mapping(options),
        )
        observation, info = self._task.reset(self._state, self.np_random)
        return observation, dict(info)

    def step(self, action: object) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        if self._state is None:
            raise RuntimeError("Call reset() before step()")
        command = self._task.command(action, self._state)
        self._state = self._require_session().step(
            command,
            physics_steps=self._frame_skip,
        )
        self._episode_step += 1
        result = self._task.evaluate(self._state, episode_step=self._episode_step)
        return (
            result.observation,
            float(result.reward),
            bool(result.terminated),
            bool(result.truncated),
            dict(result.info),
        )

    def render(self) -> BackendState | None:
        return self._state if self.render_mode == "state" else None

    def close(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None
        self._state = None

    def _require_session(self) -> SimulationBackendSession:
        if self._session is None:
            raise RuntimeError("SimLabEnv is closed")
        return self._session
