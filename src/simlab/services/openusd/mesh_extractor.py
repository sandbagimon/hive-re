from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MeshData:
    positions: list[float] = field(default_factory=list)
    indices: list[int] = field(default_factory=list)
    colors: list[float] = field(default_factory=list)
    uvs: list[float] = field(default_factory=list)
    source_prim_paths: list[str] = field(default_factory=list)

    @property
    def vertex_count(self) -> int:
        return len(self.positions) // 3

    @property
    def triangle_count(self) -> int:
        return len(self.indices) // 3


@dataclass(frozen=True, slots=True)
class StageMeshExtraction:
    visual: MeshData
    collision: MeshData
    up_axis: str
    meters_per_unit: float
    used_dedicated_collision: bool
    point_instance_count: int
    native_primitive_count: int
    base_color_texture: str | None


@dataclass(frozen=True, slots=True)
class _GeometryInstance:
    prim: Any
    matrix: Any
    visible: bool
    collision: bool


def extract_stage_meshes(stage: Any, warnings: list[str]) -> StageMeshExtraction:
    try:
        from pxr import Gf, Usd, UsdGeom, UsdShade
    except ImportError as exc:
        raise RuntimeError(
            "OpenUSD Python bindings are unavailable. Install the 'usd-core' package."
        ) from exc

    meters_per_unit = float(UsdGeom.GetStageMetersPerUnit(stage) or 1.0)
    up_axis = str(UsdGeom.GetStageUpAxis(stage)).upper()
    if up_axis not in {"Y", "Z"}:
        warnings.append(f"Unsupported stage up axis '{up_axis}' was treated as Z-up.")
    xform_cache = UsdGeom.XformCache(Usd.TimeCode.Default())
    instances, point_instance_count = _geometry_instances(
        stage,
        xform_cache,
        Usd,
        UsdGeom,
        warnings,
    )
    visual = MeshData()
    collision = MeshData()
    native_primitive_count = 0
    base_color_texture: str | None = None
    for instance in instances:
        local_positions, local_indices, local_uvs, native = _local_geometry(
            instance.prim, UsdGeom
        )
        if not local_positions or not local_indices:
            warnings.append(f"Skipped empty or unsupported geometry: {instance.prim.GetPath()}")
            continue
        if native:
            native_primitive_count += 1
        color, texture = _display_material(instance.prim, UsdGeom, UsdShade)
        if base_color_texture is None and texture is not None:
            base_color_texture = texture
        if instance.visible:
            _append_geometry(
                visual,
                local_positions,
                local_indices,
                instance.matrix,
                color,
                local_uvs,
                str(instance.prim.GetPath()),
                Gf,
                up_axis,
                meters_per_unit,
            )
        if instance.collision:
            _append_geometry(
                collision,
                local_positions,
                local_indices,
                instance.matrix,
                color,
                local_uvs,
                str(instance.prim.GetPath()),
                Gf,
                up_axis,
                meters_per_unit,
            )

    used_dedicated_collision = collision.triangle_count > 0
    if not used_dedicated_collision:
        collision = MeshData(
            positions=list(visual.positions),
            indices=list(visual.indices),
            colors=list(visual.colors),
            uvs=list(visual.uvs),
            source_prim_paths=list(visual.source_prim_paths),
        )
        warnings.append(
            "No UsdPhysics collision geometry was found; collision falls back to the visual mesh."
        )
    if native_primitive_count:
        warnings.append(
            f"Tessellated {native_primitive_count} native USD geometric primitive(s)."
        )
    if point_instance_count:
        warnings.append(f"Expanded {point_instance_count} PointInstancer instance(s).")
    return StageMeshExtraction(
        visual=visual,
        collision=collision,
        up_axis=up_axis,
        meters_per_unit=meters_per_unit,
        used_dedicated_collision=used_dedicated_collision,
        point_instance_count=point_instance_count,
        native_primitive_count=native_primitive_count,
        base_color_texture=base_color_texture,
    )


