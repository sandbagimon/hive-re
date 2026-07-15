from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from simlab.models.robotics import (
    Actuator,
    Articulation,
    Collider,
    ControlType,
    GeometryType,
    Inertial,
    Joint,
    JointLimits,
    JointType,
    Link,
    RigidTransform,
    RoboticsModel,
    VisualGeometry,
)
from simlab.services.openusd.import_report import ImportReport
from simlab.services.openusd.stage_loader import OpenUsdStageError, load_openusd_stage
from simlab.services.robotics_validation import (
    RoboticsValidationError,
    validate_robotics_model,
)


class OpenUsdArticulationError(RuntimeError):
    """Raised when a USD stage cannot be mapped to the robotics model."""

    def __init__(self, report: ImportReport) -> None:
        self.report = report
        message = next(
            (issue.message for issue in report.issues if issue.severity == "error"),
            "OpenUSD articulation import failed",
        )
        super().__init__(message)


@dataclass(slots=True)
class ArticulationImportResult:
    model: RoboticsModel
    report: ImportReport


def _stable_id(kind: str, prim_path: Any) -> str:
    digest = hashlib.sha256(f"{kind}:{prim_path}".encode()).hexdigest()[:12]
    return f"{kind}_{digest}"


def _display_name(prim: Any) -> str:
    return str(prim.GetDisplayName() or prim.GetName())


def _vector3(value: Any) -> list[float]:
    return [float(value[0]), float(value[1]), float(value[2])]


def _quaternion(value: Any) -> list[float]:
    imaginary = value.GetImaginary()
    return [
        float(imaginary[0]),
        float(imaginary[1]),
        float(imaginary[2]),
        float(value.GetReal()),
    ]


def _quaternion_multiply(left: list[float], right: list[float]) -> list[float]:
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    return [
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
        lw * rw - lx * rx - ly * ry - lz * rz,
    ]


def _to_z_up_vector(value: list[float], up_axis: str) -> list[float]:
    if up_axis == "Y":
        return [value[0], -value[2], value[1]]
    return value


def _to_z_up_quaternion(value: list[float], up_axis: str) -> list[float]:
    if up_axis != "Y":
        return value
    half_angle = math.pi / 4.0
    basis = [math.sin(half_angle), 0.0, 0.0, math.cos(half_angle)]
    basis_inverse = [-basis[0], -basis[1], -basis[2], basis[3]]
    return _quaternion_multiply(
        _quaternion_multiply(basis, value), basis_inverse
    )


def _rigid_transform(
    matrix: Any,
    gf: Any,
    up_axis: str,
    meters_per_unit: float,
) -> tuple[RigidTransform, list[float]]:
    transform = gf.Transform(matrix)
    position = [component * meters_per_unit for component in _vector3(transform.GetTranslation())]
    rotation = _quaternion(transform.GetRotation().GetQuat())
    scale = [abs(component) for component in _vector3(transform.GetScale())]
    return (
        RigidTransform(
            position=_to_z_up_vector(position, up_axis),
            quaternion=_to_z_up_quaternion(rotation, up_axis),
        ),
        scale,
    )


def _relative_matrix(child_world: Any, parent_world: Any | None) -> Any:
    return child_world if parent_world is None else child_world * parent_world.GetInverse()


def _body_target(joint: Any, relation_name: str) -> str | None:
    relation = getattr(joint, f"Get{relation_name}Rel")()
    targets = relation.GetTargets()
    return str(targets[0]) if targets else None


def _nearest_rigid_body_path(prim: Any, rigid_body_paths: set[str]) -> str | None:
    path = prim.GetPath().GetParentPath()
    while not path.IsAbsoluteRootPath():
        path_text = str(path)
        if path_text in rigid_body_paths:
            return path_text
        path = path.GetParentPath()
    return None


