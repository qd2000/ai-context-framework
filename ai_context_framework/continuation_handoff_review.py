"""Agent-first takeover of ownerless dirty WIP after a graceful handoff.

Ownerless handoff drift means task-owned WIP changed after a
``released_to_running_handoff`` release while no lease was held.  ACF keeps the
task blocked, lets the *same* runner review the preserved scene in bulk, and then
accepts the reviewed WIP inside one claim state lock.

The division of responsibility is deliberate:

* The Agent decides whether the WIP deserves to be preserved and continued, using
  task context, diffs, checkpoints and file scope.  It does not have to prove the
  content is correct, complete or tested.
* ACF never judges code semantics.  It only proves the deterministic facts the
  decision was based on are still exactly true: digests, HEAD, generation,
  runner identity, ownership coverage and scope.  Then it transfers the WIP.

Accepting WIP means "preserve and keep working on it", never "this is correct".
Nothing here writes to the worktree: the review package is read-only and the
takeover only mutates ACF control-plane state.

This module was split out of ``continuation_workspace.py`` so every module stays
inside the repository's agent-friendly size budget.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ai_context_framework.continuation_workspace import (
    HANDOFF_TAKEOVER_ENTRY_SCHEMA,
    HANDOFF_TAKEOVER_SCHEMA,
    MAX_ENTRIES,
    MAX_TAKEOVER_RECEIPT_BYTES,
    ContinuationWorkspaceError,
    classify,
    normalize_path,
    observe_handoff,
    path_matches_scope,
    paths_overlap,
    summary,
    validate_manifest,
)
from ai_context_framework.continuation_workspace import _drift_pairs
from ai_context_framework.continuation_workspace import _entries
from ai_context_framework.continuation_workspace import _entry_map
from ai_context_framework.continuation_workspace import _evidence_refs
from ai_context_framework.continuation_workspace import _run_git
from ai_context_framework.continuation_workspace import _text

__all__ = [
    "DEFAULT_REVIEW_PAGE_SIZE",
    "HANDOFF_REVIEW_ACTIONS",
    "HANDOFF_REVIEW_CHANGE_KINDS",
    "HANDOFF_REVIEW_DECISION_SCHEMA",
    "HANDOFF_REVIEW_ENTRY_SCHEMA",
    "HANDOFF_REVIEW_GROUP_SCHEMA",
    "HANDOFF_REVIEW_SCHEMA",
    "HANDOFF_TAKEOVER_ENTRY_SCHEMA",
    "HANDOFF_TAKEOVER_SCHEMA",
    "MAX_TAKEOVER_RECEIPT_BYTES",
    "apply_handoff_review",
    "build_handoff_review_bundle",
    "handoff_review_observation",
    "observation_digest",
    "paginate_review_bundle",
]

HANDOFF_REVIEW_SCHEMA = "acf.continuation.workspace-handoff-review.v1"
HANDOFF_REVIEW_ENTRY_SCHEMA = "acf.continuation.workspace-handoff-review-entry.v1"
HANDOFF_REVIEW_GROUP_SCHEMA = "acf.continuation.workspace-handoff-review-group.v1"
HANDOFF_REVIEW_DECISION_SCHEMA = "acf.continuation.workspace-handoff-review-decision.v1"

HANDOFF_REVIEW_ACTIONS = ("inherit_for_triage", "preserve_external", "semantic_clean", "block")
HANDOFF_REVIEW_CHANGE_KINDS = ("content_changed", "status_changed", "disappeared")
DEFAULT_REVIEW_PAGE_SIZE = 50

def _bounded_payload(payload: Mapping[str, Any], message: str) -> None:
    encoded = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_TAKEOVER_RECEIPT_BYTES:
        raise ContinuationWorkspaceError(message, code="workspace_manifest_full")


def _numstat_int(value: str) -> int:
    text = str(value).strip()
    if not text or text == "-":
        return 0
    try:
        return max(0, int(text))
    except ValueError:
        return 0


def _untracked_added_lines(root: Path, path_value: str) -> int:
    try:
        path = root / Path(path_value)
    except (ValueError, OSError):
        return 0
    try:
        if not path.is_file():
            return 0
        total = 0
        last = b"\n"
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                total += chunk.count(b"\n")
                if chunk:
                    last = chunk[-1:]
        if last and last != b"\n":
            total += 1
        return total
    except OSError:
        return 0


def _diff_stat_map(root: Path | None) -> dict[str, dict[str, int]]:
    """Best-effort added/deleted line counts for changed paths.

    Diagnostics only: a Git failure or an unparseable record degrades to zero
    rather than blocking the review package, because the reviewable facts are
    the status/content digests, not the line counts.
    """

    if root is None:
        return {}
    try:
        output = _run_git(
            root, "-c", "core.quotepath=off", "diff", "HEAD", "--numstat", "--no-ext-diff"
        )
    except ContinuationWorkspaceError:
        return {}
    result: dict[str, dict[str, int]] = {}
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        raw_path = "\t".join(parts[2:])
        if " => " in raw_path:
            raw_path = raw_path.split(" => ", 1)[1]
        try:
            key = normalize_path(raw_path.replace("\\", "/").strip())
        except ContinuationWorkspaceError:
            continue
        result[key] = {"added": _numstat_int(parts[0]), "deleted": _numstat_int(parts[1])}
    return result


def observation_digest(
    *,
    manifest_digest: str,
    entries: Iterable[Mapping[str, Any]],
) -> str:
    """Fingerprint the exact file facts an agent review decision was made against.

    The digest binds the workspace manifest provenance digest and the per-path
    prior/current status and content digests.  Recomputing it inside the claim
    state lock is what makes "the reviewed scene has not changed" a mechanically
    verifiable fact instead of a caller promise.

    Git HEAD is deliberately NOT folded into this digest: HEAD drift has its own
    explicit rule requiring the review file to record and the caller to accept
    the exact current SHA.  Folding it in would make an accepted HEAD change
    indistinguishable from unreviewed content drift and force a needless
    re-review of otherwise unchanged WIP.
    """

    payload = {
        "manifest_digest": str(manifest_digest),
        "entries": [
            {
                "path": str(item["path"]),
                "prior_status": str(item["prior_status"]),
                "prior_digest": str(item["prior_digest"]),
                "current_status": str(item["current_status"]),
                "current_digest": str(item["current_digest"]),
            }
            for item in sorted(entries, key=lambda item: str(item["path"]))
        ],
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _review_entries(
    manifest: Mapping[str, Any],
    *,
    task_id: str,
    snapshot: Mapping[str, Any],
    root: Path | None,
    allowed_scopes: Sequence[str],
    candidate_paths: Mapping[str, Sequence[str]],
) -> tuple[list[dict[str, Any]], dict[str, tuple[dict[str, Any], dict[str, Any] | None]]]:
    current = validate_manifest(manifest, task_id=task_id)
    observed = _entry_map(_entries(snapshot.get("entries"), field="snapshot.entries"))
    raw_aliases = snapshot.get("legacy_digest_aliases", {})
    drift = _drift_pairs(
        _entry_map(current["task_owned"]),
        observed,
        raw_aliases if isinstance(raw_aliases, Mapping) else {},
    )
    if not drift:
        raise ContinuationWorkspaceError(
            "ownerless handoff review requires task-owned handoff drift",
            code="workspace_handoff_review_required",
        )
    intents = list(current["write_intents"])
    scopes = list(allowed_scopes or [])
    candidates = candidate_paths if isinstance(candidate_paths, Mapping) else {}
    diff_stats = _diff_stat_map(root)
    entries: list[dict[str, Any]] = []
    for path_value in sorted(drift):
        prior, live = drift[path_value]
        if live is None:
            current_status = ""
            current_digest = ""
            change_kind = "disappeared"
        else:
            current_status = str(live["status"])
            current_digest = str(live["digest"])
            change_kind = (
                "status_changed" if current_status != str(prior["status"]) else "content_changed"
            )
        stat = diff_stats.get(path_value)
        if stat is None and root is not None:
            stat = {"added": _untracked_added_lines(root, path_value), "deleted": 0}
        if stat is None:
            stat = {"added": 0, "deleted": 0}
        path_candidates = [
            str(value) for value in (candidates.get(path_value) or [path_value])
        ] or [path_value]
        inside_scope = True
        if scopes:
            inside_scope = any(
                path_matches_scope(candidate, scope)
                for candidate in path_candidates
                for scope in scopes
            )
        entries.append(
            {
                "schema_version": HANDOFF_REVIEW_ENTRY_SCHEMA,
                "path": path_value,
                "prior_status": str(prior["status"]),
                "prior_digest": str(prior["digest"]),
                "current_status": current_status,
                "current_digest": current_digest,
                "change_kind": change_kind,
                "intent_covered": any(paths_overlap(path_value, intent) for intent in intents),
                "inside_workstream_scope": inside_scope,
                "diff_stat": {
                    "added": int(stat.get("added", 0)),
                    "deleted": int(stat.get("deleted", 0)),
                },
            }
        )
    return entries, drift


def _review_groups(
    entries: Sequence[Mapping[str, Any]],
    *,
    intents: Sequence[str],
) -> list[dict[str, Any]]:
    """Group drift paths by directory, covering write intent, status and change kind.

    Grouping is presentation only.  Decisions stay free to combine any paths,
    including across groups, and the final takeover remains one atomic step.
    """

    grouped: dict[str, dict[str, Any]] = {}
    for entry in entries:
        path_value = str(entry["path"])
        directory = path_value.rsplit("/", 1)[0] if "/" in path_value else "."
        intent = next(
            (value for value in intents if paths_overlap(path_value, value)),
            None,
        )
        key_source = [directory, intent, str(entry["current_status"]), str(entry["change_kind"])]
        encoded = json.dumps(key_source, ensure_ascii=False, sort_keys=True).encode("utf-8")
        group_id = hashlib.sha256(encoded).hexdigest()[:12]
        group = grouped.get(group_id)
        if group is None:
            group = {
                "schema_version": HANDOFF_REVIEW_GROUP_SCHEMA,
                "group_id": group_id,
                "directory": directory,
                "write_intent": intent,
                "current_status": str(entry["current_status"]),
                "change_kind": str(entry["change_kind"]),
                "paths": [],
            }
            grouped[group_id] = group
        group["paths"].append(path_value)
    return [
        {**group, "path_count": len(group["paths"])}
        for group in sorted(grouped.values(), key=lambda item: str(item["group_id"]))
    ]


def handoff_review_observation(
    manifest: Mapping[str, Any],
    *,
    task_id: str,
    snapshot: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Cheap read-only summary of reviewable ownerless handoff drift.

    Used by ``doctor``/``prompt`` so they can advertise the reviewable scene
    without paying for scope resolution or diff statistics.  Returns ``None``
    when no task-owned drift exists.
    """

    try:
        current = validate_manifest(manifest, task_id=task_id)
        observed = _entry_map(_entries(snapshot.get("entries"), field="snapshot.entries"))
    except ContinuationWorkspaceError:
        return None
    raw_aliases = snapshot.get("legacy_digest_aliases", {})
    drift = _drift_pairs(
        _entry_map(current["task_owned"]),
        observed,
        raw_aliases if isinstance(raw_aliases, Mapping) else {},
    )
    if not drift:
        return None
    entries = [
        {
            "path": path_value,
            "prior_status": str(pair[0]["status"]),
            "prior_digest": str(pair[0]["digest"]),
            "current_status": str(pair[1]["status"]) if pair[1] is not None else "",
            "current_digest": str(pair[1]["digest"]) if pair[1] is not None else "",
        }
        for path_value, pair in sorted(drift.items())
    ]
    return {
        "paths": [str(item["path"]) for item in entries],
        "source_generation": int(current["generation"]),
        "observation_digest": observation_digest(
            manifest_digest=str(summary(current, task_id=task_id)["manifest_digest"]),
            entries=entries,
        ),
    }


