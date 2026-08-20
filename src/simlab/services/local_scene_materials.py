from __future__ import annotations

import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any

from simlab.services.openusd.asset_cache import atomic_copy

SUPPORTED_TEXTURE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def _input_value(shader: Any, names: tuple[str, ...]) -> Any:
    for name in names:
        shader_input = shader.GetInput(name)
        if not shader_input:
            continue
        value = shader_input.Get()
        if value is not None:
            return value
    return None


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _color(value: Any, fallback: list[float]) -> list[float]:
    try:
        if value is not None and len(value) >= 3:
            return [float(value[0]), float(value[1]), float(value[2]), 1.0]
    except (TypeError, ValueError):
        pass
    return list(fallback)


def _scale(value: Any) -> list[float]:
    try:
        if len(value) >= 2:
            return [float(value[0]), float(value[1])]
    except (TypeError, ValueError):
        pass
    try:
        scalar = float(value)
    except (TypeError, ValueError):
        return [1.0, 1.0]
    return [scalar, scalar]


def _property_layer_path(attribute: Any) -> Path | None:
    try:
        for spec in attribute.GetPropertyStack():
            real_path = str(spec.layer.realPath or "")
            if real_path:
                return Path(real_path).resolve()
    except Exception:
        return None
    return None


def _asset_input_path(shader_input: Any, asset_root: Path) -> Path | None:
    if not shader_input:
        return None
    value = shader_input.Get()
    authored = str(getattr(value, "path", "") or "")
    resolved = str(getattr(value, "resolvedPath", "") or "")
    candidates: list[Path] = []
    if resolved:
        candidates.append(Path(resolved))
    if authored:
        authored_path = Path(authored)
        if authored_path.is_absolute():
            candidates.append(authored_path)
        else:
            layer_path = _property_layer_path(shader_input.GetAttr())
            if layer_path is not None:
                base = layer_path.parent
                while base.is_relative_to(asset_root):
                    candidates.append(base / authored_path)
                    if base == asset_root:
                        break
                    base = base.parent
    for candidate in candidates:
        path = candidate.resolve()
        if (
            path.is_relative_to(asset_root)
            and path.is_file()
            and path.suffix.lower() in SUPPORTED_TEXTURE_EXTENSIONS
        ):
            return path
    return None


def _connected_file_input(shader_input: Any, usd_shade: Any) -> Any | None:
    if not shader_input:
        return None
    connected = shader_input.GetConnectedSource()
    if not connected:
        return None
    source = connected[0]
    shader = usd_shade.Shader(source.GetPrim())
    if not shader or not shader.GetPrim().IsValid():
        return None
    return shader.GetInput("file")


def _texture_input(
    shaders: list[Any],
    direct_names: tuple[str, ...],
    connected_names: tuple[str, ...],
    usd_shade: Any,
) -> Any | None:
    for shader in shaders:
        for name in direct_names:
            shader_input = shader.GetInput(name)
            if shader_input and shader_input.Get() is not None:
                return shader_input
    for shader in shaders:
        for name in connected_names:
            file_input = _connected_file_input(shader.GetInput(name), usd_shade)
            if file_input:
                return file_input
    return None


def _direct_bound_material(prim: Any, usd_shade: Any) -> Any | None:
    current = prim
    while current and current.IsValid() and not current.IsPseudoRoot():
        for relation_name in (
            "material:binding:full",
            "material:binding:preview",
            "material:binding",
        ):
            relation = current.GetRelationship(relation_name)
            targets = list(relation.GetTargets()) if relation else []
            if not targets:
                continue
            material = usd_shade.Material(current.GetStage().GetPrimAtPath(targets[-1]))
            if material and material.GetPrim().IsValid():
                return material
        current = current.GetParent()
    return None


