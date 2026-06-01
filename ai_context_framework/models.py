"""Shared value objects used by ACF commands and domain services."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CheckResult:
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class ContextLocation:
    project_root: Path
    context_root: Path
    profile: str


@dataclass
class KnowledgeEntry:
    knowledge_id: str
    title: str
    status: str
    summary: str
    conclusion: str
    path: Path | None


@dataclass
class WorkstreamEntry:
    workstream_id: str
    status: str
    title: str
    owner: str
    write_scope: str
    depends_on: str
    output: str
    detail: str


@dataclass
class WorkstreamDetail:
    workstream_id: str
    path: Path
    metadata: dict[str, str | list[str]]
    body: str
    diagnostics: list[FrontMatterDiagnostic]


@dataclass(frozen=True)
class WorkstreamArchiveAssessment:
    detail: WorkstreamDetail
    blockers: tuple[str, ...]
    reason: str


@dataclass
class SectionRange:
    heading_index: int
    body_start: int
    body_end: int
    level: int


@dataclass(frozen=True)
class PlanReference:
    path: str
    purpose: str


@dataclass
class TableRange:
    header_index: int
    separator_index: int
    body_start: int
    body_end: int
    headers: list[str]


@dataclass
class FrontMatterDiagnostic:
    code: str
    message: str
    field: str | None = None
    line: int | None = None
    severity: str = "error"


@dataclass
class FrontMatterSchema:
    required_fields: tuple[str, ...] = ()
    allowed_fields: tuple[str, ...] | None = None
    scalar_fields: tuple[str, ...] = ()
    list_fields: tuple[str, ...] = ()
    enum_fields: dict[str, set[str]] = field(default_factory=dict)
    scope_fields: tuple[str, ...] = ()
    typed_scope_fields: tuple[str, ...] = ()
    scope_types: set[str] = field(
        default_factory=lambda: {"authority", "draft", "owned", "assigned", "shared", "evidence"}
    )