def _geometry_size(
    prim: Any, usd_geom: Any, scale: list[float]
) -> tuple[GeometryType, list[float]]:
    if prim.IsA(usd_geom.Cube):
        side = float(usd_geom.Cube(prim).GetSizeAttr().Get() or 2.0)
        return "box", [side * scale[index] * 0.5 for index in range(3)]
    if prim.IsA(usd_geom.Sphere):
        radius = float(usd_geom.Sphere(prim).GetRadiusAttr().Get() or 1.0)
        if math.isclose(scale[0], scale[1]) and math.isclose(scale[1], scale[2]):
            return "sphere", [radius * scale[0]]
        return "ellipsoid", [radius * component for component in scale]
    if prim.IsA(usd_geom.Cylinder):
        cylinder = usd_geom.Cylinder(prim)
        radius = float(cylinder.GetRadiusAttr().Get() or 1.0)
        half_height = float(cylinder.GetHeightAttr().Get() or 2.0) * 0.5
        return "cylinder", [radius * scale[0], half_height * scale[2]]
    if prim.IsA(usd_geom.Capsule):
        capsule = usd_geom.Capsule(prim)
        radius = float(capsule.GetRadiusAttr().Get() or 1.0)
        half_height = float(capsule.GetHeightAttr().Get() or 2.0) * 0.5
        return "capsule", [radius * scale[0], half_height * scale[2]]
    return "mesh", [1.0, 1.0, 1.0]


def _display_color(prim: Any, usd_geom: Any) -> list[float]:
    gprim = usd_geom.Gprim(prim)
    colors = gprim.GetDisplayColorAttr().Get() or []
    if not colors:
        return [0.7, 0.7, 0.7, 1.0]
    return [float(colors[0][0]), float(colors[0][1]), float(colors[0][2]), 1.0]


def _is_visible(prim: Any, usd_geom: Any) -> bool:
    imageable = usd_geom.Imageable(prim)
    return imageable.ComputeVisibility() != usd_geom.Tokens.invisible


def _inertial(
    prim: Any,
    usd_physics: Any,
    report: ImportReport,
    up_axis: str,
    meters_per_unit: float,
) -> Inertial:
    mass_api = usd_physics.MassAPI(prim)
    mass_value = mass_api.GetMassAttr().Get()
    mass = float(mass_value) if mass_value is not None and float(mass_value) > 0 else 1.0
    if mass_value is None or float(mass_value) <= 0:
        report.add(
            "warning",
            "usd.mass_defaulted",
            "Rigid body has no positive authored mass; defaulted to 1 kg.",
            prim_path=str(prim.GetPath()),
            field="physics:mass",
            fallback="mass=1.0",
        )
    center_value = mass_api.GetCenterOfMassAttr().Get()
    center = _vector3(center_value) if center_value is not None else [0.0, 0.0, 0.0]
    center = _to_z_up_vector(
        [component * meters_per_unit for component in center], up_axis
    )
    diagonal_value = mass_api.GetDiagonalInertiaAttr().Get()
    diagonal = _vector3(diagonal_value) if diagonal_value is not None else None
    if diagonal is not None and not all(value > 0 for value in diagonal):
        diagonal = None
        report.add(
            "warning",
            "usd.inertia_defaulted",
            "Non-positive diagonal inertia was omitted for engine-side inference.",
            prim_path=str(prim.GetPath()),
            field="physics:diagonalInertia",
            fallback="infer from colliders and mass",
        )
    elif diagonal is not None:
        inertia_scale = meters_per_unit * meters_per_unit
        diagonal = [component * inertia_scale for component in diagonal]
        if up_axis == "Y":
            diagonal = [diagonal[0], diagonal[2], diagonal[1]]
    return Inertial(
        mass=mass,
        center_of_mass=center,
        diagonal_inertia=diagonal,
        full_inertia=None,
    )


def _joint_axis(joint: Any, up_axis: str) -> list[float]:
    token = str(joint.GetAxisAttr().Get() or "X").upper()
    source = {
        "X": [1.0, 0.0, 0.0],
        "Y": [0.0, 1.0, 0.0],
        "Z": [0.0, 0.0, 1.0],
    }.get(token, [1.0, 0.0, 0.0])
    return _to_z_up_vector(source, up_axis)


