"""Parser wiring for continuation progress, effect, and recovery commands."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable


def register_round_effect_parsers(
    subparsers,
    add_json_argument,
    *,
    round_phases: Iterable[str],
    effect_statuses: Iterable[str],
    progress_command: Callable,
    effect_prepare_command: Callable,
    effect_update_command: Callable,
    effect_list_command: Callable,
    register_recovery_parsers: Callable,
) -> None:
    progress = subparsers.add_parser(
        "progress",
        help="record bounded runtime-neutral round phase/milestone progress",
    )
    progress.add_argument("path", nargs="?", type=Path)
    progress.add_argument("--task-id", default=None)
    progress.add_argument("--lease-id", required=True)
    progress.add_argument("--generation", type=int, default=None)
    progress.add_argument("--fence-token", default=None)
    progress.add_argument("--phase", choices=tuple(sorted(set(round_phases) - {"released"})), default=None)
    progress.add_argument("--milestone", default=None)
    progress.add_argument("--evidence-ref", action="append", default=None)
    add_json_argument(progress)
    progress.set_defaults(func=progress_command)

    effect = subparsers.add_parser(
        "effect",
        help="record bounded write-ahead identities and durable external-effect observations",
    )
    effect_subparsers = effect.add_subparsers(dest="continuation_effect_command", required=True)

    prepare = effect_subparsers.add_parser(
        "prepare",
        help="prepare one deterministic external-effect identity before executing it",
    )
    prepare.add_argument("path", nargs="?", type=Path)
    prepare.add_argument("--task-id", default=None)
    prepare.add_argument("--lease-id", required=True)
    prepare.add_argument("--generation", type=int, default=None)
    prepare.add_argument("--fence-token", default=None)
    prepare.add_argument("--key", required=True)
    prepare.add_argument("--kind", required=True)
    prepare.add_argument("--external-id", default=None)
    prepare.add_argument("--milestone", default=None)
    prepare.add_argument("--evidence-ref", action="append", default=None)
    add_json_argument(prepare)
    prepare.set_defaults(func=effect_prepare_command)

    update = effect_subparsers.add_parser(
        "update",
        help="record an observed durable effect status/milestone/evidence update",
    )
    update.add_argument("path", nargs="?", type=Path)
    update.add_argument("--task-id", default=None)
    update.add_argument("--lease-id", required=True)
    update.add_argument("--generation", type=int, default=None)
    update.add_argument("--fence-token", default=None)
    update.add_argument("--key", required=True)
    update.add_argument("--status", choices=tuple(sorted(effect_statuses)), default=None)
    update.add_argument("--external-id", default=None)
    update.add_argument("--milestone", default=None)
    update.add_argument("--evidence-ref", action="append", default=None)
    add_json_argument(update)
    update.set_defaults(func=effect_update_command)

    list_parser = effect_subparsers.add_parser(
        "list",
        help="list compact durable effect records for reconciliation/reuse decisions",
    )
    list_parser.add_argument("path", nargs="?", type=Path)
    list_parser.add_argument("--task-id", default=None)
    add_json_argument(list_parser)
    list_parser.set_defaults(func=effect_list_command)

    register_recovery_parsers(subparsers, add_json_argument)
