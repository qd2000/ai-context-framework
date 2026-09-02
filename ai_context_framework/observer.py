"""Project-level Observer storage, locking, and read-only snapshot primitives.

The Observer is intentionally separate from continuation ownership/control.
It may read broadly from one Git project, but its runtime writes are confined
to the user-level ACF state directory under ``~/.acf/projects/.../observer``.
"""

from __future__ import annotations

import hashlib
import json
import os
import statistics
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ai_context_framework.front_matter import parse_front_matter
from ai_context_framework.git_support import (
    GitCommandError, discover_git_project, is_ancestor, list_registries,
    list_worktrees, path_key,
)
from ai_context_framework.observability import acf_home, atomic_write_text, usage_project_dir
from ai_context_framework.observer_storage import (
    ObserverLockedError, _continuation_lease_liveness, _parse_utc_iso, _read_json_object,
    _read_jsonl_objects, acquire_observer_lock, append_jsonl, append_jsonl_unique,
    attach_semantic_interpretations, ensure_jsonl_file, observer_lock_health, observer_paths,
    observer_status_payload, project_narrative_status, read_glossary, read_observer_history_stream, refresh_history_index,
    release_observer_lock,
    rotate_jsonl_monthly, rotate_observer_history, sanitize_observer_payload, utc_now_iso,
    write_dashboard, write_json_atomic,
)
from ai_context_framework.observer_targets import build_target_views
from ai_context_framework.observer_presentation import attach_presentation_status, presentation_alert_specs
from ai_context_framework.paths import discover_context, resolve_status_location, slugify_project_name
from ai_context_framework.version import VERSION
from ai_context_framework.worktree_status import capture_git_worktree_snapshot


OBSERVER_CURRENT_SCHEMA = "acf.observer.current.v1"
OBSERVER_RUN_SCHEMA = "acf.observer.run.v1"
OBSERVER_STATUS_SCHEMA = "acf.observer.status.v1"
OBSERVER_LOCK_SCHEMA = "acf.observer.lock.v1"
OBSERVER_EVENT_SCHEMA = "acf.observer.event.v1"
OBSERVER_OBSERVATION_SCHEMA = "acf.observer.observation.v1"
OBSERVER_PROJECT_SCHEMA = "acf.observer.project.v1"
OBSERVER_WORKTREE_SCHEMA = "acf.observer.worktree.v1"
OBSERVER_WORKSTREAM_SCHEMA = "acf.observer.workstream.v1"
OBSERVER_CONTINUATION_SCHEMA = "acf.observer.continuation.v1"
OBSERVER_MACHINE_STATE_SCHEMA = "acf.observer.machine-state.v1"
OBSERVER_ALERT_SCHEMA = "acf.observer.alert.v1"
OBSERVER_ALERT_EVENT_SCHEMA = "acf.observer.alert-event.v1"
OBSERVER_MIN_STALE_WINDOW_SECONDS = 2 * 60 * 60
OBSERVER_MIN_CRITICAL_WINDOW_SECONDS = 6 * 60 * 60
OBSERVER_FIRST_UNCHANGED_MILESTONE_SECONDS = 6 * 60 * 60
OBSERVER_SECOND_UNCHANGED_MILESTONE_SECONDS = 12 * 60 * 60
OBSERVER_DAILY_UNCHANGED_MILESTONE_SECONDS = 24 * 60 * 60
OBSERVER_CONTINUATION_READ_HOME_ENV = "ACF_OBSERVER_CONTINUATION_READ_HOME"


def _usage_project_dir_from_home(project_root: Path, home: Path) -> Path:
    resolved = project_root.resolve()
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:12]
    return home / "projects" / f"{slugify_project_name(resolved.name)}-{digest}"


def _observer_continuation_read_home() -> Path:
    """Resolve the optional read-only continuation evidence home for Observer."""

    override = os.environ.get(OBSERVER_CONTINUATION_READ_HOME_ENV, "").strip()
    if not override:
        return acf_home()
    candidate = Path(override).expanduser()
    if not candidate.is_absolute():
        raise ValueError(f"{OBSERVER_CONTINUATION_READ_HOME_ENV} must be an absolute path")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError(
            f"{OBSERVER_CONTINUATION_READ_HOME_ENV} does not resolve to an existing directory: {candidate}"
        ) from exc
    if not resolved.is_dir():
        raise ValueError(f"{OBSERVER_CONTINUATION_READ_HOME_ENV} must resolve to a directory: {resolved}")
    return resolved
@dataclass(frozen=True)
class ObserverProject:
    project_id: str
    canonical_root: Path
    invocation_root: Path
    context_root: Path
    observer_dir: Path
    git_managed: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "schema_version": OBSERVER_PROJECT_SCHEMA,
            "project_id": self.project_id,
            "canonical_root": str(self.canonical_root),
            "invocation_root": str(self.invocation_root),
            "context_root": str(self.context_root),
            "observer_dir": str(self.observer_dir),
            "git_managed": self.git_managed,
        }


def observer_project_id(project_root: Path) -> str:
    resolved = project_root.resolve()
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:12]
    return f"{slugify_project_name(resolved.name)}-{digest}"


def observer_project_dir(project_root: Path) -> Path:
    return acf_home() / "projects" / observer_project_id(project_root) / "observer"


def resolve_observer_project(path: Path | None = None) -> ObserverProject:
    """Resolve one invocation to its canonical project-level Observer domain.

    For Git worktrees the primary checkout is the canonical project root, so
    invoking Observer from any linked worktree resolves to the same state
    directory. Non-Git ACF contexts fall back to the discovered project root.
    """

    location = resolve_status_location(path)
    invocation_root = location.project_root.resolve()
    canonical_root = invocation_root
    git_managed = False
    try:
        git_project = discover_git_project(invocation_root)
        canonical_root = git_project.config.primary_checkout.resolve()
        git_managed = True
    except (SystemExit, OSError):
        pass
    context_root = location.context_root.resolve()
    if git_managed:
        # Project Observer state is project-level, so the canonical context
        # identity must not drift depending on which linked worktree invoked
        # the command.  The primary checkout is the stable project anchor;
        # individual worktree contexts are still scanned separately below.
        try:
            context_root = resolve_status_location(canonical_root).context_root.resolve()
        except SystemExit:
            # Preserve the invocation context as a conservative fallback for
            # unusual repositories whose primary checkout has no ACF context.
            pass
    project_id = observer_project_id(canonical_root)
    return ObserverProject(
        project_id=project_id,
        canonical_root=canonical_root,
        invocation_root=invocation_root,
        context_root=context_root,
        observer_dir=observer_project_dir(canonical_root),
        git_managed=git_managed,
    )


def _worktree_payload(path: Path, *, listed_head: str | None, listed_branch: str | None) -> dict[str, object]:
    snapshot = capture_git_worktree_snapshot(path)
    return {
        "schema_version": OBSERVER_WORKTREE_SCHEMA,
        "path": str(path.resolve()),
        "branch": snapshot.get("branch") or listed_branch,
        "head": snapshot.get("head") or listed_head,
        "clean": not bool(snapshot.get("entries")),
        "staged_paths": list(snapshot.get("staged_paths") or []),
        "unstaged_paths": list(snapshot.get("unstaged_paths") or []),
        "untracked_paths": list(snapshot.get("untracked_paths") or []),
        "unmerged_paths": list(snapshot.get("unmerged_paths") or []),
        "sequencer": snapshot.get("sequencer") or {},
        "git_fingerprint": snapshot.get("fingerprint"),
    }


def capture_project_worktrees(project: ObserverProject) -> list[dict[str, object]]:
    if not project.git_managed:
        return []
    records = list_worktrees(project.canonical_root)
    registry_rows = _safe_registry_rows(project)
    registry_by_path = {
        path_key(str(row["path"])): row
        for row in registry_rows
        if isinstance(row.get("path"), str)
    }
    registry_managed_domain = bool(registry_rows)
    payloads: list[dict[str, object]] = []
    for record in records:
        if record.bare or not record.path.is_dir():
            continue
        try:
            payload = _worktree_payload(
                record.path,
                listed_head=record.head,
                listed_branch=record.branch_short,
            )
        except (GitCommandError, SystemExit, OSError) as exc:
            payload = {
                "schema_version": OBSERVER_WORKTREE_SCHEMA,
                "path": str(record.path),
                "branch": record.branch_short,
                "head": record.head,
                "clean": None,
                "read_error": str(exc),
                "git_fingerprint": None,
            }
        payload["detached"] = record.detached
        payload["prunable"] = record.prunable
        record_key = path_key(str(record.path))
        registry = registry_by_path.get(record_key)
        primary = record_key == path_key(project.canonical_root)
        payload["primary"] = primary
        payload["registered"] = registry is not None
        payload["registry"] = registry
        # When an ACF worktree registry exists, it defines the project-managed
        # observation domain.  Raw Git worktrees outside that domain remain in
        # current.json for diagnosis, but do not become semantic/progress
        # sources merely because a workspace tool created a temporary linked
        # worktree.  Repositories without an ACF registry retain all Git
        # worktrees as in-scope so Observer stays model/tool agnostic.
        payload["observer_scope"] = primary or registry is not None or not registry_managed_domain
        payloads.append(payload)
    return payloads


