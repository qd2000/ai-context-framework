"""CLI adapter for bounded continuation round/effect journal commands.

A round journal records the current fenced round's phase and milestone; an
effect journal records durable write-ahead identities so a new generation can
prove which non-idempotent side effect already happened instead of replaying an
uncertain outcome.  These commands live outside the main continuation controller
so every module stays inside the repository's agent-friendly size budget.
"""

from __future__ import annotations

import argparse
from typing import Any

from ai_context_framework import continuation_effect_archive, continuation_rounds
from ai_context_framework.commands import continuation_workspace as continuation_workspace_commands


def _core():
    # Imported lazily to avoid a module-import cycle: the main continuation
    # controller imports this adapter for backwards-compatible command aliases.
    from ai_context_framework.commands import continuation

    return continuation


def continuation_progress_command(args: argparse.Namespace) -> int:
    core = _core()

    def operation() -> dict[str, Any]:
        if args.phase is None and args.milestone is None and not (args.evidence_ref or []):
            raise core.ContinuationError(
                "progress requires --phase, --milestone, or --evidence-ref",
                code="progress_empty",
            )
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            snapshot = core._lease_snapshot(paths, control)
            lease, _owner_context = continuation_workspace_commands.assert_owner_context(
                args,
                paths,
                root=root,
                control=control,
                snapshot=snapshot,
            )
            generation = core._require_fenced_generation(lease)
            journal = core._load_round_journal(paths, control, require_existing=True)
            milestone = (
                core._validate_public_input_text(args.milestone, field="milestone")
                if args.milestone is not None
                else None
            )
            evidence_refs = [
                core._validate_public_input_text(value, field="evidence_ref")
                for value in (args.evidence_ref or [])
            ]
            try:
                journal, record = continuation_rounds.update_round(
                    journal,
                    task_id=str(control["task_id"]),
                    generation=generation,
                    lease_id=str(lease["lease_id"]),
                    phase=args.phase,
                    milestone=milestone,
                    evidence_refs=evidence_refs,
                    now=core._iso(),
                )
            except continuation_rounds.ContinuationRoundError as exc:
                raise core._round_error(exc) from exc
            core._write_json(paths["rounds"], journal)
            return {
                "status": "progress_recorded",
                "round": record,
                "generation": generation,
            }

    return core._guarded(args, "continuation progress", operation)


def continuation_effect_prepare_command(args: argparse.Namespace) -> int:
    core = _core()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            snapshot = core._lease_snapshot(paths, control)
            lease, _owner_context = continuation_workspace_commands.assert_owner_context(
                args,
                paths,
                root=root,
                control=control,
                snapshot=snapshot,
            )
            generation = core._require_fenced_generation(lease)
            journal = core._load_effect_journal(paths, control)
            logical_key = core._validate_public_input_text(args.key, field="logical_key")
            kind = core._validate_public_input_text(args.kind, field="effect_kind")
            external_id = (
                core._validate_public_input_text(args.external_id, field="external_id")
                if args.external_id is not None
                else None
            )
            milestone = (
                core._validate_public_input_text(args.milestone, field="milestone")
                if args.milestone is not None
                else None
            )
            evidence_refs = [
                core._validate_public_input_text(value, field="evidence_ref")
                for value in (args.evidence_ref or [])
            ]
            try:
                journal, effect, created, summary, rollover = continuation_effect_archive.prepare_with_rollover(
                    paths["effects"], journal,
                    task_id=str(control["task_id"]), generation=generation,
                    logical_key=logical_key, kind=kind, external_id=external_id,
                    milestone=milestone, evidence_refs=evidence_refs, now=core._iso(),
                )
            except continuation_rounds.ContinuationRoundError as exc:
                raise core._round_error(exc) from exc
            return {
                "status": "effect_prepared" if created else "effect_exists",
                "created": created,
                "effect": effect,
                "summary": summary,
                "rollover": rollover,
            }

    return core._guarded(args, "continuation effect prepare", operation)


def continuation_effect_update_command(args: argparse.Namespace) -> int:
    core = _core()

    def operation() -> dict[str, Any]:
        if (
            args.status is None
            and args.external_id is None
            and args.milestone is None
            and not (args.evidence_ref or [])
        ):
            raise core.ContinuationError(
                "effect update requires a status, external id, milestone, or evidence reference",
                code="effect_update_empty",
            )
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            snapshot = core._lease_snapshot(paths, control)
            lease, _owner_context = continuation_workspace_commands.assert_owner_context(
                args,
                paths,
                root=root,
                control=control,
                snapshot=snapshot,
            )
            generation = core._require_fenced_generation(lease)
            journal = core._load_effect_journal(paths, control, require_existing=True)
            logical_key = core._validate_public_input_text(args.key, field="logical_key")
            external_id = (
                core._validate_public_input_text(args.external_id, field="external_id")
                if args.external_id is not None
                else None
            )
            milestone = (
                core._validate_public_input_text(args.milestone, field="milestone")
                if args.milestone is not None
                else None
            )
            evidence_refs = [
                core._validate_public_input_text(value, field="evidence_ref")
                for value in (args.evidence_ref or [])
            ]
            try:
                journal, effect, summary = continuation_effect_archive.update_across_history(
                    paths["effects"],
                    journal,
                    task_id=str(control["task_id"]),
                    generation=generation,
                    logical_key=logical_key,
                    status=args.status,
                    external_id=external_id,
                    milestone=milestone,
                    evidence_refs=evidence_refs,
                    now=core._iso(),
                )
            except continuation_rounds.ContinuationRoundError as exc:
                raise core._round_error(exc) from exc
            return {
                "status": "effect_updated",
                "effect": effect,
                "summary": summary,
            }

    return core._guarded(args, "continuation effect update", operation)


def continuation_effect_list_command(args: argparse.Namespace) -> int:
    core = _core()

    def operation() -> dict[str, Any]:
        root = core._workspace_root(args.path)
        paths = core._paths(root, args.task_id)
        with core._state_lock(paths["lock"]):
            control = core._load_control(paths, root)
            journal = core._load_effect_journal(paths, control)
            try:
                effects, summary, archive_paths = continuation_effect_archive.list_history(
                    paths["effects"], journal, task_id=str(control["task_id"])
                )
            except continuation_rounds.ContinuationRoundError as exc:
                raise core._round_error(exc) from exc
            return {
                "status": "listed",
                "effects": effects,
                "summary": summary,
                "path": str(paths["effects"]),
                "archive_paths": archive_paths,
            }

    return core._guarded(args, "continuation effect list", operation)


__all__ = [
    "continuation_effect_list_command",
    "continuation_effect_prepare_command",
    "continuation_effect_update_command",
    "continuation_progress_command",
]