def _joint_origin(
    joint: Any,
    up_axis: str,
    meters_per_unit: float,
) -> RigidTransform:
    position_value = joint.GetLocalPos0Attr().Get()
    rotation_value = joint.GetLocalRot0Attr().Get()
    position = _vector3(position_value) if position_value is not None else [0.0, 0.0, 0.0]
    position = [component * meters_per_unit for component in position]
    quaternion = (
        _quaternion(rotation_value)
        if rotation_value is not None
        else [0.0, 0.0, 0.0, 1.0]
    )
    return RigidTransform(
        position=_to_z_up_vector(position, up_axis),
        quaternion=_to_z_up_quaternion(quaternion, up_axis),
    )


def _joint_limits(joint: Any) -> JointLimits | None:
    lower = joint.GetLowerLimitAttr().Get()
    upper = joint.GetUpperLimitAttr().Get()
    if lower is None and upper is None:
        return None
    return JointLimits(
        lower=math.radians(float(lower)) if lower is not None else None,
        upper=math.radians(float(upper)) if upper is not None else None,
    )


def _drive_actuator(
    prim: Any,
    joint_model: Joint,
    usd_physics: Any,
) -> Actuator | None:
    drive = usd_physics.DriveAPI.Get(prim, "angular")
    if not drive or not drive.GetPrim().IsValid():
        return None
    stiffness = float(drive.GetStiffnessAttr().Get() or 0.0)
    damping = float(drive.GetDampingAttr().Get() or 0.0)
    target_position = drive.GetTargetPositionAttr().Get()
    target_velocity = drive.GetTargetVelocityAttr().Get()
    if target_position is not None or stiffness > 0:
        control_type: ControlType = "position"
    elif target_velocity is not None or damping > 0:
        control_type = "velocity"
    else:
        control_type = "motor"
    if (
        joint_model.limits
        and joint_model.limits.lower is not None
        and joint_model.limits.upper is not None
    ):
        control_range = [joint_model.limits.lower, joint_model.limits.upper]
    else:
        control_range = [-math.pi, math.pi]
    max_force_value = drive.GetMaxForceAttr().Get()
    max_force = (
        float(max_force_value)
        if max_force_value is not None and math.isfinite(float(max_force_value))
        else None
    )
    return Actuator(
        id=_stable_id("actuator", prim.GetPath()),
        name=f"{_display_name(prim)} Drive",
        joint_id=joint_model.id,
        control_type=control_type,
        control_range=control_range,
        stiffness=stiffness,
        damping=damping,
        max_force=max_force,
        source_prim_path=f"{prim.GetPath()}.drive:angular",
    )