def _observer_scope_worktrees(
    project: ObserverProject,
    worktrees: list[dict[str, object]],
) -> list[dict[str, object]]:
    scoped = [row for row in worktrees if row.get("observer_scope") is not False]
    if scoped:
        return scoped
    # Backward compatibility for synthetic callers / older snapshot shapes.
    return worktrees or [{"path": str(project.invocation_root)}]


def _section_text(body: str, heading: str) -> str | None:
    lines = body.splitlines()
    start: int | None = None
    heading_level = len(heading) - len(heading.lstrip("#"))
    for index, line in enumerate(lines):
        if line.strip() == heading:
            start = index + 1
            break
    if start is None:
        return None
    collected: list[str] = []
    for line in lines[start:]:
        stripped = line.strip()
        if stripped in {"---", "***", "___"}:
            break
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            if level <= heading_level:
                break
        collected.append(line)
    text = "\n".join(collected).strip()
    return text or None


def _string_metadata(metadata: dict[str, str | list[str]], key: str) -> str | None:
    value = metadata.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _workstream_occurrences_for_root(root: Path) -> list[dict[str, object]]:
    try:
        location = discover_context(root)
    except SystemExit:
        return []
    details_dir = location.context_root / "active" / "workstreams"
    if not details_dir.is_dir():
        return []
    rows: list[dict[str, object]] = []
    for detail_path in sorted(details_dir.glob("WS*.md")):
        try:
            text = detail_path.read_text(encoding="utf-8")
        except OSError as exc:
            rows.append(
                {
                    "schema_version": OBSERVER_WORKSTREAM_SCHEMA,
                    "id": detail_path.stem,
                    "source_worktree": str(root.resolve()),
                    "detail_path": str(detail_path),
                    "read_error": str(exc),
                }
            )
            continue
        metadata, body, diagnostics = parse_front_matter(text)
        workstream_id = _string_metadata(metadata, "id") or detail_path.stem
        rows.append(
            {
                "schema_version": OBSERVER_WORKSTREAM_SCHEMA,
                "id": workstream_id,
                "type": _string_metadata(metadata, "type"),
                "status": _string_metadata(metadata, "status"),
                "attention": _string_metadata(metadata, "attention"),
                "owner": _string_metadata(metadata, "owner"),
                "title": _string_metadata(metadata, "title"),
                "goal": _section_text(body, "## 目标"),
                "source_worktree": str(root.resolve()),
                "context_root": str(location.context_root.resolve()),
                "detail_path": str(detail_path.resolve()),
                "front_matter_diagnostics": [diagnostic.code for diagnostic in diagnostics],
            }
        )
    return rows


def _archived_workstream_ids_for_root(root: Path) -> set[str]:
    """Return Workstream ids that the primary context has moved to archive.

    Archive presence is lifecycle authority, not another current semantic
    source.  The ids are used only to prevent stale linked-worktree copies
    from resurrecting a Workstream after the primary checkout has archived it.
    """

    try:
        location = discover_context(root)
    except SystemExit:
        return set()
    archive_dir = location.context_root / "archive" / "workstreams"
    if not archive_dir.is_dir():
        return set()
    archived: set[str] = set()
    for detail_path in sorted(archive_dir.glob("WS*.md")):
        workstream_id = detail_path.stem
        try:
            text = detail_path.read_text(encoding="utf-8")
        except OSError:
            archived.add(workstream_id)
            continue
        metadata, _body, _diagnostics = parse_front_matter(text)
        archived.add(_string_metadata(metadata, "id") or workstream_id)
    return archived


def _safe_registry_rows(project: ObserverProject) -> list[dict[str, object]]:
    if not project.git_managed:
        return []
    try:
        git_project = discover_git_project(project.canonical_root)
        rows = list_registries(git_project.common_dir)
    except (SystemExit, OSError):
        return []
    safe: list[dict[str, object]] = []
    for row in rows:
        safe.append(
            {
                "key": row.get("key"),
                "workstream": row.get("workstream"),
                "branch": row.get("branch"),
                "path": row.get("path"),
                "state": row.get("state"),
                "slug": row.get("slug"),
                "updated_at": row.get("updated_at"),
            }
        )
    return safe


def capture_project_workstreams(
    project: ObserverProject,
    worktrees: list[dict[str, object]],
    *,
    workstream_ids: set[str] | None = None,
) -> list[dict[str, object]]:
    roots: list[Path] = []
    scoped_worktrees = _observer_scope_worktrees(project, worktrees)
    if scoped_worktrees:
        for item in scoped_worktrees:
            raw = item.get("path")
            if isinstance(raw, str):
                roots.append(Path(raw))
    else:
        roots.append(project.invocation_root)
    occurrences: list[dict[str, object]] = []
    for root in roots:
        rows = _workstream_occurrences_for_root(root)
        if workstream_ids is not None:
            rows = [row for row in rows if row.get("id") in workstream_ids]
        occurrences.extend(rows)
    registry_rows = _safe_registry_rows(project)
    registry_managed_domain = bool(registry_rows)
    primary_key = path_key(project.canonical_root)
    worktree_by_path = {
        path_key(str(row["path"])): row
        for row in worktrees
        if isinstance(row.get("path"), str)
    }
    primary_archived_ids = _archived_workstream_ids_for_root(project.canonical_root)
    by_id: dict[str, list[dict[str, object]]] = {}
    for row in occurrences:
        workstream_id = row.get("id")
        if isinstance(workstream_id, str) and workstream_id:
            by_id.setdefault(workstream_id, []).append(row)

    result: list[dict[str, object]] = []
    for workstream_id in sorted(by_id):
        sources = by_id[workstream_id]
        primary_source_present = any(
            isinstance(row.get("source_worktree"), str)
            and path_key(str(row["source_worktree"])) == primary_key
            for row in sources
        )
        # Once the primary context has archived a Workstream, stale active
        # details left in linked worktrees are historical evidence only.  They
        # must never resurrect that Workstream in the current Observer view.
        if workstream_id in primary_archived_ids and not primary_source_present:
            continue
        registry = next(
            (
                row
                for row in registry_rows
                if row.get("workstream") == workstream_id or row.get("key") == workstream_id
            ),
            None,
        )
        registry_by_path = {
            path_key(str(row["path"])): row
            for row in registry_rows
            if isinstance(row.get("path"), str)
        }
        authoritative_sources = [
            row
            for row in sources
            if isinstance(row.get("source_worktree"), str)
            and (
                path_key(str(row["source_worktree"])) == primary_key
                or (
                    (source_registry := registry_by_path.get(path_key(str(row["source_worktree"])))) is not None
                    and (
                        source_registry.get("workstream") == workstream_id
                        or source_registry.get("key") == workstream_id
                    )
                    and str(source_registry.get("state") or "").casefold() == "active"
                )
            )
        ]
        if registry_managed_domain:
            sources = authoritative_sources
        elif authoritative_sources:
            sources = authoritative_sources
        if not sources:
            continue
        selected: dict[str, object] | None = None
        if registry and isinstance(registry.get("path"), str):
            expected_path = path_key(str(registry["path"]))
            selected = next(
                (
                    row
                    for row in sources
                    if isinstance(row.get("source_worktree"), str)
                    and path_key(str(row["source_worktree"])) == expected_path
                ),
                None,
            )
        if selected is None:
            selected = next(
                (
                    row
                    for row in sources
                    if isinstance(row.get("source_worktree"), str)
                    and path_key(str(row["source_worktree"])) == primary_key
                ),
                sources[0],
            )
        comparable = {
            (
                row.get("title"),
                row.get("status"),
                row.get("attention"),
                row.get("goal"),
            )
            for row in sources
            if not row.get("read_error")
        }
        source_consistency = "consistent" if len(comparable) <= 1 else "divergent"
        source_consistency_basis = "identical_authoritative_sources" if len(comparable) <= 1 else "conflicting_authoritative_sources"
        if source_consistency == "divergent" and registry and isinstance(registry.get("path"), str):
            selected_key = path_key(str(registry["path"]))
            primary_worktree = worktree_by_path.get(primary_key)
            selected_worktree = worktree_by_path.get(selected_key)
            source_keys = {path_key(str(row["source_worktree"])) for row in sources if row.get("source_worktree")}
            primary_head = primary_worktree.get("head") if primary_worktree else None
            selected_head = selected_worktree.get("head") if selected_worktree else None
            # Ordered active-worktree progress is lineage, not contradictory authority.
            if (
                str(registry.get("state") or "").casefold() == "active"
                and source_keys <= {primary_key, selected_key}
                and primary_worktree is not None
                and bool(primary_worktree.get("clean"))
                and isinstance(primary_head, str) and primary_head
                and isinstance(selected_head, str) and selected_head
                and is_ancestor(project.canonical_root, primary_head, selected_head)
            ):
                source_consistency = "consistent"
                source_consistency_basis = "active_registered_worktree_descends_clean_primary"
        result.append(
            {
                "schema_version": OBSERVER_WORKSTREAM_SCHEMA,
                "id": workstream_id,
                "title": selected.get("title"),
                "status": selected.get("status"),
                "attention": selected.get("attention"),
                "owner": selected.get("owner"),
                "goal": selected.get("goal"),
                "source_consistency": source_consistency,
                "source_consistency_basis": source_consistency_basis,
                "selected_source": selected.get("source_worktree"),
                "registry": registry,
                "sources": sources,
            }
        )
    return result


