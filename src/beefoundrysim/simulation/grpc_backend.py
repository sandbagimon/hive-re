from __future__ import annotations

import argparse
import hmac
import os
import threading
import uuid
from concurrent import futures
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NoReturn, cast

try:
    import grpc
except ImportError as exc:  # pragma: no cover - depends on optional remote extra
    raise RuntimeError(
        "gRPC support is not installed. Install BeeFoundrySim with: pip install -e '.[remote]'"
    ) from exc

from beefoundrysim.simulation.backend import (
    ActuatorDescription,
    BackendSessionClosedError,
    BackendState,
    BodyDescription,
    ControlCommand,
    InvalidControlError,
    JointDescription,
    ModelDescription,
    ModelSchemaMismatchError,
    ResetOptions,
    SceneBundle,
    SimulationBackend,
    SimulationBackendError,
    SimulationBackendSession,
    validate_state_layout,
)
from beefoundrysim.simulation.mujoco_backend import MujocoBackend
from beefoundrysim.simulation.proto import algorithm_backend_pb2 as messages
from beefoundrysim.simulation.proto import algorithm_backend_pb2_grpc as services

CONTRACT_VERSION = "beefoundrysim.algorithm.v2"


@dataclass(slots=True)
class _ServerSession:
    session: SimulationBackendSession
    lock: threading.RLock = field(default_factory=threading.RLock)


class GrpcBackendServicer(services.AlgorithmSimulationBackendServicer):
    """Host engine-neutral sessions behind an atomic gRPC data plane."""

    def __init__(
        self,
        backend: SimulationBackend,
        *,
        token: str | None = None,
        asset_root: str | Path | None = None,
    ) -> None:
        self._backend = backend
        self._token = token
        self._asset_root = str(Path(asset_root).resolve()) if asset_root else None
        self._sessions: dict[str, _ServerSession] = {}
        self._sessions_lock = threading.RLock()

    def CreateSession(self, request: Any, context: grpc.ServicerContext) -> Any:
        self._authorize(context)
        if request.contract_version != CONTRACT_VERSION:
            context.abort(
                grpc.StatusCode.FAILED_PRECONDITION,
                f"Unsupported contract version: {request.contract_version}",
            )
        try:
            bundle = SceneBundle(
                scene_json=request.bundle.scene_json,
                scene_hash=request.bundle.scene_hash,
                asset_root=self._asset_root,
                export_path=None,
            )
            session = self._backend.create_session(bundle)
        except Exception as exc:
            self._abort_for_exception(context, exc)
        session_id = uuid.uuid4().hex
        with self._sessions_lock:
            self._sessions[session_id] = _ServerSession(session)
        return messages.CreateSessionResponse(
            session_id=session_id,
            description=_description_to_proto(session.model_description),
        )

    def Reset(self, request: Any, context: grpc.ServicerContext) -> Any:
        self._authorize(context)
        entry = self._entry(request.session_id, context)
        options = ResetOptions(
            joint_positions={item.id: item.value for item in request.options.joint_positions},
            joint_velocities={item.id: item.value for item in request.options.joint_velocities},
            actuator_controls={item.id: item.value for item in request.options.actuator_controls},
        )
        try:
            with entry.lock:
                state = entry.session.reset(
                    seed=request.seed if request.HasField("seed") else None,
                    options=options,
                )
        except Exception as exc:
            self._abort_for_exception(context, exc)
        return messages.StateResponse(state=_state_to_proto(state))

    def Step(self, request: Any, context: grpc.ServicerContext) -> Any:
        self._authorize(context)
        entry = self._entry(request.session_id, context)
        try:
            with entry.lock:
                state = entry.session.step(
                    ControlCommand(
                        schema_hash=request.schema_hash,
                        values=tuple(request.controls),
                    ),
                    physics_steps=request.physics_steps,
                )
        except Exception as exc:
            self._abort_for_exception(context, exc)
        return messages.StateResponse(state=_state_to_proto(state))

    def Close(self, request: Any, context: grpc.ServicerContext) -> Any:
        self._authorize(context)
        with self._sessions_lock:
            entry = self._sessions.pop(request.session_id, None)
        if entry is None:
            context.abort(grpc.StatusCode.NOT_FOUND, "Simulation session was not found")
        assert entry is not None
        with entry.lock:
            entry.session.close()
        return messages.CloseResponse()

    def close_all(self) -> None:
        with self._sessions_lock:
            entries = list(self._sessions.values())
            self._sessions.clear()
        for entry in entries:
            with entry.lock:
                entry.session.close()

    def _authorize(self, context: grpc.ServicerContext) -> None:
        if self._token is None:
            return
        metadata = dict(context.invocation_metadata())
        supplied = metadata.get("authorization", "")
        if not hmac.compare_digest(supplied, f"Bearer {self._token}"):
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid access token")

    def _entry(self, session_id: str, context: grpc.ServicerContext) -> _ServerSession:
        with self._sessions_lock:
            entry = self._sessions.get(session_id)
        if entry is None:
            context.abort(grpc.StatusCode.NOT_FOUND, "Simulation session was not found")
        assert entry is not None
        return entry

    @staticmethod
    def _abort_for_exception(context: grpc.ServicerContext, exc: Exception) -> NoReturn:
        if isinstance(exc, InvalidControlError | ValueError):
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(exc))
        if isinstance(
            exc,
            ModelSchemaMismatchError | BackendSessionClosedError,
        ):
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(exc))
        if isinstance(exc, SimulationBackendError):
            context.abort(grpc.StatusCode.FAILED_PRECONDITION, str(exc))
        context.abort(grpc.StatusCode.INTERNAL, "Simulation backend failed")
        raise AssertionError("gRPC context.abort returned unexpectedly")


