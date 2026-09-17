"""Reviewable automation wrapper and prompt-execution contracts.

These contracts keep two concerns deliberately separate:

* the static, high-salience Writer scheduler bootstrap; and
* the dynamic Writer continuation prompt/execution policy.

The module is intentionally pure.  It describes machine-readable contracts but
does not claim continuation ownership, mutate continuation runtime state, or
infer project-specific semantics.  The former Production Observer automation
contracts were retired in ``v0.0.3.92``; only the Writer contracts and the
historical negative Writer token remain.
"""

from __future__ import annotations

from typing import Any, Mapping


AUTOMATION_PROMPT_EXECUTION_SCHEMA = "acf.automation.prompt-execution.v2"
WRITER_SCHEDULER_WRAPPER_SCHEMA = "acf.automation.writer-scheduler-wrapper.v1"
WRITER_RUNTIME_PROMPT_SCHEMA = "acf.automation.writer-runtime-prompt.v1"


WRITER_BOOTSTRAP_TOPICS = [
    "exact_existing_workspace",
    "project_access_tool_mode",
    "stable_acf_upgrade_adaptation",
    "authority_refresh",
    "execute_generated_plan",
    "owner_liveness_disclosure",
    "project_constraints",
    "write_scope_and_effect_safety",
    "checkpoint_commit_gate_not_stop",
    "final_response_contract",
]

LEGACY_WRITER_BOOTSTRAP_TOPICS = [
    "exact_existing_workspace",
    "project_access_tool_mode",
    "stable_acf_upgrade_adaptation",
    "authority_refresh",
    "execute_generated_plan",
    "owner_liveness_disclosure",
    "project_constraints",
    "final_response_contract",
]

WRITER_VOLATILE_FIELDS = [
    "owner",
    "generation",
    "stage",
    "next_action",
    "directive_content",
    "issue_batch",
    "release_candidate",
    "acceptance_counter",
]

WRITER_EXECUTION_EVIDENCE_FIELDS = [
    "semantic_stage",
    "milestone",
    "major_outcome",
    "proven",
    "excluded",
    "blocker",
    "problem",
    "plan_impact",
    "route_impact",
    "next_logic",
]

WRITER_ACTIVE_SEARCH_ALTERNATIVE_CLASSES = [
    "blocker_root_cause_diagnosis",
    "adjacent_gap_implementation",
    "validation_and_evidence",
    "reusable_contract_hardening",
    "accessible_target_dogfood",
    "release_preparation",
    "low_side_effect_diagnostics",
]

def _copy_identity(identity: Mapping[str, Any]) -> dict[str, Any]:
    """Copy the stable Writer identity without accepting arbitrary fields."""

    return {
        "workspace_root": identity.get("workspace_root"),
        "branch": identity.get("branch"),
        "task_id": identity.get("task_id"),
        "workstream_id": identity.get("workstream_id"),
    }


