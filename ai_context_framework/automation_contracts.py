"""Reviewable automation wrapper and prompt-execution contracts.

These contracts keep three concerns deliberately separate:

* the static, high-salience Writer scheduler bootstrap;
* the dynamic Writer continuation prompt/execution policy; and
* the static Production Observer scheduler bootstrap plus semantic-review rules.

The module is intentionally pure.  It describes machine-readable contracts but
does not claim continuation ownership, mutate Observer runtime state, or infer
project-specific semantics.
"""

from __future__ import annotations

from typing import Any, Mapping


AUTOMATION_PROMPT_EXECUTION_SCHEMA = "acf.automation.prompt-execution.v1"
WRITER_SCHEDULER_WRAPPER_SCHEMA = "acf.automation.writer-scheduler-wrapper.v1"
WRITER_RUNTIME_PROMPT_SCHEMA = "acf.automation.writer-runtime-prompt.v1"
PRODUCTION_OBSERVER_WRAPPER_SCHEMA = "acf.automation.production-observer-wrapper.v1"
OBSERVER_SEMANTIC_REVIEW_SCHEMA = "acf.automation.observer-semantic-review.v1"
OBSERVER_EXECUTION_EVIDENCE_SCHEMA = "acf.automation.observer-execution-evidence.v1"
PRESENTATION_MAINTENANCE_SCHEMA = "acf.automation.presentation-maintenance.v1"


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

OBSERVER_SEMANTIC_REVIEW_DECISIONS = [
    "unchanged",
    "patch",
    "rebuild",
    "presentation_change",
    "project_overview_enable",
    "project_overview_disable",
]

OBSERVER_PRESENTATION_TYPES = [
    "flow",
    "branch",
    "architecture",
    "dependency",
    "roadmap",
    "state_machine",
    "timeline",
    "multi_lane",
    "tree",
    "text",
    "hybrid",
]
OBSERVER_PRIMARY_VISUALIZATION_KINDS = [
    "metric_trend",
    "status_matrix",
    "process_flow",
    "roadmap",
]

OBSERVER_AUTHORITY_REVIEW_INPUTS = [
    "plan",
    "task_plan",
    "workstream",
    "current_task",
    "planning_references",
    "adr",
    "user_directives",
    "current_stage",
    "key_evidence",
    "execution_deviation",
    "problems",
    "dependencies",
    "parallel_paths",
    "strategy",
]