def _import_articulation(
    stage: Any,
    root_prim: Any,
    source_path: Path,
    report: ImportReport,
    gf: Any,
    usd_geom: Any,
    usd_physics: Any,
) -> Articulation:
    meters_per_unit = float(usd_geom.GetStageMetersPerUnit(stage) or 1.0)
    up_axis = str(usd_geom.GetStageUpAxis(stage)).upper()
    root_path = root_prim.GetPath()
    subtree = [prim for prim in stage.Traverse() if prim.GetPath().HasPrefix(root_path)]
    rigid_prims = [
        prim for prim in subtree if "PhysicsRigidBodyAPI" in prim.GetAppliedSchemas()
    ]
    if not rigid_prims:
        report.add(
            "error",
            "usd.articulation_without_links",
            "Articulation root contains no UsdPhysics rigid bodies.",
            prim_path=str(root_path),
            field="apiSchemas",
        )
        raise OpenUsdArticulationError(report)

    xform_cache = usd_geom.XformCache()
    prim_by_path = {str(prim.GetPath()): prim for prim in rigid_prims}
    link_id_by_path = {
        path: _stable_id("link", prim.GetPath()) for path, prim in prim_by_path.items()
    }
    parent_path_by_child: dict[str, str] = {}
    fixed_world_targets: set[str] = set()
    joint_prims: list[Any] = []
    for prim in subtree:
        if not prim.IsA(usd_physics.Joint):
            continue
        joint_prims.append(prim)
        joint_schema = usd_physics.Joint(prim)
        body0 = _body_target(joint_schema, "Body0")
        body1 = _body_target(joint_schema, "Body1")
        if body1 in prim_by_path and body0 in prim_by_path:
            parent_path_by_child[body1] = body0
        elif body1 in prim_by_path and body0 is None and prim.IsA(usd_physics.FixedJoint):
            fixed_world_targets.add(body1)

    root_candidates = [path for path in prim_by_path if path not in parent_path_by_child]
    root_link_path = next(
        (path for path in root_candidates if path in fixed_world_targets),
        root_candidates[0] if root_candidates else next(iter(prim_by_path)),
    )

    links: list[Link] = []
    links_by_path: dict[str, Link] = {}
    rigid_paths = set(prim_by_path)
    geometry_by_link: dict[str, list[Any]] = {path: [] for path in rigid_paths}
    for prim in subtree:
        if not prim.IsA(usd_geom.Gprim):
            continue
        body_path = _nearest_rigid_body_path(prim, rigid_paths)
        if body_path is not None:
            geometry_by_link[body_path].append(prim)

    for path, prim in prim_by_path.items():
        parent_path = parent_path_by_child.get(path)
        world = xform_cache.GetLocalToWorldTransform(prim)
        parent_world = (
            xform_cache.GetLocalToWorldTransform(prim_by_path[parent_path])
            if parent_path is not None
            else None
        )
        link_transform, body_scale = _rigid_transform(
            _relative_matrix(world, parent_world), gf, up_axis, meters_per_unit
        )
        if any(not math.isclose(value, 1.0, abs_tol=1e-6) for value in body_scale):
            report.add(
                "warning",
                "usd.rigid_body_scale_ignored",
                "Rigid body scale is not supported and was omitted from the link transform.",
                prim_path=path,
                field="xformOp:scale",
                fallback="bake scale into child geometry",
            )
        link = Link(
            id=link_id_by_path[path],
            name=_display_name(prim),
            parent_link_id=(
                link_id_by_path[parent_path] if parent_path is not None else None
            ),
            transform=link_transform,
            inertial=_inertial(
                prim, usd_physics, report, up_axis, meters_per_unit
            ),
            source_prim_path=path,
        )
        for geometry_prim in geometry_by_link[path]:
            geometry_world = xform_cache.GetLocalToWorldTransform(geometry_prim)
            geometry_transform, geometry_scale = _rigid_transform(
                _relative_matrix(geometry_world, world), gf, up_axis, meters_per_unit
            )
            geometry_type, size = _geometry_size(geometry_prim, usd_geom, geometry_scale)
            size = [component * meters_per_unit for component in size]
            is_collider = "PhysicsCollisionAPI" in geometry_prim.GetAppliedSchemas()
            if is_collider:
                link.colliders.append(
                    Collider(
                        id=_stable_id("collider", geometry_prim.GetPath()),
                        name=_display_name(geometry_prim),
                        geometry_type=geometry_type,
                        transform=geometry_transform,
                        size=size,
                        asset_uri=(str(source_path) if geometry_type == "mesh" else None),
                        source_prim_path=str(geometry_prim.GetPath()),
                    )
                )
            if _is_visible(geometry_prim, usd_geom):
                link.visual_geometries.append(
                    VisualGeometry(
                        id=_stable_id("visual", geometry_prim.GetPath()),
                        name=_display_name(geometry_prim),
                        geometry_type=geometry_type,
                        transform=geometry_transform,
                        size=size,
                        asset_uri=(str(source_path) if geometry_type == "mesh" else None),
                        source_prim_path=str(geometry_prim.GetPath()),
                        rgba=_display_color(geometry_prim, usd_geom),
                    )
                )
        links.append(link)
        links_by_path[path] = link

    joints: list[Joint] = []
    actuators: list[Actuator] = []
    for prim in joint_prims:
        joint_schema = usd_physics.Joint(prim)
        body0 = _body_target(joint_schema, "Body0")
        body1 = _body_target(joint_schema, "Body1")
        if body0 is None and body1 in fixed_world_targets:
            continue
        if body0 not in link_id_by_path or body1 not in link_id_by_path:
            report.add(
                "warning",
                "usd.joint_body_unresolved",
                "Joint was skipped because its body relationship is outside the articulation.",
                prim_path=str(prim.GetPath()),
                field="physics:body0/physics:body1",
                fallback="joint omitted",
            )
            continue
        assert body0 is not None and body1 is not None
        if prim.IsA(usd_physics.RevoluteJoint):
            typed_joint = usd_physics.RevoluteJoint(prim)
            joint_type: JointType = "revolute"
            limits = _joint_limits(typed_joint)
            axis = _joint_axis(typed_joint, up_axis)
        elif prim.IsA(usd_physics.FixedJoint):
            typed_joint = usd_physics.FixedJoint(prim)
            joint_type = "fixed"
            limits = None
            axis = [0.0, 0.0, 0.0]
        else:
            report.add(
                "warning",
                "usd.joint_type_unsupported",
                f"Unsupported joint type was omitted: {prim.GetTypeName()}",
                prim_path=str(prim.GetPath()),
                field="typeName",
                fallback="joint omitted",
            )
            continue
        drive = usd_physics.DriveAPI.Get(prim, "angular")
        target = drive.GetTargetPositionAttr().Get() if drive else None
        initial_position = math.radians(float(target)) if target is not None else 0.0
        joint_model = Joint(
            id=_stable_id("joint", prim.GetPath()),
            name=_display_name(prim),
            type=joint_type,
            parent_link_id=link_id_by_path[body0],
            child_link_id=link_id_by_path[body1],
            origin=_joint_origin(typed_joint, up_axis, meters_per_unit),
            axis=axis,
            limits=limits,
            initial_position=initial_position,
            source_prim_path=str(prim.GetPath()),
        )
        joints.append(joint_model)
        actuator = _drive_actuator(prim, joint_model, usd_physics)
        if actuator is not None:
            actuators.append(actuator)

    return Articulation(
        id=_stable_id("articulation", root_path),
        name=_display_name(root_prim),
        root_link_id=link_id_by_path[root_link_path],
        fixed_base=root_link_path in fixed_world_targets,
        links=links,
        joints=joints,
        actuators=actuators,
        source_uri=str(source_path),
        source_prim_path=str(root_path),
    )


