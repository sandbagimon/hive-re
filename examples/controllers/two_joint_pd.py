from __future__ import annotations

from simlab.controllers import JointPdConfig, JointPositionPdController
from simlab.services.controller_runtime import ControllerAction, ControllerObservation


class TwoJointPdExample:
    name = "Two Joint PD Example"

    def __init__(self) -> None:
        self.controller: JointPositionPdController | None = None

    def reset(self, observation: ControllerObservation) -> None:
        joint_ids = list(observation.joints)
        if len(joint_ids) < 2:
            raise ValueError("Two Joint PD Example requires at least two joints")
        first, second = joint_ids[:2]
        self.controller = JointPositionPdController(
            {
                first: JointPdConfig(
                    target=observation.joints[first].qpos + 0.4,
                    kp=0.2,
                    kd=0.01,
                    max_delta=0.04,
                ),
                second: JointPdConfig(
                    target=observation.joints[second].qpos - 0.4,
                    kp=0.2,
                    kd=0.01,
                    max_delta=0.04,
                ),
            },
            name=self.name,
        )
        self.controller.reset(observation)

    def step(self, observation: ControllerObservation) -> ControllerAction:
        if self.controller is None:
            raise RuntimeError("Controller reset was not called")
        return self.controller.step(observation)


def create_controller() -> TwoJointPdExample:
    return TwoJointPdExample()