def _read_safe_continuation_task(task_dir: Path, workspace_root: Path) -> dict[str, object] | None:
    control = _read_json_object(task_dir / "control.json")
    state = _read_json_object(task_dir / "state.json")
    if control is None or state is None:
        return None
    lease = _read_json_object(task_dir / "lease.json")
    effects = _read_json_object(task_dir / "effects.json")
    rounds = _read_json_object(task_dir / "rounds.json")
    effect_status_counts: dict[str, int] = {}
    unresolved_effect_count = 0
    if effects:
        raw_effects = effects.get("effects")
        if isinstance(raw_effects, list):
            for item in raw_effects:
                if not isinstance(item, dict):
                    continue
                status = str(item.get("status") or "unknown")
                effect_status_counts[status] = effect_status_counts.get(status, 0) + 1
                if status in {"prepared", "active", "unknown"}:
                    unresolved_effect_count += 1
        elif isinstance(raw_effects, dict):
            for item in raw_effects.values():
                if not isinstance(item, dict):
                    continue
                status = str(item.get("status") or "unknown")
                effect_status_counts[status] = effect_status_counts.get(status, 0) + 1
                if status in {"prepared", "active", "unknown"}:
                    unresolved_effect_count += 1
    lease_summary: dict[str, object] | None = None
    if lease:
        lease_liveness = _continuation_lease_liveness(lease, control)
        lease_summary = {
            "present": True,
            "runner_id": lease.get("runner_id"),
            "generation": lease.get("generation"),
            "issued_at": lease.get("issued_at"),
            "expires_at": lease.get("expires_at"),
            "last_heartbeat_at": lease.get("last_heartbeat_at"),
            "last_renew_at": lease.get("last_renew_at"),
            "branch": lease.get("branch"),
            "head": lease.get("head"),
            "liveness": lease_liveness,
        }
    latest_round: dict[str, object] | None = None
    if rounds:
        raw_rounds = rounds.get("rounds")
        if isinstance(raw_rounds, list):
            candidates = [item for item in raw_rounds if isinstance(item, dict)]
            if candidates:
                source = candidates[-1]
                latest_round = {
                    "generation": source.get("generation"),
                    "runner_id": source.get("runner_id"),
                    "phase": source.get("phase"),
                    "milestone": source.get("milestone"),
                    "started_at": source.get("started_at"),
                    "updated_at": source.get("updated_at"),
                    "ended_at": source.get("ended_at"),
                    "evidence_refs": list(source.get("evidence_refs") or []),
                }
    return {
        "schema_version": OBSERVER_CONTINUATION_SCHEMA,
        "task_id": control.get("task_id") or state.get("task_id") or task_dir.name,
        "workstream_id": control.get("workstream_id"),
        "workspace_root": str(workspace_root.resolve()),
        "title": control.get("title"),
        "objective": state.get("objective") or control.get("objective"),
        "stage": state.get("stage"),
        "status": state.get("status"),
        "next_action": state.get("next_action"),
        "state_updated_at": state.get("updated_at"),
        "lease": lease_summary or {"present": False},
        "latest_round": latest_round,
        "effects": {
            "status_counts": effect_status_counts,
            "unresolved_count": unresolved_effect_count,
        },
        "source_dir": str(task_dir),
    }


def capture_project_continuations(
    project: ObserverProject,
    worktrees: list[dict[str, object]],
) -> list[dict[str, object]]:
    continuation_read_home = _observer_continuation_read_home()
    roots: list[Path] = []
    scoped_worktrees = _observer_scope_worktrees(project, worktrees)
    if scoped_worktrees:
        roots.extend(
            Path(str(item["path"]))
            for item in scoped_worktrees
            if isinstance(item.get("path"), str)
        )
    else:
        roots.append(project.invocation_root)
    rows: list[dict[str, object]] = []
    seen_dirs: set[str] = set()
    for root in roots:
        parent = _usage_project_dir_from_home(root.resolve(), continuation_read_home) / "continuation"
        if not parent.is_dir():
            continue
        for task_dir in sorted(path for path in parent.iterdir() if path.is_dir()):
            key = str(task_dir.resolve())
            if key in seen_dirs:
                continue
            seen_dirs.add(key)
            row = _read_safe_continuation_task(task_dir, root)
            if row is not None:
                rows.append(row)
    rows.sort(key=lambda row: (str(row.get("workstream_id") or ""), str(row.get("task_id") or ""), str(row.get("workspace_root") or "")))
    return rows


def _continuations_for_workstream(
    workstream_id: str,
    continuations: list[dict[str, object]],
) -> list[dict[str, object]]:
    rows = [row for row in continuations if row.get("workstream_id") == workstream_id]
    rows.sort(
        key=lambda row: (
            str(row.get("state_updated_at") or ""),
            str(row.get("task_id") or ""),
            str(row.get("workspace_root") or ""),
        )
    )
    return rows


def _continuation_effect_risk(row: dict[str, object]) -> dict[str, object]:
    effects = row.get("effects") if isinstance(row.get("effects"), dict) else {}
    counts = effects.get("status_counts") if isinstance(effects.get("status_counts"), dict) else {}
    prepared = int(counts.get("prepared") or 0)
    active = int(counts.get("active") or 0)
    unknown = int(counts.get("unknown") or 0)
    unresolved = prepared + active + unknown
    lease = row.get("lease") if isinstance(row.get("lease"), dict) else {}
    liveness = lease.get("liveness") if isinstance(lease.get("liveness"), dict) else {}
    lease_state = str(liveness.get("state") or ("absent" if not lease.get("present") else "unknown"))
    if unknown:
        severity = "critical"
        reason = "effect_outcome_unknown"
    elif active and lease_state != "fresh":
        severity = "critical"
        reason = "active_effect_without_fresh_owner"
    elif prepared and lease_state != "fresh":
        severity = "warning"
        reason = "prepared_effect_without_fresh_owner"
    else:
        severity = "none"
        reason = "effects_in_flight_under_fresh_owner" if unresolved else "no_unresolved_effects"
    return {
        "severity": severity,
        "reason": reason,
        "unresolved_count": unresolved,
        "prepared_count": prepared,
        "active_count": active,
        "unknown_count": unknown,
        "lease_liveness": lease_state,
    }


def _continuation_liveness_risk(row: dict[str, object]) -> dict[str, object]:
    """Classify continuation owner liveness without attempting recovery."""

    status = str(row.get("status") or "").casefold()
    latest_round = row.get("latest_round") if isinstance(row.get("latest_round"), dict) else {}
    phase = str(latest_round.get("phase") or "")
    lease = row.get("lease") if isinstance(row.get("lease"), dict) else {}
    present = bool(lease.get("present"))
    liveness = lease.get("liveness") if isinstance(lease.get("liveness"), dict) else {}
    lease_state = str(liveness.get("state") or ("unknown" if present else "absent"))
    if status != "running":
        severity = "none"
        reason = "continuation_not_running"
    elif phase == "waiting_external":
        severity = "none"
        reason = "waiting_external_does_not_require_fresh_writer"
    elif lease_state == "expired":
        severity = "critical"
        reason = "continuation_lease_expired"
    elif lease_state == "stale":
        severity = "warning"
        reason = "continuation_owner_stale"
    elif lease_state in {"absent", "unknown"}:
        severity = "warning"
        reason = "continuation_running_without_fresh_lease"
    else:
        severity = "none"
        reason = "continuation_owner_fresh"
    return {
        "severity": severity,
        "reason": reason,
        "lease_liveness": lease_state,
        "heartbeat_age_seconds": liveness.get("heartbeat_age_seconds"),
        "stale_after_seconds": liveness.get("stale_after_seconds"),
        "expires_at": liveness.get("expires_at") or lease.get("expires_at"),
    }