def build_handoff_review_bundle(
    manifest: Mapping[str, Any],
    *,
    task_id: str,
    runner_id: str,
    snapshot: Mapping[str, Any],
    now: str,
    root: Path | None = None,
    allowed_scopes: Sequence[str] = (),
    candidate_paths: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Build one read-only review package bound to the current file fingerprints.

    This never edits project files, never rewrites the workspace manifest and
    never grants ownership.  It only describes the drifted task-owned WIP so the
    same agent can decide what deserves to be preserved and continued.
    """

    current = validate_manifest(manifest, task_id=task_id)
    entries, _drift = _review_entries(
        current,
        task_id=task_id,
        snapshot=snapshot,
        root=root,
        allowed_scopes=allowed_scopes,
        candidate_paths=candidate_paths if isinstance(candidate_paths, Mapping) else {},
    )
    manifest_digest = str(summary(current, task_id=task_id)["manifest_digest"])
    bundle = {
        "schema_version": HANDOFF_REVIEW_SCHEMA,
        "task_id": task_id,
        "runner_id": _text(runner_id, field="runner_id", max_bytes=256),
        "source_generation": int(current["generation"]),
        "baseline_head": str(current["baseline_head"]),
        "current_head": _text(snapshot.get("head"), field="current_head", max_bytes=128),
        "manifest_digest": manifest_digest,
        "observation_digest": observation_digest(
            manifest_digest=manifest_digest,
            entries=entries,
        ),
        "created_at": _text(now, field="created_at", max_bytes=128),
        "total_entries": len(entries),
        "groups": _review_groups(entries, intents=list(current["write_intents"])),
        "entries": entries,
        "decisions": [],
    }
    _bounded_payload(bundle, "workspace handoff review bundle exceeds bounded size")
    return bundle


def paginate_review_bundle(
    bundle: Mapping[str, Any],
    *,
    page: int = 1,
    page_size: int = DEFAULT_REVIEW_PAGE_SIZE,
) -> dict[str, Any]:
    """Return one page view of a full review bundle without mutating the bundle."""

    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise ContinuationWorkspaceError("workspace handoff review page is invalid")
    if (
        isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or page_size < 1
        or page_size > MAX_ENTRIES
    ):
        raise ContinuationWorkspaceError("workspace handoff review page size is invalid")
    entries = list(bundle.get("entries") or [])
    total_pages = max(1, -(-len(entries) // page_size))
    start = (page - 1) * page_size
    view = dict(bundle)
    view["page"] = page
    view["page_size"] = page_size
    view["total_pages"] = total_pages
    view["entries"] = entries[start : start + page_size]
    return view


def _review_decision(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContinuationWorkspaceError(
            "workspace handoff review decision must be an object",
            code="workspace_handoff_review_incomplete",
        )
    record = dict(value)
    if record.get("schema_version") is not None and record.get(
        "schema_version"
    ) != HANDOFF_REVIEW_DECISION_SCHEMA:
        raise ContinuationWorkspaceError(
            "workspace handoff review decision schema is invalid",
            code="workspace_handoff_review_incomplete",
        )
    action = _text(record.get("action"), field="action", max_bytes=32)
    if action not in HANDOFF_REVIEW_ACTIONS:
        raise ContinuationWorkspaceError(
            f"workspace handoff review action is unsupported: {action}",
            code="workspace_handoff_review_incomplete",
        )
    raw_paths = record.get("paths")
    if not isinstance(raw_paths, list) or not raw_paths or len(raw_paths) > MAX_ENTRIES:
        raise ContinuationWorkspaceError(
            "workspace handoff review decision requires a non-empty bounded path list",
            code="workspace_handoff_review_incomplete",
        )
    paths = [normalize_path(_text(item, field="path")) for item in raw_paths]
    if len(paths) != len(set(paths)):
        raise ContinuationWorkspaceError(
            "workspace handoff review decision contains duplicate paths",
            code="workspace_handoff_review_incomplete",
        )
    return {
        "schema_version": HANDOFF_REVIEW_DECISION_SCHEMA,
        "action": action,
        "paths": sorted(paths),
        "reason": _text(record.get("reason"), field="reason", max_bytes=4096),
        "evidence_refs": _evidence_refs(record.get("evidence_refs")),
    }


def apply_handoff_review(
    manifest: Mapping[str, Any],
    *,
    task_id: str,
    runner_id: str,
    snapshot: Mapping[str, Any],
    review: Mapping[str, Any],
    allowed_scopes: Sequence[str] = (),
    candidate_paths: Mapping[str, Sequence[str]] | None = None,
    accepted_head: str | None = None,
    handoff_round: Mapping[str, Any] | None = None,
    receipt_id: str,
    now: str,
    new_generation: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Atomically accept one reviewed ownerless handoff into a fenced generation.

    ACF does not judge whether the inherited WIP is correct; it only verifies the
    deterministic facts the agent's decision was based on are still exactly true:
    the runner is the reviewer, the generation still matches, HEAD is accepted,
    the observation digest is unchanged, every drift path is decided exactly
    once, and each decision satisfies the ownership/scope/cleanliness rules.
    Any failure leaves the caller without a lease and without partial workspace
    mutation.
    """

    current = validate_manifest(manifest, task_id=task_id)
    if not isinstance(review, Mapping):
        raise ContinuationWorkspaceError(
            "ownerless handoff review file is missing",
            code="workspace_handoff_review_incomplete",
        )
    if review.get("schema_version") != HANDOFF_REVIEW_SCHEMA:
        raise ContinuationWorkspaceError(
            "ownerless handoff review schema is invalid",
            code="workspace_handoff_review_incomplete",
        )
    if str(review.get("task_id")) != task_id:
        raise ContinuationWorkspaceError(
            "ownerless handoff review task identity mismatch",
            code="workspace_handoff_review_task_mismatch",
        )
    review_runner = _text(review.get("runner_id"), field="runner_id", max_bytes=256)
    normalized_runner = _text(runner_id, field="runner_id", max_bytes=256)
    if review_runner != normalized_runner:
        raise ContinuationWorkspaceError(
            "ownerless handoff review runner does not match the claiming runner",
            code="workspace_handoff_review_runner_mismatch",
        )
    if isinstance(new_generation, bool) or not isinstance(new_generation, int) or (
        new_generation <= int(current["generation"])
    ):
        raise ContinuationWorkspaceError(
            "ownerless handoff takeover generation must advance",
            code="workspace_generation_mismatch",
        )
    source_generation = review.get("source_generation")
    if (
        isinstance(source_generation, bool)
        or not isinstance(source_generation, int)
        or source_generation != int(current["generation"])
    ):
        raise ContinuationWorkspaceError(
            "ownerless handoff review generation does not match the workspace manifest",
            code="workspace_generation_mismatch",
        )

    normalized_now = _text(now, field="accepted_at", max_bytes=128)
    normalized_receipt_id = _text(receipt_id, field="receipt_id", max_bytes=128)
    entries, drift = _review_entries(
        current,
        task_id=task_id,
        snapshot=snapshot,
        root=None,
        allowed_scopes=allowed_scopes,
        candidate_paths=candidate_paths if isinstance(candidate_paths, Mapping) else {},
    )
    manifest_digest = str(summary(current, task_id=task_id)["manifest_digest"])
    expected_digest = observation_digest(
        manifest_digest=manifest_digest,
        entries=entries,
    )
    current_head = _text(snapshot.get("head"), field="current_head", max_bytes=128)
    review_head = _text(review.get("current_head"), field="current_head", max_bytes=128)
    normalized_accepted_head = (
        _text(accepted_head, field="accepted_head", max_bytes=128)
        if accepted_head is not None
        else None
    )
    if current_head != review_head:
        if normalized_accepted_head != current_head:
            raise ContinuationWorkspaceError(
                "ownerless handoff review refuses unaccepted Git HEAD drift",
                code="workspace_handoff_review_head_unaccepted",
            )
    elif normalized_accepted_head is not None and normalized_accepted_head != current_head:
        raise ContinuationWorkspaceError(
            "accepted ownerless handoff HEAD does not match current Git HEAD",
            code="workspace_handoff_review_head_unaccepted",
        )

    recorded_digest = review.get("observation_digest")
    if not isinstance(recorded_digest, str) or not recorded_digest:
        raise ContinuationWorkspaceError(
            "ownerless handoff review is missing its observation digest",
            code="workspace_handoff_review_stale",
        )
    if recorded_digest != expected_digest:
        raise ContinuationWorkspaceError(
            "ownerless handoff review is stale; the reviewed file scene changed, "
            "regenerate it with `acf continuation workspace review-handoff`",
            code="workspace_handoff_review_stale",
        )

    raw_decisions = review.get("decisions")
    if not isinstance(raw_decisions, list) or not raw_decisions or len(raw_decisions) > MAX_ENTRIES:
        raise ContinuationWorkspaceError(
            "ownerless handoff review requires a non-empty bounded decision list",
            code="workspace_handoff_review_incomplete",
        )
    decisions = [_review_decision(item) for item in raw_decisions if isinstance(item, Mapping)]
    if len(decisions) != len(raw_decisions):
        raise ContinuationWorkspaceError(
            "ownerless handoff review contains a non-object decision",
            code="workspace_handoff_review_incomplete",
        )
    blocked = [item for item in decisions if item["action"] == "block"]
    if blocked:
        raise ContinuationWorkspaceError(
            "ownerless handoff review contains block decisions; keep the task blocked "
            "and escalate for human review",
            code="workspace_handoff_review_blocked",
        )
    selected: list[str] = []
    for item in decisions:
        selected.extend(item["paths"])
    if len(selected) != len(set(selected)):
        raise ContinuationWorkspaceError(
            "ownerless handoff review decisions repeat a path",
            code="workspace_handoff_review_incomplete",
        )
    for index, left in enumerate(selected):
        for right in selected[index + 1 :]:
            if paths_overlap(left, right):
                raise ContinuationWorkspaceError(
                    f"ownerless handoff review decisions overlap: {left} / {right}",
                    code="workspace_handoff_review_incomplete",
                )
    if set(selected) != set(drift):
        missing = sorted(set(drift) - set(selected))
        unexpected = sorted(set(selected) - set(drift))
        raise ContinuationWorkspaceError(
            "ownerless handoff review must decide every drift path exactly once; "
            f"missing={missing} unexpected={unexpected}",
            code="workspace_handoff_review_incomplete",
        )

    classified = classify(current, task_id=task_id, snapshot=snapshot, now=normalized_now)
    if classified["conflicts"]:
        raise ContinuationWorkspaceError(
            "ownerless handoff review cannot accept unrelated workspace conflicts",
            code="workspace_handoff_review_conflict_mismatch",
        )
    observed_handoff = observe_handoff(
        current,
        task_id=task_id,
        snapshot=snapshot,
        now=normalized_now,
    )
    expected_conflicts = {(path_value, "task_owned_handoff_drift") for path_value in drift}
    actual_conflicts = {
        (str(item.get("path")), str(item.get("reason")))
        for item in observed_handoff["conflicts"]
    }
    if actual_conflicts != expected_conflicts:
        raise ContinuationWorkspaceError(
            "ownerless handoff review must account for every current conflict exactly; "
            f"expected {sorted(expected_conflicts)}, observed {sorted(actual_conflicts)}",
            code="workspace_handoff_review_conflict_mismatch",
        )

    scopes = list(allowed_scopes or [])
    candidates = candidate_paths if isinstance(candidate_paths, Mapping) else {}
    intents = list(current["write_intents"])
    observed = _entry_map(snapshot.get("entries") or [])
    base_task = _entry_map(classified["task_owned"])
    base_baseline = _entry_map(
        [*classified["baseline_external"], *classified["unexpected_nonoverlap"]]
    )
    decision_by_path = {
        path_value: item for item in decisions for path_value in item["paths"]
    }
    inherited: list[str] = []
    preserved: list[str] = []
    cleaned: list[str] = []
    receipt_entries: list[dict[str, Any]] = []

    def _in_scope(path_value: str) -> bool:
        if not scopes:
            return True
        path_candidates = [str(value) for value in (candidates.get(path_value) or [path_value])]
        return any(
            path_matches_scope(candidate, scope)
            for candidate in path_candidates
            for scope in scopes
        )

    for path_value in sorted(decision_by_path):
        decision = decision_by_path[path_value]
        action = str(decision["action"])
        prior = drift[path_value][0]
        if action == "semantic_clean":
            if path_value in observed:
                raise ContinuationWorkspaceError(
                    f"ownerless handoff review path is still semantically dirty: {path_value}",
                    code="workspace_handoff_review_conflict_mismatch",
                )
            base_task.pop(path_value, None)
            cleaned.append(path_value)
            accepted_status = ""
            accepted_digest = ""
        elif action == "preserve_external":
            if path_value not in base_task:
                raise ContinuationWorkspaceError(
                    f"ownerless handoff review path is no longer task-owned WIP: {path_value}",
                    code="workspace_handoff_review_conflict_mismatch",
                )
            if any(paths_overlap(path_value, intent) for intent in intents):
                raise ContinuationWorkspaceError(
                    f"ownerless handoff review external path overlaps retained write intent: {path_value}",
                    code="workspace_handoff_review_scope_conflict",
                )
            if scopes and _in_scope(path_value):
                raise ContinuationWorkspaceError(
                    f"ownerless handoff review external path is inside Workstream write_scope: {path_value}",
                    code="workspace_handoff_review_scope_conflict",
                )
            live = base_task.pop(path_value)
            base_baseline[path_value] = live
            preserved.append(path_value)
            accepted_status = str(live["status"])
            accepted_digest = str(live["digest"])
        else:
            if path_value not in base_task:
                raise ContinuationWorkspaceError(
                    f"ownerless handoff review path is no longer task-owned WIP: {path_value}",
                    code="workspace_handoff_review_conflict_mismatch",
                )
            if not any(paths_overlap(path_value, intent) for intent in intents):
                raise ContinuationWorkspaceError(
                    f"ownerless handoff review path lacks retained write intent: {path_value}",
                    code="workspace_handoff_review_intent_missing",
                )
            if not _in_scope(path_value):
                raise ContinuationWorkspaceError(
                    f"ownerless handoff review inheritance is outside Workstream write_scope: {path_value}",
                    code="workspace_handoff_review_scope_conflict",
                )
            live = base_task[path_value]
            inherited.append(path_value)
            accepted_status = str(live["status"])
            accepted_digest = str(live["digest"])
        receipt_entries.append(
            {
                "schema_version": HANDOFF_TAKEOVER_ENTRY_SCHEMA,
                "path": path_value,
                "prior_status": str(prior["status"]),
                "prior_digest": str(prior["digest"]),
                "accepted_status": accepted_status,
                "accepted_digest": accepted_digest,
                "decision": action,
                "reason": str(decision["reason"]),
                "evidence_refs": list(decision["evidence_refs"]),
            }
        )

    retained_intents = [
        intent
        for intent in intents
        if any(paths_overlap(intent, path_value) for path_value in base_task)
    ]
    payload = {
        **current,
        "baseline_head": current_head,
        "generation": new_generation,
        "baseline_external": list(base_baseline.values()),
        "write_intents": sorted(set(retained_intents)),
        "task_owned": list(base_task.values()),
        "unexpected_nonoverlap": [],
        "conflicts": [],
        "last_observed_at": normalized_now,
    }
    try:
        review_file_digest = hashlib.sha256(
            json.dumps(dict(review), ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")
        ).hexdigest()
    except (TypeError, ValueError):
        review_file_digest = ""
    receipt = {
        "schema_version": HANDOFF_TAKEOVER_SCHEMA,
        "receipt_id": normalized_receipt_id,
        "task_id": task_id,
        "runner_id": review_runner,
        "source_generation": int(current["generation"]),
        "new_generation": new_generation,
        "handoff_round": dict(handoff_round) if isinstance(handoff_round, Mapping) else None,
        "baseline_head": str(current["baseline_head"]),
        "current_head": current_head,
        "accepted_head": normalized_accepted_head,
        "manifest_digest": manifest_digest,
        "observation_digest": expected_digest,
        "review_file_digest": review_file_digest,
        "inherited_dirty_wip_paths": sorted(inherited),
        "preserved_external_paths": sorted(preserved),
        "cleaned_paths": sorted(cleaned),
        "decisions": [
            {
                "schema_version": HANDOFF_REVIEW_DECISION_SCHEMA,
                "action": item["action"],
                "paths": list(item["paths"]),
                "reason": item["reason"],
                "evidence_refs": list(item["evidence_refs"]),
            }
            for item in decisions
        ],
        "accepted_at": normalized_now,
        "entries": receipt_entries,
    }
    _bounded_payload(receipt, "workspace handoff takeover receipt exceeds bounded size")
    return validate_manifest(payload, task_id=task_id), receipt
