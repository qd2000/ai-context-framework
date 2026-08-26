"""CLI adapter for durable continuation user-authority directives."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Mapping

from ai_context_framework import continuation_directive_archive, continuation_directives


def _continuation():
    # Lazy import avoids a module cycle while reusing the canonical continuation
    # workspace discovery, locking, JSON, and error contracts.
    from ai_context_framework.commands import continuation

    return continuation


def _directive_error(exc: continuation_directives.DirectiveError):
    core = _continuation()
    return core.ContinuationError(str(exc), code=exc.code)


def load_journal(paths: Mapping[str, Path], control: Mapping[str, Any]) -> dict[str, Any]:
    try:
        journal = continuation_directives.load_journal(
            paths["directives"],
            task_id=str(control["task_id"]),
        )
        continuation_directive_archive.history_journal(
            paths["directives"], journal, task_id=str(control["task_id"])
        )
        return journal
    except continuation_directives.DirectiveError as exc:
        raise _directive_error(exc) from exc


def directive_context(paths: Mapping[str, Path], control: Mapping[str, Any]) -> dict[str, Any]:
    try:
        journal = load_journal(paths, control)
        context = continuation_directives.directive_context(journal)
        _, audit = continuation_directive_archive.history_journal(
            paths["directives"], journal, task_id=str(control["task_id"])
        )
        context["archive_count"] = audit["archive_count"]
        context["history_digest"] = audit["history_digest"]
        return context
    except continuation_directives.DirectiveError as exc:
        raise _directive_error(exc) from exc


def observe_directive_context(
    lease: dict[str, Any],
    context: Mapping[str, Any],
) -> dict[str, Any]:
    previous_revision = lease.get("directive_revision_seen")
    previous_digest = lease.get("directive_digest_seen")
    revision = int(context.get("revision") or 0)
    digest = str(context.get("digest") or "")
    changed = previous_revision is not None and (
        previous_revision != revision or previous_digest != digest
    )
    lease["directive_revision_seen"] = revision
    lease["directive_digest_seen"] = digest
    latest = context.get("latest_directive")
    latest_id = latest.get("id") if isinstance(latest, Mapping) else None
    return {
        "schema_version": continuation_directives.DIRECTIVE_CONTEXT_SCHEMA,
        "revision": revision,
        "digest": digest,
        "pending_count": int(context.get("pending_count") or 0),
        "adopted_count": int(context.get("adopted_count") or 0),
        "active_count": int(context.get("active_count") or 0),
        "pressure": dict(context.get("pressure") or {}),
        "archive_count": int(context.get("archive_count") or 0),
        "history_digest": context.get("history_digest"),
        "latest_directive_id": latest_id,
        "authority_refresh_required": bool(context.get("authority_refresh_required")),
        "changed_since_last_observation": changed,
        "previous_revision": previous_revision,
        "previous_digest": previous_digest,
    }


def write_journal(
    paths: Mapping[str, Path],
    control: Mapping[str, Any],
    journal: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        return continuation_directive_archive.store_with_rollover(
            paths["directives"],
            journal,
            task_id=str(control["task_id"]),
        )
    except continuation_directives.DirectiveError as exc:
        raise _directive_error(exc) from exc


def directive_hygiene(paths: Mapping[str, Path], control: Mapping[str, Any], *, now: str) -> dict[str, Any]:
    current = load_journal(paths, control)
    try:
        return continuation_directive_archive.hygiene_findings(
            paths["directives"], current, task_id=str(control["task_id"]), now=now
        )
    except continuation_directives.DirectiveError as exc:
        raise _directive_error(exc) from exc


def continuation_directive_add_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            journal = load_journal(paths, control)
            try:
                journal, directive = continuation_directives.add_directive(
                    journal,
                    kind=args.kind,
                    priority=args.priority,
                    text=args.text,
                    created_at=core._iso(),
                    actor=args.actor,
                    lifetime=args.lifetime,
                    evidence_refs=args.evidence_ref or [],
                )
            except continuation_directives.DirectiveError as exc:
                raise _directive_error(exc) from exc
            journal, rollover = write_journal(paths, control, journal)
            return {
                "status": "directive_added",
                "task_id": control["task_id"],
                "directive": directive,
                "directive_context": directive_context(paths, control),
                "rollover": rollover,
                "journal_path": str(paths["directives"]),
            }

    return core._guarded(args, "continuation directive add", operation)


def continuation_directive_list_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        control = core._load_control(paths, root)
        journal = load_journal(paths, control)
        try:
            directives, history_audit = continuation_directive_archive.history_directives(
                paths["directives"],
                journal,
                task_id=str(control["task_id"]),
                status=args.status,
            )
            context = directive_context(paths, control)
        except continuation_directives.DirectiveError as exc:
            raise _directive_error(exc) from exc
        return {
            "status": "directives_listed",
            "task_id": control["task_id"],
            "directive_count": len(directives),
            "directives": directives,
            "directive_context": context,
            "history_audit": history_audit,
            "journal_path": str(paths["directives"]),
        }

    return core._guarded(args, "continuation directive list", operation)


def continuation_directive_show_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        control = core._load_control(paths, root)
        journal = load_journal(paths, control)
        try:
            directive, history_audit = continuation_directive_archive.show_history_directive(
                paths["directives"],
                journal,
                task_id=str(control["task_id"]),
                directive_id=args.directive_id,
            )
        except continuation_directives.DirectiveError as exc:
            raise _directive_error(exc) from exc
        return {
            "status": "directive_shown",
            "task_id": control["task_id"],
            "directive": directive,
            "directive_context": directive_context(paths, control),
            "history_audit": history_audit,
            "journal_path": str(paths["directives"]),
        }

    return core._guarded(args, "continuation directive show", operation)


def continuation_directive_adopt_command(args: argparse.Namespace) -> int:
    return _transition_command(args, transition="adopt")


def continuation_directive_resolve_command(args: argparse.Namespace) -> int:
    return _transition_command(args, transition="resolve")


def continuation_directive_withdraw_command(args: argparse.Namespace) -> int:
    return _transition_command(args, transition="withdraw")


def _transition_command(args: argparse.Namespace, *, transition: str) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            journal = load_journal(paths, control)
            try:
                function = {
                    "adopt": continuation_directives.adopt_directive,
                    "resolve": continuation_directives.resolve_directive,
                    "withdraw": continuation_directives.withdraw_directive,
                }[transition]
                journal, directive, changed = function(
                    journal,
                    directive_id=args.directive_id,
                    occurred_at=core._iso(),
                    actor=args.actor,
                    evidence_refs=args.evidence_ref or [],
                    note=args.note,
                )
            except continuation_directives.DirectiveError as exc:
                raise _directive_error(exc) from exc
            rollover = {"rolled_over": False}
            if changed:
                journal, rollover = write_journal(paths, control, journal)
                directive, _ = continuation_directive_archive.show_history_directive(
                    paths["directives"],
                    journal,
                    task_id=str(control["task_id"]),
                    directive_id=args.directive_id,
                )
            past_tense = {"adopt": "adopted", "resolve": "resolved", "withdraw": "withdrawn"}[transition]
            return {
                "status": f"directive_{past_tense}" if changed else f"directive_already_{past_tense}",
                "task_id": control["task_id"],
                "changed": changed,
                "directive": directive,
                "directive_context": directive_context(paths, control),
                "rollover": rollover,
                "journal_path": str(paths["directives"]),
            }

    return core._guarded(args, f"continuation directive {transition}", operation)


def continuation_directive_supersede_command(args: argparse.Namespace) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            journal = load_journal(paths, control)
            try:
                journal, superseded, replacement = continuation_directives.supersede_directive(
                    journal,
                    directive_id=args.directive_id,
                    kind=args.kind,
                    priority=args.priority,
                    text=args.text,
                    occurred_at=core._iso(),
                    actor=args.actor,
                    lifetime=args.lifetime,
                    evidence_refs=args.evidence_ref or [],
                    note=args.note,
                )
            except continuation_directives.DirectiveError as exc:
                raise _directive_error(exc) from exc
            journal, rollover = write_journal(paths, control, journal)
            superseded, _ = continuation_directive_archive.show_history_directive(
                paths["directives"], journal, task_id=str(control["task_id"]), directive_id=str(superseded["id"])
            )
            replacement, _ = continuation_directive_archive.show_history_directive(
                paths["directives"], journal, task_id=str(control["task_id"]), directive_id=str(replacement["id"])
            )
            return {
                "status": "directive_superseded",
                "task_id": control["task_id"],
                "superseded": superseded,
                "replacement": replacement,
                "directive_context": directive_context(paths, control),
                "rollover": rollover,
                "journal_path": str(paths["directives"]),
            }

    return core._guarded(args, "continuation directive supersede", operation)


def register_directive_parser(subparsers, add_json_argument) -> None:
    directive = subparsers.add_parser(
        "directive",
        help="record and consume durable user-authority steering directives",
    )
    actions = directive.add_subparsers(dest="continuation_directive_command", required=True)

    add = actions.add_parser("add", help="add one pending user-authority directive")
    _identity_args(add)
    add.add_argument("--kind", choices=tuple(sorted(continuation_directives.DIRECTIVE_KINDS)), required=True)
    add.add_argument("--priority", type=int, default=50)
    add.add_argument("--lifetime", choices=tuple(sorted(continuation_directives.DIRECTIVE_LIFETIMES)), default="unspecified")
    add.add_argument("--text", required=True)
    add.add_argument("--evidence-ref", action="append", default=None)
    add.add_argument("--actor", default="user")
    add_json_argument(add)
    add.set_defaults(func=continuation_directive_add_command)

    list_parser = actions.add_parser("list", help="list projected directive inbox state")
    _identity_args(list_parser)
    list_parser.add_argument("--status", choices=tuple(sorted(continuation_directives.DIRECTIVE_STATUSES)), default=None)
    add_json_argument(list_parser)
    list_parser.set_defaults(func=continuation_directive_list_command)

    show = actions.add_parser("show", help="show one directive and its projected lifecycle state")
    _identity_args(show)
    show.add_argument("--directive-id", required=True)
    add_json_argument(show)
    show.set_defaults(func=continuation_directive_show_command)

    for name, command, help_text in (
        ("adopt", continuation_directive_adopt_command, "mark a pending directive adopted after authority refresh"),
        ("resolve", continuation_directive_resolve_command, "mark a pending/adopted directive resolved"),
        ("withdraw", continuation_directive_withdraw_command, "mark a pending/adopted directive withdrawn by explicit user or higher authority"),
    ):
        parser = actions.add_parser(name, help=help_text)
        _identity_args(parser)
        parser.add_argument("--directive-id", required=True)
        parser.add_argument("--evidence-ref", action="append", default=None)
        parser.add_argument("--note", default=None)
        parser.add_argument("--actor", default="agent")
        add_json_argument(parser)
        parser.set_defaults(func=command)

    supersede = actions.add_parser(
        "supersede",
        help="replace one active directive with a new pending directive without rewriting history",
    )
    _identity_args(supersede)
    supersede.add_argument("--directive-id", required=True)
    supersede.add_argument("--kind", choices=tuple(sorted(continuation_directives.DIRECTIVE_KINDS)), required=True)
    supersede.add_argument("--priority", type=int, default=50)
    supersede.add_argument("--lifetime", choices=tuple(sorted(continuation_directives.DIRECTIVE_LIFETIMES)), default=None)
    supersede.add_argument("--text", required=True)
    supersede.add_argument("--evidence-ref", action="append", default=None)
    supersede.add_argument("--note", default=None)
    supersede.add_argument("--actor", default="user")
    add_json_argument(supersede)
    supersede.set_defaults(func=continuation_directive_supersede_command)


def _identity_args(parser) -> None:
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--task-id", default=None)


__all__ = [
    "continuation_directive_add_command",
    "continuation_directive_adopt_command",
    "continuation_directive_list_command",
    "continuation_directive_resolve_command",
    "continuation_directive_show_command",
    "continuation_directive_supersede_command",
    "continuation_directive_withdraw_command",
    "directive_context",
    "directive_hygiene",
    "load_journal",
    "observe_directive_context",
    "register_directive_parser",
]
