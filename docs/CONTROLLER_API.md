# Python Controller API

SimLab controllers receive an immutable snapshot before every MuJoCo physics step and may return
joint position targets. They never receive mutable `MjModel` or `MjData` objects.

```python
from simlab.services.controller_runtime import (
    ControllerAction,
    ControllerObservation,
)


class ReachController:
    def reset(self, observation: ControllerObservation) -> None:
        self.started_at = observation.time

    def step(self, observation: ControllerObservation) -> ControllerAction:
        shoulder = observation.joints["joint_shoulder"]
        target = min(0.6, shoulder.qpos + 0.01)
        return ControllerAction({"joint_shoulder": target})


session.attach_controller(ReachController(), name="Reach")
state = session.step(steps=100)
session.detach_controller()
```

`ControllerObservation` contains simulation `time`, fixed `timestep`, joint `qpos/qvel`, and actuator
`ctrl/force`, all keyed by stable Scene robotics IDs. `ControllerAction` currently supports position
targets; Session applies the same actuator mapping and control-range clamping used by UI joint commands.

For a reusable bounded outer loop, import `JointPdConfig` and `JointPositionPdController` from
`simlab.controllers`. It computes a qpos/qvel correction, limits each per-step position-target delta, and
leaves force generation to the MuJoCo position actuator. Runtime goals can be changed with `set_target()`
or atomic `set_targets()`. See [`examples/controllers/two_joint_pd.py`](../examples/controllers/two_joint_pd.py)
for a project-loadable example that configures the first two observed joints relative to Home without
hard-coded USD Prim names.

Controller lifecycle:

- `attach_controller()` calls `reset()` once at the current simulation state.
- `step()` runs before each `mj_step`.
- Session `reset()` invokes `reset()` again for a healthy attached controller.
- Exceptions, invalid actions, and configured deadline overruns set controller status to `fault` and
  disable later callbacks. Physics stepping continues.
- `detach_controller()` is required before manual joint commands or trajectory playback.

Set `simulation_config.controller_deadline` to a positive number of seconds to enforce a per-call
deadline. This is elapsed-time detection, not thread preemption: an overrun is detected after the user
callback returns, its action is discarded, and later callbacks are disabled.

Project controller files define a no-argument factory:

```python
def create_controller():
    return ReachController()
```

`ProjectControllerLoader` only accepts `.py` files whose resolved path is inside the project root. Loading
is always explicit, recompiles the source for reload, and reports path validation, import, factory, or
contract validation as distinct phases. Scene Open never executes controller code. The Python Bridge
provides `loadController`, `loadControllerPath`, and `detachController`. The robot Inspector Controller
section exposes explicit Load, Reload, and Detach controls; Load and Reload require trusted-code confirmation.

Controller modules are trusted in-process Python code with the same filesystem permissions as SimLab. The
project-root check prevents accidental selection outside the project, but it is not a security sandbox.
