"""Agent-first takeover of ownerless dirty WIP after a graceful handoff.

An ownerless handoff drift means task-owned WIP changed after a
``released_to_running_handoff`` release while no lease was held.  ACF keeps the
task blocked, lets the *same* runner review the preserved scene in bulk through
``review-handoff``, and then accepts the reviewed WIP inside one claim state
lock through ``claim --handoff-review-file``.

The division of responsibility is deliberate:

* The Agent decides whether the WIP deserves to be preserved and continued.  It
  does not have to prove the content is correct, complete or tested.
* ACF never judges code semantics.  It only proves the deterministic facts the
  decision was based on are still exactly true: digests, HEAD, generation,
  runner identity, ownership coverage and scope.  Then it transfers the WIP.

Nothing here writes to the worktree.  The review package is read-only and the
takeover only mutates ACF control-plane state.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from ai_context_framework import (
    continuation_handoff_review,
    continuation_rounds,
    continuation_workspace,
)
from ai_context_framework.commands import continuation_workspace as continuation_workspace_commands


def _core():
    # Imported lazily to avoid a module-import cycle: the main continuation
    # controller imports this adapter for the reviewed takeover path.
    from ai_context_framework.commands import continuation

    return continuation


_HANDOFF_REVIEW_NEXT_ACTIONS: dict[str, list[str]] = {
    "workspace_handoff_review_required": [
        "Run `acf continuation workspace review-handoff ... --runner-id <runner> --draft-file <local-review.json> --json` and decide each drift path."
    ],
    "workspace_handoff_review_incomplete": [
        "Every drift path needs exactly one decision group: inherit_for_triage, preserve_external, semantic_clean, or block. Regenerate the draft and fill all paths without duplicates or overlaps."
    ],
    "workspace_handoff_review_stale": [
        "The reviewed Git scene changed. Re-run `acf continuation workspace review-handoff ...` and re-decide before claiming."
    ],
    "workspace_handoff_review_runner_mismatch": [
        "Claim with the exact same --runner-id that generated the review file."
    ],
    "workspace_handoff_review_scope_conflict": [
        "Inherited paths must stay inside the bound Workstream direct write scope, while preserve_external paths must not overlap it or retained write intents."
    ],
    "workspace_handoff_review_conflict_mismatch": [
        "Decisions must account for every current conflict exactly. Inspect `acf continuation workspace status --json` and reconcile any unrelated conflict first."
    ],
    "workspace_handoff_review_head_unaccepted": [
        "Pass `--accept-head <current-head>` with the exact current Git HEAD, or re-run review-handoff after the HEAD change."
    ],
    "workspace_handoff_review_effects_unresolved": [
        "Reconcile durable effect identity/outcome before taking over ownerless workspace WIP."
    ],
    "workspace_handoff_review_blocked": [
        "The review contains block decisions. Keep the task blocked and escalate the reported paths for human review."
    ],
    "workspace_handoff_review_intent_missing": [
        "An inherited path lacks a retained write intent. Do not take it over; use preserve_external or resolve the intent provenance."
    ],
}
_DEFAULT_HANDOFF_REVIEW_NEXT_ACTIONS = [
    "Inspect `acf continuation doctor --json` and `acf continuation workspace status --json`, then regenerate the review package if needed."
]


def handoff_review_next_actions(
    code: str,
    root: Path,
    control: Mapping[str, Any],
) -> list[str]:
    actions = list(_HANDOFF_REVIEW_NEXT_ACTIONS.get(code) or _DEFAULT_HANDOFF_REVIEW_NEXT_ACTIONS)
    actions.append(
        "Run `acf continuation workspace review-handoff "
        f"{str(root)!s} --task-id {control['task_id']} --runner-id <same-runner> "
        "--draft-file <local-review.json> --json`, fill the draft, then claim with "
        "`--handoff-review-file <local-review.json>` and the same runner id."
    )
    return actions


def load_handoff_review_file(value: str) -> dict[str, Any]:
    core = _core()
    path = Path(value)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise core.ContinuationError(
            f"handoff review file is unreadable: {exc}",
            code="workspace_handoff_review_unreadable",
            exit_code=3,
            next_actions=["Regenerate the review draft with `acf continuation workspace review-handoff ...`."],
        ) from exc
    except json.JSONDecodeError as exc:
        raise core.ContinuationError(
            "handoff review file is not valid JSON",
            code="workspace_handoff_review_unreadable",
            exit_code=3,
            next_actions=["Regenerate the review draft with `acf continuation workspace review-handoff ...`."],
        ) from exc
    if not isinstance(payload, dict):
        raise core.ContinuationError(
            "handoff review file must contain a JSON object",
            code="workspace_handoff_review_unreadable",
            exit_code=3,
            next_actions=["Regenerate the review draft with `acf continuation workspace review-handoff ...`."],
        )
    return payload


def ownerless_handoff_review_context(
    paths: Mapping[str, Path],
    control: Mapping[str, Any],
) -> dict[str, Any]:
    """Prove the deterministic ownerless-handoff preconditions for a WIP takeover.

    Shared by ``review-handoff`` and ``claim --handoff-review-file`` so the review
    package and the atomic takeover can never disagree about which handoff they
    are talking about.  Every failure is fail-closed: no lease, no partial state.
    """

    core = _core()
    lease_snapshot = core._lease_snapshot(paths, control)
    if lease_snapshot["state"] != "absent":
        raise core.ContinuationError(
            "ownerless handoff review requires no lease record",
            code="workspace_handoff_review_owner_present",
            exit_code=3,
            details={"lease_state": lease_snapshot["state"]},
            next_actions=[
                "Use the active-owner workspace flow, or formally resolve/recover the interrupted owner first."
            ],
        )
    state = core._load_state(paths)
    if state["status"] not in {*core.RUNNABLE_STATUSES, "running"}:
        raise core.ContinuationError(
            "ownerless handoff review requires a runnable long-lived continuation",
            code="workspace_handoff_review_state_invalid",
            exit_code=3,
            details={"state_status": state["status"]},
        )
    rounds = core._load_round_journal(paths, control, require_existing=True)
    latest_round = continuation_rounds.latest_round(
        rounds,
        task_id=str(control["task_id"]),
    )
    if not isinstance(latest_round, Mapping) or (
        latest_round.get("phase") != "released"
        or latest_round.get("milestone") != "released_to_running_handoff"
    ):
        raise core.ContinuationError(
            "ownerless handoff review is only valid after an explicit graceful running handoff",
            code="workspace_handoff_review_not_handoff",
            exit_code=3,
            details={"latest_round": latest_round},
            next_actions=[
                "Only a `released_to_running_handoff` release opens the ownerless review path; "
                "resolve the interrupted owner lifecycle first."
            ],
        )
    effects = core._load_effect_journal(paths, control)
    effect_summary = continuation_rounds.effect_summary(
        effects,
        task_id=str(control["task_id"]),
    )
    unresolved_effects = list(effect_summary.get("unresolved") or [])
    if unresolved_effects:
        raise core.ContinuationError(
            "ownerless handoff review refuses unresolved effects",
            code="workspace_handoff_review_effects_unresolved",
            exit_code=3,
            details={"unresolved_effects": unresolved_effects},
            next_actions=[
                "Reconcile durable effect identity/outcome before reviewing ownerless workspace WIP."
            ],
        )
    manifest = continuation_workspace_commands.load_workspace_manifest(
        paths, control, require_existing=True
    )
    assert manifest is not None
    if int(manifest["generation"]) != int(latest_round["generation"]):
        raise core.ContinuationError(
            "workspace manifest generation does not match the released handoff generation",
            code="workspace_generation_mismatch",
            exit_code=3,
            details={
                "workspace_generation": manifest["generation"],
                "handoff_generation": latest_round["generation"],
            },
        )
    return {
        "lease": lease_snapshot,
        "latest_round": latest_round,
        "manifest": manifest,
    }


def continuation_workspace_review_handoff_command(args: argparse.Namespace) -> int:
    core = _core()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        runner_id = core._validate_public_input_text(args.runner_id, field="runner_id")
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            context = ownerless_handoff_review_context(paths, control)
            manifest = context["manifest"]
            allowed_scopes, context_root = continuation_workspace_commands.workstream_direct_write_scopes(
                root,
                str(control.get("workstream_id")) if control.get("workstream_id") else None,
            )
            snapshot = continuation_workspace_commands.workspace_current_snapshot(root)
            candidate_paths: dict[str, list[str]] = {}
            for entry in [*snapshot["entries"], *manifest["task_owned"]]:
                path_value = str(entry["path"])
                candidate_paths.setdefault(
                    path_value,
                    continuation_workspace_commands.workspace_intent_candidates(
                        root, context_root, path_value
                    ),
                )
            try:
                bundle = continuation_handoff_review.build_handoff_review_bundle(
                    manifest,
                    task_id=str(control["task_id"]),
                    runner_id=runner_id,
                    snapshot=snapshot,
                    now=core._iso(),
                    root=root,
                    allowed_scopes=allowed_scopes,
                    candidate_paths=candidate_paths,
                )
                view = continuation_handoff_review.paginate_review_bundle(
                    bundle,
                    page=int(args.page or 1),
                    page_size=int(
                        args.page_size or continuation_handoff_review.DEFAULT_REVIEW_PAGE_SIZE
                    ),
                )
            except continuation_workspace.ContinuationWorkspaceError as exc:
                error = continuation_workspace_commands.workspace_error(exc)
                error.exit_code = 3
                raise error from exc
            draft_path = Path(str(args.draft_file)).expanduser()
            try:
                if draft_path.parent and not draft_path.parent.exists():
                    draft_path.parent.mkdir(parents=True, exist_ok=True)
                draft_path.write_text(
                    json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            except OSError as exc:
                raise core.ContinuationError(
                    f"handoff review draft file is not writable: {exc}",
                    code="workspace_handoff_review_draft_unwritable",
                    exit_code=3,
                    next_actions=["Choose a writable local --draft-file path outside the project worktree."],
                ) from exc
            task_flag = f" --task-id {json.dumps(str(control['task_id']))}"
            return {
                "status": "workspace_handoff_review_ready",
                "task_id": control["task_id"],
                "generation": manifest["generation"],
                "runner_id": runner_id,
                "draft_file": str(draft_path),
                "source_generation": bundle["source_generation"],
                "current_head": bundle["current_head"],
                "observation_digest": bundle["observation_digest"],
                "review_path_count": bundle["total_entries"],
                "review_paths": [str(item["path"]) for item in view["entries"]],
                "page": view["page"],
                "page_size": view["page_size"],
                "total_entries": view["total_entries"],
                "total_pages": view["total_pages"],
                "groups": bundle["groups"],
                "entries": view["entries"],
                "next_actions": [
                    "Fill every drift path in the draft with exactly one decision "
                    "(inherit_for_triage, preserve_external, semantic_clean, block).",
                    "Do not modify, format, stash, commit, revert, or delete the WIP while reviewing; "
                    "any change invalidates the review fingerprints and forces a new review.",
                    f"Then claim in this same activation with `acf continuation claim {json.dumps(str(root))}"
                    f"{task_flag} --runner-id {json.dumps(runner_id)} "
                    f"--handoff-review-file {json.dumps(str(draft_path))} --json`.",
                ],
            }

    return core._guarded(args, "continuation workspace review-handoff", operation)


__all__ = [
    "continuation_workspace_review_handoff_command",
    "handoff_review_next_actions",
    "load_handoff_review_file",
    "ownerless_handoff_review_context",
]