PRESENTATION_MAINTENANCE_LIFECYCLES = [
    "transient_patch",
    "one_shot_semantic_review",
    "durable_rule",
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


def production_observer_wrapper_contract() -> dict[str, Any]:
    """Return the static Production Observer scheduler bootstrap contract."""

    return {
        "schema_version": PRODUCTION_OBSERVER_WRAPPER_SCHEMA,
        "wrapper_family": "production_observer",
        "role": "production_observer",
        "bootstrap_policy": "sufficient_high_salience",
        "access_boundary": {
            "read": "broad",
            "write": "narrow_user_level_observer_state",
            "control": "none",
        },
        "existing_checkout_required": True,
        "display_scope_source": "explicit_user_level_target_registry",
        "anti_masking": {
            "maintenance_writer_refresh_counts_as_production": False,
            "production_activation_required_for_acceptance": True,
        },
        "semantic_review_required_each_refresh": True,
        "map_review_gate_required_for_semantic_risk": True,
        "truthful_run_history_required": True,
        "authority_source_policy": {
            "local_authority_first": True,
            "derived_state_replaces_authority": False,
            "required_review_inputs": list(OBSERVER_AUTHORITY_REVIEW_INPUTS),
        },
        "project_overview_policy": {
            "enable_when_unified_route_is_evidence_backed": True,
            "disable_requires_evidence": True,
            "disable_for_convenience_allowed": False,
            "reevaluate_when_authority_changes": True,
        },
        "presentation_selection": {
            "select_from_semantics": True,
            "allowed_types": list(OBSERVER_PRESENTATION_TYPES),
            "fixed_template_required": False,
            "primary_progress_question_required": True,
            "one_dominant_primary_visualization": True,
            "allowed_primary_visualization_kinds": list(OBSERVER_PRIMARY_VISUALIZATION_KINDS),
            "renderer_selects_kind": False,
            "project_or_target_hardcoding_allowed": False,
            "generic_fallback_must_remain_fail_visible": True,
        },
        "cross_project_interference_allowed": False,
        "human_information_policy": "human_first_but_detailed",
        "human_visible_required_fields": [
            "goal",
            "route",
            "current_position",
            "why",
            "proven",
            "problems",
            "next",
            "health",
            "run_history",
        ],
        "named_extension_slot": {
            "name": "project_target_specific_observer_rules",
            "classes": [
                "project_authority",
                "target_semantics",
                "display_policy",
                "human_time_presentation",
                "privacy_and_security",
            ],
        },
        "copy_writer_state_machine": False,
    }


def observer_semantic_review_contract() -> dict[str, Any]:
    """Return the fail-visible semantic anti-laziness contract."""

    return {
        "schema_version": OBSERVER_SEMANTIC_REVIEW_SCHEMA,
        "required_each_semantic_refresh": True,
        "decision_values": list(OBSERVER_SEMANTIC_REVIEW_DECISIONS),
        "required_evidence_fields": [
            "decision",
            "reason",
            "evidence_refs",
            "source_fingerprint",
        ],
        "source_fingerprint_role": "triage_only_not_semantic_completion",
        "unchanged_is_audited_decision": True,
        "authority_review_inputs": list(OBSERVER_AUTHORITY_REVIEW_INPUTS),
        "map_relevant_change_requires_authority_reread": True,
        "map_relevant_change_classes": [
            "node_relationship",
            "route_order",
            "dependency",
            "stage_or_completion_state",
            "architecture",
            "mainline_or_branch_semantics",
            "project_overview_decision",
        ],
        "task_semantic_visualization": {
            "derive_primary_progress_question_from_fresh_authority": True,
            "record_selection_reason_and_evidence": True,
            "allowed_kinds": list(OBSERVER_PRIMARY_VISUALIZATION_KINDS),
            "low_confidence_must_be_fail_visible": True,
            "renderer_may_infer_project_semantics": False,
        },
        "insufficient_evidence_behavior": "remain_stale_fail_visible",
    }


def observer_execution_evidence_contract() -> dict[str, Any]:
    """Return the minimum semantic evidence useful to an Observer/human."""

    return {
        "schema_version": OBSERVER_EXECUTION_EVIDENCE_SCHEMA,
        "required_fields": list(WRITER_EXECUTION_EVIDENCE_FIELDS),
        "heartbeat_generation_only_is_sufficient": False,
        "run_history": {
            "preferred_time_source": "continuation_round",
            "fallback_time_source": "user_level_observer_run_marker",
            "required_fields": ["start", "end", "duration", "result", "major_outcome", "route_link"],
            "incomplete_run_may_fabricate_end": False,
            "incomplete_run_display": ["last_activity", "lower_bound_or_approximate_duration"],
        },
        "purpose": "explain what changed, what is proven/excluded, route impact, blockers, and next logic",
    }


def presentation_maintenance_contract() -> dict[str, Any]:
    """Return lifecycle/safety rules for interactive Observer presentation maintenance."""

    return {
        "schema_version": PRESENTATION_MAINTENANCE_SCHEMA,
        "lifecycles": list(PRESENTATION_MAINTENANCE_LIFECYCLES),
        "access_boundary": {
            "read": "broad",
            "write": "narrow_user_level_derived_presentation_state",
            "control": "none",
            "writer_ownership_required": False,
            "foreign_project_noninterference_required": True,
        },
        "review_before_record": {
            "required": True,
            "agent_responsibility": "understand_current_derived_state_and_user_intent",
            "required_fields": ["reviewed_intent", "scope", "rationale", "evidence_refs"],
            "acf_responsibility": "deterministic_record_validation_and_concurrency_only",
            "acf_judges_semantics": False,
        },
        "transient_patch": {
            "scope": "presentation_only_derived_state",
            "may_apply_immediately": True,
            "application_surface": "user_level_derived_presentation",
            "deterministic_rerender_required": True,
            "direct_dashboard_edit_allowed": False,
            "semantic_change_allowed": False,
        },
        "one_shot_semantic_review": {
            "consumed_by": "next_production_observer_semantic_review",
            "remove_from_active_context_after_success": True,
            "preserve_audit_history": True,
            "resolved_guidance_may_resurrect": False,
        },
        "durable_rule": {
            "active_until_terminal_disposition": True,
            "supports_supersede": True,
            "supports_withdraw": True,
            "resolved_transient_guidance_may_resurrect": False,
        },
        "optimistic_concurrency": {
            "required": True,
            "compare": ["presentation_revision", "presentation_fingerprint"],
            "conflict_behavior": "fail_closed_reread_and_reevaluate",
        },
        "semantic_risk_escalation": {
            "required": True,
            "action": "map_review_and_authority_reread",
            "change_classes": observer_semantic_review_contract()["map_relevant_change_classes"],
        },
        # Compatibility keys retained for existing first-candidate consumers.
        "writer_ownership_required": False,
        "cross_project_interference_allowed": False,
    }


def automation_prompt_execution_contract() -> dict[str, Any]:
    """Return the common reviewable P1.5 automation family contract."""

    return {
        "schema_version": AUTOMATION_PROMPT_EXECUTION_SCHEMA,
        "separation_required": True,
        "roles": [
            "writer_scheduler_wrapper",
            "writer_runtime_generated",
            "production_observer_scheduler_wrapper",
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
        "production_observer_scheduler_wrapper": production_observer_wrapper_contract(),
        "observer_semantic_review": observer_semantic_review_contract(),
        "observer_execution_evidence": observer_execution_evidence_contract(),
        "presentation_maintenance": presentation_maintenance_contract(),
        "dogfood_acceptance": {
            "task_families": [
                "acf_writer",
                "acf_observer",
                "fcc_ws079_writer",
                "fcc_ws080_writer",
                "fcc_ws086_writer",
                "fcc_observer",
                "astockt_ai_writer",
                "astockt_ai_observer",
            ],
            "shared_core_consistency_required": True,
            "project_unique_constraints_preserved": True,
            "existing_wrapper_migration_must_be_safe": True,
            "real_scheduled_agent_consumption_required": True,
            "presentation_lifecycle_cases": [
                "immediate_interactive_correction",
                "next_run_semantic_review",
                "transient_cleanup",
                "durable_rule_persistence",
                "production_render_does_not_resurrect_one_shot",
            ],
        },
    }


__all__ = [
    "AUTOMATION_PROMPT_EXECUTION_SCHEMA",
    "OBSERVER_AUTHORITY_REVIEW_INPUTS",
    "OBSERVER_PRIMARY_VISUALIZATION_KINDS",
    "OBSERVER_PRESENTATION_TYPES",
    "OBSERVER_SEMANTIC_REVIEW_DECISIONS",
    "PRESENTATION_MAINTENANCE_LIFECYCLES",
    "WRITER_BOOTSTRAP_TOPICS",
    "WRITER_ACTIVE_SEARCH_ALTERNATIVE_CLASSES",
    "WRITER_EXECUTION_EVIDENCE_FIELDS",
    "automation_prompt_execution_contract",
    "observer_execution_evidence_contract",
    "observer_semantic_review_contract",
    "presentation_maintenance_contract",
    "production_observer_wrapper_contract",
    "writer_continuous_execution_contract",
    "writer_runtime_prompt_contract",
    "writer_scheduler_wrapper_contract",
]
