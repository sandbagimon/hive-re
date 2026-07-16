from __future__ import annotations

import traceback
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

from simlab.services.controller_runtime import StepController


class ControllerLoadError(RuntimeError):
    def __init__(
        self,
        path: Path,
        phase: str,
        message: str,
        traceback_text: str | None = None,
    ) -> None:
        super().__init__(f"Controller {phase} failed for {path}: {message}")
        self.path = path
        self.phase = phase
        self.message = message
        self.traceback_text = traceback_text


@dataclass(frozen=True, slots=True)
class LoadedController:
    controller: StepController
    path: Path
    name: str

    def metadata(self) -> dict[str, str]:
        return {"path": str(self.path), "name": self.name}


class ProjectControllerLoader:
    """Explicitly load trusted controller source constrained to one project root."""

    def __init__(self, project_root: str | Path) -> None:
        self.project_root = Path(project_root).resolve()

    def load(self, path: str | Path) -> LoadedController:
        source_path = self._resolve_source(path)
        module = self._execute_module(source_path)
        factory = getattr(module, "create_controller", None)
        if not callable(factory):
            raise ControllerLoadError(
                source_path,
                "factory",
                "Module must define callable create_controller()",
            )
        try:
            controller = factory()
        except Exception as exc:
            raise ControllerLoadError(
                source_path,
                "factory",
                str(exc),
                traceback.format_exc(),
            ) from exc
        self._validate_controller(source_path, controller)
        raw_name = getattr(controller, "name", None)
        name = str(raw_name).strip() if raw_name is not None else type(controller).__name__
        if not name:
            name = type(controller).__name__
        return LoadedController(controller=controller, path=source_path, name=name)

    def _resolve_source(self, path: str | Path) -> Path:
        source_path = Path(path).expanduser().resolve()
        if not source_path.is_relative_to(self.project_root):
            raise ControllerLoadError(
                source_path,
                "path validation",
                f"Controller must be inside project root: {self.project_root}",
            )
        if source_path.suffix.lower() != ".py":
            raise ControllerLoadError(
                source_path,
                "path validation",
                "Controller source must use the .py extension",
            )
        if not source_path.is_file():
            raise ControllerLoadError(
                source_path,
                "path validation",
                "Controller source does not exist",
            )
        return source_path

    @staticmethod
    def _execute_module(path: Path) -> ModuleType:
        module = ModuleType(f"simlab_project_controller_{path.stem}")
        module.__file__ = str(path)
        module.__package__ = None
        try:
            source = path.read_text(encoding="utf-8")
            code = compile(source, str(path), "exec")
            exec(code, module.__dict__)
        except Exception as exc:
            raise ControllerLoadError(
                path,
                "import",
                str(exc),
                traceback.format_exc(),
            ) from exc
        return module

    @staticmethod
    def _validate_controller(path: Path, controller: Any) -> None:
        if not callable(getattr(controller, "reset", None)) or not callable(
            getattr(controller, "step", None)
        ):
            raise ControllerLoadError(
                path,
                "validation",
                "create_controller() must return an object with reset() and step()",
            )
