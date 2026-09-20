"""Parser registration for the `workstream` command group.

The parser tree used to be built inline inside ``ai_context_framework/runtime.py``.
``commands/workstream.py`` is already close to the 2000-line agent-reviewability
gate, so the registration lives in this dedicated module instead.

Handlers are supplied by the caller as a mapping keyed by a stable subcommand
label. They must be the ``runtime_parts`` adapters that supply each handler's
dependencies, not the raw command functions defined in ``commands/workstream.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping

from ai_context_framework.commands import workstream_authorization as workstream_authorization_commands
from ai_context_framework.constants import (
    DEFAULT_STALE_DAYS,
    VALID_MERGE_RESOLUTIONS,
    VALID_WORKSTREAM_ATTENTION,
    VALID_WORKSTREAM_STATUSES,
    VALID_WORKSTREAM_TYPES,
)
from ai_context_framework.validators.checks import (
    validate_draft_name,
    validate_workstream_id,
    validate_workstream_stage_id,
)

REQUIRED_WORKSTREAM_HANDLERS = (
    "init",
    "status",
    "list",
    "dashboard",
    "archive-candidates",
    "archive-draft",
    "archive",
    "sync",
    "stage-add",
    "stage-list",
    "stage-done",
    "focus",
    "show",
    "context",
    "next-actions",
    "preflight",
    "add",
    "reserve",
    "set",
    "block",
    "cancel",
    "merge-request",
    "merge-start",
    "ready",
    "done",
    "claim",
    "scope-add",
    "guard",
    "note",
)


def register_workstream_parsers(
    subparsers: Any,
    add_json_argument: Callable[..., None],
    add_write_arguments: Callable[..., None],
    *,
    handlers: Mapping[str, Callable[..., int]],
) -> None:
    """Register the whole `workstream` parser tree."""

    missing = sorted(set(REQUIRED_WORKSTREAM_HANDLERS) - set(handlers))
    if missing:
        raise ValueError(f"workstream parser registration is missing handlers: {missing}")

    workstream_parser = subparsers.add_parser("workstream", help="manage optional parallel Workstream metadata")
    workstream_subparsers = workstream_parser.add_subparsers(dest="workstream_command", required=True)

    workstream_init_parser = workstream_subparsers.add_parser("init", help="enable the optional Workstream layer")
    workstream_init_parser.add_argument("path", nargs="?", type=Path)
    add_write_arguments(workstream_init_parser)
    workstream_init_parser.set_defaults(func=handlers["init"])

    workstream_status_parser = workstream_subparsers.add_parser("status", help="show Workstream layer status")
    workstream_status_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(workstream_status_parser)
    workstream_status_parser.set_defaults(func=handlers["status"])

    workstream_list_parser = workstream_subparsers.add_parser("list", help="list Workstream index entries")
    workstream_list_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(workstream_list_parser)
    workstream_list_parser.set_defaults(func=handlers["list"])

    workstream_dashboard_parser = workstream_subparsers.add_parser("dashboard", help="show parallel Workstream safety dashboard")
    workstream_dashboard_parser.add_argument("path", nargs="?", type=Path)
    workstream_dashboard_parser.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS, help="days before an active Workstream is reported as stale")
    add_json_argument(workstream_dashboard_parser)
    workstream_dashboard_parser.set_defaults(func=handlers["dashboard"])

    workstream_archive_candidates_parser = workstream_subparsers.add_parser(
        "archive-candidates",
        help="report terminal Workstreams that can be considered for archive",
    )
    workstream_archive_candidates_parser.add_argument("path", nargs="?", type=Path)
    workstream_archive_candidates_parser.add_argument("--today", default=None, help="override current date for keep-active checks")
    add_json_argument(workstream_archive_candidates_parser)
    workstream_archive_candidates_parser.set_defaults(func=handlers["archive-candidates"])

    workstream_archive_draft_parser = workstream_subparsers.add_parser(
        "archive-draft",
        help="create a reviewable Workstream archive draft",
    )
    workstream_archive_draft_parser.add_argument("path", nargs="?", type=Path)
    workstream_archive_draft_parser.add_argument("--date", default=None, help="draft date in YYYY-MM-DD; defaults to today")
    workstream_archive_draft_parser.add_argument("--name", type=validate_draft_name, default=None, help="optional draft name suffix")
    workstream_archive_draft_parser.add_argument("--force", action="store_true", help="replace an existing archive draft")
    add_write_arguments(workstream_archive_draft_parser)
    workstream_archive_draft_parser.set_defaults(func=handlers["archive-draft"])

    workstream_archive_parser = workstream_subparsers.add_parser(
        "archive",
        help="archive one terminal Workstream detail and update indexes",
    )
    workstream_archive_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_archive_parser.add_argument("path", nargs="?", type=Path)
    workstream_archive_parser.add_argument("--reason", default=None, help="archive reason, usually referencing an archive draft")
    workstream_archive_parser.add_argument("--date", default=None, help="archive date in YYYY-MM-DD; defaults to today")
    add_write_arguments(workstream_archive_parser)
    workstream_archive_parser.set_defaults(func=handlers["archive"])

    workstream_sync_parser = workstream_subparsers.add_parser("sync", help="sync Workstreams index rows from detail front matter")
    workstream_sync_parser.add_argument("path", nargs="?", type=Path)
    add_write_arguments(workstream_sync_parser)
    workstream_sync_parser.set_defaults(func=handlers["sync"])

    workstream_stage_parser = workstream_subparsers.add_parser("stage", help="manage Workstream internal stages")
    workstream_stage_subparsers = workstream_stage_parser.add_subparsers(dest="workstream_stage_command", required=True)

    workstream_stage_add_parser = workstream_stage_subparsers.add_parser("add", help="register a Workstream internal stage")
    workstream_stage_add_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS004")
    workstream_stage_add_parser.add_argument("path", nargs="?", type=Path)
    workstream_stage_add_parser.add_argument("--id", dest="stage_id", type=validate_workstream_stage_id, required=True, help="stage id, for example WS004.2")
    workstream_stage_add_parser.add_argument("--title", required=True, help="stage title")
    workstream_stage_add_parser.add_argument("--depends", default="无。", help="stage dependencies")
    workstream_stage_add_parser.add_argument("--output", default="待补充。", help="expected stage output")
    workstream_stage_add_parser.add_argument("--next-action", default="待推进。", help="stage next action")
    add_write_arguments(workstream_stage_add_parser)
    workstream_stage_add_parser.set_defaults(func=handlers["stage-add"])

    workstream_stage_list_parser = workstream_stage_subparsers.add_parser("list", help="list Workstream internal stages")
    workstream_stage_list_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS004")
    workstream_stage_list_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(workstream_stage_list_parser)
    workstream_stage_list_parser.set_defaults(func=handlers["stage-list"])

    workstream_stage_done_parser = workstream_stage_subparsers.add_parser("done", help="mark a Workstream internal stage done")
    workstream_stage_done_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS004")
    workstream_stage_done_parser.add_argument("stage_id", type=validate_workstream_stage_id, help="stage id, for example WS004.2")
    workstream_stage_done_parser.add_argument("path", nargs="?", type=Path)
    workstream_stage_done_parser.add_argument("--evidence", default=None, help="stage completion evidence")
    workstream_stage_done_parser.add_argument("--clear-current", action="store_true", help="clear current_stage when completing the focused stage")
    workstream_stage_done_parser.add_argument("--next-action", default=None, help="optional replacement next action")
    add_write_arguments(workstream_stage_done_parser)
    workstream_stage_done_parser.set_defaults(func=handlers["stage-done"])

    workstream_focus_parser = workstream_subparsers.add_parser("focus", help="focus a Workstream on a registered internal stage")
    workstream_focus_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS004")
    workstream_focus_parser.add_argument("stage_id", type=validate_workstream_stage_id, help="stage id, for example WS004.2")
    workstream_focus_parser.add_argument("path", nargs="?", type=Path)
    add_write_arguments(workstream_focus_parser)
    workstream_focus_parser.set_defaults(func=handlers["focus"])

    workstream_show_parser = workstream_subparsers.add_parser("show", help="show a Workstream detail file")
    workstream_show_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_show_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(workstream_show_parser)
    workstream_show_parser.set_defaults(func=handlers["show"])

    workstream_context_parser = workstream_subparsers.add_parser("context", help="print the AI execution context packet for one Workstream")
    workstream_context_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_context_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(workstream_context_parser)
    workstream_context_parser.set_defaults(func=handlers["context"])

    workstream_next_actions_parser = workstream_subparsers.add_parser("next-actions", help="recommend safe next actions for a Workstream")
    workstream_next_actions_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_next_actions_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(workstream_next_actions_parser)
    workstream_next_actions_parser.set_defaults(func=handlers["next-actions"])

    workstream_preflight_parser = workstream_subparsers.add_parser("preflight", help="check Workstream scope before editing")
    workstream_preflight_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_preflight_parser.add_argument("path", nargs="?", type=Path)
    add_json_argument(workstream_preflight_parser)
    workstream_preflight_parser.set_defaults(func=handlers["preflight"])

    workstream_add_parser = workstream_subparsers.add_parser("add", help="create a Workstream detail and index row")
    workstream_add_parser.add_argument("path", nargs="?", type=Path)
    workstream_add_parser.add_argument("--id", type=validate_workstream_id, required=True, help="Workstream id, for example WS002")
    workstream_add_parser.add_argument("--type", choices=tuple(sorted(VALID_WORKSTREAM_TYPES)), default="Task", help="Workstream type")
    workstream_add_parser.add_argument("--title", required=True, help="Workstream title")
    workstream_add_parser.add_argument("--owner", required=True, help="Workstream owner")
    workstream_add_parser.add_argument("--depends-on", action="append", default=None, help="dependency id; can be repeated")
    workstream_add_parser.add_argument("--read-scope", action="append", default=None, help="recommended read scope; can be repeated")
    workstream_add_parser.add_argument("--write-scope", action="append", default=None, help="typed write scope, for example `assigned: active/Current_Task.md`; can be repeated")
    workstream_add_parser.add_argument("--output", default="待补充。", help="expected output summary")
    workstream_add_parser.add_argument("--goal", default=None, help="goal text written to the Workstream detail")
    workstream_add_parser.add_argument("--attention", choices=tuple(sorted(VALID_WORKSTREAM_ATTENTION)), default=None, help="attention state: Now, Next, Waiting, or Retained")
    add_write_arguments(workstream_add_parser)
    workstream_add_parser.set_defaults(func=handlers["add"])

    workstream_reserve_parser = workstream_subparsers.add_parser(
        "reserve",
        help="reserve a unique Workstream ID on the primary branch without creating a worktree",
    )
    workstream_reserve_parser.add_argument("path", nargs="?", type=Path)
    workstream_reserve_parser.add_argument("--id", type=validate_workstream_id, default=None, help="optional explicit Workstream id")
    workstream_reserve_parser.add_argument("--type", choices=tuple(sorted(VALID_WORKSTREAM_TYPES)), default="Task")
    workstream_reserve_parser.add_argument("--title", default=None)
    workstream_reserve_parser.add_argument("--slug", default=None, help="portable lowercase task slug used if a worktree is created later")
    workstream_reserve_parser.add_argument("--owner", default=None)
    workstream_reserve_parser.add_argument("--depends-on", action="append", default=None)
    workstream_reserve_parser.add_argument("--read-scope", action="append", default=None)
    workstream_reserve_parser.add_argument("--write-scope", action="append", default=None)
    workstream_reserve_parser.add_argument("--output", default="待补充。")
    workstream_reserve_parser.add_argument("--goal", default=None)
    workstream_reserve_parser.add_argument("--attention", choices=tuple(sorted(VALID_WORKSTREAM_ATTENTION)), default=None)
    workstream_reserve_parser.add_argument("--merge-owner", type=validate_workstream_id, default=None)
    workstream_reserve_parser.add_argument("--coordination", choices=("parallel", "serial"), default=None)
    workstream_reserve_parser.add_argument("--message", default=None, help="reservation commit message")
    workstream_reserve_parser.add_argument("--resume-operation", default=None, help="resume one interrupted reservation journal")
    workstream_reserve_parser.add_argument("--apply", action="store_true", help="write and commit the reservation on the primary branch")
    add_json_argument(workstream_reserve_parser)
    workstream_reserve_parser.set_defaults(func=handlers["reserve"])

    workstream_set_parser = workstream_subparsers.add_parser("set", help="set Workstream status through allowed transitions")
    workstream_set_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_set_parser.add_argument("path", nargs="?", type=Path)
    workstream_set_parser.add_argument("--status", choices=tuple(sorted(VALID_WORKSTREAM_STATUSES)), default=None)
    workstream_set_parser.add_argument("--goal", default=None, help="replace the Workstream goal section")
    workstream_set_parser.add_argument("--attention", choices=tuple(sorted(VALID_WORKSTREAM_ATTENTION)), default=None, help="attention state: Now, Next, Waiting, or Retained")
    add_write_arguments(workstream_set_parser)
    workstream_set_parser.set_defaults(func=handlers["set"])

    workstream_block_parser = workstream_subparsers.add_parser("block", help="mark a Workstream blocked")
    workstream_block_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_block_parser.add_argument("path", nargs="?", type=Path)
    workstream_block_parser.add_argument("--reason", default=None, help="blocker reason")
    add_write_arguments(workstream_block_parser)
    workstream_block_parser.set_defaults(func=handlers["block"])

    workstream_cancel_parser = workstream_subparsers.add_parser("cancel", help="cancel a Workstream")
    workstream_cancel_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_cancel_parser.add_argument("path", nargs="?", type=Path)
    workstream_cancel_parser.add_argument("--reason", default=None, help="cancellation reason")
    add_write_arguments(workstream_cancel_parser)
    workstream_cancel_parser.set_defaults(func=handlers["cancel"])

    workstream_merge_parser = workstream_subparsers.add_parser("merge-request", help="write a reviewable merge request section")
    workstream_merge_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_merge_parser.add_argument("path", nargs="?", type=Path)
    workstream_merge_parser.add_argument("--target", action="append", required=True, help="merge target; can be repeated")
    workstream_merge_parser.add_argument("--summary", default=None, help="candidate change summary")
    workstream_merge_parser.add_argument("--verification", required=True, help="verification result")
    workstream_merge_parser.add_argument("--question", action="append", default=None, help="open question; can be repeated")
    workstream_merge_parser.add_argument("--conflict", action="append", default=None, help="known conflict; can be repeated")
    workstream_merge_parser.add_argument("--strategy", default="", help="suggested merge strategy")
    workstream_merge_parser.add_argument("--input", type=Path, default=None, help="file containing candidate change summary")
    add_write_arguments(workstream_merge_parser)
    workstream_merge_parser.set_defaults(func=handlers["merge-request"])

    workstream_merge_start_parser = workstream_subparsers.add_parser("merge-start", help="mark a Merge or Maintenance Workstream as Merging")
    workstream_merge_start_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_merge_start_parser.add_argument("path", nargs="?", type=Path)
    workstream_merge_start_parser.add_argument("--summary", default=None, help="optional merge-start note")
    add_write_arguments(workstream_merge_start_parser)
    workstream_merge_start_parser.set_defaults(func=handlers["merge-start"])

    workstream_ready_parser = workstream_subparsers.add_parser("ready", help="mark a Workstream ReadyToMerge")
    workstream_ready_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_ready_parser.add_argument("path", nargs="?", type=Path)
    workstream_ready_parser.add_argument(
        "--human-approved",
        action="store_true",
        help=(
            "legacy compatibility assertion only; does not create approval evidence or bypass "
            "the closeout authorization resolver"
        ),
    )
    add_write_arguments(workstream_ready_parser)
    workstream_ready_parser.set_defaults(func=handlers["ready"])

    workstream_authorization_commands.register_workstream_authorization_parsers(
        workstream_subparsers,
        validate_workstream_id=validate_workstream_id,
        valid_workstream_types=VALID_WORKSTREAM_TYPES,
        add_json_argument=add_json_argument,
    )

    workstream_done_parser = workstream_subparsers.add_parser("done", help="mark a ReadyToMerge Workstream done")
    workstream_done_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_done_parser.add_argument("path", nargs="?", type=Path)
    workstream_done_parser.add_argument("--evidence", default=None, help="completion evidence")
    workstream_done_parser.add_argument(
        "--merge-resolution",
        choices=tuple(sorted(VALID_MERGE_RESOLUTIONS)),
        default=None,
        help="final merge outcome: merged, rejected, no_merge_required, or archived",
    )
    workstream_done_parser.add_argument("--summary", default=None, help="optional completion record")
    add_write_arguments(workstream_done_parser)
    workstream_done_parser.set_defaults(func=handlers["done"])

    workstream_claim_parser = workstream_subparsers.add_parser("claim", help="append Workstream read/write scope claims")
    workstream_claim_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_claim_parser.add_argument("path", nargs="?", type=Path)
    workstream_claim_parser.add_argument("--read", action="append", default=None, help="read scope path; can be repeated")
    workstream_claim_parser.add_argument("--write", action="append", default=None, help="typed write scope; can be repeated")
    add_write_arguments(workstream_claim_parser)
    workstream_claim_parser.set_defaults(func=handlers["claim"])

    workstream_scope_add_parser = workstream_subparsers.add_parser("scope-add", help="append read/write scope with reason and activity log")
    workstream_scope_add_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_scope_add_parser.add_argument("path", nargs="?", type=Path)
    workstream_scope_add_parser.add_argument("--read", action="append", default=None, help="read scope path; can be repeated")
    workstream_scope_add_parser.add_argument("--write", action="append", default=None, help="typed write scope; can be repeated")
    workstream_scope_add_parser.add_argument("--reason", required=True, help="reason for expanding scope")
    workstream_scope_add_parser.add_argument("--merge-owner", type=validate_workstream_id, default=None, help="Workstream that owns final merge for shared scope")
    workstream_scope_add_parser.add_argument("--coordination", choices=("parallel", "serial"), default=None, help="coordination mode for shared scope")
    add_write_arguments(workstream_scope_add_parser)
    workstream_scope_add_parser.set_defaults(func=handlers["scope-add"])

    workstream_guard_parser = workstream_subparsers.add_parser("guard", help="check changed files against one Workstream write boundary")
    workstream_guard_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_guard_parser.add_argument("path", nargs="?", type=Path)
    workstream_guard_parser.add_argument("--file", action="append", default=None, help="explicit changed file; can be repeated")
    workstream_guard_parser.add_argument("--files", action="append", nargs="+", default=None, help="explicit changed files")
    workstream_guard_parser.add_argument("--from-git", action="store_true", help="read changed files from git")
    workstream_guard_parser.add_argument("--workspace", action="store_true", help="check the whole workspace")
    workstream_guard_parser.add_argument("--strict-workspace", action="store_true", help="fail on unrelated workspace changes")
    workstream_guard_parser.add_argument("--owned-only", action="store_true", help="disallow shared scope writes")
    workstream_guard_parser.add_argument("--changed-file", action="append", default=None, help="override git diff with explicit changed file; can be repeated")
    add_json_argument(workstream_guard_parser)
    workstream_guard_parser.set_defaults(func=handlers["guard"])

    workstream_note_parser = workstream_subparsers.add_parser("note", help="append a note to a Workstream detail section")
    workstream_note_parser.add_argument("id", type=validate_workstream_id, help="Workstream id, for example WS001")
    workstream_note_parser.add_argument("path", nargs="?", type=Path)
    workstream_note_parser.add_argument("--section", required=True, help="allowed note section")
    workstream_note_parser.add_argument("--text", default=None, help="note text")
    workstream_note_parser.add_argument("--input", type=Path, default=None, help="file containing note text")
    add_write_arguments(workstream_note_parser)
    workstream_note_parser.set_defaults(func=handlers["note"])