def _workstream_machine_state(
    workstream: dict[str, object],
    continuations: list[dict[str, object]],
) -> dict[str, object]:
    """Derive conservative machine-facing state without inventing progress.

    This layer intentionally stays below semantic interpretation.  It exposes
    enough normalized signals for later history/semantic stages while keeping
    `progress=unknown` until Observer history can prove movement or stasis.
    """

    workstream_id = str(workstream.get("id") or "")
    related = _continuations_for_workstream(workstream_id, continuations)
    workstream_status = str(workstream.get("status") or "")
    workstream_status_key = workstream_status.casefold()
    signals: list[str] = []

    execution = "idle"
    if workstream_status_key in {"done", "cancelled"}:
        execution = "done"
        signals.append(f"workstream_status:{workstream_status}")
    elif workstream_status_key == "blocked":
        execution = "blocked"
        signals.append("workstream_status:Blocked")
    else:
        round_phases = {
            str((row.get("latest_round") or {}).get("phase") or "")
            for row in related
            if isinstance(row.get("latest_round"), dict)
        }
        continuation_statuses = {str(row.get("status") or "") for row in related}
        lease_present = any(bool((row.get("lease") or {}).get("present")) for row in related if isinstance(row.get("lease"), dict))
        if "waiting_external" in round_phases:
            execution = "waiting_external"
            signals.append("continuation_round:waiting_external")
        elif related and (
            bool(round_phases.intersection({"claimed", "executing", "finalizing", "reconciling"}))
            or "running" in continuation_statuses
            or lease_present
        ):
            execution = "running"
            signals.append("continuation:active")
        elif workstream_status_key in {"active", "merging", "readytomerge"}:
            execution = "idle"
            signals.append(f"workstream_status:{workstream_status}")

    health = "healthy"
    health_reasons: list[str] = []
    if workstream.get("source_consistency") == "divergent":
        health = "warning"
        health_reasons.append("workstream_sources_divergent")
    registry = workstream.get("registry") if isinstance(workstream.get("registry"), dict) else None
    registry_state = str((registry or {}).get("state") or "").casefold()
    if (
        registry is not None
        and workstream_status_key in {"active", "blocked", "readytomerge", "merging"}
        and registry_state != "active"
    ):
        health = "warning"
        health_reasons.append("workstream_registry_not_active")
    liveness_risks = [_continuation_liveness_risk(row) for row in related]
    effect_risks = [_continuation_effect_risk(row) for row in related]
    unresolved_effects = sum(int(risk.get("unresolved_count") or 0) for risk in effect_risks)
    critical_liveness_risks = [risk for risk in liveness_risks if risk.get("severity") == "critical"]
    warning_liveness_risks = [risk for risk in liveness_risks if risk.get("severity") == "warning"]
    critical_effect_risks = [risk for risk in effect_risks if risk.get("severity") == "critical"]
    warning_effect_risks = [risk for risk in effect_risks if risk.get("severity") == "warning"]
    if critical_liveness_risks or critical_effect_risks:
        health = "critical"
        health_reasons.extend(str(risk.get("reason")) for risk in critical_liveness_risks)
        health_reasons.extend(str(risk.get("reason")) for risk in critical_effect_risks)
    elif warning_liveness_risks or warning_effect_risks:
        health = "warning"
        health_reasons.extend(str(risk.get("reason")) for risk in warning_liveness_risks)
        health_reasons.extend(str(risk.get("reason")) for risk in warning_effect_risks)
    elif unresolved_effects:
        signals.append(f"effects_in_flight:{unresolved_effects}")
    if not health_reasons:
        health_reasons.append("no_machine_warning_detected")

    return {
        "schema_version": OBSERVER_MACHINE_STATE_SCHEMA,
        "execution": execution,
        "progress": "unknown",
        "health": health,
        "signals": signals,
        "health_reasons": health_reasons,
        "continuation_count": len(related),
        "progress_basis": "history_not_evaluated",
    }


def enrich_workstream_machine_states(
    workstreams: list[dict[str, object]],
    continuations: list[dict[str, object]],
) -> list[dict[str, object]]:
    enriched: list[dict[str, object]] = []
    for row in workstreams:
        item = dict(row)
        item["machine_state"] = _workstream_machine_state(item, continuations)
        enriched.append(item)
    return enriched


def derive_snapshot_alerts(project: ObserverProject, snapshot: dict[str, object]) -> list[dict[str, object]]:
    observed_at = str(snapshot.get("observed_at") or utc_now_iso())
    alerts: list[dict[str, object]] = []

    def add_alert(**fields: object) -> None:
        alerts.append({
            "schema_version": OBSERVER_ALERT_SCHEMA,
            "project_id": project.project_id,
            "status": "active",
            "observed_at": observed_at,
            **fields,
        })

    consistency = snapshot.get("snapshot_consistency")
    if isinstance(consistency, dict) and consistency.get("state") == "unstable":
        add_alert(
            alert_key="project:snapshot-consistency-unstable",
            severity="critical",
            title="项目状态无法获得稳定一致快照",
            explanation="连续多次读取期间项目事实仍持续变化，本次快照只能作为部分一致观察，不能据此生成高置信度新结论。",
            canonical_identity={"type": "project", "id": project.project_id},
            provenance=[
                {
                    "source": "snapshot_consistency",
                    "first_fingerprint": consistency.get("first_fingerprint"),
                    "second_fingerprint": consistency.get("second_fingerprint"),
                    "final_fingerprint": consistency.get("final_fingerprint"),
                }
            ],
        )

    project_narrative = snapshot.get("project_narrative")
    if isinstance(project_narrative, dict) and project_narrative.get("status") == "stale":
        narrative = project_narrative.get("narrative") if isinstance(project_narrative.get("narrative"), dict) else {}
        add_alert(
            alert_key="project:narrative-stale",
            severity="warning",
            title="Project Narrative 已落后于当前项目 authority",
            explanation="项目地图的 source fingerprint 与当前项目事实或显式 authority 文件不再一致；Dashboard 会保留旧叙事用于追溯，但不会把它当作 current project story。",
            canonical_identity={"type": "project", "id": project.project_id},
            provenance=[
                {
                    "source": "project_narrative",
                    "narrative_version": narrative.get("narrative_version"),
                    "stored_source_fingerprint": narrative.get("source_fingerprint"),
                    "current_source_fingerprint": project_narrative.get("source_fingerprint"),
                    "source_error": project_narrative.get("source_error"),
                }
            ],
        )

    for spec in presentation_alert_specs(snapshot.get("presentation")):
        add_alert(**spec)

    for row in snapshot.get("workstreams") or []:
        if not isinstance(row, dict):
            continue
        workstream_id = str(row.get("id") or "unknown")
        if row.get("source_consistency") == "divergent":
            add_alert(
                alert_key=f"workstream:{workstream_id}:source-divergent",
                severity="critical",
                title=f"{workstream_id} 的权威来源出现不一致",
                explanation="同一 Workstream 的项目级来源在标题、状态、关注度或目标上存在冲突；在来源重新一致前不应把其中任一版本当作确定语义事实。",
                canonical_identity={"type": "workstream", "id": workstream_id},
                provenance=[
                    {
                        "source": "workstream_sources",
                        "source_paths": [
                            item.get("detail_path")
                            for item in row.get("sources") or []
                            if isinstance(item, dict)
                        ],
                    }
                ],
            )
        registry = row.get("registry") if isinstance(row.get("registry"), dict) else None
        workstream_status = str(row.get("status") or "")
        registry_state = str((registry or {}).get("state") or "").casefold()
        if (
            registry is not None
            and workstream_status.casefold() in {"active", "blocked", "readytomerge", "merging"}
            and registry_state != "active"
        ):
            add_alert(
                alert_key=f"workstream:{workstream_id}:registry-lifecycle-mismatch",
                severity="warning",
                title=f"{workstream_id} 的 Worktree registry 与活动状态不一致",
                explanation="Workstream 仍处于活动类状态，但其已绑定 Worktree registry 不是 active；依赖 verified worktree 选择的 ACF 命令可能因此拒绝进入该 Workstream。",
                canonical_identity={"type": "workstream", "id": workstream_id},
                provenance=[
                    {
                        "source": "worktree_registry",
                        "workstream_status": workstream_status,
                        "registry_state": registry.get("state"),
                        "registry_path": registry.get("path"),
                        "registry_branch": registry.get("branch"),
                    }
                ],
            )

    for row in snapshot.get("continuations") or []:
        if not isinstance(row, dict):
            continue
        task_id = str(row.get("task_id") or "unknown")
        liveness_risk = _continuation_liveness_risk(row)
        liveness_severity = str(liveness_risk.get("severity") or "none")
        if liveness_severity != "none":
            if liveness_risk.get("reason") == "continuation_lease_expired":
                title = f"{task_id} 的 continuation lease 已过期"
                explanation = "任务仍标记为 running，但当前 owner lease 已经过期。Observer 只报告该控制面不一致，不执行 challenge、reconcile 或 recovery。"
            elif liveness_risk.get("reason") == "continuation_owner_stale":
                title = f"{task_id} 的 continuation owner 已超过新鲜度阈值"
                explanation = "任务仍标记为 running，但最近 heartbeat 已超过 stale threshold。该状态需要由 continuation contention/recovery 协议处理，Observer 本身不接管。"
            else:
                title = f"{task_id} 正在运行但缺少可确认的新鲜 owner lease"
                explanation = "continuation state 标记为 running，但 Observer 无法确认 fresh lease。应由 continuation 控制面判断 ownership；Observer 只保留告警。"
            add_alert(
                alert_key=f"continuation:{task_id}:owner-liveness",
                severity=liveness_severity,
                title=title,
                explanation=explanation,
                canonical_identity={
                    "type": "continuation",
                    "task_id": task_id,
                    "workstream_id": row.get("workstream_id"),
                },
                provenance=[{"source": "continuation_lease_liveness", **liveness_risk}],
            )
        effects = row.get("effects") if isinstance(row.get("effects"), dict) else {}
        risk = _continuation_effect_risk(row)
        unresolved = int(risk.get("unresolved_count") or 0)
        severity = str(risk.get("severity") or "none")
        if unresolved <= 0 or severity == "none":
            continue
        if risk.get("reason") == "effect_outcome_unknown":
            title = f"{task_id} 存在结果未知的外部副作用"
            explanation = "检测到 unknown effect；在获得外部权威终态前不能安全假定成功、失败或重新提交，Observer 只报告而不执行恢复。"
        elif risk.get("reason") == "active_effect_without_fresh_owner":
            title = f"{task_id} 存在失去新鲜 owner 保护的活动副作用"
            explanation = "检测到 active effect，但当前 continuation lease 已不再 fresh。该外部动作可能仍在运行，需要持久化外部身份与权威终态证据进行恢复判断。"
        else:
            title = f"{task_id} 存在未由新鲜 owner 保护的待执行副作用"
            explanation = "检测到 prepared effect，但当前 continuation lease 已不再 fresh。需要先确认该动作是否真正越过外部提交边界，再决定恢复或终止。"
        add_alert(
            alert_key=f"continuation:{task_id}:unresolved-effects",
            severity=severity,
            title=title,
            explanation=explanation,
            canonical_identity={
                "type": "continuation",
                "task_id": task_id,
                "workstream_id": row.get("workstream_id"),
            },
            provenance=[
                {
                    "source": "continuation_effect_summary",
                    "source_dir": row.get("source_dir"),
                    "status_counts": effects.get("status_counts") or {},
                    "lease_liveness": risk.get("lease_liveness"),
                    "risk_reason": risk.get("reason"),
                }
            ],
        )

    for row in snapshot.get("worktrees") or []:
        if not isinstance(row, dict) or not row.get("read_error"):
            continue
        add_alert(
            alert_key=f"worktree:{path_key(str(row.get('path') or 'unknown'))}:read-error",
            severity="warning",
            title="部分项目 Worktree 无法完成状态读取",
            explanation="Observer 保留了该 Worktree 的基础身份，但无法获得完整 Git 状态；本次项目视图可能缺少该工作区的最新事实。",
            canonical_identity={"type": "worktree", "path": row.get("path")},
            provenance=[{"source": "git_worktree_snapshot", "error": row.get("read_error")}],
        )

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda row: (severity_order.get(str(row.get("severity")), 9), str(row.get("alert_key"))))
    return alerts