def import_openusd_articulations(source: str | Path) -> ArticulationImportResult:
    """Map supported USD Physics articulations into the shared robotics model."""
    source_path = Path(source).expanduser().resolve()
    try:
        stage_result = load_openusd_stage(source_path)
    except OpenUsdStageError as exc:
        raise OpenUsdArticulationError(exc.report) from exc
    report = stage_result.report
    if report.has_errors:
        raise OpenUsdArticulationError(report)

    try:
        from pxr import Gf, UsdGeom, UsdPhysics
    except ImportError:
        report.add(
            "error",
            "usd.bindings_unavailable",
            "OpenUSD Python bindings are unavailable. Install the 'usd-core' package.",
            field="runtime",
        )
        raise OpenUsdArticulationError(report) from None

    roots = [
        prim
        for prim in stage_result.stage.Traverse()
        if "PhysicsArticulationRootAPI" in prim.GetAppliedSchemas()
    ]
    if not roots:
        report.add(
            "error",
            "usd.articulation_missing",
            "The OpenUSD stage contains no UsdPhysics articulation root.",
            field="apiSchemas",
        )
        raise OpenUsdArticulationError(report)

    articulations = [
        _import_articulation(
            stage_result.stage,
            root,
            source_path,
            report,
            Gf,
            UsdGeom,
            UsdPhysics,
        )
        for root in roots
    ]
    model = RoboticsModel(articulations=articulations)
    try:
        validate_robotics_model(model)
    except RoboticsValidationError as exc:
        for issue in exc.issues:
            report.add(
                "error",
                f"robotics.{issue.code}",
                issue.message,
                field=issue.path,
            )
        raise OpenUsdArticulationError(report) from exc
    return ArticulationImportResult(model=model, report=report)