class GrpcSimulationBackend:
    """Remote backend factory with the same interface as ``MujocoBackend``."""

    def __init__(
        self,
        target: str,
        *,
        token: str | None = None,
        timeout: float = 10.0,
        channel: grpc.Channel | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("gRPC timeout must be > 0")
        self.target = target
        self.timeout = float(timeout)
        self._metadata = (("authorization", f"Bearer {token}"),) if token is not None else None
        self._owns_channel = channel is None
        self._channel = channel or grpc.insecure_channel(target)
        self._stub = services.AlgorithmSimulationBackendStub(self._channel)

    def create_session(self, bundle: SceneBundle) -> GrpcSimulationBackendSession:
        proto_bundle = messages.SceneBundle(
            scene_json=bundle.scene_json,
            scene_hash=bundle.scene_hash,
        )
        response = self._call(
            self._stub.CreateSession,
            messages.CreateSessionRequest(
                contract_version=CONTRACT_VERSION,
                bundle=proto_bundle,
            ),
        )
        return GrpcSimulationBackendSession(
            stub=self._stub,
            session_id=response.session_id,
            description=_description_from_proto(response.description),
            metadata=self._metadata,
            timeout=self.timeout,
        )

    def close(self) -> None:
        if self._owns_channel:
            self._channel.close()

    def _call(self, method: Any, request: Any) -> Any:
        try:
            return method(request, timeout=self.timeout, metadata=self._metadata)
        except grpc.RpcError as exc:
            raise _translate_rpc_error(exc) from exc


class GrpcSimulationBackendSession:
    def __init__(
        self,
        *,
        stub: Any,
        session_id: str,
        description: ModelDescription,
        metadata: tuple[tuple[str, str], ...] | None,
        timeout: float,
    ) -> None:
        self._stub = stub
        self._session_id = session_id
        self._description = description
        self._metadata = metadata
        self._timeout = timeout
        self._closed = False

    @property
    def model_description(self) -> ModelDescription:
        return self._description

    def reset(
        self,
        *,
        seed: int | None = None,
        options: ResetOptions | None = None,
    ) -> BackendState:
        self._require_open()
        options = options or ResetOptions()
        request = messages.ResetRequest(
            session_id=self._session_id,
            options=messages.ResetOptions(
                joint_positions=_named_values(options.joint_positions),
                joint_velocities=_named_values(options.joint_velocities),
                actuator_controls=_named_values(options.actuator_controls),
            ),
        )
        if seed is not None:
            request.seed = seed
        response = self._call(self._stub.Reset, request)
        return _state_from_proto(response.state, self._description)

    def step(self, command: ControlCommand, *, physics_steps: int = 1) -> BackendState:
        self._require_open()
        response = self._call(
            self._stub.Step,
            messages.StepRequest(
                session_id=self._session_id,
                schema_hash=command.schema_hash,
                controls=command.values,
                physics_steps=physics_steps,
            ),
        )
        return _state_from_proto(response.state, self._description)

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._call(
                self._stub.Close,
                messages.CloseRequest(session_id=self._session_id),
            )
        finally:
            self._closed = True

    def _require_open(self) -> None:
        if self._closed:
            raise BackendSessionClosedError("Simulation session is closed")

    def _call(self, method: Any, request: Any) -> Any:
        try:
            return method(request, timeout=self._timeout, metadata=self._metadata)
        except grpc.RpcError as exc:
            raise _translate_rpc_error(exc) from exc


def create_grpc_server(
    bind: str,
    *,
    backend: SimulationBackend | None = None,
    token: str | None = None,
    asset_root: str | Path | None = None,
    max_workers: int = 8,
) -> tuple[grpc.Server, int, GrpcBackendServicer]:
    if max_workers < 1:
        raise ValueError("max_workers must be >= 1")
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    servicer = GrpcBackendServicer(backend or MujocoBackend(), token=token, asset_root=asset_root)
    services.add_AlgorithmSimulationBackendServicer_to_server(servicer, server)
    port = server.add_insecure_port(bind)
    if port == 0:
        raise RuntimeError(f"Could not bind gRPC algorithm server to {bind}")
    return server, port, servicer


def serve_grpc_backend(
    bind: str = "127.0.0.1:50051",
    *,
    token: str | None = None,
    asset_root: str | Path | None = None,
    max_workers: int = 8,
) -> None:
    server, port, servicer = create_grpc_server(
        bind, token=token, asset_root=asset_root, max_workers=max_workers
    )
    server.start()
    print(f"BeeFoundrySim algorithm gRPC server listening on {bind} (port {port})")
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(grace=2.0)
    finally:
        servicer.close_all()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the BeeFoundrySim algorithm gRPC backend")
    parser.add_argument("--bind", default="127.0.0.1:50051")
    parser.add_argument("--token", default=os.environ.get("BEEFOUNDRYSIM_ALGORITHM_TOKEN"))
    parser.add_argument("--asset-root", default=None)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args(argv)
    serve_grpc_backend(
        args.bind,
        token=args.token,
        asset_root=args.asset_root,
        max_workers=args.workers,
    )
    return 0


def _description_to_proto(description: ModelDescription) -> Any:
    joints = []
    for item in description.joints:
        joint = messages.JointDescription(id=item.id)
        if item.lower is not None:
            joint.lower = item.lower
        if item.upper is not None:
            joint.upper = item.upper
        joints.append(joint)
    return messages.ModelDescription(
        backend_name=description.backend_name,
        backend_version=description.backend_version,
        timestep=description.timestep,
        scene_hash=description.scene_hash,
        schema_hash=description.schema_hash,
        bodies=[messages.BodyDescription(id=item.id) for item in description.bodies],
        joints=joints,
        actuators=[
            messages.ActuatorDescription(
                id=item.id,
                joint_id=item.joint_id,
                control_type=item.control_type,
                lower=item.lower,
                upper=item.upper,
            )
            for item in description.actuators
        ],
    )


def _description_from_proto(description: Any) -> ModelDescription:
    return ModelDescription(
        backend_name=description.backend_name,
        backend_version=description.backend_version,
        timestep=description.timestep,
        scene_hash=description.scene_hash,
        schema_hash=description.schema_hash,
        bodies=tuple(BodyDescription(id=item.id) for item in description.bodies),
        joints=tuple(
            JointDescription(
                id=item.id,
                lower=item.lower if item.HasField("lower") else None,
                upper=item.upper if item.HasField("upper") else None,
            )
            for item in description.joints
        ),
        actuators=tuple(
            ActuatorDescription(
                id=item.id,
                joint_id=item.joint_id,
                control_type=item.control_type,
                lower=item.lower,
                upper=item.upper,
            )
            for item in description.actuators
        ),
    )


def _state_to_proto(state: BackendState) -> Any:
    return messages.BackendState(
        schema_hash=state.schema_hash,
        time=state.time,
        step_index=state.step_index,
        joint_positions=state.joint_positions,
        joint_velocities=state.joint_velocities,
        actuator_controls=state.actuator_controls,
        actuator_forces=state.actuator_forces,
        body_positions=[value for item in state.body_positions for value in item],
        body_quaternions=[value for item in state.body_quaternions for value in item],
        body_linear_velocities=[
            value for item in state.body_linear_velocities for value in item
        ],
        body_angular_velocities=[
            value for item in state.body_angular_velocities for value in item
        ],
    )


def _state_from_proto(state: Any, description: ModelDescription) -> BackendState:
    expected_bodies = len(description.bodies)
    if len(state.body_positions) != expected_bodies * 3:
        raise SimulationBackendError("Remote backend returned invalid body position layout")
    if len(state.body_quaternions) != expected_bodies * 4:
        raise SimulationBackendError("Remote backend returned invalid body quaternion layout")
    if len(state.body_linear_velocities) != expected_bodies * 3:
        raise SimulationBackendError(
            "Remote backend returned invalid body linear velocity layout"
        )
    if len(state.body_angular_velocities) != expected_bodies * 3:
        raise SimulationBackendError(
            "Remote backend returned invalid body angular velocity layout"
        )
    return validate_state_layout(
        description,
        BackendState(
            schema_hash=state.schema_hash,
            time=state.time,
            step_index=state.step_index,
            joint_positions=tuple(state.joint_positions),
            joint_velocities=tuple(state.joint_velocities),
            actuator_controls=tuple(state.actuator_controls),
            actuator_forces=tuple(state.actuator_forces),
            body_positions=tuple(
                cast(
                    tuple[float, float, float],
                    tuple(state.body_positions[index : index + 3]),
                )
                for index in range(0, expected_bodies * 3, 3)
            ),
            body_quaternions=tuple(
                cast(
                    tuple[float, float, float, float],
                    tuple(state.body_quaternions[index : index + 4]),
                )
                for index in range(0, expected_bodies * 4, 4)
            ),
            body_linear_velocities=tuple(
                cast(
                    tuple[float, float, float],
                    tuple(state.body_linear_velocities[index : index + 3]),
                )
                for index in range(0, expected_bodies * 3, 3)
            ),
            body_angular_velocities=tuple(
                cast(
                    tuple[float, float, float],
                    tuple(state.body_angular_velocities[index : index + 3]),
                )
                for index in range(0, expected_bodies * 3, 3)
            ),
        ),
    )


def _named_values(values: Any) -> list[Any]:
    return [messages.NamedValue(id=identifier, value=value) for identifier, value in values.items()]


def _translate_rpc_error(exc: grpc.RpcError) -> SimulationBackendError:
    code = exc.code()
    details = exc.details() or "Remote simulation request failed"
    if code == grpc.StatusCode.INVALID_ARGUMENT:
        return InvalidControlError(details)
    if code == grpc.StatusCode.FAILED_PRECONDITION and "schema" in details.lower():
        return ModelSchemaMismatchError(details)
    return SimulationBackendError(f"gRPC {code.name}: {details}")


if __name__ == "__main__":
    raise SystemExit(main())
