from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from simlab.services.openusd.import_report import ImportReport

SUPPORTED_USD_EXTENSIONS = {".usd", ".usda", ".usdc", ".usdz"}


class OpenUsdStageError(RuntimeError):
    """Raised when an external USD file cannot produce an inspectable stage."""

    def __init__(self, report: ImportReport) -> None:
        self.report = report
        message = next(
            (issue.message for issue in report.issues if issue.severity == "error"),
            "OpenUSD stage loading failed",
        )
        super().__init__(message)


@dataclass(slots=True)
class StageLoadResult:
    stage: Any
    report: ImportReport


def _fail(report: ImportReport, code: str, message: str, *, field: str) -> None:
    report.add("error", code, message, field=field)
    raise OpenUsdStageError(report)


def _list_op_items(list_op: Any) -> list[Any]:
    applied_items = getattr(list_op, "GetAppliedItems", None)
    if applied_items is not None:
        return list(applied_items())
    items: list[Any] = []
    for attribute_name in (
        "explicitItems",
        "prependedItems",
        "addedItems",
        "appendedItems",
    ):
        items.extend(getattr(list_op, attribute_name, []))
    return items


def _asset_path(value: Any) -> str | None:
    path = getattr(value, "path", None)
    if path:
        return str(path)
    if isinstance(value, str) and value:
        return value
    return None


def _dependency_locations(stage: Any) -> dict[str, tuple[str, str]]:
    locations: dict[str, tuple[str, str]] = {}
    for prim in stage.TraverseAll():
        prim_path = str(prim.GetPath())
        for metadata_name in ("references", "payload"):
            list_op = prim.GetMetadata(metadata_name)
            if list_op is None:
                continue
            for item in _list_op_items(list_op):
                path = _asset_path(getattr(item, "assetPath", None))
                if path:
                    locations[path] = (prim_path, metadata_name)
        for attribute in prim.GetAttributes():
            value = attribute.Get()
            values = value if isinstance(value, (list, tuple)) else [value]
            for item in values:
                path = _asset_path(item)
                if path:
                    locations[path] = (prim_path, str(attribute.GetName()))
    return locations


def _diagnostic_prim_path(message: str) -> str | None:
    matches = re.findall(r"<(/[^>]+)>", message)
    return matches[-1] if matches else None


def _diagnostic_dependency_location(
    dependency: str, diagnostic_messages: list[str]
) -> tuple[str | None, str] | None:
    dependency_name = Path(dependency).name
    for message in diagnostic_messages:
        if dependency not in message and dependency_name not in message:
            continue
        lowered = message.lower()
        if "payload" in lowered:
            field = "payload"
        elif "reference" in lowered:
            field = "references"
        else:
            field = "asset_path"
        return _diagnostic_prim_path(message), field
    return None


def load_openusd_stage(source: str | Path) -> StageLoadResult:
    """Open an external USD stage and report composition or asset dependency failures."""
    source_path = Path(source).expanduser().resolve()
    report = ImportReport(source_path=str(source_path))
    if source_path.suffix.lower() not in SUPPORTED_USD_EXTENSIONS:
        expected = ", ".join(sorted(SUPPORTED_USD_EXTENSIONS))
        _fail(
            report,
            "usd.unsupported_extension",
            f"Unsupported OpenUSD extension. Expected one of: {expected}",
            field="source_path",
        )
    if not source_path.is_file():
        _fail(
            report,
            "usd.source_missing",
            f"OpenUSD file does not exist: {source_path}",
            field="source_path",
        )

    try:
        from pxr import Tf, Usd, UsdUtils
    except ImportError:
        _fail(
            report,
            "usd.bindings_unavailable",
            "OpenUSD Python bindings are unavailable. Install the 'usd-core' package.",
            field="runtime",
        )

    mark = Tf.Error.Mark()
    mark.SetMark()
    stage = Usd.Stage.Open(str(source_path))
    diagnostics = list(mark.GetErrors())
    diagnostic_messages = [str(diagnostic.commentary) for diagnostic in diagnostics]
    mark.Clear()
    if stage is None:
        for diagnostic in diagnostics:
            message = str(diagnostic.commentary)
            report.add(
                "error",
                "usd.stage_diagnostic",
                message,
                prim_path=_diagnostic_prim_path(message),
                field="stage",
            )
        if not diagnostics:
            report.add(
                "error",
                "usd.stage_open_failed",
                f"OpenUSD could not open stage: {source_path}",
                field="source_path",
            )
        raise OpenUsdStageError(report)

    for message in diagnostic_messages:
        report.add(
            "warning",
            "usd.stage_diagnostic",
            message,
            prim_path=_diagnostic_prim_path(message),
            field="stage",
            fallback="The stage was opened with the affected composition arc omitted.",
        )

    locations = _dependency_locations(stage)
    layers, resolved_assets, unresolved_assets = UsdUtils.ComputeAllDependencies(
        str(source_path)
    )
    resolved_layers = {
        str(layer.realPath or layer.identifier)
        for layer in layers
        if str(layer.realPath or layer.identifier) != str(source_path)
    }
    report.resolved_dependencies = sorted(
        resolved_layers | {str(path) for path in resolved_assets}
    )
    report.unresolved_dependencies = sorted({str(path) for path in unresolved_assets})
    for dependency in report.unresolved_dependencies:
        location = locations.get(dependency) or _diagnostic_dependency_location(
            dependency, diagnostic_messages
        )
        prim_path, field = location or (None, "asset_path")
        report.add(
            "error",
            "usd.missing_dependency",
            f"OpenUSD dependency could not be resolved: {dependency}",
            prim_path=prim_path,
            field=field,
        )

    if not stage.GetDefaultPrim().IsValid():
        report.add(
            "warning",
            "usd.default_prim_missing",
            "The stage does not declare a valid defaultPrim.",
            field="defaultPrim",
            fallback="The importer will traverse all root prims.",
        )
    return StageLoadResult(stage=stage, report=report)
