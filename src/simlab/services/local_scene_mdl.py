from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

MAX_MDL_SOURCE_BYTES = 4 * 1024 * 1024

_OMNIPBR_CALL = re.compile(r"(?:(?:::)?OmniPBR::)?OmniPBR\s*\(")


@dataclass(frozen=True, slots=True)
class ParsedMdlMaterial:
    source: Path
    subidentifier: str
    arguments: dict[str, Any]


def _strip_comments(source: str) -> str:
    output: list[str] = []
    index = 0
    quoted = False
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if quoted:
            output.append(char)
            if char == "\\" and following:
                output.append(following)
                index += 2
                continue
            if char == '"':
                quoted = False
            index += 1
            continue
        if char == '"':
            quoted = True
            output.append(char)
            index += 1
            continue
        if char == "/" and following == "/":
            index += 2
            while index < len(source) and source[index] not in "\r\n":
                index += 1
            continue
        if char == "/" and following == "*":
            index += 2
            while index + 1 < len(source) and source[index : index + 2] != "*/":
                index += 1
            index = min(index + 2, len(source))
            continue
        output.append(char)
        index += 1
    return "".join(output)


def _matching_parenthesis(source: str, opening: int) -> int | None:
    depth = 0
    quoted = False
    index = opening
    while index < len(source):
        char = source[index]
        if quoted:
            if char == "\\":
                index += 2
                continue
            if char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _split_top_level(source: str, delimiter: str) -> list[str]:
    values: list[str] = []
    start = 0
    depth = 0
    quoted = False
    index = 0
    while index < len(source):
        char = source[index]
        if quoted:
            if char == "\\":
                index += 2
                continue
            if char == '"':
                quoted = False
        elif char == '"':
            quoted = True
        elif char in "([{":
            depth += 1
        elif char in ")]}" and depth:
            depth -= 1
        elif char == delimiter and depth == 0:
            values.append(source[start:index].strip())
            start = index + 1
        index += 1
    values.append(source[start:].strip())
    return [value for value in values if value]


def _float(value: str) -> float | None:
    normalized = value.strip().lower()
    if normalized.endswith("f"):
        normalized = normalized[:-1]
    try:
        return float(normalized)
    except ValueError:
        return None


def _vector(value: str, constructor: str) -> list[float] | None:
    match = re.fullmatch(rf"{constructor}\s*\((.*)\)", value.strip(), re.DOTALL)
    if match is None:
        return None
    components = [_float(item) for item in _split_top_level(match.group(1), ",")]
    if not components or any(item is None for item in components):
        return None
    output = [float(item) for item in components if item is not None]
    if constructor == "float2" and len(output) == 1:
        output *= 2
    return output


def _texture_path(value: str) -> str | None:
    match = re.fullmatch(r"texture_2d\s*\((.*)\)", value.strip(), re.DOTALL)
    if match is None:
        return None
    path = re.match(r'\s*"((?:\\.|[^"\\])*)"', match.group(1))
    if path is None:
        return ""
    return path.group(1).replace(r"\"", '"').replace(r"\\", "\\")


def _value(source: str) -> Any:
    value = source.strip()
    if value == "true":
        return True
    if value == "false":
        return False
    for constructor in ("color", "float2", "float3", "float4"):
        parsed = _vector(value, constructor)
        if parsed is not None:
            return parsed
    if value.startswith("texture_2d"):
        return _texture_path(value)
    number = _float(value)
    return number if number is not None else value


def parse_omnipbr_material(
    source_path: Path,
    subidentifier: str,
) -> ParsedMdlMaterial | None:
    """Read direct OmniPBR arguments without attempting to execute arbitrary MDL."""
    if not subidentifier or source_path.stat().st_size > MAX_MDL_SOURCE_BYTES:
        return None
    source = _strip_comments(source_path.read_text(encoding="utf-8", errors="replace"))
    declaration = re.search(
        rf"\bexport\s+material\s+{re.escape(subidentifier)}\b",
        source,
    )
    if declaration is None:
        return None
    next_declaration = re.search(r"\bexport\s+material\b", source[declaration.end() :])
    limit = (
        declaration.end() + next_declaration.start()
        if next_declaration is not None
        else len(source)
    )
    call = _OMNIPBR_CALL.search(source, declaration.end(), limit)
    if call is None:
        return None
    opening = call.end() - 1
    closing = _matching_parenthesis(source, opening)
    if closing is None or closing > limit:
        return None
    arguments: dict[str, Any] = {}
    for item in _split_top_level(source[opening + 1 : closing], ","):
        pair = _split_top_level(item, ":")
        if len(pair) != 2 or not re.fullmatch(r"[A-Za-z_]\w*", pair[0]):
            continue
        arguments[pair[0]] = _value(pair[1])
    if not arguments:
        return None
    return ParsedMdlMaterial(
        source=source_path,
        subidentifier=subidentifier,
        arguments=arguments,
    )
