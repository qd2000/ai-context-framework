"""Parser wiring for continuation workspace/configure commands.

This module deliberately contains no continuation state semantics.  It keeps
the large argparse surface separate from the workspace command adapter so both
modules stay small enough for agent review.
"""

from __future__ import annotations

from pathlib import Path


def _commands():
    # Lazy import avoids a module-load cycle: continuation_workspace exposes
    # these parser functions while the parser callbacks live in that module.
    from ai_context_framework.commands import continuation_workspace

    return continuation_workspace


def register_workspace_parsers(subparsers, add_json_argument) -> None:
    commands = _commands()
    list_parser = subparsers.add_parser(
        "list",
        help="read ACF_HOME continuation task/schema/timing compatibility without mutating state",
    )
    list_parser.add_argument("path", nargs="?", type=Path)
    list_parser.add_argument("--task-id", default=None)
    list_parser.add_argument(
        "--all-projects",
        action="store_true",
        help="scan every continuation namespace under the current ACF_HOME",
    )
    add_json_argument(list_parser)
    list_parser.set_defaults(func=commands.continuation_list_command)

    migrate = subparsers.add_parser(
        "migrate",
        help="plan or apply an explicit history-preserving migration for supported legacy state",
    )
    migrate.add_argument("path", nargs="?", type=Path)
    migrate.add_argument("--task-id", default=None)
    migrate.add_argument("--apply", action="store_true")
    migrate.add_argument("--dry-run", action="store_true")
    migrate.add_argument("--reason", default=None)
    add_json_argument(migrate)
    migrate.set_defaults(func=commands.continuation_migrate_command)

    workspace = subparsers.add_parser(
        "workspace",
        help="inspect and declare bounded Git workspace ownership without editing project files",
    )
    workspace_subparsers = workspace.add_subparsers(
        dest="continuation_workspace_command",
        required=True,
    )

    status = workspace_subparsers.add_parser(
        "status",
        help="classify baseline, runner-owned, unrelated and conflicting dirty paths",
    )
    status.add_argument("path", nargs="?", type=Path)
    status.add_argument("--task-id", default=None)
    add_json_argument(status)
    status.set_defaults(func=commands.continuation_workspace_status_command)

    intent = workspace_subparsers.add_parser(
        "intent",
        help="declare concrete paths the active fenced owner intends to modify",
    )
    intent.add_argument("path", nargs="?", type=Path)
    intent.add_argument("--task-id", default=None)
    intent.add_argument("--lease-id", required=True)
    intent.add_argument("--generation", type=int, default=None)
    intent.add_argument("--fence-token", default=None)
    intent.add_argument("--path", dest="intent_path", action="append", required=True)
    add_json_argument(intent)
    intent.set_defaults(func=commands.continuation_workspace_intent_command)

    reclassify = workspace_subparsers.add_parser(
        "reclassify",
        help="evidence-review unexpected dirty paths into task-owned or protected external ownership",
    )
    reclassify.add_argument("path", nargs="?", type=Path)
    reclassify.add_argument("--task-id", default=None)
    reclassify.add_argument("--lease-id", required=True)
    reclassify.add_argument("--generation", type=int, default=None)
    reclassify.add_argument("--fence-token", default=None)
    reclassify.add_argument(
        "--task-owned",
        dest="task_owned_path",
        action="append",
        default=[],
        help=(
            "reviewed unexpected path, or exact baseline-external recovery path, "
            "attributable to this task; repeat per path"
        ),
    )
    reclassify.add_argument(
        "--baseline-external",
        dest="baseline_external_path",
        action="append",
        default=[],
        help="reviewed unexpected path confirmed external to this task; repeat per path",
    )
    reclassify.add_argument("--evidence-ref", action="append", required=True)
    reclassify.add_argument("--reason", required=True)
    add_json_argument(reclassify)
    reclassify.set_defaults(func=commands.continuation_workspace_reclassify_command)

    reconcile_handoff = workspace_subparsers.add_parser(
        "reconcile-handoff",
        help="evidence-accept deterministic cleanup of task-owned WIP after a graceful ownerless handoff",
    )
    reconcile_handoff.add_argument("path", nargs="?", type=Path)
    reconcile_handoff.add_argument("--task-id", default=None)
    reconcile_handoff.add_argument(
        "--cleanup",
        dest="cleanup_path",
        action="append",
        required=True,
        help="recorded task-owned path now proven semantic-clean; repeat per path",
    )
    reconcile_handoff.add_argument(
        "--accept-head",
        default=None,
        help="explicitly accept the exact current Git HEAD when reviewed closeout also advanced HEAD",
    )
    reconcile_handoff.add_argument("--evidence-ref", action="append", required=True)
    reconcile_handoff.add_argument("--reason", required=True)
    add_json_argument(reconcile_handoff)
    reconcile_handoff.set_defaults(func=commands.continuation_workspace_reconcile_handoff_command)

    adopt = workspace_subparsers.add_parser(
        "adopt",
        help="explicitly classify every reviewed dirty path for a legacy task missing a workspace manifest",
    )
    adopt.add_argument("path", nargs="?", type=Path)
    adopt.add_argument("--task-id", default=None)
    adopt.add_argument(
        "--task-owned",
        dest="task_owned_path",
        action="append",
        default=[],
        help="reviewed changed path attributable to this continuation task; repeat per path",
    )
    adopt.add_argument(
        "--baseline-external",
        dest="baseline_external_path",
        action="append",
        default=[],
        help="reviewed changed path owned outside this continuation task; repeat per path",
    )
    adopt.add_argument("--evidence-ref", action="append", required=True)
    adopt.add_argument("--reason", required=True)
    add_json_argument(adopt)
    adopt.set_defaults(func=commands.continuation_workspace_adopt_command)

    refresh = workspace_subparsers.add_parser(
        "refresh",
        help="refresh compact workspace ownership digests for the active fenced owner",
    )
    refresh.add_argument("path", nargs="?", type=Path)
    refresh.add_argument("--task-id", default=None)
    refresh.add_argument("--lease-id", required=True)
    refresh.add_argument("--generation", type=int, default=None)
    refresh.add_argument("--fence-token", default=None)
    add_json_argument(refresh)
    refresh.set_defaults(func=commands.continuation_workspace_refresh_command)


def register_configure_parser(subparsers, add_json_argument) -> None:
    commands = _commands()
    configure = subparsers.add_parser(
        "configure",
        help="update timing for an existing continuation task without re-initializing its state",
    )
    configure.add_argument("path", nargs="?", type=Path)
    configure.add_argument("--task-id", default=None)
    configure.add_argument("--profile", choices=tuple(sorted(commands.TIMING_PROFILES)), default=None)
    configure.add_argument("--interval-minutes", type=int, default=None)
    configure.add_argument("--lease-ttl-minutes", type=int, default=None)
    configure.add_argument("--renew-interval-minutes", type=int, default=None)
    configure.add_argument("--heartbeat-interval-minutes", type=int, default=None)
    configure.add_argument("--stale-after-minutes", type=int, default=None)
    add_json_argument(configure)
    configure.set_defaults(func=commands.continuation_configure_command)


__all__ = ["register_configure_parser", "register_workspace_parsers"]
