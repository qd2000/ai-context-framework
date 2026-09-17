from __future__ import annotations

import unittest

from ai_context_framework.automation_contracts import (
    AUTOMATION_PROMPT_EXECUTION_SCHEMA,
    WRITER_ACTIVE_SEARCH_ALTERNATIVE_CLASSES,
    WRITER_BOOTSTRAP_TOPICS,
    WRITER_EXECUTION_EVIDENCE_FIELDS,
    automation_prompt_execution_contract,
    writer_continuous_execution_contract,
    writer_runtime_prompt_contract,
    writer_scheduler_wrapper_contract,
)


class AutomationContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.identity = {
            "workspace_root": r"C:\PROJECT\example_worktree",
            "branch": "codex/WS900-example",
            "task_id": "WS900",
            "workstream_id": "WS900",
            "ignored": "must-not-leak",
        }
        self.slot = {
            "required": True,
            "classes": [
                "tooling",
                "runtime",
                "resource",
                "permission",
                "security",
                "scientific",
                "validation",
                "issue_reporting",
            ],
            "rule": "Project/task rules stay in this named extension slot.",
        }

    def test_writer_wrapper_preserves_v1_compatibility_and_adds_p15_boundary(self) -> None:
        contract = writer_scheduler_wrapper_contract(self.identity, self.slot)

        self.assertEqual("acf.continuation.scheduler_wrapper.v1", contract["schema_version"])
        self.assertEqual("writer", contract["wrapper_family"])
        self.assertEqual("maintenance_writer", contract["role"])
        self.assertEqual("acf continuation prompt", contract["generic_protocol_source"])
        self.assertEqual("execution_policy", contract["runtime_execution_policy_source"])
        self.assertTrue(contract["refresh_prompt_each_run"])
        self.assertEqual("sufficient_high_salience", contract["bootstrap_policy"])
        self.assertFalse(contract["copy_generic_state_machine"])
        self.assertFalse(contract["checkpoint_commit_gate_are_stop"])
        continuous = contract["continuous_execution"]
        self.assertTrue(continuous["mission_open_defaults_to_active_search"])
        self.assertTrue(continuous["blocked_lane_switch_to_safe_alternative"])
        self.assertFalse(continuous["no_op_waiting_is_default"])
        self.assertTrue(continuous["avoid_micro_workstream_fragmentation"])
        self.assertTrue(continuous["checkpoint_requires_authority_refresh_and_continue"])
        self.assertTrue(continuous["no_useful_work_conclusion_requires_alternative_audit"])
        self.assertEqual(WRITER_ACTIVE_SEARCH_ALTERNATIVE_CLASSES, continuous["alternative_classes"])
        self.assertNotIn("ignored", contract["identity"])
        self.assertEqual("project_task_specific_constraints", contract["named_extension_slot"]["name"])
        self.assertEqual(self.slot["classes"], contract["project_constraint_classes"])
        self.assertEqual(WRITER_BOOTSTRAP_TOPICS, contract["p15_required_bootstrap_topics"])
        self.assertEqual(WRITER_EXECUTION_EVIDENCE_FIELDS, contract["execution_evidence_fields"])
        self.assertIn("owner", contract["volatile_fields_not_static"])
        self.assertIn("generation", contract["volatile_fields_not_static"])
        self.assertIn("next_action", contract["volatile_fields_not_static"])

        # Existing v1 consumers keep the original eight-topic compatibility list.
        self.assertEqual(
            [
                "exact_existing_workspace",
                "project_access_tool_mode",
                "stable_acf_upgrade_adaptation",
                "authority_refresh",
                "execute_generated_plan",
                "owner_liveness_disclosure",
                "project_constraints",
                "final_response_contract",
            ],
            contract["required_bootstrap_topics"],
        )

    def test_writer_runtime_prompt_is_dynamic_generic_authority_only(self) -> None:
        contract = writer_runtime_prompt_contract()

        self.assertEqual("writer_runtime_generated", contract["role"])
        self.assertEqual(["acf continuation prompt", "execution_policy"], contract["authority_sources"])
        self.assertTrue(contract["refresh_each_scheduler_wake"])
        self.assertIn("owner_liveness", contract["owns_dynamic_generic_authority"])
        self.assertIn("directive_inbox", contract["owns_dynamic_generic_authority"])
        self.assertFalse(contract["project_specific_constraints_static_in_runtime_prompt"])
        self.assertIn("production_observer_semantic_state_machine", contract["must_not_embed"])
        self.assertEqual(writer_continuous_execution_contract(), contract["continuous_execution"])

    def test_writer_continuous_execution_requires_active_alternative_search(self) -> None:
        contract = writer_continuous_execution_contract()

        self.assertTrue(contract["mission_open_defaults_to_active_search"])
        self.assertTrue(contract["blocked_lane_switch_to_safe_alternative"])
        self.assertEqual(
            "unchanged_failed_action_without_new_evidence_input_environment_or_strategy",
            contract["anti_busywork_scope"],
        )
        self.assertFalse(contract["no_op_waiting_is_default"])
        self.assertEqual(WRITER_ACTIVE_SEARCH_ALTERNATIVE_CLASSES, contract["alternative_classes"])
        self.assertEqual("overall_mission_and_plan_stage", contract["prefer_work_unit"])
        self.assertTrue(contract["avoid_micro_workstream_fragmentation"])
        self.assertTrue(contract["checkpoint_requires_authority_refresh_and_continue"])
        self.assertTrue(
            contract["session_end_without_hard_stop_requires_exhausted_safe_incremental_alternatives"]
        )
        self.assertTrue(contract["no_useful_work_conclusion_requires_alternative_audit"])
        self.assertTrue(contract["control_plane_checks_proportional_to_evidence_backed_risk"])
        self.assertTrue(contract["prefer_cheapest_deterministic_safe_continuation"])
        self.assertEqual("fail_closed", contract["genuine_ambiguity_behavior"])
        self.assertTrue(contract["safe_session_end_requires_graceful_handoff"])
        self.assertFalse(contract["ghost_running_owner_allowed_at_safe_end"])
        self.assertTrue(contract["verified_live_physical_execution_must_not_duplicate"])
        self.assertIn("active_lease", contract["non_stop_signals"])
        self.assertIn("single_blocked_lane", contract["non_stop_signals"])
        self.assertTrue(contract["timing_policy"]["liveness_timing_configurable"])
        self.assertTrue(contract["timing_policy"]["elapsed_time_diagnostic_only"])
        self.assertFalse(contract["timing_policy"]["fixed_execution_budget_semantic_policy_allowed"])
        observability = contract["execution_observability"]
        self.assertEqual(
            [
                "bootstrap_control_plane",
                "project_work",
                "physical_execution",
                "graceful_handoff",
                "abnormal_incomplete_termination",
                "recovery_overhead",
            ],
            observability["classes"],
        )
        self.assertTrue(observability["timing_values_are_diagnostic_only"])
        self.assertFalse(observability["fixed_timing_budget_allowed"])

    def test_aggregate_contract_keeps_role_separation_reviewable(self) -> None:
        contract = automation_prompt_execution_contract()

        self.assertEqual(AUTOMATION_PROMPT_EXECUTION_SCHEMA, contract["schema_version"])
        self.assertTrue(contract["separation_required"])
        self.assertEqual(
            [
                "writer_scheduler_wrapper",
                "writer_runtime_generated",
            ],
            contract["roles"],
        )
        self.assertFalse(contract["writer_scheduler_wrapper"]["copy_generic_state_machine"])
        self.assertEqual(
            writer_continuous_execution_contract(),
            contract["writer_scheduler_wrapper"]["continuous_execution"],
        )
        self.assertEqual(
            writer_continuous_execution_contract(),
            contract["writer_continuous_execution"],
        )
        self.assertEqual(
            "writer_runtime_generated",
            contract["writer_runtime_generated"]["role"],
        )
        self.assertNotIn("production_observer_scheduler_wrapper", contract)
        self.assertNotIn("observer_semantic_review", contract)
        self.assertNotIn("observer_execution_evidence", contract)
        self.assertNotIn("presentation_maintenance", contract)
        dogfood = contract["dogfood_acceptance"]
        self.assertTrue(dogfood["shared_core_consistency_required"])
        self.assertTrue(dogfood["project_unique_constraints_preserved"])
        self.assertTrue(dogfood["existing_wrapper_migration_must_be_safe"])
        self.assertTrue(dogfood["real_scheduled_agent_consumption_required"])
        self.assertIn("fcc_ws086_writer", dogfood["task_families"])
        self.assertNotIn("acf_observer", dogfood["task_families"])
        self.assertNotIn("presentation_lifecycle_cases", dogfood)
        self.assertNotIn("agent_first_cases", dogfood)


if __name__ == "__main__":
    unittest.main()