def _constraint_slot(slot: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the named project/task extension slot for a Writer wrapper."""

    classes = [str(value) for value in slot.get("classes") or []]
    return {
        "name": "project_task_specific_constraints",
        "required": bool(slot.get("required", True)),
        "classes": classes,
        "rule": str(slot.get("rule") or ""),
    }


def writer_scheduler_wrapper_contract(
    identity: Mapping[str, Any],
    project_constraint_slot: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the concrete static Writer scheduler wrapper contract.

    Existing ``acf.continuation.scheduler_wrapper.v1`` keys are preserved for
    compatibility while P1.5 adds explicit family/role/boundary/evidence fields.
    """

    normalized_identity = _copy_identity(identity)
    extension_slot = _constraint_slot(project_constraint_slot)
    return {
        "schema_version": "acf.continuation.scheduler_wrapper.v1",
        "contract_ref": "automation_prompt_execution_contract.writer_scheduler_wrapper",
        "wrapper_family": "writer",
        "role": "maintenance_writer",
        "generic_protocol_source": "acf continuation prompt",
        "runtime_execution_policy_source": "execution_policy",
        "refresh_prompt_each_run": True,
        "bootstrap_policy": "sufficient_high_salience",
        "identity": normalized_identity,
        "project_constraint_classes": list(extension_slot["classes"]),
        "project_specific_constraints_slot": {
            "classes": list(extension_slot["classes"]),
            "required": extension_slot["required"],
            "rule": extension_slot["rule"],
        },
        "named_extension_slot": extension_slot,
        # Preserve the v1 compatibility surface while exposing the expanded
        # P1.5 high-salience list separately.
        "required_bootstrap_topics": list(LEGACY_WRITER_BOOTSTRAP_TOPICS),
        "p15_required_bootstrap_topics": list(WRITER_BOOTSTRAP_TOPICS),
        "volatile_fields_not_static": list(WRITER_VOLATILE_FIELDS),
        "execution_evidence_fields": list(WRITER_EXECUTION_EVIDENCE_FIELDS),
        "static_vs_runtime_boundary": {
            "wrapper_owns": "stable high-salience bootstrap and project/task extension rules",
            "generated_prompt_owns": "dynamic generic ownership/recovery/directive/progress/checkpoint/release/exit authority",
        },
        "copy_generic_state_machine": False,
        "checkpoint_commit_gate_are_stop": False,
        "continuous_execution": writer_continuous_execution_contract(),
    }


def writer_continuous_execution_contract() -> dict[str, Any]:
    """Return the durable long-running Writer autonomy contract."""

    return {
        "mission_open_defaults_to_active_search": True,
        "blocked_lane_switch_to_safe_alternative": True,
        "anti_busywork_scope": "unchanged_failed_action_without_new_evidence_input_environment_or_strategy",
        "no_op_waiting_is_default": False,
        "alternative_classes": list(WRITER_ACTIVE_SEARCH_ALTERNATIVE_CLASSES),
        "prefer_work_unit": "overall_mission_and_plan_stage",
        "avoid_micro_workstream_fragmentation": True,
        "checkpoint_requires_authority_refresh_and_continue": True,
        "session_end_without_hard_stop_requires_exhausted_safe_incremental_alternatives": True,
        "no_useful_work_conclusion_requires_alternative_audit": True,
        "control_plane_checks_proportional_to_evidence_backed_risk": True,
        "prefer_cheapest_deterministic_safe_continuation": True,
        "genuine_ambiguity_behavior": "fail_closed",
        "safe_session_end_requires_graceful_handoff": True,
        "ghost_running_owner_allowed_at_safe_end": False,
        "verified_live_physical_execution_must_not_duplicate": True,
        "non_stop_signals": [
            "active_lease",
            "prior_abnormal_generation",
            "task_owned_dirty_state",
            "scheduler_wake",
            "checkpoint",
            "test",
            "commit",
            "gate_completion",
            "single_blocked_lane",
        ],
        "timing_policy": {
            "liveness_timing_configurable": True,
            "elapsed_time_diagnostic_only": True,
            "fixed_execution_budget_semantic_policy_allowed": False,
        },
        "execution_observability": {
            "classes": [
                "bootstrap_control_plane",
                "project_work",
                "physical_execution",
                "graceful_handoff",
                "abnormal_incomplete_termination",
                "recovery_overhead",
            ],
            "timing_values_are_diagnostic_only": True,
            "fixed_timing_budget_allowed": False,
        },
    }


def writer_runtime_prompt_contract() -> dict[str, Any]:
    """Return the dynamic Writer-runtime side of the P1.5 separation contract."""

    return {
        "schema_version": WRITER_RUNTIME_PROMPT_SCHEMA,
        "role": "writer_runtime_generated",
        "authority_sources": ["acf continuation prompt", "execution_policy"],
        "refresh_each_scheduler_wake": True,
        "owns_dynamic_generic_authority": [
            "owner_liveness",
            "claim_challenge_reconcile_recover",
            "workspace_provenance_and_fencing",
            "directive_inbox",
            "current_plan",
            "progress_checkpoint_release",
            "session_exit",
        ],
        "must_not_embed": [
            "project_specific_runtime_rules",
            "project_specific_scientific_rules",
            "project_specific_resource_rules",
            "production_observer_semantic_state_machine",
        ],
        "project_specific_constraints_static_in_runtime_prompt": False,
        "copy_scheduler_wrapper": False,
        "continuous_execution": writer_continuous_execution_contract(),
    }


def automation_prompt_execution_contract() -> dict[str, Any]:
    """Return the common reviewable P1.5 automation family contract."""

    return {
        "schema_version": AUTOMATION_PROMPT_EXECUTION_SCHEMA,
        "separation_required": True,
        "roles": [
            "writer_scheduler_wrapper",
            "writer_runtime_generated",
        ],
        "writer_scheduler_wrapper": {
            "schema_version": WRITER_SCHEDULER_WRAPPER_SCHEMA,
            "bootstrap_policy": "sufficient_high_salience",
            "required_bootstrap_topics": list(WRITER_BOOTSTRAP_TOPICS),
            "volatile_fields_not_static": list(WRITER_VOLATILE_FIELDS),
            "named_extension_slot": "project_task_specific_constraints",
            "copy_generic_state_machine": False,
            "continuous_execution": writer_continuous_execution_contract(),
        },
        "writer_continuous_execution": writer_continuous_execution_contract(),
        "writer_runtime_generated": writer_runtime_prompt_contract(),
        "dogfood_acceptance": {
            "task_families": [
                "acf_writer",
                "fcc_ws079_writer",
                "fcc_ws080_writer",
                "fcc_ws086_writer",
                "astockt_ai_writer",
            ],
            "shared_core_consistency_required": True,
            "project_unique_constraints_preserved": True,
            "existing_wrapper_migration_must_be_safe": True,
            "real_scheduled_agent_consumption_required": True,
        },
    }


__all__ = [
    "AUTOMATION_PROMPT_EXECUTION_SCHEMA",
    "WRITER_BOOTSTRAP_TOPICS",
    "WRITER_ACTIVE_SEARCH_ALTERNATIVE_CLASSES",
    "WRITER_EXECUTION_EVIDENCE_FIELDS",
    "automation_prompt_execution_contract",
    "writer_continuous_execution_contract",
    "writer_runtime_prompt_contract",
    "writer_scheduler_wrapper_contract",
]
