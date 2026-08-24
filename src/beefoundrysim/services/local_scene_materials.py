from __future__ import annotations

import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any

from beefoundrysim.services.local_scene_mdl import ParsedMdlMaterial, parse_omnipbr_material
from beefoundrysim.services.openusd.asset_cache import atomic_copy

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


def _asset_value_path(
    value: Any,
    attribute: Any,
    asset_root: Path,
    extensions: set[str],
) -> Path | None:
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
            layer_path = _property_layer_path(attribute)
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
            and path.suffix.lower() in extensions
        ):
            return path
    return None


def _asset_input_path(shader_input: Any, asset_root: Path) -> Path | None:
    if not shader_input:
        return None
    return _asset_value_path(
        shader_input.Get(),
        shader_input.GetAttr(),
        asset_root,
        SUPPORTED_TEXTURE_EXTENSIONS,
    )


def _asset_attribute_path(
    attribute: Any,
    asset_root: Path,
    extensions: set[str],
) -> Path | None:
    if not attribute:
        return None
    return _asset_value_path(attribute.Get(), attribute, asset_root, extensions)


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
        self._mdl_cache: dict[tuple[Path, str], ParsedMdlMaterial | None] = {}
        self.mdl_source_paths: set[Path] = set()
        self._missing_mdl_references: set[tuple[str, str]] = set()
        self._missing_texture_references: set[tuple[str, str]] = set()
        self.missing_texture_count = 0
        self.missing_mdl_count = 0

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
            "normal_scale": 1.0,
            "texture_scale": [1.0, 1.0],
            "texture_offset": [0.0, 0.0],
            "texture_rotation": 0.0,
            "emissive_color": [0.0, 0.0, 0.0],
            "emissive_intensity": 0.0,
            "source_model": "displayColor",
            "textures": {},
        }

    def _mdl_for_shaders(self, shaders: list[Any]) -> ParsedMdlMaterial | None:
        for shader in shaders:
            prim = shader.GetPrim()
            source_attribute = prim.GetAttribute("info:mdl:sourceAsset")
            if not source_attribute or source_attribute.Get() is None:
                continue
            subidentifier_attribute = prim.GetAttribute(
                "info:mdl:sourceAsset:subIdentifier"
            )
            subidentifier = str(
                subidentifier_attribute.Get() if subidentifier_attribute else ""
            )
            source = _asset_attribute_path(
                source_attribute,
                self.asset_root,
                {".mdl"},
            )
            reference = (str(prim.GetPath()), subidentifier)
            if source is None:
                if reference not in self._missing_mdl_references:
                    self._missing_mdl_references.add(reference)
                    self.missing_mdl_count += 1
                continue
            key = (source, subidentifier)
            if key not in self._mdl_cache:
                try:
                    self._mdl_cache[key] = parse_omnipbr_material(
                        source,
                        subidentifier,
                    )
                except OSError:
                    self._mdl_cache[key] = None
            parsed = self._mdl_cache[key]
            if parsed is not None:
                self.mdl_source_paths.add(source)
                return parsed
        return None

    def _mdl_texture_path(
        self,
        mdl: ParsedMdlMaterial,
        argument_name: str,
    ) -> Path | None:
        authored = mdl.arguments.get(argument_name)
        if not isinstance(authored, str) or not authored:
            return None
        relative = Path(authored)
        candidates = [relative] if relative.is_absolute() else []
        if not relative.is_absolute():
            base = mdl.source.parent
            while base.is_relative_to(self.asset_root):
                candidates.append(base / relative)
                if base == self.asset_root:
                    break
                base = base.parent
        for candidate in candidates:
            source = candidate.resolve()
            if (
                source.is_relative_to(self.asset_root)
                and source.is_file()
                and source.suffix.lower() in SUPPORTED_TEXTURE_EXTENSIONS
            ):
                return source
        reference = (str(mdl.source), argument_name)
        if reference not in self._missing_texture_references:
            self._missing_texture_references.add(reference)
            self.missing_texture_count += 1
        return None

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
        mdl = self._mdl_for_shaders(ordered)
        mdl_arguments = mdl.arguments if mdl is not None else {}

        def shader_value(names: tuple[str, ...]) -> Any:
            return next(
                (
                    value
                    for shader in ordered
                    if (value := _input_value(shader, names)) is not None
                ),
                None,
            )

        preview_color_value = shader_value(("diffuseColor",))
        diffuse_constant_value = shader_value(
            ("diffuse_color_constant", "base_color")
        )
        if diffuse_constant_value is None:
            diffuse_constant_value = mdl_arguments.get("diffuse_color_constant")
        tint_value = shader_value(("diffuse_tint",))
        if tint_value is None:
            tint_value = mdl_arguments.get("diffuse_tint")
        roughness_value = shader_value(
            ("roughness", "reflection_roughness_constant")
        )
        if roughness_value is None:
            roughness_value = mdl_arguments.get("reflection_roughness_constant")
        metalness_value = shader_value(("metallic", "metalness", "metallic_constant"))
        if metalness_value is None:
            metalness_value = mdl_arguments.get("metallic_constant")
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
        if opacity_value is None and bool(mdl_arguments.get("enable_opacity")):
            opacity_value = mdl_arguments.get("opacity_constant")
        texture_scale_value = shader_value(("texture_scale", "uv_scale"))
        if texture_scale_value is None:
            texture_scale_value = mdl_arguments.get("texture_scale")
        texture_offset_value = shader_value(("texture_translate", "uv_translate"))
        if texture_offset_value is None:
            texture_offset_value = mdl_arguments.get("texture_translate")
        texture_rotation_value = shader_value(("texture_rotate", "uv_rotation"))
        if texture_rotation_value is None:
            texture_rotation_value = mdl_arguments.get("texture_rotate")
        normal_scale_value = shader_value(("bump_factor", "normal_scale"))
        if normal_scale_value is None:
            normal_scale_value = mdl_arguments.get("bump_factor")
        emissive_color_value = shader_value(("emissiveColor", "emissive_color"))
        if emissive_color_value is None and bool(mdl_arguments.get("enable_emission")):
            emissive_color_value = mdl_arguments.get("emissive_color")
        emissive_intensity_value = shader_value(("emissive_intensity",))
        if emissive_intensity_value is None and bool(
            mdl_arguments.get("enable_emission")
        ):
            emissive_intensity_value = mdl_arguments.get("emissive_intensity")
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
            "opacity": _texture_input(
                ordered,
                ("opacity_texture",),
                ("opacity",),
                usd_shade,
            ),
            "emissive": _texture_input(
                ordered,
                ("emissive_mask_texture", "emissive_texture"),
                ("emissiveColor",),
                usd_shade,
            ),
        }
        for slot, shader_input in texture_inputs.items():
            source = _asset_input_path(shader_input, self.asset_root)
            if source is None:
                if shader_input and shader_input.Get() is not None:
                    reference = (str(shader_input.GetAttr().GetPath()), slot)
                    if reference not in self._missing_texture_references:
                        self._missing_texture_references.add(reference)
                        self.missing_texture_count += 1
                continue
            textures[slot] = self._register_texture(source)
        if mdl is not None:
            mdl_texture_arguments = {
                "base_color": "diffuse_texture",
                "normal": "normalmap_texture",
                "roughness": "reflectionroughness_texture",
                "metalness": "metallic_texture",
                "orm": "ORM_texture",
                "opacity": "opacity_texture",
                "emissive": "emissive_mask_texture",
            }
            enabled = {
                "base_color": True,
                "normal": _number(normal_scale_value, 1.0) != 0.0,
                "roughness": _number(
                    mdl_arguments.get("reflection_roughness_texture_influence"),
                    1.0,
                )
                != 0.0,
                "metalness": _number(
                    mdl_arguments.get("metallic_texture_influence"),
                    1.0,
                )
                != 0.0,
                "orm": bool(mdl_arguments.get("enable_ORM_texture")),
                "opacity": bool(mdl_arguments.get("enable_opacity")),
                "emissive": bool(mdl_arguments.get("enable_emission")),
            }
            for slot, argument_name in mdl_texture_arguments.items():
                if slot in textures or not enabled[slot]:
                    continue
                source = self._mdl_texture_path(mdl, argument_name)
                if source is not None:
                    textures[slot] = self._register_texture(source)

        if preview_color_value is not None:
            color_value = preview_color_value
        elif "base_color" in textures:
            color_value = tint_value if tint_value is not None else [1.0, 1.0, 1.0]
        elif diffuse_constant_value is not None:
            color_value = diffuse_constant_value
        else:
            color_value = tint_value
        base_color = _color(color_value, fallback_color)
        opacity = max(0.0, min(1.0, _number(opacity_value, 1.0)))
        base_color[3] = opacity
        emissive_color = _color(emissive_color_value, [0.0, 0.0, 0.0, 1.0])[:3]
        emissive_intensity = max(0.0, _number(emissive_intensity_value, 0.0))
        return {
            "name": str(material.GetPrim().GetName()),
            "base_color": base_color,
            "roughness": max(0.0, min(1.0, _number(roughness_value, 0.72))),
            "metalness": max(0.0, min(1.0, _number(metalness_value, 0.03))),
            "opacity": opacity,
            "normal_scale": max(0.0, _number(normal_scale_value, 1.0)),
            "texture_scale": _scale(texture_scale_value),
            "texture_offset": (
                _scale(texture_offset_value)
                if texture_offset_value is not None
                else [0.0, 0.0]
            ),
            "texture_rotation": _number(texture_rotation_value, 0.0),
            "emissive_color": emissive_color,
            "emissive_intensity": emissive_intensity,
            "source_model": "MDL:OmniPBR" if mdl is not None else "USD",
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