def _geometry_instances(
    stage: Any,
    xform_cache: Any,
    usd: Any,
    usd_geom: Any,
    warnings: list[str],
) -> tuple[list[_GeometryInstance], int]:
    point_instancers = [
        usd_geom.PointInstancer(prim)
        for prim in stage.Traverse()
        if prim.IsA(usd_geom.PointInstancer)
    ]
    prototype_roots = {
        str(path)
        for instancer in point_instancers
        for path in instancer.GetPrototypesRel().GetTargets()
    }
    output: list[_GeometryInstance] = []
    for prim in stage.Traverse():
        if _is_supported_geometry(prim, usd_geom) and not _inside_prototype(
            str(prim.GetPath()), prototype_roots
        ):
            output.append(
                _GeometryInstance(
                    prim=prim,
                    matrix=xform_cache.GetLocalToWorldTransform(prim),
                    visible=_is_visible(prim, usd_geom),
                    collision=_is_collision(prim),
                )
            )

    instance_count = 0
    for instancer in point_instancers:
        prototypes = list(instancer.GetPrototypesRel().GetTargets())
        proto_indices = list(instancer.GetProtoIndicesAttr().Get() or [])
        transforms = list(
            instancer.ComputeInstanceTransformsAtTime(
                usd.TimeCode.Default(),
                usd.TimeCode.Default(),
            )
        )
        instancer_world = xform_cache.GetLocalToWorldTransform(instancer.GetPrim())
        for instance_index, instance_matrix in enumerate(transforms):
            if instance_index >= len(proto_indices):
                warnings.append(
                    f"PointInstancer {instancer.GetPath()} has no prototype index for "
                    f"instance {instance_index}."
                )
                continue
            prototype_index = int(proto_indices[instance_index])
            if prototype_index < 0 or prototype_index >= len(prototypes):
                warnings.append(
                    f"PointInstancer {instancer.GetPath()} references invalid prototype "
                    f"index {prototype_index}."
                )
                continue
            prototype = stage.GetPrimAtPath(prototypes[prototype_index])
            if not prototype.IsValid():
                continue
            prototype_world = xform_cache.GetLocalToWorldTransform(prototype)
            for prim in usd.PrimRange(prototype):
                if not _is_supported_geometry(prim, usd_geom):
                    continue
                prim_world = xform_cache.GetLocalToWorldTransform(prim)
                relative = prim_world * prototype_world.GetInverse()
                output.append(
                    _GeometryInstance(
                        prim=prim,
                        matrix=relative * instance_matrix * instancer_world,
                        visible=(
                            _is_visible(prim, usd_geom)
                            and _is_visible(instancer.GetPrim(), usd_geom)
                        ),
                        collision=_is_collision(prim),
                    )
                )
            instance_count += 1
    return output, instance_count


def _inside_prototype(path: str, prototype_roots: set[str]) -> bool:
    return any(path == root or path.startswith(f"{root}/") for root in prototype_roots)


def _is_supported_geometry(prim: Any, usd_geom: Any) -> bool:
    return any(
        prim.IsA(schema)
        for schema in (
            usd_geom.Mesh,
            usd_geom.Cube,
            usd_geom.Sphere,
            usd_geom.Cylinder,
            usd_geom.Cone,
            usd_geom.Capsule,
        )
    )


def _is_visible(prim: Any, usd_geom: Any) -> bool:
    imageable = usd_geom.Imageable(prim)
    return imageable.ComputeVisibility() != usd_geom.Tokens.invisible


def _is_collision(prim: Any) -> bool:
    schemas = prim.GetAppliedSchemas()
    if "PhysicsCollisionAPI" in schemas:
        value = prim.GetAttribute("physics:collisionEnabled").Get()
        return value is None or bool(value)
    return bool(prim.GetAttribute("physics:collisionEnabled").Get())


def _local_geometry(
    prim: Any, usd_geom: Any
) -> tuple[list[list[float]], list[int], list[float], bool]:
    if prim.IsA(usd_geom.Mesh):
        positions, indices, uvs = _mesh_geometry(prim, usd_geom)
        return positions, indices, uvs, False
    if prim.IsA(usd_geom.Cube):
        half = float(usd_geom.Cube(prim).GetSizeAttr().Get() or 2.0) * 0.5
        return _box_mesh(half), _box_indices(), [], True
    if prim.IsA(usd_geom.Sphere):
        radius = float(usd_geom.Sphere(prim).GetRadiusAttr().Get() or 1.0)
        positions, indices = _lathe_mesh(
            [(math.sin(angle) * radius, math.cos(angle) * radius) for angle in _angles(12)],
            24,
        )
        return positions, indices, [], True
    if prim.IsA(usd_geom.Cylinder) or prim.IsA(usd_geom.Cone):
        schema = (
            usd_geom.Cylinder(prim)
            if prim.IsA(usd_geom.Cylinder)
            else usd_geom.Cone(prim)
        )
        radius = float(schema.GetRadiusAttr().Get() or 1.0)
        half_height = float(schema.GetHeightAttr().Get() or 2.0) * 0.5
        top_radius = radius if prim.IsA(usd_geom.Cylinder) else 0.0
        positions, indices = _cylinder_mesh(radius, top_radius, half_height, 24)
        return (
            _orient_axis(positions, str(schema.GetAxisAttr().Get() or "Z")),
            indices,
            [],
            True,
        )
    capsule = usd_geom.Capsule(prim)
    radius = float(capsule.GetRadiusAttr().Get() or 1.0)
    half_height = float(capsule.GetHeightAttr().Get() or 2.0) * 0.5
    profile = []
    for angle in _angles(12):
        z = math.cos(angle) * radius
        z += half_height if z >= 0 else -half_height
        profile.append((math.sin(angle) * radius, z))
    positions, indices = _lathe_mesh(profile, 24)
    return (
        _orient_axis(positions, str(capsule.GetAxisAttr().Get() or "Z")),
        indices,
        [],
        True,
    )