def _alert_index(snapshot: dict[str, object] | None) -> dict[str, dict[str, object]]:
    if not snapshot:
        return {}
    rows = snapshot.get("alerts")
    if not isinstance(rows, list):
        return {}
    result: dict[str, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = row.get("alert_key")
        if isinstance(key, str) and key:
            result[key] = row
    return result


def build_alert_lifecycle_events(
    project: ObserverProject,
    previous: dict[str, object] | None,
    current: dict[str, object],
) -> list[dict[str, object]]:
    observed_at = str(current.get("observed_at") or utc_now_iso())
    previous_alerts = _alert_index(previous)
    current_alerts = _alert_index(current)
    if previous is not None and isinstance(previous.get("revision"), int):
        occurrence_anchor = f"revision:{previous['revision']}"
    elif previous and previous.get("observed_at"):
        occurrence_anchor = f"observed_at:{previous['observed_at']}"
    else:
        occurrence_anchor = "__observer_bootstrap__"
    events: list[dict[str, object]] = []
    for alert_key in sorted(set(previous_alerts) | set(current_alerts)):
        before = previous_alerts.get(alert_key)
        after = current_alerts.get(alert_key)
        if before is None and after is not None:
            kind = "opened"
        elif before is not None and after is None:
            kind = "resolved"
        elif before is not None and after is not None:
            comparable_before = {key: before.get(key) for key in ("severity", "title", "explanation", "canonical_identity")}
            comparable_after = {key: after.get(key) for key in ("severity", "title", "explanation", "canonical_identity")}
            if comparable_before == comparable_after:
                continue
            kind = "updated"
        else:
            continue
        identity_payload = {
            "occurrence_anchor": occurrence_anchor,
            "alert_key": alert_key,
            "kind": kind,
            "before": before,
            "after": after,
        }
        source = after or before or {}
        events.append(
            {
                "schema_version": OBSERVER_ALERT_EVENT_SCHEMA,
                "project_id": project.project_id,
                "alert_event_id": _stable_id("alert", identity_payload),
                "observed_at": observed_at,
                "occurrence_anchor": occurrence_anchor,
                "kind": kind,
                "alert_key": alert_key,
                "severity": source.get("severity"),
                "title": source.get("title"),
                "explanation": source.get("explanation"),
                "canonical_identity": source.get("canonical_identity"),
                "before": before,
                "after": after,
                "provenance": source.get("provenance") or [],
            }
        )
    return events


def _stable_id(prefix: str, payload: dict[str, object]) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}-{digest}"


def _observation_projection(snapshot: dict[str, object] | None) -> dict[str, object]:
    """Project durable meaning used for history de-duplication.

    Snapshot consistency deliberately includes volatile facts such as lease
    heartbeat timestamps and exact dirty fingerprints. Those facts are useful
    for proving one read is internally consistent, but they must not create a
    new project-progress observation every hour. Raw facts remain in
    current.json; this projection is only the history-change detector.
    """

    if not snapshot:
        return {"workstreams": [], "continuations": [], "worktrees": []}

    workstreams: list[dict[str, object]] = []
    for workstream_id, row in sorted(_workstream_index(snapshot).items()):
        machine = row.get("machine_state") if isinstance(row.get("machine_state"), dict) else {}
        workstreams.append(
            {
                "id": workstream_id,
                "title": row.get("title"),
                "status": row.get("status"),
                "attention": row.get("attention"),
                "source_consistency": row.get("source_consistency"),
                "execution": machine.get("execution"),
                "progress": machine.get("progress"),
                "health": machine.get("health"),
            }
        )

    continuations: list[dict[str, object]] = []
    for (workstream_id, task_id), row in sorted(_continuation_index(snapshot).items()):
        latest_round = row.get("latest_round") if isinstance(row.get("latest_round"), dict) else {}
        effects = row.get("effects") if isinstance(row.get("effects"), dict) else {}
        continuations.append(
            {
                "workstream_id": workstream_id or None,
                "task_id": task_id,
                "stage": row.get("stage"),
                "status": row.get("status"),
                "next_action": row.get("next_action"),
                "round_phase": latest_round.get("phase"),
                "round_milestone": latest_round.get("milestone"),
                "round_evidence_refs": list(latest_round.get("evidence_refs") or []),
                "effect_status_counts": effects.get("status_counts") or {},
                "unresolved_effect_count": effects.get("unresolved_count") or 0,
            }
        )

    worktrees: list[dict[str, object]] = []
    for _key, row in sorted(_worktree_index(snapshot).items()):
        if row.get("observer_scope") is False:
            continue
        worktrees.append(
            {
                "path": row.get("path"),
                "branch": row.get("branch"),
                "head": row.get("head"),
            }
        )
    return {
        "workstreams": workstreams,
        "continuations": continuations,
        "worktrees": worktrees,
    }


def _observation_fingerprint(snapshot: dict[str, object] | None) -> str | None:
    if not snapshot:
        return None
    return _stable_fingerprint(_observation_projection(snapshot))


def _event_payload(
    project: ObserverProject,
    *,
    observed_at: str,
    occurrence_anchor: str,
    kind: str,
    canonical_identity: dict[str, object],
    before: object,
    after: object,
    source_fingerprint: str,
    previous_observation_fingerprint: str | None,
    current_observation_fingerprint: str | None,
    provenance: list[dict[str, object]],
) -> dict[str, object]:
    identity_payload = {
        "occurrence_anchor": occurrence_anchor,
        "kind": kind,
        "canonical_identity": canonical_identity,
        "before": before,
        "after": after,
        "previous_observation_fingerprint": previous_observation_fingerprint,
        "current_observation_fingerprint": current_observation_fingerprint,
    }
    return {
        "schema_version": OBSERVER_EVENT_SCHEMA,
        "project_id": project.project_id,
        "event_id": _stable_id("event", identity_payload),
        "observed_at": observed_at,
        "occurrence_anchor": occurrence_anchor,
        "kind": kind,
        "canonical_identity": canonical_identity,
        "before": before,
        "after": after,
        "source_fingerprint": source_fingerprint,
        "previous_observation_fingerprint": previous_observation_fingerprint,
        "current_observation_fingerprint": current_observation_fingerprint,
        "provenance": provenance,
        "semantic_interpretation_version": 0,
    }


