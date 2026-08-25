"""CLI adapter for durable continuation user-authority directives."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Mapping

from ai_context_framework import continuation_directives


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
        return continuation_directives.load_journal(
            paths["directives"],
            task_id=str(control["task_id"]),
        )
    except continuation_directives.DirectiveError as exc:
        raise _directive_error(exc) from exc


def directive_context(paths: Mapping[str, Path], control: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return continuation_directives.directive_context(load_journal(paths, control))
    except continuation_directives.DirectiveError as exc:
        raise _directive_error(exc) from exc


def write_journal(paths: Mapping[str, Path], journal: Mapping[str, Any]) -> None:
    _continuation()._write_json(paths["directives"], journal)


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
                    evidence_refs=args.evidence_ref or [],
                )
            except continuation_directives.DirectiveError as exc:
                raise _directive_error(exc) from exc
            write_journal(paths, journal)
            return {
                "status": "directive_added",
                "task_id": control["task_id"],
                "directive": directive,
                "directive_context": continuation_directives.directive_context(journal),
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
            directives = continuation_directives.list_directives(journal, status=args.status)
            context = continuation_directives.directive_context(journal)
        except continuation_directives.DirectiveError as exc:
            raise _directive_error(exc) from exc
        return {
            "status": "directives_listed",
            "task_id": control["task_id"],
            "directive_count": len(directives),
            "directives": directives,
            "directive_context": context,
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
            directive = continuation_directives.show_directive(journal, args.directive_id)
        except continuation_directives.DirectiveError as exc:
            raise _directive_error(exc) from exc
        return {
            "status": "directive_shown",
            "task_id": control["task_id"],
            "directive": directive,
            "directive_context": continuation_directives.directive_context(journal),
            "journal_path": str(paths["directives"]),
        }

    return core._guarded(args, "continuation directive show", operation)


def continuation_directive_adopt_command(args: argparse.Namespace) -> int:
    return _transition_command(args, transition="adopt")


def continuation_directive_resolve_command(args: argparse.Namespace) -> int:
    return _transition_command(args, transition="resolve")


def _transition_command(args: argparse.Namespace, *, transition: str) -> int:
    core = _continuation()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            journal = load_journal(paths, control)
            try:
                function = (
                    continuation_directives.adopt_directive
                    if transition == "adopt"
                    else continuation_directives.resolve_directive
                )
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
            if changed:
                write_journal(paths, journal)
            past_tense = "adopted" if transition == "adopt" else "resolved"
            return {
                "status": f"directive_{past_tense}" if changed else f"directive_already_{past_tense}",
                "task_id": control["task_id"],
                "changed": changed,
                "directive": directive,
                "directive_context": continuation_directives.directive_context(journal),
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
                    evidence_refs=args.evidence_ref or [],
                    note=args.note,
                )
            except continuation_directives.DirectiveError as exc:
                raise _directive_error(exc) from exc
            write_journal(paths, journal)
            return {
                "status": "directive_superseded",
                "task_id": control["task_id"],
                "superseded": superseded,
                "replacement": replacement,
                "directive_context": continuation_directives.directive_context(journal),
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
    "directive_context",
    "load_journal",
    "register_directive_parser",
]