def _mesh_geometry(
    prim: Any, usd_geom: Any
) -> tuple[list[list[float]], list[int], list[float]]:
    mesh = usd_geom.Mesh(prim)
    source_points = mesh.GetPointsAttr().Get() or []
    points = [
        [float(point[0]), float(point[1]), float(point[2])]
        for point in source_points
    ]
    counts = [int(value) for value in (mesh.GetFaceVertexCountsAttr().Get() or [])]
    face_indices = [int(value) for value in (mesh.GetFaceVertexIndicesAttr().Get() or [])]
    primvar = usd_geom.PrimvarsAPI(prim).GetPrimvar("st")
    uv_values = list(primvar.ComputeFlattened() or []) if primvar else []
    interpolation = str(primvar.GetInterpolation()) if primvar else ""

    if uv_values and interpolation in {"faceVarying", "uniform"}:
        positions: list[list[float]] = []
        indices: list[int] = []
        uvs: list[float] = []
        cursor = 0
        for face_number, count in enumerate(counts):
            face = face_indices[cursor : cursor + count]
            if count >= 3:
                for triangle_index in range(1, count - 1):
                    for corner in (0, triangle_index, triangle_index + 1):
                        positions.append(points[face[corner]])
                        uv_index = (
                            cursor + corner
                            if interpolation == "faceVarying"
                            else face_number
                        )
                        uv = uv_values[uv_index]
                        uvs.extend([float(uv[0]), float(uv[1])])
                        indices.append(len(indices))
            cursor += count
        return positions, indices, uvs

    indices = []
    cursor = 0
    for count in counts:
        face = face_indices[cursor : cursor + count]
        cursor += count
        if count < 3:
            continue
        for triangle_index in range(1, count - 1):
            indices.extend([face[0], face[triangle_index], face[triangle_index + 1]])
    if not uv_values:
        return points, indices, []
    if interpolation == "constant":
        uv = uv_values[0]
        return points, indices, [float(value) for _ in points for value in uv[:2]]
    if len(uv_values) >= len(points):
        return (
            points,
            indices,
            [float(value) for uv in uv_values[: len(points)] for value in uv[:2]],
        )
    return points, indices, []


def _angles(segments: int) -> list[float]:
    return [math.pi * index / segments for index in range(segments + 1)]


def _lathe_mesh(
    profile: list[tuple[float, float]], segments: int
) -> tuple[list[list[float]], list[int]]:
    positions: list[list[float]] = []
    indices: list[int] = []
    for radius, z in profile:
        for segment in range(segments):
            angle = 2.0 * math.pi * segment / segments
            positions.append([radius * math.cos(angle), radius * math.sin(angle), z])
    for ring in range(len(profile) - 1):
        for segment in range(segments):
            next_segment = (segment + 1) % segments
            lower = ring * segments + segment
            lower_next = ring * segments + next_segment
            upper = (ring + 1) * segments + segment
            upper_next = (ring + 1) * segments + next_segment
            indices.extend([lower, lower_next, upper_next, lower, upper_next, upper])
    return positions, indices


def _cylinder_mesh(
    bottom_radius: float,
    top_radius: float,
    half_height: float,
    segments: int,
) -> tuple[list[list[float]], list[int]]:
    profile = [(bottom_radius, -half_height), (top_radius, half_height)]
    positions, indices = _lathe_mesh(profile, segments)
    bottom_center = len(positions)
    positions.append([0.0, 0.0, -half_height])
    top_center = len(positions)
    positions.append([0.0, 0.0, half_height])
    for segment in range(segments):
        next_segment = (segment + 1) % segments
        indices.extend([bottom_center, next_segment, segment])
        if top_radius > 0:
            indices.extend([top_center, segments + segment, segments + next_segment])
    return positions, indices