def _workstream_index(snapshot: dict[str, object] | None) -> dict[str, dict[str, object]]:
    if not snapshot:
        return {}
    rows = snapshot.get("workstreams")
    if not isinstance(rows, list):
        return {}
    result: dict[str, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        workstream_id = row.get("id")
        if isinstance(workstream_id, str) and workstream_id:
            result[workstream_id] = row
    return result


def _continuation_index(snapshot: dict[str, object] | None) -> dict[tuple[str, str], dict[str, object]]:
    if not snapshot:
        return {}
    rows = snapshot.get("continuations")
    if not isinstance(rows, list):
        return {}
    result: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        task_id = row.get("task_id")
        workstream_id = row.get("workstream_id")
        if isinstance(task_id, str) and task_id:
            result[(str(workstream_id or ""), task_id)] = row
    return result


def _worktree_index(snapshot: dict[str, object] | None) -> dict[str, dict[str, object]]:
    if not snapshot:
        return {}
    rows = snapshot.get("worktrees")
    if not isinstance(rows, list):
        return {}
    result: dict[str, dict[str, object]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        raw_path = row.get("path")
        if isinstance(raw_path, str) and raw_path:
            result[path_key(raw_path)] = row
    return result


def build_meaningful_events(
    project: ObserverProject,
    previous: dict[str, object] | None,
    current: dict[str, object],
) -> list[dict[str, object]]:
    """Build durable machine events from meaningful state transitions.

    Events intentionally capture durable project movement rather than every
    dirty-file fluctuation.  Semantic interpretation can later enrich these
    records without rewriting the canonical machine transition.
    """

    observed_at = str(current.get("observed_at") or utc_now_iso())
    # Anchor one transition occurrence to the last successfully persisted
    # current snapshot.  This keeps event IDs stable across a retry after an
    # interrupted append (the previous current snapshot has not advanced),
    # while allowing the same semantic transition to happen legitimately
    # again later without being de-duplicated out of permanent history.
    if previous is not None and isinstance(previous.get("revision"), int):
        occurrence_anchor = f"revision:{previous['revision']}"
    elif previous is not None and previous.get("observed_at"):
        # Backward-compatible anchor for state written before current revision
        # numbers were introduced.
        occurrence_anchor = f"observed_at:{previous['observed_at']}"
    else:
        occurrence_anchor = "__observer_bootstrap__"
    consistency = current.get("snapshot_consistency")
    source_fingerprint = ""
    if isinstance(consistency, dict):
        source_fingerprint = str(consistency.get("final_fingerprint") or "")
    previous_observation_fingerprint = _observation_fingerprint(previous)
    current_observation_fingerprint = _observation_fingerprint(current)
    provenance = [
        {
            "source": "observer_snapshot",
            "observed_at": observed_at,
            "snapshot_fingerprint": source_fingerprint,
        }
    ]
    events: list[dict[str, object]] = []
    previous_workstreams = _workstream_index(previous)
    current_workstreams = _workstream_index(current)
    for workstream_id, row in sorted(current_workstreams.items()):
        identity = {"type": "workstream", "id": workstream_id}
        before = previous_workstreams.get(workstream_id)
        if before is None:
            events.append(
                _event_payload(
                    project,
                    observed_at=observed_at,
                    occurrence_anchor=occurrence_anchor,
                    kind="workstream_discovered",
                    canonical_identity=identity,
                    before=None,
                    after={"status": row.get("status"), "title": row.get("title")},
                    source_fingerprint=source_fingerprint,
                    previous_observation_fingerprint=previous_observation_fingerprint,
                    current_observation_fingerprint=current_observation_fingerprint,
                    provenance=provenance,
                )
            )
            continue
        for kind, before_value, after_value in (
            ("workstream_status_changed", before.get("status"), row.get("status")),
            ("workstream_source_consistency_changed", before.get("source_consistency"), row.get("source_consistency")),
            (
                "workstream_execution_changed",
                (before.get("machine_state") or {}).get("execution") if isinstance(before.get("machine_state"), dict) else None,
                (row.get("machine_state") or {}).get("execution") if isinstance(row.get("machine_state"), dict) else None,
            ),
            (
                "workstream_health_changed",
                (before.get("machine_state") or {}).get("health") if isinstance(before.get("machine_state"), dict) else None,
                (row.get("machine_state") or {}).get("health") if isinstance(row.get("machine_state"), dict) else None,
            ),
        ):
            if before_value == after_value:
                continue
            events.append(
                _event_payload(
                    project,
                    observed_at=observed_at,
                    occurrence_anchor=occurrence_anchor,
                    kind=kind,
                    canonical_identity=identity,
                    before=before_value,
                    after=after_value,
                    source_fingerprint=source_fingerprint,
                    previous_observation_fingerprint=previous_observation_fingerprint,
                    current_observation_fingerprint=current_observation_fingerprint,
                    provenance=provenance,
                )
            )

    previous_continuations = _continuation_index(previous)
    current_continuations = _continuation_index(current)
    for key, row in sorted(current_continuations.items()):
        workstream_id, task_id = key
        identity = {"type": "continuation", "workstream_id": workstream_id or None, "task_id": task_id}
        before = previous_continuations.get(key)
        if before is None:
            events.append(
                _event_payload(
                    project,
                    observed_at=observed_at,
                    occurrence_anchor=occurrence_anchor,
                    kind="continuation_discovered",
                    canonical_identity=identity,
                    before=None,
                    after={"stage": row.get("stage"), "status": row.get("status")},
                    source_fingerprint=source_fingerprint,
                    previous_observation_fingerprint=previous_observation_fingerprint,
                    current_observation_fingerprint=current_observation_fingerprint,
                    provenance=provenance,
                )
            )
            continue
        for kind, before_value, after_value in (
            ("continuation_stage_changed", before.get("stage"), row.get("stage")),
            ("continuation_status_changed", before.get("status"), row.get("status")),
            ("continuation_next_action_changed", before.get("next_action"), row.get("next_action")),
            (
                "continuation_round_phase_changed",
                (before.get("latest_round") or {}).get("phase") if isinstance(before.get("latest_round"), dict) else None,
                (row.get("latest_round") or {}).get("phase") if isinstance(row.get("latest_round"), dict) else None,
            ),
        ):
            if before_value == after_value:
                continue
            events.append(
                _event_payload(
                    project,
                    observed_at=observed_at,
                    occurrence_anchor=occurrence_anchor,
                    kind=kind,
                    canonical_identity=identity,
                    before=before_value,
                    after=after_value,
                    source_fingerprint=source_fingerprint,
                    previous_observation_fingerprint=previous_observation_fingerprint,
                    current_observation_fingerprint=current_observation_fingerprint,
                    provenance=provenance,
                )
            )

    previous_worktrees = _worktree_index(previous)
    current_worktrees = _worktree_index(current)
    for key, row in sorted(current_worktrees.items()):
        if row.get("observer_scope") is False:
            continue
        identity = {"type": "worktree", "path": row.get("path")}
        before = previous_worktrees.get(key)
        if before is None:
            events.append(
                _event_payload(
                    project,
                    observed_at=observed_at,
                    occurrence_anchor=occurrence_anchor,
                    kind="worktree_discovered",
                    canonical_identity=identity,
                    before=None,
                    after={"head": row.get("head"), "branch": row.get("branch")},
                    source_fingerprint=source_fingerprint,
                    previous_observation_fingerprint=previous_observation_fingerprint,
                    current_observation_fingerprint=current_observation_fingerprint,
                    provenance=provenance,
                )
            )
            continue
        if before.get("head") != row.get("head"):
            events.append(
                _event_payload(
                    project,
                    observed_at=observed_at,
                    occurrence_anchor=occurrence_anchor,
                    kind="worktree_head_changed",
                    canonical_identity=identity,
                    before=before.get("head"),
                    after=row.get("head"),
                    source_fingerprint=source_fingerprint,
                    previous_observation_fingerprint=previous_observation_fingerprint,
                    current_observation_fingerprint=current_observation_fingerprint,
                    provenance=provenance,
                )
            )
    return events


def build_observation_record(
    project: ObserverProject,
    previous: dict[str, object] | None,
    current: dict[str, object],
    events: list[dict[str, object]],
) -> dict[str, object] | None:
    consistency = current.get("snapshot_consistency")
    source_snapshot_fingerprint = (
        str(consistency.get("final_fingerprint") or "") if isinstance(consistency, dict) else ""
    )
    current_fingerprint = _observation_fingerprint(current) or ""
    previous_fingerprint = _observation_fingerprint(previous)
    if previous is not None and previous_fingerprint == current_fingerprint and not events:
        return None
    observed_at = str(current.get("observed_at") or utc_now_iso())
    identity_payload = {
        "project_id": project.project_id,
        "current_fingerprint": current_fingerprint,
        "event_ids": [event.get("event_id") for event in events],
    }
    workstreams = _workstream_index(current)
    return {
        "schema_version": OBSERVER_OBSERVATION_SCHEMA,
        "project_id": project.project_id,
        "observation_id": _stable_id("observation", identity_payload),
        "observed_at": observed_at,
        "current_fingerprint": current_fingerprint,
        "previous_fingerprint": previous_fingerprint,
        "source_snapshot_fingerprint": source_snapshot_fingerprint,
        "meaningful_event_ids": [event.get("event_id") for event in events],
        "workstream_states": {
            workstream_id: {
                "status": row.get("status"),
                "execution": (row.get("machine_state") or {}).get("execution") if isinstance(row.get("machine_state"), dict) else None,
                "progress": (row.get("machine_state") or {}).get("progress") if isinstance(row.get("machine_state"), dict) else None,
                "health": (row.get("machine_state") or {}).get("health") if isinstance(row.get("machine_state"), dict) else None,
            }
            for workstream_id, row in sorted(workstreams.items())
        },
        "provenance": [
            {
                "source": "observer_snapshot",
                "snapshot_fingerprint": source_snapshot_fingerprint,
                "observation_fingerprint": current_fingerprint,
                "observed_at": observed_at,
            }
        ],
        "semantic_interpretation_version": 0,
    }


def _unchanged_milestone_seconds(elapsed_seconds: float) -> int | None:
    if elapsed_seconds < OBSERVER_FIRST_UNCHANGED_MILESTONE_SECONDS:
        return None
    if elapsed_seconds < OBSERVER_SECOND_UNCHANGED_MILESTONE_SECONDS:
        return OBSERVER_FIRST_UNCHANGED_MILESTONE_SECONDS
    if elapsed_seconds < OBSERVER_DAILY_UNCHANGED_MILESTONE_SECONDS:
        return OBSERVER_SECOND_UNCHANGED_MILESTONE_SECONDS
    complete_days = max(1, int(elapsed_seconds // OBSERVER_DAILY_UNCHANGED_MILESTONE_SECONDS))
    return complete_days * OBSERVER_DAILY_UNCHANGED_MILESTONE_SECONDS


def build_unchanged_milestone_observation(
    project: ObserverProject,
    current: dict[str, object],
) -> dict[str, object] | None:
    """Record sparse liveness milestones when project meaning is unchanged.

    This deliberately does not copy the full snapshot every hour.  The first
    unchanged milestone is emitted after six hours, the second after twelve,
    and then once per completed day.  Each milestone is anchored to the last
    observation that represented a real project-state change, so retries are
    idempotent even when history has already rotated.
    """

    rows = read_observer_history_stream(project, "observations")
    meaningful = [row for row in rows if row.get("observation_kind") != "unchanged_milestone"]
    if not meaningful:
        return None
    anchor = meaningful[-1]
    anchor_at = _parse_utc_iso(anchor.get("observed_at"))
    current_at = _parse_utc_iso(current.get("observed_at"))
    if anchor_at is None or current_at is None or current_at <= anchor_at:
        return None
    current_fingerprint = _observation_fingerprint(current) or ""
    if anchor.get("current_fingerprint") != current_fingerprint:
        return None
    elapsed_seconds = (current_at - anchor_at).total_seconds()
    milestone_seconds = _unchanged_milestone_seconds(elapsed_seconds)
    if milestone_seconds is None:
        return None
    anchor_id = str(anchor.get("observation_id") or "")
    for row in rows:
        if (
            row.get("observation_kind") == "unchanged_milestone"
            and row.get("anchor_observation_id") == anchor_id
            and row.get("milestone_seconds") == milestone_seconds
        ):
            return None

    workstreams = _workstream_index(current)
    identity_payload = {
        "project_id": project.project_id,
        "anchor_observation_id": anchor_id,
        "current_fingerprint": current_fingerprint,
        "milestone_seconds": milestone_seconds,
    }
    return {
        "schema_version": OBSERVER_OBSERVATION_SCHEMA,
        "project_id": project.project_id,
        "observation_id": _stable_id("observation", identity_payload),
        "observation_kind": "unchanged_milestone",
        "observed_at": str(current.get("observed_at") or utc_now_iso()),
        "anchor_observation_id": anchor_id,
        "anchor_observed_at": anchor.get("observed_at"),
        "milestone_seconds": milestone_seconds,
        "unchanged_for_seconds": int(elapsed_seconds),
        "current_fingerprint": current_fingerprint,
        "previous_fingerprint": current_fingerprint,
        "source_snapshot_fingerprint": (
            (current.get("snapshot_consistency") or {}).get("final_fingerprint")
            if isinstance(current.get("snapshot_consistency"), dict)
            else None
        ),
        "meaningful_event_ids": [],
        "workstream_states": {
            workstream_id: {
                "status": row.get("status"),
                "execution": (row.get("machine_state") or {}).get("execution")
                if isinstance(row.get("machine_state"), dict)
                else None,
                "progress": "unchanged",
                "health": (row.get("machine_state") or {}).get("health")
                if isinstance(row.get("machine_state"), dict)
                else None,
            }
            for workstream_id, row in sorted(workstreams.items())
        },
        "provenance": [
            {
                "source": "observer_unchanged_milestone",
                "anchor_observation_id": anchor_id,
                "anchor_observed_at": anchor.get("observed_at"),
                "milestone_seconds": milestone_seconds,
            }
        ],
        "semantic_interpretation_version": 0,
    }


def _capture_project_facts(project: ObserverProject) -> dict[str, object]:
    worktrees = capture_project_worktrees(project)
    workstreams = capture_project_workstreams(project, worktrees)
    continuations = capture_project_continuations(project, worktrees)
    workstreams = enrich_workstream_machine_states(workstreams, continuations)
    return {
        "worktrees": worktrees,
        "workstreams": workstreams,
        "continuations": continuations,
    }


def _consistency_projection(value: object) -> object:
    """Remove derived wall-clock fields from source-fact consistency checks."""

    if isinstance(value, dict):
        return {
            key: _consistency_projection(item)
            for key, item in value.items()
            if key not in {"heartbeat_age_seconds"}
        }
    if isinstance(value, list):
        return [_consistency_projection(item) for item in value]
    return value


def _stable_fingerprint(facts: dict[str, object]) -> str:
    text = json.dumps(
        _consistency_projection(facts),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_observer_snapshot(
    project: ObserverProject,
    *,
    previous_revision: int = 0,
) -> dict[str, object]:
    observed_at = utc_now_iso()
    first = _capture_project_facts(project)
    first_digest = _stable_fingerprint(first)
    second = _capture_project_facts(project)
    second_digest = _stable_fingerprint(second)
    stable = first_digest == second_digest
    final = second if stable else _capture_project_facts(project)
    final_digest = _stable_fingerprint(final)
    consistency = "stable" if stable or second_digest == final_digest else "unstable"
    attempts = 2 if stable else 3
    worktrees = list(final.get("worktrees") or [])
    workstreams = list(final.get("workstreams") or [])
    continuations = list(final.get("continuations") or [])
    workstreams, semantic_summary = attach_semantic_interpretations(project, workstreams, continuations)
    narrative_summary = project_narrative_status(project, workstreams, continuations)
    target_views = build_target_views(project, {"workstreams": workstreams, "continuations": continuations})
    target_presentation = attach_presentation_status(project, target_views)
    snapshot = {
        "schema_version": OBSERVER_CURRENT_SCHEMA,
        "project_id": project.project_id,
        "revision": previous_revision + 1,
        "observed_at": observed_at,
        "project": project.to_payload(),
        "snapshot_consistency": {
            "state": consistency,
            "attempts": attempts,
            "first_fingerprint": first_digest,
            "second_fingerprint": second_digest,
            "final_fingerprint": final_digest,
        },
        "worktrees": worktrees,
        "workstream_count": len(workstreams),
        "workstreams": workstreams,
        "continuation_count": len(continuations),
        "continuations": continuations,
        "alerts": [],
        "semantic": semantic_summary,
        "project_narrative": narrative_summary,
        "targets": target_views,
        "presentation": target_presentation,
    }
    snapshot["alerts"] = derive_snapshot_alerts(project, snapshot)
    sanitized = sanitize_observer_payload(snapshot)
    if not isinstance(sanitized, dict):
        raise TypeError("Observer snapshot sanitization must preserve object shape")
    return sanitized


def _estimate_observer_cadence_seconds(
    runs_path: Path,
    history_root: Path | None = None,
) -> tuple[float | None, int]:
    successful_times: list[datetime] = []
    rows = _read_jsonl_objects(runs_path)
    if history_root is not None:
        for shard_path in sorted((history_root / "runs").glob("*.jsonl")):
            rows.extend(_read_jsonl_objects(shard_path))
    seen_run_ids: set[str] = set()
    for row in rows:
        if row.get("status") != "success":
            continue
        run_id = row.get("run_id")
        if isinstance(run_id, str) and run_id:
            if run_id in seen_run_ids:
                continue
            seen_run_ids.add(run_id)
        parsed = _parse_utc_iso(row.get("started_at"))
        if parsed is not None:
            successful_times.append(parsed)
    successful_times = sorted(successful_times)[-9:]
    intervals = [
        (right - left).total_seconds()
        for left, right in zip(successful_times, successful_times[1:])
        if (right - left).total_seconds() > 0
    ]
    if len(intervals) < 2:
        return None, len(intervals)
    return float(statistics.median(intervals)), len(intervals)


def observer_data_age(
    current: dict[str, object] | None,
    runs_path: Path,
    history_root: Path | None = None,
) -> dict[str, object]:
    if current is None:
        return {
            "state": "missing",
            "age_seconds": None,
            "observed_at": None,
            "expected_interval_seconds": None,
            "cadence_sample_count": 0,
            "stale_after_seconds": None,
            "critical_after_seconds": None,
        }
    observed = _parse_utc_iso(current.get("observed_at"))
    age_seconds = max(0.0, (datetime.now(timezone.utc) - observed).total_seconds()) if observed else None
    expected_interval, sample_count = _estimate_observer_cadence_seconds(runs_path, history_root)
    stale_after: float | None = None
    critical_after: float | None = None
    freshness = "unknown"
    if age_seconds is None:
        freshness = "unknown"
    elif expected_interval is not None:
        stale_after = max(OBSERVER_MIN_STALE_WINDOW_SECONDS, expected_interval * 2)
        critical_after = max(OBSERVER_MIN_CRITICAL_WINDOW_SECONDS, expected_interval * 6)
        if age_seconds > critical_after:
            freshness = "critical"
        elif age_seconds > stale_after:
            freshness = "stale"
        else:
            freshness = "fresh"
    return {
        "state": freshness,
        "age_seconds": round(age_seconds, 3) if age_seconds is not None else None,
        "observed_at": current.get("observed_at"),
        "expected_interval_seconds": round(expected_interval, 3) if expected_interval is not None else None,
        "cadence_sample_count": sample_count,
        "stale_after_seconds": round(stale_after, 3) if stale_after is not None else None,
        "critical_after_seconds": round(critical_after, 3) if critical_after is not None else None,
    }


def observer_snapshot(project: ObserverProject) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    run_id = str(uuid.uuid4())
    started_at = utc_now_iso()
    started = time.perf_counter()
    paths = observer_paths(project)
    lock_path, recovered_lock_owner = acquire_observer_lock(project, run_id)
    try:
        try:
            previous_current = _read_json_object(paths["current"])
            previous_revision = (
                int(previous_current.get("revision"))
                if previous_current is not None and isinstance(previous_current.get("revision"), int)
                else 0
            )
            current = build_observer_snapshot(project, previous_revision=previous_revision)
            ensure_jsonl_file(paths["timeline"])
            ensure_jsonl_file(paths["observations"])
            ensure_jsonl_file(paths["alerts"])
            ensure_jsonl_file(paths["runs"])
            rotations = rotate_observer_history(project)
            events = build_meaningful_events(project, previous_current, current)
            appended_event_count = 0
            for event in events:
                if append_jsonl_unique(paths["timeline"], event, id_field="event_id"):
                    appended_event_count += 1
            observation = build_observation_record(project, previous_current, current, events)
            if observation is None:
                observation = build_unchanged_milestone_observation(project, current)
            observation_recorded = False
            if observation is not None:
                observation_recorded = append_jsonl_unique(
                    paths["observations"],
                    observation,
                    id_field="observation_id",
                )
            alert_events = build_alert_lifecycle_events(project, previous_current, current)
            appended_alert_event_count = 0
            for alert_event in alert_events:
                if append_jsonl_unique(paths["alerts"], alert_event, id_field="alert_event_id"):
                    appended_alert_event_count += 1
            finished_at = utc_now_iso()
            duration_ms = int((time.perf_counter() - started) * 1000)
            run = {
                "schema_version": OBSERVER_RUN_SCHEMA,
                "project_id": project.project_id,
                "run_id": run_id,
                "started_at": started_at,
                "finished_at": finished_at,
                "status": "success",
                "workstreams_scanned": int(current.get("workstream_count") or 0),
                "worktrees_scanned": len(current.get("worktrees") or []),
                "snapshot_consistency": (current.get("snapshot_consistency") or {}).get("state"),
                "meaningful_event_count": appended_event_count,
                "alert_event_count": appended_alert_event_count,
                "observation_recorded": observation_recorded,
                "observation_kind": observation.get("observation_kind", "state_change")
                if observation_recorded and observation is not None
                else None,
                "history_rotation_count": sum(int(item.get("records_moved") or 0) for item in rotations),
                "stale_lock_recovered": recovered_lock_owner is not None,
                "recovered_lock_owner": recovered_lock_owner,
                "duration_ms": duration_ms,
            }
            previous_status = _read_json_object(paths["status"]) or {}
            data_age = observer_data_age(current, paths["runs"], paths["history"])
            status = observer_status_payload(
                project,
                acf_version=VERSION,
                last_started=started_at,
                last_success=finished_at,
                last_failure=previous_status.get("last_failure") if isinstance(previous_status.get("last_failure"), str) else None,
                last_duration_ms=duration_ms,
                last_run_id=run_id,
                last_run_status="success",
                worktrees_scanned=len(current.get("worktrees") or []),
                errors=[],
                data_age=data_age,
            )
            write_json_atomic(paths["current"], current)
            try:
                dashboard = write_dashboard(
                    project,
                    current=current,
                    status=status,
                    machine_events=read_observer_history_stream(project, "timeline"),
                    interpretations=read_observer_history_stream(project, "interpretations"),
                    glossary=read_glossary(project),
                )
                status["dashboard"] = dashboard
                run["dashboard_render_status"] = "success"
            except Exception as dashboard_exc:
                status["dashboard"] = {
                    "status": "failed",
                    "failed_at": utc_now_iso(),
                    "path": str(paths["dashboard"]),
                    "error": str(dashboard_exc),
                }
                run["dashboard_render_status"] = "failed"
                run["dashboard_render_error"] = str(dashboard_exc)
            append_jsonl(paths["runs"], run)
            # The rotation pass happens before this run's new records are
            # appended. Refresh the index after the append so consumers see a
            # complete archived + live history count for the just-finished
            # successful run.
            refresh_history_index(project)
            status["data_age"] = observer_data_age(current, paths["runs"], paths["history"])
            write_json_atomic(paths["status"], status)
            return current, run, status
        except Exception as exc:
            finished_at = utc_now_iso()
            duration_ms = int((time.perf_counter() - started) * 1000)
            failure = {
                "schema_version": OBSERVER_RUN_SCHEMA,
                "project_id": project.project_id,
                "run_id": run_id,
                "started_at": started_at,
                "finished_at": finished_at,
                "status": "failed",
                "error": str(exc),
                "duration_ms": duration_ms,
            }
            previous_status = _read_json_object(paths["status"]) or {}
            data_age = observer_data_age(_read_json_object(paths["current"]), paths["runs"], paths["history"])
            status = observer_status_payload(
                project,
                acf_version=VERSION,
                last_started=started_at,
                last_success=previous_status.get("last_success") if isinstance(previous_status.get("last_success"), str) else None,
                last_failure=finished_at,
                last_duration_ms=duration_ms,
                last_run_id=run_id,
                last_run_status="failed",
                worktrees_scanned=0,
                errors=[str(exc)],
                data_age=data_age,
            )
            try:
                append_jsonl(paths["runs"], failure)
                write_json_atomic(paths["status"], status)
            finally:
                pass
            raise
    finally:
        release_observer_lock(lock_path, run_id)


def observer_status(project: ObserverProject) -> dict[str, object]:
    paths = observer_paths(project)
    current = _read_json_object(paths["current"])
    status = _read_json_object(paths["status"])
    lock = _read_json_object(paths["lock"])
    history_index = _read_json_object(paths["history_index"])
    data_age = observer_data_age(current, paths["runs"], paths["history"])
    lock_health = observer_lock_health(lock)
    self_health_alerts: list[dict[str, object]] = []
    if data_age.get("state") in {"stale", "critical"}:
        severity = "critical" if data_age.get("state") == "critical" else "warning"
        self_health_alerts.append(
            {
                "schema_version": OBSERVER_ALERT_SCHEMA,
                "project_id": project.project_id,
                "alert_key": "observer:data-age",
                "severity": severity,
                "status": "active",
                "title": "Observer 数据已明显陈旧" if severity == "critical" else "Observer 数据更新时间超出常规节奏",
                "explanation": "该提示来自 Observer 自身运行历史推断的常规刷新节奏；项目本身可能仍在变化，请不要把旧 Dashboard 当作当前实时状态。",
                "canonical_identity": {"type": "observer", "project_id": project.project_id},
                "observed_at": utc_now_iso(),
                "provenance": [{"source": "observer_data_age", **data_age}],
            }
        )
    if status is not None:
        last_failure = _parse_utc_iso(status.get("last_failure"))
        last_success = _parse_utc_iso(status.get("last_success"))
        latest_failed = status.get("last_run_status") == "failed" or (
            last_failure is not None and (last_success is None or last_failure > last_success)
        )
        if latest_failed:
            self_health_alerts.append(
                {
                    "schema_version": OBSERVER_ALERT_SCHEMA,
                    "project_id": project.project_id,
                    "alert_key": "observer:last-run-failed",
                    "severity": "critical" if last_success is None else "warning",
                    "status": "active",
                    "title": "Observer 最近一次更新失败",
                    "explanation": "上一份成功快照仍被保留，但最近一次 Observer 运行没有完成；应结合 data age 判断 Dashboard 是否已经陈旧。",
                    "canonical_identity": {"type": "observer", "project_id": project.project_id},
                    "observed_at": utc_now_iso(),
                    "provenance": [
                        {
                            "source": "observer_status",
                            "last_failure": status.get("last_failure"),
                            "last_success": status.get("last_success"),
                            "errors": status.get("errors") or [],
                        }
                    ],
                }
            )
        dashboard = status.get("dashboard") if isinstance(status.get("dashboard"), dict) else {}
        if dashboard.get("status") == "failed":
            self_health_alerts.append(
                {
                    "schema_version": OBSERVER_ALERT_SCHEMA,
                    "project_id": project.project_id,
                    "alert_key": "observer:dashboard-render-failed",
                    "severity": "warning",
                    "status": "active",
                    "title": "Observer Dashboard 最近一次渲染失败",
                    "explanation": "结构化 Observer state 已保留；上一份有效 Dashboard 未被半写覆盖。请以 current/status 为事实，并修复 renderer 后重新生成静态 HTML。",
                    "canonical_identity": {"type": "observer", "project_id": project.project_id},
                    "observed_at": utc_now_iso(),
                    "provenance": [{"source": "observer_status.dashboard", **dashboard}],
                }
            )
    if lock_health.get("state") == "abandoned":
        self_health_alerts.append(
            {
                "schema_version": OBSERVER_ALERT_SCHEMA,
                "project_id": project.project_id,
                "alert_key": "observer:abandoned-lock",
                "severity": "warning",
                "status": "active",
                "title": "Observer 检测到可回收的遗留锁",
                "explanation": "锁对应进程已经明确不存在且超过保护宽限期；下一次写入型 Observer 运行可按安全锁协议回收，不需要修改 Writer 控制面。",
                "canonical_identity": {"type": "observer", "project_id": project.project_id},
                "observed_at": utc_now_iso(),
                "provenance": [{"source": "observer_lock_health", **lock_health}],
            }
        )
    return {
        "project": project.to_payload(),
        "observer_dir": str(project.observer_dir),
        "initialized": current is not None or status is not None,
        "current_path": str(paths["current"]),
        "status_path": str(paths["status"]),
        "runs_path": str(paths["runs"]),
        "timeline_path": str(paths["timeline"]),
        "observations_path": str(paths["observations"]),
        "dashboard_path": str(paths["dashboard"]),
        "history_index_path": str(paths["history_index"]),
        "lock": lock,
        "lock_health": lock_health,
        "current": current,
        "self_health": status,
        "data_age": data_age,
        "self_health_alerts": self_health_alerts,
        "history_index": history_index,
    }
