from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ImportSeverity = Literal["info", "warning", "error"]


@dataclass(frozen=True, slots=True)
class ImportIssue:
    severity: ImportSeverity
    code: str
    message: str
    prim_path: str | None = None
    field: str | None = None
    fallback: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "prim_path": self.prim_path,
            "field": self.field,
            "message": self.message,
            "fallback": self.fallback,
        }


@dataclass(slots=True)
class ImportReport:
    source_path: str
    issues: list[ImportIssue] = field(default_factory=list)
    resolved_dependencies: list[str] = field(default_factory=list)
    unresolved_dependencies: list[str] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)

    def add(
        self,
        severity: ImportSeverity,
        code: str,
        message: str,
        *,
        prim_path: str | None = None,
        field: str | None = None,
        fallback: str | None = None,
    ) -> None:
        self.issues.append(
            ImportIssue(
                severity=severity,
                code=code,
                message=message,
                prim_path=prim_path,
                field=field,
                fallback=fallback,
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_path": self.source_path,
            "issues": [issue.to_dict() for issue in self.issues],
            "resolved_dependencies": list(self.resolved_dependencies),
            "unresolved_dependencies": list(self.unresolved_dependencies),
            "has_errors": self.has_errors,
        }