def _orient_axis(positions: list[list[float]], axis: str) -> list[list[float]]:
    axis = axis.upper()
    if axis == "X":
        return [[z, x, y] for x, y, z in positions]
    if axis == "Y":
        return [[x, z, y] for x, y, z in positions]
    return positions


def _box_mesh(half: float) -> list[list[float]]:
    return [
        [x * half, y * half, z * half]
        for x, y, z in (
            (-1, -1, -1),
            (1, -1, -1),
            (1, 1, -1),
            (-1, 1, -1),
            (-1, -1, 1),
            (1, -1, 1),
            (1, 1, 1),
            (-1, 1, 1),
        )
    ]


def _box_indices() -> list[int]:
    return [
        0, 2, 1, 0, 3, 2,
        4, 5, 6, 4, 6, 7,
        0, 1, 5, 0, 5, 4,
        1, 2, 6, 1, 6, 5,
        2, 3, 7, 2, 7, 6,
        3, 0, 4, 3, 4, 7,
    ]


def _display_material(
    prim: Any, usd_geom: Any, usd_shade: Any
) -> tuple[list[float], str | None]:
    colors = usd_geom.Gprim(prim).GetDisplayColorAttr().Get() or []
    opacity_values = usd_geom.Gprim(prim).GetDisplayOpacityAttr().Get() or []
    authored_color: list[float] | None = None
    if colors:
        color = [float(colors[0][0]), float(colors[0][1]), float(colors[0][2])]
        opacity = float(opacity_values[0]) if opacity_values else 1.0
        authored_color = [*color, opacity]
    try:
        material = usd_shade.MaterialBindingAPI(prim).ComputeBoundMaterial()[0]
        if material and material.GetPrim().IsValid():
            source = material.ComputeSurfaceSource()
            shader = source[0] if source else None
            if shader and shader.GetPrim().IsValid():
                diffuse = shader.GetInput("diffuseColor").Get()
                opacity = shader.GetInput("opacity").Get()
                texture_path = _connected_texture_path(
                    shader.GetInput("diffuseColor"), usd_shade
                )
                if authored_color is not None:
                    return authored_color, texture_path
                if diffuse is not None:
                    return (
                        [
                            float(diffuse[0]),
                            float(diffuse[1]),
                            float(diffuse[2]),
                            float(opacity) if opacity is not None else 1.0,
                        ],
                        texture_path,
                    )
                if texture_path is not None:
                    return [1.0, 1.0, 1.0, 1.0], texture_path
    except Exception:
        pass
    return authored_color or [0.55, 0.62, 0.7, 1.0], None


def _connected_texture_path(diffuse_input: Any, usd_shade: Any) -> str | None:
    if not diffuse_input:
        return None
    connected = diffuse_input.GetConnectedSource()
    if not connected:
        return None
    source = connected[0]
    texture_shader = usd_shade.Shader(source.GetPrim())
    if not texture_shader or not texture_shader.GetPrim().IsValid():
        return None
    file_value = texture_shader.GetInput("file").Get()
    if file_value is None:
        return None
    resolved = str(getattr(file_value, "resolvedPath", "") or "")
    authored = str(getattr(file_value, "path", "") or "")
    return resolved or authored or None


def _append_geometry(
    target: MeshData,
    positions: list[list[float]],
    indices: list[int],
    matrix: Any,
    color: list[float],
    uvs: list[float],
    prim_path: str,
    gf: Any,
    up_axis: str,
    scale: float,
) -> None:
    base = target.vertex_count
    for point in positions:
        transformed = matrix.Transform(gf.Vec3d(*point))
        x, y, z = (
            float(transformed[0]) * scale,
            float(transformed[1]) * scale,
            float(transformed[2]) * scale,
        )
        target.positions.extend([x, -z, y] if up_axis == "Y" else [x, y, z])
        target.colors.extend(color)
    target.indices.extend(base + index for index in indices)
    if uvs:
        if not target.uvs and base:
            target.uvs.extend([0.0] * base * 2)
        target.uvs.extend(uvs)
    elif target.uvs:
        target.uvs.extend([0.0] * len(positions) * 2)
    if prim_path not in target.source_prim_paths:
        target.source_prim_paths.append(prim_path)
