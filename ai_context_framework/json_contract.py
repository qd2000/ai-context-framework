"""JSON and CLI contract helpers shared by ACF commands."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from ai_context_framework.constants import (
    ANCHOR_NOT_FOUND,
    APPEND_FORCE_CONFLICT,
    EXIT_INPUT_ERROR,
    EXIT_SAFETY_REFUSED,
    JSON_SCHEMA_VERSION,
    TARGET_EXISTS_APPEND_REQUIRED,
)
from ai_context_framework.models import CheckResult


def json_enabled(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "json", False))


def dry_run_enabled(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "dry_run", False))


def check_after_enabled(args: argparse.Namespace) -> bool:
    return bool(getattr(args, "check_after", False))


def path_values(paths: Sequence[Path]) -> list[str]:
    return [str(path) for path in paths]


def set_result_payload(args: argparse.Namespace, payload: dict[str, object]) -> None:
    setattr(args, "_acf_result_payload", payload)


def get_result_payload(args: argparse.Namespace) -> dict[str, object]:
    payload = getattr(args, "_acf_result_payload", None)
    return payload if isinstance(payload, dict) else {}


def command_name_from_argv(argv: Sequence[str]) -> str | None:
    for token in argv:
        if token.startswith("-"):
            continue
        return token
    return None


def json_requested(argv: Sequence[str]) -> bool:
    return "--json" in argv


def print_json(payload: dict[str, object]) -> None:
    payload.setdefault("schema_version", JSON_SCHEMA_VERSION)
    payload.setdefault("error_code", None)
    payload.setdefault("next_actions", [])
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def check_payload(result: CheckResult) -> dict[str, object]:
    return {
        "ok": result.ok,
        "errors": result.errors,
        "warnings": result.warnings,
    }


def check_error_code(result: CheckResult | None) -> str | None:
    if result is not None and not result.ok:
        return "check_failed"
    return None


def check_next_actions(result: CheckResult | None, strict: bool = False) -> list[str]:
    if result is None:
        return []
    command = "acf check --strict" if strict else "acf check"
    if result.errors:
        return [
            "Fix the reported errors.",
            f"Rerun `{command}`.",
        ]
    if result.warnings:
        return [
            "Review the reported warnings.",
            "Use `acf check --strict` when this context should reject placeholders.",
        ]
    return []


def write_next_actions(
    dry_run: bool, check_result: CheckResult | None, changed_files: Sequence[Path] = ()
) -> list[str]:
    if dry_run:
        if not changed_files:
            return ["No changes needed."]
        return [
            "Review changed_files.",
            "Rerun the command without `--dry-run` to apply changes.",
        ]
    if check_result is not None and not check_result.ok:
        return [
            "Fix the reported check errors.",
            "Rerun the command after correction.",
        ]
    return []


def error_next_actions(error_code: str) -> list[str]:
    if error_code == "curation_draft_exists":
        return ["Review the existing curation draft; choose a different --name if a separate draft is needed."]
    if error_code == TARGET_EXISTS_APPEND_REQUIRED:
        return ["Rerun with `--append` to add an entry or `--force` to replace the daily worklog."]
    if error_code == APPEND_FORCE_CONFLICT:
        return ["Use either `--append` or `--force`, not both."]
    if error_code == ANCHOR_NOT_FOUND:
        return ["Stop and report the missing worklog anchor; do not guess an insertion point."]
    if error_code == "workstream_not_initialized":
        return ["Run `acf workstream init` for this context before using Workstream detail commands."]
    if error_code == "workstream_not_found":
        return ["Run `acf workstream list` to see available Workstream IDs."]
    if error_code == "workstream_schema_failed":
        return ["Fix the Workstream detail front matter, then rerun the command."]
    if error_code == "workstream_duplicate_id":
        return ["Choose an unused Workstream ID or rerun `acf workstream reserve` without --id."]
    if error_code == "workstream_not_reserved_on_primary":
        return ["Reserve and commit the Workstream on the configured primary branch before creating a worktree."]
    if error_code == "reservation_requires_primary_checkout":
        return ["Run the reservation command against the configured primary checkout."]
    if error_code == "workstream_reservation_stage_mismatch":
        return ["Review the Git index; reservation commits only the Workstream detail and index row."]
    if error_code == "workstream_reservation_fields_required":
        return ["Provide --title, --slug, and --owner, or use --resume-operation for an interrupted reservation."]
    if error_code == "workstream_reservation_conflict":
        return ["Inspect the reservation journal and existing detail/index content; ACF will not overwrite conflicting files."]
    if error_code == "primary_reservation_path_conflict":
        return ["Keep the reservation detail and Workstreams index paths unchanged, then rerun the reservation; unrelated dirty files are allowed."]
    if error_code == "primary_local_state_changed_during_reservation":
        return ["Inspect the primary checkout changes and rerun the reservation only after the protected local state is stable; do not reset or clean another agent's work."]
    if error_code == "workstream_invalid_transition":
        return ["Review the Workstream state machine and use the next valid state."]
    if error_code == "workstream_reason_required":
        return ["Provide `--reason` so the blocker or cancellation is written to the detail file."]
    if error_code == "workstream_missing_merge_request":
        return ["Run `acf workstream merge-request ...` with target and summary before `ready`."]
    if error_code == "workstream_human_approval_required":
        return ["Ask the human owner to confirm completion, then rerun with `--human-approved`."]
    if error_code == "workstream_missing_evidence":
        return ["Provide `--evidence` so completion remains traceable."]
    if error_code == "workstream_missing_merge_resolution":
        return ["Provide `--merge-resolution` with one of: merged, rejected, no_merge_required, archived."]
    if error_code == "workstream_section_not_allowed":
        return ["Use one of the allowed Workstream note sections."]
    if error_code == "workstream_scope_invalid":
        return ["Use a normalized relative scope path and typed write scopes such as `assigned: src/foo.py`."]
    if error_code == "workstream_claim_conflict":
        return ["Choose a different write scope or resolve the conflicting active Workstream first."]
    if error_code == "workstream_guard_git_unavailable":
        return ["Run guard inside a git working tree, or pass explicit --changed-file values."]
    if error_code == "workstream_guard_failed":
        return ["Move changes inside the Workstream write scope, use `acf workstream scope-add ... --reason`, or create a Merge/Maintenance Workstream."]
    if error_code == "workstream_dashboard_conflicts":
        return ["Resolve reported write-scope conflicts before starting parallel work."]
    if error_code == "workstream_owned_scope_invalid":
        return ["Use `owned:` only for the current Workstream detail file."]
    if error_code == "workstream_stage_duplicate_id":
        return ["Choose an unused Workstream stage ID in this Workstream detail file."]
    if error_code == "workstream_stage_scope_invalid":
        return ["Use a Workstream stage ID that belongs to the target Workstream, for example `WS004.2` in `WS004`."]
    if error_code == "workstream_stage_not_found":
        return ["Run `acf workstream stage list ...` and choose a registered stage ID."]
    if error_code == "workstream_stage_terminal":
        return ["Choose a non-terminal Workstream stage; terminal stages cannot be focused."]
    if error_code == "workstream_stage_active_conflict":
        return ["Resolve the existing Active stage first; this version does not automatically demote other Active stages."]
    if error_code == "workstream_stage_dependency_blocked":
        return ["Finish the dependent Workstream stage before focusing this stage."]
    if error_code == "workstream_stage_clear_current_required":
        return ["Pass `--clear-current` when completing the current Workstream stage."]
    if error_code == "workstream_archive_candidates_invalid_today":
        return ["Use `--today YYYY-MM-DD` or omit it to use the current date."]
    if error_code == "workstream_archive_candidates_plan_unreadable":
        return ["Fix active/Task_Plan.md or run `acf check` before reviewing archive candidates."]
    if error_code == "workstream_archive_draft_exists":
        return ["Review the existing archive draft, rerun with --name for a separate draft, or use --force to replace it."]
    if error_code == "workstream_archive_blocked":
        return ["Resolve the reported blocked_by items, then rerun the archive command."]
    if error_code == "workstream_archive_target_exists":
        return ["Review the existing archive target and choose a different manual recovery path before retrying."]
    if error_code == "workstream_archive_duplicate_index":
        return ["Fix duplicate rows in active/Workstreams.md before archiving."]
    if error_code == "feedback_not_found":
        return ["Run `acf feedback list --json` and choose an existing feedback ID."]
    if error_code == "feedback_archive_blocked":
        return ["Mark the feedback Done or Rejected before archiving it."]
    if error_code == "human_notes_missing":
        return ["Use a standard context with human/ enabled, run upgrade if appropriate, or use `acf new feedback`."]
    if error_code == "human_index_missing":
        return ["Run `acf upgrade` or `acf human index sync` on a standard context."]
    if error_code == "human_index_item_not_found":
        return ["Run `acf human list --json` to find the item ID or path."]
    if error_code == "task_stage_duplicate_id":
        return ["Choose an unused Task Stage ID in active/Task_Plan.md."]
    if error_code == "task_stage_scope_invalid":
        return ["Use a Task Stage ID that belongs to the parent task, for example `T001.2` under `T001`."]
    if error_code == "task_stage_parent_not_found":
        return ["Run `acf plan status ... --json` and choose an existing parent task ID."]
    if error_code == "task_stage_workstream_not_found":
        return ["Run `acf workstream list ... --json` or omit `--workstream` when no Workstream owner applies."]
    if error_code == "task_stage_not_found":
        return ["Run `acf plan stage list ... --json` and choose a registered Task Stage ID."]
    if error_code == "task_stage_missing_evidence":
        return ["Provide `--evidence` so Task Stage completion remains traceable."]
    if error_code == "generated_marker_missing":
        return ["Rerun with `--init-marker` after reviewing where the generated block should live."]
    if error_code == "generated_marker_duplicate":
        return ["Keep one generated marker pair, move manual content outside it, then rerun the command."]
    if error_code == "generated_marker_unclosed":
        return ["Fix the unbalanced generated marker pair before rerunning the command."]
    if error_code == "sync_source_invalid":
        return ["Fix or remove the invalid source file, then rerun the sync command."]
    if error_code == "doctor_projects_fix_unsupported":
        return ["Run `acf doctor --projects ... --json` read-only, then run single-project `acf doctor <path> --fix safe`."]
    if error_code == "doctor_projects_write_unsupported":
        return ["Run `acf doctor --projects ... --json` read-only, then run a single-project doctor write command."]
    if error_code == "doctor_report_exists":
        return ["Review the existing doctor report, rerun with a different --today date, or use --force to replace it."]
    if error_code == "doctor_draft_exists":
        return ["Review the existing doctor writeback draft, rerun with a different --today date, or use --force to replace it."]
    if error_code in {
        "git_command_failed",
        "git_repository_not_found",
        "git_ref_not_found",
        "git_project_config_invalid",
        "primary_branch_missing",
        "primary_checkout_missing",
        "git_common_dir_mismatch",
        "primary_branch_mismatch",
        "primary_branch_advanced",
        "primary_checkout_dirty",
        "primary_reservation_path_conflict",
        "primary_local_state_changed_during_reservation",
    }:
        return [
            "Review the configured primary checkout, branch, and Git common-dir.",
            "Rerun the read-only worktree plan or audit after correcting the repository state.",
        ]
    if error_code in {
        "worktree_slug_invalid",
        "invalid_low_information_slug",
        "worktree_kind_invalid",
        "worktree_slug_required",
        "worktree_target_required",
        "worktree_name_mismatch",
    }:
        return ["Use the configured naming policy and provide a descriptive lowercase slug."]
    if error_code in {
        "branch_already_checked_out",
        "worktree_branch_mismatch",
        "worktree_branch_conflict",
        "workstream_already_bound",
        "primary_branch_not_allowed_for_linked_worktree",
    }:
        return ["Inspect `acf worktree list --json`; do not force, move, or reuse the conflicting branch/worktree automatically."]
    if error_code in {
        "target_path_exists_not_worktree",
        "orphan_target_path",
        "worktree_not_registered",
        "detached_worktree_not_supported",
        "worktree_verification_failed",
        "worktree_registry_invalid",
    }:
        return ["Run `acf worktree verify` or `acf worktree audit`; preserve the existing path and repair explicitly."]
    if error_code in {
        "worktree_operation_locked",
        "worktree_operation_lock_timeout",
        "worktree_lock_invalid",
        "worktree_lock_lost",
        "worktree_lock_replaced",
        "operation_not_found",
        "operation_journal_invalid",
        "operation_resume_unsupported",
        "merge_operation_target_mismatch",
    }:
        return ["Inspect the ACF operation journal and active lock; retry or resume after the recorded operation becomes inactive. Do not delete a live lock manually."]
    if error_code in {
        "artifact_manifest_not_found",
        "artifact_manifest_invalid",
        "artifact_handoff_required",
        "artifact_handoff_incomplete",
        "artifact_source_missing",
        "artifact_override_path_not_found",
        "artifact_required_invalid",
        "artifact_reference_invalid",
    }:
        return ["Run `acf worktree artifact-plan`, classify every unknown entry, verify destinations, then run `artifact-migrate --apply` before promotion or close."]
    if error_code in {
        "integration_worktree_missing",
        "integration_worktree_create_failed",
        "integration_slot_not_clean",
        "integration_tip_missing_source_head",
        "merge_candidate_tree_missing",
        "primary_promotion_identity_mismatch",
        "quarantine_restore_collision",
    }:
        return ["Inspect the merge operation journal and its temporary integration worktree. Preserve the conflict/candidate evidence and resume after correcting the reported identity or path issue."]
    if error_code in {
        "worktree_close_timeout",
        "worktree_branch_delete_timeout",
    }:
        return ["Close applications holding the worktree or Git refs, then resume the same close operation. ACF will not force-remove a dirty worktree or force-delete a branch."]
    if error_code in {
        "worktree_dirty",
        "branch_not_merged",
        "workstream_not_ready_to_merge",
        "merge_conflicts_detected",
        "worktree_branch_advanced",
        "worktree_pre_merge_check_failed",
        "worktree_post_merge_check_failed",
        "worktree_check_argv_invalid",
    }:
        return ["Review the reported branch, status, merge preview, and checks; ACF will not stash, reset, clean, rebase, or resolve conflicts automatically."]
    if error_code == "input_error":
        return [
            "Check command arguments and paths.",
            "Rerun with `--help` if needed.",
        ]
    if error_code == "safety_refused":
        return [
            "Review the target state and changed files.",
            "Rerun with `--force` only if overwriting is intended.",
        ]
    if error_code == "runtime_error":
        return [
            "Inspect the error message.",
            "Rerun after fixing the unexpected failure.",
        ]
    return []


def classify_cli_error(message: str) -> tuple[str, int]:
    workstream_codes = (
        "workstream_not_initialized",
        "workstream_not_found",
        "workstream_schema_failed",
        "workstream_duplicate_id",
        "workstream_invalid_transition",
        "workstream_reason_required",
        "workstream_missing_merge_request",
        "workstream_human_approval_required",
        "workstream_missing_evidence",
        "workstream_missing_merge_resolution",
        "workstream_section_not_allowed",
        "workstream_scope_invalid",
        "workstream_claim_conflict",
        "workstream_guard_git_unavailable",
        "workstream_guard_failed",
        "workstream_dashboard_conflicts",
        "workstream_owned_scope_invalid",
        "workstream_stage_duplicate_id",
        "workstream_stage_scope_invalid",
        "workstream_stage_not_found",
        "workstream_stage_terminal",
        "workstream_stage_active_conflict",
        "workstream_stage_dependency_blocked",
        "workstream_stage_clear_current_required",
        "workstream_archive_candidates_invalid_today",
        "workstream_archive_candidates_plan_unreadable",
        "workstream_archive_draft_exists",
        "workstream_archive_blocked",
        "workstream_archive_target_exists",
        "workstream_archive_duplicate_index",
        "workstream_not_reserved_on_primary",
        "reservation_requires_primary_checkout",
        "workstream_reservation_stage_mismatch",
        "workstream_reservation_fields_required",
        "workstream_reservation_conflict",
    )
    git_worktree_codes = (
        "git_command_failed",
        "git_repository_not_found",
        "git_ref_not_found",
        "git_project_config_invalid",
        "primary_branch_missing",
        "primary_checkout_missing",
        "git_common_dir_mismatch",
        "primary_branch_mismatch",
        "primary_branch_advanced",
        "primary_checkout_dirty",
        "primary_reservation_path_conflict",
        "primary_local_state_changed_during_reservation",
        "worktree_slug_invalid",
        "invalid_low_information_slug",
        "worktree_kind_invalid",
        "worktree_slug_required",
        "worktree_target_required",
        "worktree_name_mismatch",
        "branch_already_checked_out",
        "worktree_branch_mismatch",
        "worktree_branch_conflict",
        "workstream_already_bound",
        "primary_branch_not_allowed_for_linked_worktree",
        "target_path_exists_not_worktree",
        "orphan_target_path",
        "worktree_not_registered",
        "detached_worktree_not_supported",
        "worktree_verification_failed",
        "worktree_registry_invalid",
        "worktree_operation_locked",
        "worktree_operation_lock_timeout",
        "worktree_lock_invalid",
        "worktree_lock_lost",
        "worktree_lock_replaced",
        "operation_not_found",
        "operation_journal_invalid",
        "operation_resume_unsupported",
        "merge_operation_target_mismatch",
        "artifact_manifest_not_found",
        "artifact_manifest_invalid",
        "artifact_handoff_required",
        "artifact_handoff_incomplete",
        "artifact_source_missing",
        "artifact_override_path_not_found",
        "artifact_required_invalid",
        "artifact_reference_invalid",
        "integration_worktree_missing",
        "integration_worktree_create_failed",
        "integration_slot_not_clean",
        "integration_tip_missing_source_head",
        "merge_candidate_tree_missing",
        "primary_promotion_identity_mismatch",
        "quarantine_restore_collision",
        "worktree_close_timeout",
        "worktree_branch_delete_timeout",
        "worktree_dirty",
        "branch_not_merged",
        "workstream_not_ready_to_merge",
        "merge_conflicts_detected",
        "worktree_branch_advanced",
        "worktree_pre_merge_check_failed",
        "worktree_post_merge_check_failed",
        "worktree_check_argv_invalid",
    )
    task_stage_codes = (
        "task_stage_duplicate_id",
        "task_stage_scope_invalid",
        "task_stage_parent_not_found",
        "task_stage_workstream_not_found",
        "task_stage_not_found",
        "task_stage_missing_evidence",
    )
    generated_marker_codes = (
        "generated_marker_missing",
        "generated_marker_duplicate",
        "generated_marker_unclosed",
        "sync_source_invalid",
    )
    feedback_codes = (
        "feedback_not_found",
        "feedback_archive_blocked",
        "human_notes_missing",
    )
    doctor_codes = (
        "doctor_projects_fix_unsupported",
        "doctor_projects_write_unsupported",
        "doctor_report_exists",
        "doctor_draft_exists",
    )
    for code in (*workstream_codes, *git_worktree_codes, *task_stage_codes, *generated_marker_codes, *feedback_codes, *doctor_codes):
        if message == code or message.startswith(f"{code}:"):
            return code, EXIT_INPUT_ERROR
    if message.startswith("curation_draft_exists:"):
        return "curation_draft_exists", EXIT_SAFETY_REFUSED
    safety_markers = (
        "already exists",
        "already contains",
        "current task is Active",
        "path is a directory",
        "similar knowledge",
        "target already exists",
        "unfinished dependencies",
        "outside context root",
        "context is locked",
        "managed by another command",
    )
    if any(marker in message for marker in safety_markers):
        return "safety_refused", EXIT_SAFETY_REFUSED
    return "input_error", EXIT_INPUT_ERROR


def emit_cli_error(argv: Sequence[str], message: str, error_code: str, exit_code: int) -> int:
    if json_requested(argv):
        print_json(
            {
                "command": command_name_from_argv(argv),
                "ok": False,
                "error_code": error_code,
                "message": message,
                "next_actions": error_next_actions(error_code),
            }
        )
    else:
        print(f"ERROR: {message}", file=sys.stderr)
    return exit_code


def emit_write_result(
    args: argparse.Namespace,
    command: str,
    message: str,
    changed_files: Sequence[Path],
    check_result: CheckResult | None = None,
    extra_payload: dict[str, object] | None = None,
    warnings: Sequence[str] = (),
) -> int:
    dry_run = dry_run_enabled(args)
    payload: dict[str, object] = {
        "command": command,
        "ok": check_result.ok if check_result is not None else True,
        "error_code": check_error_code(check_result),
        "dry_run": dry_run,
        "changed_files": path_values(changed_files),
        "message": message,
        "next_actions": write_next_actions(dry_run, check_result, changed_files),
    }
    if warnings:
        payload["warnings"] = list(warnings)
    if extra_payload:
        payload.update(extra_payload)
    if check_result is not None:
        payload["check"] = check_payload(check_result)
    set_result_payload(args, payload)

    if json_enabled(args):
        print_json(payload)
    else:
        print(message)
        label = "would change" if dry_run else "changed"
        for changed_file in changed_files:
            print(f"{label}: {changed_file}")
        if check_result is not None:
            print(f"check: {'passed' if check_result.ok else 'failed'}")
            for error in check_result.errors:
                print(f"ERROR: {error}", file=sys.stderr)
            for warning in check_result.warnings:
                print(f"WARN: {warning}", file=sys.stderr)
        for warning in warnings:
            print(f"WARN: {warning}", file=sys.stderr)

    return 0 if check_result is None or check_result.ok else 1
