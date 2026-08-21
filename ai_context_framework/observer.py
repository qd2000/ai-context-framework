"""Project-level Observer storage, locking, and read-only snapshot primitives.

The Observer is intentionally separate from continuation ownership/control.
It may read broadly from one Git project, but its runtime writes are confined
to the user-level ACF state directory under ``~/.acf/projects/.../observer``.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ai_context_framework.front_matter import parse_front_matter
from ai_context_framework.git_support import (
    GitCommandError,
    discover_git_project,
    list_registries,
    list_worktrees,
    path_key,
)
from ai_context_framework.observability import acf_home, atomic_write_text, usage_project_dir
from ai_context_framework.paths import discover_context, resolve_status_location, slugify_project_name
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


class ObserverLockedError(RuntimeError):
    def __init__(self, path: Path, owner: dict[str, object] | None = None):
        self.path = path
        self.owner = owner or {}
        super().__init__(f"observer_locked: {path}")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


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


def observer_paths(project: ObserverProject) -> dict[str, Path]:
    root = project.observer_dir
    return {
        "root": root,
        "current": root / "state" / "current.json",
        "timeline": root / "state" / "timeline.jsonl",
        "observations": root / "state" / "observations.jsonl",
        "alerts": root / "state" / "alerts.jsonl",
        "runs": root / "state" / "runs.jsonl",
        "status": root / "observer_status.json",
        "lock": root / "lock.json",
        "dashboard": root / "dashboard.html",
    }


def _read_json_object(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def append_jsonl(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            # Some virtual filesystems do not support fsync; the append remains
            # valid and the Observer lock still prevents concurrent writers.
            pass


def ensure_jsonl_file(path: Path) -> None:
    if path.exists():
        return
    atomic_write_text(path, "")


def _jsonl_contains_id(path: Path, *, field: str, value: str) -> bool:
    if not path.is_file():
        return False
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict) and payload.get(field) == value:
                    return True
    except OSError:
        return False
    return False


def append_jsonl_unique(path: Path, payload: dict[str, object], *, id_field: str) -> bool:
    raw_id = payload.get(id_field)
    if not isinstance(raw_id, str) or not raw_id:
        raise ValueError(f"{id_field} must be a non-empty string")
    if _jsonl_contains_id(path, field=id_field, value=raw_id):
        return False
    append_jsonl(path, payload)
    return True


def acquire_observer_lock(project: ObserverProject, run_id: str) -> Path:
    paths = observer_paths(project)
    lock_path = paths["lock"]
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": OBSERVER_LOCK_SCHEMA,
        "project_id": project.project_id,
        "run_id": run_id,
        "pid": os.getpid(),
        "started_at": utc_now_iso(),
    }
    try:
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ObserverLockedError(lock_path, _read_json_object(lock_path)) from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            handle.flush()
            try:
                os.fsync(handle.fileno())
            except OSError:
                pass
    except Exception:
        try:
            lock_path.unlink()
        except OSError:
            pass
        raise
    return lock_path


def release_observer_lock(lock_path: Path, run_id: str) -> None:
    current = _read_json_object(lock_path)
    if current is not None and current.get("run_id") != run_id:
        return
    try:
        lock_path.unlink()
    except FileNotFoundError:
        return


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
        occurrences.extend(_workstream_occurrences_for_root(root))
    registry_rows = _safe_registry_rows(project)
    by_id: dict[str, list[dict[str, object]]] = {}
    for row in occurrences:
        workstream_id = row.get("id")
        if isinstance(workstream_id, str) and workstream_id:
            by_id.setdefault(workstream_id, []).append(row)

    result: list[dict[str, object]] = []
    for workstream_id in sorted(by_id):
        sources = by_id[workstream_id]
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
                path_key(str(row["source_worktree"])) == path_key(project.canonical_root)
                or (
                    (source_registry := registry_by_path.get(path_key(str(row["source_worktree"])))) is not None
                    and (
                        source_registry.get("workstream") == workstream_id
                        or source_registry.get("key") == workstream_id
                    )
                )
            )
        ]
        if authoritative_sources:
            sources = authoritative_sources
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
                    and path_key(str(row["source_worktree"])) == path_key(project.canonical_root)
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
        result.append(
            {
                "schema_version": OBSERVER_WORKSTREAM_SCHEMA,
                "id": workstream_id,
                "title": selected.get("title"),
                "status": selected.get("status"),
                "attention": selected.get("attention"),
                "owner": selected.get("owner"),
                "goal": selected.get("goal"),
                "source_consistency": "consistent" if len(comparable) <= 1 else "divergent",
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
        parent = usage_project_dir(root.resolve()) / "continuation"
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
    unresolved_effects = sum(
        int((row.get("effects") or {}).get("unresolved_count") or 0)
        for row in related
        if isinstance(row.get("effects"), dict)
    )
    if unresolved_effects:
        health = "warning"
        health_reasons.append(f"unresolved_effects:{unresolved_effects}")
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


def _stable_fingerprint(facts: dict[str, object]) -> str:
    text = json.dumps(facts, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
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
    return {
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
        "semantic": {
            "schema_version": "acf.observer.semantic.v1",
            "interpretation_version": 1,
            "status": "not_interpreted",
            "note": "Semantic Workstream interpretation is populated by a later Observer stage.",
        },
    }


def _status_payload(
    project: ObserverProject,
    *,
    last_started: str | None,
    last_success: str | None,
    last_failure: str | None,
    last_duration_ms: int | None,
    last_run_id: str | None,
    worktrees_scanned: int,
    errors: list[str],
) -> dict[str, object]:
    return {
        "schema_version": OBSERVER_STATUS_SCHEMA,
        "project_id": project.project_id,
        "last_started": last_started,
        "last_success": last_success,
        "last_failure": last_failure,
        "last_duration_ms": last_duration_ms,
        "last_run_id": last_run_id,
        "worktrees_scanned": worktrees_scanned,
        "errors": errors,
    }


def observer_snapshot(project: ObserverProject) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    run_id = str(uuid.uuid4())
    started_at = utc_now_iso()
    started = time.perf_counter()
    paths = observer_paths(project)
    lock_path = acquire_observer_lock(project, run_id)
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
            events = build_meaningful_events(project, previous_current, current)
            appended_event_count = 0
            for event in events:
                if append_jsonl_unique(paths["timeline"], event, id_field="event_id"):
                    appended_event_count += 1
            observation = build_observation_record(project, previous_current, current, events)
            observation_recorded = False
            if observation is not None:
                observation_recorded = append_jsonl_unique(
                    paths["observations"],
                    observation,
                    id_field="observation_id",
                )
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
                "observation_recorded": observation_recorded,
                "duration_ms": duration_ms,
            }
            previous_status = _read_json_object(paths["status"]) or {}
            status = _status_payload(
                project,
                last_started=started_at,
                last_success=finished_at,
                last_failure=previous_status.get("last_failure") if isinstance(previous_status.get("last_failure"), str) else None,
                last_duration_ms=duration_ms,
                last_run_id=run_id,
                worktrees_scanned=len(current.get("worktrees") or []),
                errors=[],
            )
            write_json_atomic(paths["current"], current)
            append_jsonl(paths["runs"], run)
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
            status = _status_payload(
                project,
                last_started=started_at,
                last_success=previous_status.get("last_success") if isinstance(previous_status.get("last_success"), str) else None,
                last_failure=finished_at,
                last_duration_ms=duration_ms,
                last_run_id=run_id,
                worktrees_scanned=0,
                errors=[str(exc)],
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
        "lock": lock,
        "current": current,
        "self_health": status,
    }
