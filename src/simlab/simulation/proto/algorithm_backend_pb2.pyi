from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class SceneBundle(_message.Message):
    __slots__ = ("scene_json", "scene_hash")
    SCENE_JSON_FIELD_NUMBER: _ClassVar[int]
    SCENE_HASH_FIELD_NUMBER: _ClassVar[int]
    scene_json: str
    scene_hash: str
    def __init__(self, scene_json: _Optional[str] = ..., scene_hash: _Optional[str] = ...) -> None: ...

class BodyDescription(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: str
    def __init__(self, id: _Optional[str] = ...) -> None: ...

class JointDescription(_message.Message):
    __slots__ = ("id", "lower", "upper")
    ID_FIELD_NUMBER: _ClassVar[int]
    LOWER_FIELD_NUMBER: _ClassVar[int]
    UPPER_FIELD_NUMBER: _ClassVar[int]
    id: str
    lower: float
    upper: float
    def __init__(self, id: _Optional[str] = ..., lower: _Optional[float] = ..., upper: _Optional[float] = ...) -> None: ...

class ActuatorDescription(_message.Message):
    __slots__ = ("id", "joint_id", "control_type", "lower", "upper")
    ID_FIELD_NUMBER: _ClassVar[int]
    JOINT_ID_FIELD_NUMBER: _ClassVar[int]
    CONTROL_TYPE_FIELD_NUMBER: _ClassVar[int]
    LOWER_FIELD_NUMBER: _ClassVar[int]
    UPPER_FIELD_NUMBER: _ClassVar[int]
    id: str
    joint_id: str
    control_type: str
    lower: float
    upper: float
    def __init__(self, id: _Optional[str] = ..., joint_id: _Optional[str] = ..., control_type: _Optional[str] = ..., lower: _Optional[float] = ..., upper: _Optional[float] = ...) -> None: ...

class ModelDescription(_message.Message):
    __slots__ = ("backend_name", "backend_version", "timestep", "scene_hash", "schema_hash", "bodies", "joints", "actuators")
    BACKEND_NAME_FIELD_NUMBER: _ClassVar[int]
    BACKEND_VERSION_FIELD_NUMBER: _ClassVar[int]
    TIMESTEP_FIELD_NUMBER: _ClassVar[int]
    SCENE_HASH_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_HASH_FIELD_NUMBER: _ClassVar[int]
    BODIES_FIELD_NUMBER: _ClassVar[int]
    JOINTS_FIELD_NUMBER: _ClassVar[int]
    ACTUATORS_FIELD_NUMBER: _ClassVar[int]
    backend_name: str
    backend_version: str
    timestep: float
    scene_hash: str
    schema_hash: str
    bodies: _containers.RepeatedCompositeFieldContainer[BodyDescription]
    joints: _containers.RepeatedCompositeFieldContainer[JointDescription]
    actuators: _containers.RepeatedCompositeFieldContainer[ActuatorDescription]
    def __init__(self, backend_name: _Optional[str] = ..., backend_version: _Optional[str] = ..., timestep: _Optional[float] = ..., scene_hash: _Optional[str] = ..., schema_hash: _Optional[str] = ..., bodies: _Optional[_Iterable[_Union[BodyDescription, _Mapping]]] = ..., joints: _Optional[_Iterable[_Union[JointDescription, _Mapping]]] = ..., actuators: _Optional[_Iterable[_Union[ActuatorDescription, _Mapping]]] = ...) -> None: ...

class BackendState(_message.Message):
    __slots__ = ("schema_hash", "time", "step_index", "joint_positions", "joint_velocities", "actuator_controls", "actuator_forces", "body_positions", "body_quaternions")
    SCHEMA_HASH_FIELD_NUMBER: _ClassVar[int]
    TIME_FIELD_NUMBER: _ClassVar[int]
    STEP_INDEX_FIELD_NUMBER: _ClassVar[int]
    JOINT_POSITIONS_FIELD_NUMBER: _ClassVar[int]
    JOINT_VELOCITIES_FIELD_NUMBER: _ClassVar[int]
    ACTUATOR_CONTROLS_FIELD_NUMBER: _ClassVar[int]
    ACTUATOR_FORCES_FIELD_NUMBER: _ClassVar[int]
    BODY_POSITIONS_FIELD_NUMBER: _ClassVar[int]
    BODY_QUATERNIONS_FIELD_NUMBER: _ClassVar[int]
    schema_hash: str
    time: float
    step_index: int
    joint_positions: _containers.RepeatedScalarFieldContainer[float]
    joint_velocities: _containers.RepeatedScalarFieldContainer[float]
    actuator_controls: _containers.RepeatedScalarFieldContainer[float]
    actuator_forces: _containers.RepeatedScalarFieldContainer[float]
    body_positions: _containers.RepeatedScalarFieldContainer[float]
    body_quaternions: _containers.RepeatedScalarFieldContainer[float]
    def __init__(self, schema_hash: _Optional[str] = ..., time: _Optional[float] = ..., step_index: _Optional[int] = ..., joint_positions: _Optional[_Iterable[float]] = ..., joint_velocities: _Optional[_Iterable[float]] = ..., actuator_controls: _Optional[_Iterable[float]] = ..., actuator_forces: _Optional[_Iterable[float]] = ..., body_positions: _Optional[_Iterable[float]] = ..., body_quaternions: _Optional[_Iterable[float]] = ...) -> None: ...

class NamedValue(_message.Message):
    __slots__ = ("id", "value")
    ID_FIELD_NUMBER: _ClassVar[int]
    VALUE_FIELD_NUMBER: _ClassVar[int]
    id: str
    value: float
    def __init__(self, id: _Optional[str] = ..., value: _Optional[float] = ...) -> None: ...

class ResetOptions(_message.Message):
    __slots__ = ("joint_positions", "joint_velocities", "actuator_controls")
    JOINT_POSITIONS_FIELD_NUMBER: _ClassVar[int]
    JOINT_VELOCITIES_FIELD_NUMBER: _ClassVar[int]
    ACTUATOR_CONTROLS_FIELD_NUMBER: _ClassVar[int]
    joint_positions: _containers.RepeatedCompositeFieldContainer[NamedValue]
    joint_velocities: _containers.RepeatedCompositeFieldContainer[NamedValue]
    actuator_controls: _containers.RepeatedCompositeFieldContainer[NamedValue]
    def __init__(self, joint_positions: _Optional[_Iterable[_Union[NamedValue, _Mapping]]] = ..., joint_velocities: _Optional[_Iterable[_Union[NamedValue, _Mapping]]] = ..., actuator_controls: _Optional[_Iterable[_Union[NamedValue, _Mapping]]] = ...) -> None: ...

class CreateSessionRequest(_message.Message):
    __slots__ = ("contract_version", "bundle")
    CONTRACT_VERSION_FIELD_NUMBER: _ClassVar[int]
    BUNDLE_FIELD_NUMBER: _ClassVar[int]
    contract_version: str
    bundle: SceneBundle
    def __init__(self, contract_version: _Optional[str] = ..., bundle: _Optional[_Union[SceneBundle, _Mapping]] = ...) -> None: ...

class CreateSessionResponse(_message.Message):
    __slots__ = ("session_id", "description")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    DESCRIPTION_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    description: ModelDescription
    def __init__(self, session_id: _Optional[str] = ..., description: _Optional[_Union[ModelDescription, _Mapping]] = ...) -> None: ...

class ResetRequest(_message.Message):
    __slots__ = ("session_id", "seed", "options")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    SEED_FIELD_NUMBER: _ClassVar[int]
    OPTIONS_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    seed: int
    options: ResetOptions
    def __init__(self, session_id: _Optional[str] = ..., seed: _Optional[int] = ..., options: _Optional[_Union[ResetOptions, _Mapping]] = ...) -> None: ...

class StepRequest(_message.Message):
    __slots__ = ("session_id", "schema_hash", "controls", "physics_steps")
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    SCHEMA_HASH_FIELD_NUMBER: _ClassVar[int]
    CONTROLS_FIELD_NUMBER: _ClassVar[int]
    PHYSICS_STEPS_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    schema_hash: str
    controls: _containers.RepeatedScalarFieldContainer[float]
    physics_steps: int
    def __init__(self, session_id: _Optional[str] = ..., schema_hash: _Optional[str] = ..., controls: _Optional[_Iterable[float]] = ..., physics_steps: _Optional[int] = ...) -> None: ...

class StateResponse(_message.Message):
    __slots__ = ("state",)
    STATE_FIELD_NUMBER: _ClassVar[int]
    state: BackendState
    def __init__(self, state: _Optional[_Union[BackendState, _Mapping]] = ...) -> None: ...

class CloseRequest(_message.Message):
    __slots__ = ("session_id",)
    SESSION_ID_FIELD_NUMBER: _ClassVar[int]
    session_id: str
    def __init__(self, session_id: _Optional[str] = ...) -> None: ...

class CloseResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