class LocalMaterialRegistry:
    """Extract browser-readable subsets of bound USD/OmniPBR materials."""

    def __init__(self, asset_root: Path, cache_root: Path) -> None:
        self.asset_root = asset_root.resolve()
        self.cache_root = cache_root
        self.materials: dict[str, dict[str, Any]] = {}
        self.textures: dict[str, dict[str, Any]] = {}
        self._material_paths: dict[str, str] = {}
        self._texture_paths: dict[Path, str] = {}
        self.missing_texture_count = 0

    def material_for_prim(
        self,
        prim: Any,
        fallback_color: list[float],
        usd_shade: Any,
    ) -> tuple[str, list[float]]:
        material = _direct_bound_material(prim, usd_shade)
        if material is None:
            definition = self._fallback_definition(fallback_color)
            material_id = self._register_material(definition)
            return material_id, [1.0, 1.0, 1.0, 1.0]

        material_path = str(material.GetPath())
        cached_id = self._material_paths.get(material_path)
        if cached_id is not None:
            return cached_id, [1.0, 1.0, 1.0, 1.0]
        definition = self._extract_material(material, fallback_color, usd_shade)
        material_id = self._register_material(definition)
        self._material_paths[material_path] = material_id
        return material_id, [1.0, 1.0, 1.0, 1.0]

    def _fallback_definition(self, color: list[float]) -> dict[str, Any]:
        return {
            "name": "Display color fallback",
            "base_color": list(color),
            "roughness": 0.72,
            "metalness": 0.03,
            "opacity": float(color[3]),
            "texture_scale": [1.0, 1.0],
            "textures": {},
        }

    def _extract_material(
        self, material: Any, fallback_color: list[float], usd_shade: Any
    ) -> dict[str, Any]:
        shaders = [
            usd_shade.Shader(prim)
            for prim in self._prim_range(material.GetPrim())
            if prim.IsA(usd_shade.Shader)
        ]
        preview = next(
            (shader for shader in shaders if str(shader.GetIdAttr().Get()) == "UsdPreviewSurface"),
            None,
        )
        ordered = ([preview] if preview is not None else []) + [
            shader for shader in shaders if shader != preview
        ]
        color_value = None
        for names in (
            ("diffuseColor",),
            ("diffuse_color_constant", "base_color"),
            ("diffuse_tint",),
        ):
            color_value = next(
                (value for shader in ordered if (value := _input_value(shader, names)) is not None),
                None,
            )
            if color_value is not None:
                break
        roughness_value = next(
            (
                value
                for shader in ordered
                if (
                    value := _input_value(
                        shader, ("roughness", "reflection_roughness_constant")
                    )
                )
                is not None
            ),
            None,
        )
        metalness_value = next(
            (
                value
                for shader in ordered
                if (value := _input_value(shader, ("metallic", "metalness")))
                is not None
            ),
            None,
        )
        opacity_value = None
        for shader in ordered:
            shader_id = str(shader.GetIdAttr().Get() or "")
            if shader_id == "UsdPreviewSurface":
                opacity_value = _input_value(shader, ("opacity",))
            else:
                enabled = _input_value(shader, ("enable_opacity",))
                if bool(enabled):
                    opacity_value = _input_value(
                        shader,
                        ("opacity_constant", "opacity"),
                    )
            if opacity_value is not None:
                break
        texture_scale_value = next(
            (
                value
                for shader in ordered
                if (value := _input_value(shader, ("texture_scale", "uv_scale")))
                is not None
            ),
            None,
        )
        textures: dict[str, str] = {}
        texture_inputs = {
            "base_color": _texture_input(
                ordered,
                ("diffuse_texture", "base_color_texture", "albedo_texture"),
                ("diffuseColor",),
                usd_shade,
            ),
            "normal": _texture_input(
                ordered,
                ("normalmap_texture", "normal_texture"),
                ("normal",),
                usd_shade,
            ),
            "roughness": _texture_input(
                ordered,
                ("reflectionroughness_texture", "roughness_texture"),
                ("roughness",),
                usd_shade,
            ),
            "metalness": _texture_input(
                ordered,
                ("metallic_texture", "metalness_texture"),
                ("metallic",),
                usd_shade,
            ),
            "orm": _texture_input(
                ordered,
                ("ORM_texture", "orm_texture"),
                (),
                usd_shade,
            ),
        }
        for slot, shader_input in texture_inputs.items():
            source = _asset_input_path(shader_input, self.asset_root)
            if source is None:
                if shader_input and shader_input.Get() is not None:
                    self.missing_texture_count += 1
                continue
            textures[slot] = self._register_texture(source)
        base_color = _color(color_value, fallback_color)
        opacity = max(0.0, min(1.0, _number(opacity_value, 1.0)))
        base_color[3] = opacity
        return {
            "name": str(material.GetPrim().GetName()),
            "base_color": base_color,
            "roughness": max(0.0, min(1.0, _number(roughness_value, 0.72))),
            "metalness": max(0.0, min(1.0, _number(metalness_value, 0.03))),
            "opacity": opacity,
            "texture_scale": _scale(texture_scale_value),
            "textures": textures,
        }

    @staticmethod
    def _prim_range(prim: Any) -> list[Any]:
        from pxr import Usd

        return list(Usd.PrimRange(prim))

    def _register_material(self, definition: dict[str, Any]) -> str:
        identity = {key: value for key, value in definition.items() if key != "name"}
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()[:16]
        material_id = f"mat_{digest}"
        self.materials.setdefault(material_id, {"id": material_id, **definition})
        return material_id

    def _register_texture(self, source: Path) -> str:
        cached_id = self._texture_paths.get(source)
        if cached_id is not None:
            return cached_id
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:20]
        texture_id = f"tex_{digest}"
        suffix = source.suffix.lower()
        filename = f"{texture_id}{suffix}"
        destination = self.cache_root / "textures" / filename
        if not destination.is_file():
            atomic_copy(source, destination)
        self.textures.setdefault(
            texture_id,
            {
                "id": texture_id,
                "filename": filename,
                "media_type": mimetypes.guess_type(filename)[0] or "application/octet-stream",
                "byte_length": destination.stat().st_size,
            },
        )
        self._texture_paths[source] = texture_id
        return texture_id
