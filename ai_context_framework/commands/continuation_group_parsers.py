"""Parser registration for the top-level `continuation` command group.

The group fans out to the dedicated continuation sub-parser modules, so the wiring
lives here rather than inside ``commands/continuation.py`` (already close to the
2000-line agent-reviewability gate) or ``commands/continuation_parsers.py``
(``commands/continuation.py`` imports that module, so hosting this there would
create an import cycle).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ai_context_framework.commands import continuation as continuation_commands
from ai_context_framework.commands import continuation_release as continuation_release_commands
from ai_context_framework.validators.checks import validate_workstream_id


def register_continuation_parser(
    subparsers: Any, add_json_argument: Callable[..., None]
) -> None:
    """Register the whole `continuation` parser tree (moved out of ``runtime.build_parser``)."""

    continuation_parser = subparsers.add_parser(
        "continuation",
        help="manage bounded local continuation state for external AI schedulers",
    )
    continuation_subparsers = continuation_parser.add_subparsers(
        dest="continuation_command",
        required=True,
    )

    continuation_init_parser = continuation_subparsers.add_parser(
        "init",
        help="initialize bounded continuation state and capture the current Git workspace baseline",
    )
    continuation_init_parser.add_argument("path", nargs="?", type=Path)
    continuation_init_parser.add_argument("--task-id", default=None)
    continuation_init_parser.add_argument("--workstream", type=validate_workstream_id, default=None)
    continuation_init_parser.add_argument("--title", required=True)
    continuation_init_parser.add_argument("--objective", required=True)
    continuation_init_parser.add_argument("--stage", default="bootstrap")
    continuation_init_parser.add_argument("--next-action", default=None)
    continuation_init_parser.add_argument("--plan-ref", action="append", default=None)
    continuation_init_parser.add_argument("--expected-branch", default=None)
    continuation_init_parser.add_argument(
        "--profile",
        choices=tuple(sorted(continuation_commands.TIMING_PROFILES)),
        default="standard",
        help="timing profile; explicit timing flags override the selected profile",
    )
    continuation_init_parser.add_argument(
        "--interval-minutes",
        type=int,
        default=None,
    )
    continuation_init_parser.add_argument(
        "--lease-ttl-minutes",
        type=int,
        default=None,
    )
    continuation_init_parser.add_argument(
        "--renew-interval-minutes",
        type=int,
        default=None,
    )
    continuation_init_parser.add_argument("--heartbeat-interval-minutes", type=int, default=None)
    continuation_init_parser.add_argument("--stale-after-minutes", type=int, default=None)
    continuation_init_parser.add_argument("--force", action="store_true")
    add_json_argument(continuation_init_parser)
    continuation_init_parser.set_defaults(func=continuation_commands.continuation_init_command)

    continuation_commands.register_configure_parser(
        continuation_subparsers,
        add_json_argument,
    )

    continuation_doctor_parser = continuation_subparsers.add_parser(
        "doctor",
        help="verify Git/worktree identity and report whether a new round may claim",
    )
    continuation_doctor_parser.add_argument("path", nargs="?", type=Path)
    continuation_doctor_parser.add_argument("--task-id", default=None)
    add_json_argument(continuation_doctor_parser)
    continuation_doctor_parser.set_defaults(func=continuation_commands.continuation_doctor_command)

    continuation_claim_parser = continuation_subparsers.add_parser(
        "claim",
        help="claim one bounded continuation round",
    )
    continuation_claim_parser.add_argument("path", nargs="?", type=Path)
    continuation_claim_parser.add_argument("--task-id", default=None)
    continuation_claim_parser.add_argument("--runner-id", required=True)
    continuation_claim_parser.add_argument("--ttl-minutes", type=int, default=None)
    continuation_claim_parser.add_argument(
        "--handoff-review-file",
        default=None,
        help=(
            "claim by taking over reviewed ownerless handoff WIP; requires the decision file "
            "filled from `acf continuation workspace review-handoff` by the same runner"
        ),
    )
    continuation_claim_parser.add_argument(
        "--accept-head",
        default=None,
        help="explicitly accept the exact current Git HEAD when --handoff-review-file also records HEAD drift",
    )
    add_json_argument(continuation_claim_parser)
    continuation_claim_parser.set_defaults(func=continuation_commands.continuation_claim_command)

    continuation_commands.register_owner_parser(
        continuation_subparsers,
        add_json_argument,
    )

    continuation_assert_owner_parser = continuation_subparsers.add_parser(
        "assert-owner",
        help="verify that a local owner-context capability still owns the active round",
    )
    continuation_assert_owner_parser.add_argument("path", nargs="?", type=Path)
    continuation_assert_owner_parser.add_argument("--task-id", default=None)
    continuation_assert_owner_parser.add_argument("--owner-file", default=None)
    add_json_argument(continuation_assert_owner_parser)
    continuation_assert_owner_parser.set_defaults(
        func=continuation_commands.continuation_assert_owner_command
    )

    continuation_heartbeat_parser = continuation_subparsers.add_parser(
        "heartbeat",
        help="refresh runner liveness without extending the lease TTL",
    )
    continuation_heartbeat_parser.add_argument("path", nargs="?", type=Path)
    continuation_heartbeat_parser.add_argument("--task-id", default=None)
    continuation_heartbeat_parser.add_argument("--owner-file", default=None)
    add_json_argument(continuation_heartbeat_parser)
    continuation_heartbeat_parser.set_defaults(func=continuation_commands.continuation_heartbeat_command)

    continuation_commands.register_round_effect_parsers(
        continuation_subparsers,
        add_json_argument,
    )
    continuation_commands.register_workspace_parsers(
        continuation_subparsers,
        add_json_argument,
    )
    continuation_commands.register_coordination_parsers(
        continuation_subparsers,
        add_json_argument,
    )
    continuation_commands.register_execution_parser(
        continuation_subparsers,
        add_json_argument,
    )

    continuation_renew_parser = continuation_subparsers.add_parser(
        "renew",
        help="extend an active lease before it expires",
    )
    continuation_renew_parser.add_argument("path", nargs="?", type=Path)
    continuation_renew_parser.add_argument("--task-id", default=None)
    continuation_renew_parser.add_argument("--owner-file", default=None)
    continuation_renew_parser.add_argument("--ttl-minutes", type=int, default=None)
    add_json_argument(continuation_renew_parser)
    continuation_renew_parser.set_defaults(func=continuation_commands.continuation_renew_command)

    continuation_checkpoint_parser = continuation_subparsers.add_parser(
        "checkpoint",
        help="update compact continuation state while holding the active lease",
    )
    continuation_checkpoint_parser.add_argument("path", nargs="?", type=Path)
    continuation_checkpoint_parser.add_argument("--task-id", default=None)
    continuation_checkpoint_parser.add_argument("--owner-file", default=None)
    continuation_checkpoint_parser.add_argument(
        "--status",
        choices=tuple(sorted(continuation_commands.STATE_STATUSES)),
        default=None,
    )
    continuation_checkpoint_parser.add_argument("--stage", default=None)
    continuation_checkpoint_parser.add_argument("--next-action", default=None)
    continuation_checkpoint_parser.add_argument("--completed", action="append", default=None)
    continuation_checkpoint_parser.add_argument("--constraint", action="append", default=None)
    continuation_checkpoint_parser.add_argument(
        "--supersede-constraint",
        action="append",
        default=None,
        help="retire one exact current constraint superseded by newer authority; requires --evidence-ref",
    )
    continuation_checkpoint_parser.add_argument("--evidence-ref", action="append", default=None)
    continuation_checkpoint_parser.add_argument("--open-question", action="append", default=None)
    continuation_checkpoint_parser.add_argument(
        "--resolve-open-question",
        action="append",
        default=None,
        help="retire one exact current open question resolved by newer authority; requires --evidence-ref",
    )
    continuation_checkpoint_parser.add_argument("--plan-ref", action="append", default=None)
    continuation_checkpoint_parser.add_argument("--verification", action="append", default=None)
    add_json_argument(continuation_checkpoint_parser)
    continuation_checkpoint_parser.set_defaults(
        func=continuation_commands.continuation_checkpoint_command
    )

    continuation_release_commands.register_release_parser(
        continuation_subparsers,
        add_json_argument,
    )

    continuation_pause_parser = continuation_subparsers.add_parser(
        "pause",
        help="request a deterministic stop without killing an active external agent",
    )
    continuation_pause_parser.add_argument("path", nargs="?", type=Path)
    continuation_pause_parser.add_argument("--task-id", default=None)
    continuation_pause_parser.add_argument("--reason", required=True)
    continuation_pause_parser.add_argument("--requested-by", default="user")
    add_json_argument(continuation_pause_parser)
    continuation_pause_parser.set_defaults(func=continuation_commands.continuation_pause_command)

    continuation_resume_parser = continuation_subparsers.add_parser(
        "resume",
        help="resume a paused continuation after the active lease has ended",
    )
    continuation_resume_parser.add_argument("path", nargs="?", type=Path)
    continuation_resume_parser.add_argument("--task-id", default=None)
    continuation_resume_parser.add_argument("--next-action", required=True)
    add_json_argument(continuation_resume_parser)
    continuation_resume_parser.set_defaults(func=continuation_commands.continuation_resume_command)

    continuation_prompt_parser = continuation_subparsers.add_parser(
        "prompt",
        help="render a model-agnostic continuation protocol for an external agent",
    )
    continuation_prompt_parser.add_argument("path", nargs="?", type=Path)
    continuation_prompt_parser.add_argument("--task-id", default=None)
    continuation_prompt_parser.add_argument("--runner-id", default=None, help="optional current runner identity so the rendered protocol can distinguish owner vs duplicate wake")
    add_json_argument(continuation_prompt_parser)
    continuation_prompt_parser.set_defaults(func=continuation_commands.continuation_prompt_command)

    continuation_commands.register_issue_parser(continuation_subparsers, add_json_argument)
