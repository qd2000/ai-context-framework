import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import acf

from ai_context_framework.observer_targets import (
    ObserverTargetRegistryError,
    build_target_views,
    record_target_run_finish,
    record_target_run_start,
    read_expected_target_registry,
    read_target_registry,
    recover_expected_targets,
    register_target,
    register_expected_target,
    remove_expected_target,
    remove_target,
    set_project_overview_decision,
    target_registry_alert_specs,
    target_registry_health,
)
from ai_context_framework.observer_storage import SemanticSensitiveValueError, render_dashboard_html


class ObserverTargetRegistryTests(unittest.TestCase):
    def make_project(self, root: Path):
        return SimpleNamespace(
            project_id="project-test",
            observer_dir=root / "observer",
            canonical_root=root / "project",
        )

    def test_registry_is_empty_until_target_is_explicitly_registered(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            registry = read_target_registry(project)
            self.assertEqual(registry["targets"], [])
            self.assertEqual(registry["project_overview"]["decision"], "undecided")
            self.assertFalse(project.observer_dir.exists())

    def test_expected_target_contract_survives_observer_runtime_loss_and_recovers_exact_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self.make_project(root)
            expected, changed = register_expected_target(
                project,
                target_id="ws012-writer",
                mode="fixed_workstream",
                title="WS012 Writer",
                automation_ref="automation:ws012-writer",
                workstream_id="WS012",
                continuation_task_id="WS012",
                route_ref="docs/ai/reference/ws012/PLAN.md",
            )
            self.assertTrue(changed)
            expected_path = project.observer_dir.parent / "observer_expected_targets.json"
            self.assertTrue(expected_path.is_file())
            register_target(
                project,
                target_id="ws012-writer",
                mode="fixed_workstream",
                title="WS012 Writer",
                automation_ref="automation:ws012-writer",
                workstream_id="WS012",
                continuation_task_id="WS012",
                route_ref="docs/ai/reference/ws012/PLAN.md",
            )
            import shutil

            shutil.rmtree(project.observer_dir)
            self.assertTrue(expected_path.is_file())
            empty = read_target_registry(project)
            health = target_registry_health(project, registry=empty, expected_registry=expected)
            self.assertEqual(health["status"], "incomplete")
            self.assertEqual(health["missing_expected_target_ids"], ["ws012-writer"])
            self.assertEqual(target_registry_alert_specs({"registry_health": health})[0]["severity"], "warning")

            recovered, target_ids, changed = recover_expected_targets(project)
            self.assertTrue(changed)
            self.assertEqual(target_ids, ["ws012-writer"])
            self.assertEqual([row["target_id"] for row in recovered["targets"]], ["ws012-writer"])
            self.assertEqual(read_expected_target_registry(project)["targets"][0]["target_id"], "ws012-writer")
            self.assertEqual(target_registry_health(project)["status"], "healthy")

    def test_empty_registry_without_expected_contract_is_fail_visible_not_green(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            views = build_target_views(project, {"workstreams": [], "continuations": []})
            self.assertEqual(views["registry_health"]["status"], "unconfigured")
            alerts = target_registry_alert_specs(views)
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0]["alert_key"], "observer:target-registry-health")

    def test_expected_target_conflict_is_fail_visible_and_recovery_does_not_overwrite_live_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            register_expected_target(
                project,
                target_id="ws086-writer",
                mode="fixed_workstream",
                title="WS086 Writer",
                automation_ref="automation:ws086-writer",
                workstream_id="WS086",
                continuation_task_id="WS086-hourly-continuation",
                route_ref="docs/ai/reference/ws086/PLAN.md",
            )
            register_target(
                project,
                target_id="ws086-writer",
                mode="fixed_workstream",
                title="WS086 Writer",
                automation_ref="automation:ws086-writer",
                workstream_id="WS086",
                continuation_task_id="WS086",
                route_ref="docs/ai/reference/ws086/PLAN.md",
            )

            health = target_registry_health(project)
            self.assertEqual(health["status"], "conflict")
            self.assertEqual(health["reason"], "expected_target_configuration_conflict")
            self.assertEqual(health["missing_expected_target_ids"], [])
            self.assertEqual(health["conflicting_expected_target_ids"], ["ws086-writer"])
            self.assertFalse(health["recovery_available"])
            alerts = target_registry_alert_specs({"registry_health": health})
            self.assertEqual(len(alerts), 1)
            self.assertIn("冲突", alerts[0]["title"])

            registry, recovered, changed = recover_expected_targets(project)
            self.assertFalse(changed)
            self.assertEqual(recovered, [])
            self.assertEqual(registry["targets"][0]["continuation_task_id"], "WS086")
            self.assertEqual(target_registry_health(project)["status"], "conflict")

    def test_explicitly_empty_expected_contract_is_distinct_and_does_not_resurrect_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            _expected, changed = register_expected_target(
                project,
                target_id="ws012-writer",
                mode="fixed_workstream",
                title="WS012 Writer",
                automation_ref="automation:ws012-writer",
                workstream_id="WS012",
                continuation_task_id="WS012",
                route_ref="route:ws012",
            )
            self.assertTrue(changed)
            emptied, changed = remove_expected_target(project, "ws012-writer")
            self.assertTrue(changed)
            self.assertGreater(emptied["revision"], 0)
            self.assertEqual(emptied["targets"], [])
            self.assertEqual(emptied["withdrawn_target_ids"], ["ws012-writer"])

            health = target_registry_health(project, expected_registry=emptied)
            self.assertEqual(health["status"], "configured_empty")
            self.assertEqual(health["reason"], "expected_target_contract_intentionally_empty")
            self.assertEqual(target_registry_alert_specs({"registry_health": health}), [])

            registry, recovered, changed = recover_expected_targets(project)
            self.assertFalse(changed)
            self.assertEqual(recovered, [])
            self.assertEqual(registry["targets"], [])

    def test_withdrawn_expected_target_is_fail_visible_until_live_registration_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            target_kwargs = {
                "target_id": "ws012-writer",
                "mode": "fixed_workstream",
                "title": "WS012 Writer",
                "automation_ref": "automation:ws012-writer",
                "workstream_id": "WS012",
                "continuation_task_id": "WS012",
            }
            register_expected_target(project, **target_kwargs)
            register_target(project, **target_kwargs)

            withdrawn, changed = remove_expected_target(project, "ws012-writer")
            self.assertTrue(changed)
            self.assertEqual(withdrawn["targets"], [])
            self.assertEqual(withdrawn["withdrawn_target_ids"], ["ws012-writer"])

            health = target_registry_health(project)
            self.assertEqual(health["status"], "conflict")
            self.assertEqual(health["withdrawn_registered_target_ids"], ["ws012-writer"])
            self.assertEqual(health["conflicting_expected_target_ids"], ["ws012-writer"])
            alert = target_registry_alert_specs({"registry_health": health})[0]
            self.assertIn("已明确撤销但仍注册", alert["explanation"])

            registry, recovered, changed = recover_expected_targets(project)
            self.assertFalse(changed)
            self.assertEqual(recovered, [])
            self.assertEqual([row["target_id"] for row in registry["targets"]], ["ws012-writer"])

            _registry, removed = remove_target(project, "ws012-writer")
            self.assertTrue(removed)
            health = target_registry_health(project)
            self.assertEqual(health["status"], "configured_empty")
            registry, recovered, changed = recover_expected_targets(project)
            self.assertFalse(changed)
            self.assertEqual(recovered, [])
            self.assertEqual(registry["targets"], [])

            expected, changed = register_expected_target(project, **target_kwargs)
            self.assertTrue(changed)
            self.assertEqual(expected["withdrawn_target_ids"], [])
            self.assertEqual(target_registry_health(project)["status"], "incomplete")

    def test_register_fixed_workstream_is_idempotent_and_remove_is_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            registry, changed = register_target(
                project,
                target_id="ws012-writer",
                mode="fixed_workstream",
                title="WS012 Writer",
                automation_ref="automation:ws012-writer",
                workstream_id="WS012",
                continuation_task_id="WS012",
            )
            self.assertTrue(changed)
            self.assertEqual(registry["revision"], 1)
            self.assertEqual(registry["targets"][0]["workstream_id"], "WS012")
            registry2, changed2 = register_target(
                project,
                target_id="ws012-writer",
                mode="fixed_workstream",
                title="WS012 Writer",
                automation_ref="automation:ws012-writer",
                workstream_id="WS012",
                continuation_task_id="WS012",
            )
            self.assertFalse(changed2)
            self.assertEqual(registry2["revision"], 1)
            registry3, removed = remove_target(project, "ws012-writer")
            self.assertTrue(removed)
            self.assertEqual(registry3["targets"], [])
            self.assertEqual(registry3["revision"], 2)

    def test_dynamic_project_target_requires_continuation_task_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            with self.assertRaises(ObserverTargetRegistryError):
                register_target(
                    project,
                    target_id="project-writer",
                    mode="project_dynamic",
                    title="Project Writer",
                    automation_ref="automation:project-writer",
                )

    def test_overview_enable_or_disable_requires_evidence_and_authority_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            with self.assertRaises(ObserverTargetRegistryError):
                set_project_overview_decision(project, decision="disabled", reason="heterogeneous")
            registry, changed = set_project_overview_decision(
                project,
                decision="disabled",
                reason="Current authority has no explainable unified route.",
                evidence_refs=["docs/ai/active/Task_Plan.md"],
                authority_fingerprint="sha256:abc123",
            )
            self.assertTrue(changed)
            self.assertEqual(registry["project_overview"]["decision"], "disabled")

    def test_target_runtime_state_refuses_credential_like_metadata_before_persisting(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            with self.assertRaises(SemanticSensitiveValueError):
                register_target(
                    project,
                    target_id="secret-target",
                    mode="fixed_workstream",
                    title="password=do-not-store",
                    automation_ref="automation:secret-target",
                    workstream_id="WS012",
                )
            self.assertFalse(project.observer_dir.exists())

            register_target(
                project,
                target_id="safe-target",
                mode="fixed_workstream",
                title="Safe target",
                automation_ref="automation:safe-target",
                workstream_id="WS012",
            )
            with self.assertRaises(SemanticSensitiveValueError):
                record_target_run_start(
                    project,
                    target_id="safe-target",
                    run_id="activation-secret",
                    evidence_refs=["token=do-not-store"],
                )
            self.assertFalse((project.observer_dir / "targets" / "safe-target" / "run_events.jsonl").exists())

    def test_fixed_target_projects_only_matching_workstream_and_rounds_without_fake_end_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self.make_project(root)
            register_target(
                project,
                target_id="ws012-writer",
                mode="fixed_workstream",
                title="WS012 Writer",
                automation_ref="automation:ws012-writer",
                workstream_id="WS012",
                continuation_task_id="WS012",
                route_ref="route:ws012",
            )
            task_dir = root / "continuation" / "WS012"
            task_dir.mkdir(parents=True)
            (task_dir / "rounds.json").write_text(
                json.dumps(
                    {
                        "rounds": [
                            {
                                "generation": 7,
                                "runner_id": "runner-7",
                                "phase": "executing",
                                "milestone": "working",
                                "started_at": "2026-08-31T00:00:00Z",
                                "updated_at": "2026-08-31T00:10:00Z",
                                "ended_at": None,
                                "evidence_refs": ["git:abc"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            current = {
                "workstreams": [
                    {"id": "WS012", "title": "wanted"},
                    {"id": "WS999", "title": "must stay out"},
                ],
                "continuations": [
                    {
                        "task_id": "WS012",
                        "workstream_id": "WS012",
                        "source_dir": str(task_dir),
                    },
                    {
                        "task_id": "WS999",
                        "workstream_id": "WS999",
                        "source_dir": str(root / "continuation" / "WS999"),
                    },
                ],
            }
            views = build_target_views(project, current)
            self.assertEqual(views["target_count"], 1)
            view = views["targets"][0]
            self.assertEqual([row["id"] for row in view["workstreams"]], ["WS012"])
            run = view["latest_run"]
            self.assertEqual(run["status"], "incomplete")
            self.assertIsNone(run["finished_at"])
            self.assertIsNone(run["duration_seconds"])
            self.assertEqual(run["lower_bound_duration_seconds"], 600.0)
            self.assertEqual(run["route_ref"], "route:ws012")

    def test_project_dynamic_target_follows_same_task_across_workstreams(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self.make_project(root)
            register_target(
                project,
                target_id="project-writer",
                mode="project_dynamic",
                title="Project Writer",
                automation_ref="automation:project-writer",
                continuation_task_id="project-continuation",
            )
            current = {
                "workstreams": [{"id": "WS001"}, {"id": "WS002"}, {"id": "WS999"}],
                "continuations": [
                    {"task_id": "project-continuation", "workstream_id": "WS001"},
                    {"task_id": "project-continuation", "workstream_id": "WS002"},
                    {"task_id": "other", "workstream_id": "WS999"},
                ],
            }
            view = build_target_views(project, current)["targets"][0]
            self.assertEqual({row["id"] for row in view["workstreams"]}, {"WS001", "WS002"})
            self.assertEqual(len(view["continuations"]), 2)

    def test_user_level_run_markers_preserve_incomplete_runs_without_fake_end_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self.make_project(root)
            register_target(
                project,
                target_id="marker-target",
                mode="fixed_workstream",
                title="Marker target",
                automation_ref="automation:marker",
                workstream_id="WS012",
                route_ref="route:marker-target",
            )
            start, changed = record_target_run_start(
                project,
                target_id="marker-target",
                run_id="activation-001",
                evidence_refs=["scheduler:activation-001"],
            )
            self.assertTrue(changed)
            self.assertEqual(start["event_kind"], "start")
            _same, changed = record_target_run_start(
                project,
                target_id="marker-target",
                run_id="activation-001",
                evidence_refs=["scheduler:activation-001"],
            )
            self.assertFalse(changed)
            view = build_target_views(
                project,
                {
                    "workstreams": [{"id": "WS012"}],
                    "continuations": [],
                },
            )["targets"][0]
            incomplete = view["latest_run"]
            self.assertEqual(incomplete["source"], "observer_marker")
            self.assertEqual(incomplete["status"], "incomplete")
            self.assertIsNone(incomplete["finished_at"])
            self.assertIsNone(incomplete["duration_seconds"])
            self.assertEqual(incomplete["lower_bound_duration_seconds"], 0.0)
            self.assertEqual(incomplete["route_ref"], "route:marker-target")

            finish, changed = record_target_run_finish(
                project,
                target_id="marker-target",
                run_id="activation-001",
                result="success",
                major_outcome="P1 marker path validated",
                evidence_refs=["test:marker"],
            )
            self.assertTrue(changed)
            self.assertEqual(finish["event_kind"], "finish")
            completed = build_target_views(
                project,
                {"workstreams": [{"id": "WS012"}], "continuations": []},
            )["targets"][0]["latest_run"]
            self.assertEqual(completed["status"], "completed")
            self.assertEqual(completed["result"], "success")
            self.assertIsNotNone(completed["finished_at"])
            self.assertGreaterEqual(completed["duration_seconds"], 0.0)

    def test_run_finish_without_start_marker_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            register_target(
                project,
                target_id="marker-target",
                mode="fixed_workstream",
                title="Marker target",
                automation_ref="automation:marker",
                workstream_id="WS012",
            )
            with self.assertRaises(ObserverTargetRegistryError):
                record_target_run_finish(
                    project,
                    target_id="marker-target",
                    run_id="activation-404",
                    result="failed",
                )

    def test_run_event_stream_identity_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            register_target(
                project,
                target_id="marker-target",
                mode="fixed_workstream",
                title="Marker target",
                automation_ref="automation:marker",
                workstream_id="WS012",
            )
            record_target_run_start(
                project,
                target_id="marker-target",
                run_id="activation-001",
            )
            event_path = project.observer_dir / "targets" / "marker-target" / "run_events.jsonl"
            event = json.loads(event_path.read_text(encoding="utf-8").strip())
            event["project_id"] = "other-project"
            event_path.write_text(json.dumps(event) + "\n", encoding="utf-8")
            with self.assertRaises(ObserverTargetRegistryError):
                build_target_views(
                    project,
                    {"workstreams": [{"id": "WS012"}], "continuations": []},
                )

    def test_dashboard_visible_scope_contains_only_explicit_registered_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self.make_project(root)
            wanted = {
                "id": "WS012",
                "title": "Registered workstream",
                "status": "Active",
                "machine_state": {"execution": "running", "progress": "unknown", "health": "healthy"},
            }
            hidden = {
                "id": "WS999",
                "title": "UNREGISTERED-SHOULD-NOT-BE-VISIBLE",
                "status": "Active",
                "machine_state": {"execution": "blocked", "progress": "unknown", "health": "critical"},
            }
            current = {
                "observed_at": "2026-08-31T01:00:00Z",
                "workstreams": [wanted, hidden],
                "continuations": [],
                "alerts": [
                    {
                        "alert_key": "hidden-critical",
                        "severity": "critical",
                        "title": "UNREGISTERED-CRITICAL-ALERT",
                        "canonical_identity": {"type": "workstream", "id": "WS999"},
                    }
                ],
                "semantic": {"status": "current"},
                "targets": {
                    "project_overview": {"decision": "undecided"},
                    "targets": [
                        {
                            "target": {
                                "target_id": "ws012-writer",
                                "mode": "fixed_workstream",
                                "title": "WS012 scheduled writer",
                                "automation_ref": "automation:ws012",
                                "workstream_id": "WS012",
                            },
                            "workstreams": [wanted],
                            "continuations": [],
                            "runs": [
                                {
                                    "status": "incomplete",
                                    "run_id": "activation-7",
                                    "started_at": "2026-08-31T01:00:00Z",
                                    "finished_at": None,
                                    "last_activity_at": "2026-08-31T01:10:00Z",
                                    "duration_seconds": None,
                                    "lower_bound_duration_seconds": 600.0,
                                    "phase": "executing",
                                    "major_outcome": None,
                                }
                            ],
                            "latest_run": None,
                        }
                    ],
                },
            }
            html = render_dashboard_html(
                project,
                current=current,
                status={"data_age": {"state": "fresh"}},
                machine_events=[],
                interpretations=[],
                glossary={"terms": {}},
            )
            visible = html.split('<script id="observer-data"', 1)[0]
            self.assertIn("WS012 scheduled writer", visible)
            self.assertIn("Registered workstream", visible)
            self.assertNotIn("UNREGISTERED-SHOULD-NOT-BE-VISIBLE", visible)
            self.assertNotIn("UNREGISTERED-CRITICAL-ALERT", visible)
            self.assertIn("整体健康：健康", visible)
            self.assertIn("最后活动：", visible)
            self.assertIn("≥ 600.0s（下界）", visible)
            self.assertIn('data-target-tab="ws012-writer"', visible)

    def test_dashboard_project_overview_is_conditional_on_evidence_backed_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            current = {
                "observed_at": "2026-08-31T01:00:00Z",
                "workstreams": [],
                "continuations": [],
                "alerts": [],
                "semantic": {"status": "current"},
                "project_narrative": {
                    "status": "current",
                    "narrative": {"narrative_version": 99, "overall_goal": {"summary": "SHOULD-NOT-RENDER"}},
                },
                "targets": {
                    "project_overview": {
                        "decision": "disabled",
                        "reason": "Targets are intentionally heterogeneous.",
                        "evidence_refs": ["docs/ai/active/Task_Plan.md"],
                        "authority_fingerprint": "sha256:authority",
                    },
                    "targets": [],
                },
            }
            html = render_dashboard_html(
                project,
                current=current,
                status={"data_age": {"state": "fresh"}},
                machine_events=[],
                interpretations=[],
                glossary={"terms": {}},
            )
            visible = html.split('<script id="observer-data"', 1)[0]
            self.assertIn("项目总览已由 authority 明确停用", visible)
            self.assertIn("Targets are intentionally heterogeneous.", visible)
            self.assertNotIn("SHOULD-NOT-RENDER", visible)


class ObserverTargetCliTests(unittest.TestCase):
    def setUp(self):
        self._previous_acf_home = os.environ.get("ACF_HOME")
        self._acf_home = tempfile.TemporaryDirectory()
        os.environ["ACF_HOME"] = self._acf_home.name

    def tearDown(self):
        if self._previous_acf_home is None:
            os.environ.pop("ACF_HOME", None)
        else:
            os.environ["ACF_HOME"] = self._previous_acf_home
        self._acf_home.cleanup()

    def run_cli(self, args):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            exit_code = acf.main(args)
        return exit_code, stdout.getvalue(), stderr.getvalue()

    def make_project(self, root: Path) -> Path:
        project = root / "project"
        context = project / "docs" / "ai"
        exit_code, _stdout, stderr = self.run_cli(["init", str(context), "--profile", "minimal", "--json"])
        self.assertEqual(exit_code, 0, stderr)
        return project

    def test_cli_register_list_and_remove_target_without_project_git_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            before = {
                path.relative_to(project).as_posix(): path.read_bytes()
                for path in project.rglob("*")
                if path.is_file()
            }
            exit_code, stdout, stderr = self.run_cli(
                [
                    "observer",
                    "target-set",
                    str(project),
                    "--target-id",
                    "ws012-writer",
                    "--mode",
                    "fixed_workstream",
                    "--title",
                    "WS012 Writer",
                    "--automation-ref",
                    "automation:ws012-writer",
                    "--workstream",
                    "WS012",
                    "--continuation-task-id",
                    "WS012",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["changed"])
            self.assertEqual(payload["registry"]["targets"][0]["target_id"], "ws012-writer")

            exit_code, stdout, stderr = self.run_cli(
                [
                    "observer",
                    "target-run-start",
                    str(project),
                    "--target-id",
                    "ws012-writer",
                    "--run-id",
                    "activation-001",
                    "--route-ref",
                    "route:p1",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(json.loads(stdout)["event"]["event_kind"], "start")

            exit_code, stdout, stderr = self.run_cli(["observer", "targets", str(project), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["target_views"]["target_count"], 1)
            self.assertEqual(payload["registry"]["targets"][0]["automation_ref"], "automation:ws012-writer")
            self.assertEqual(payload["target_views"]["targets"][0]["latest_run"]["status"], "incomplete")

            exit_code, stdout, stderr = self.run_cli(
                [
                    "observer",
                    "target-run-finish",
                    str(project),
                    "--target-id",
                    "ws012-writer",
                    "--run-id",
                    "activation-001",
                    "--result",
                    "success",
                    "--major-outcome",
                    "Target registry smoke complete",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(json.loads(stdout)["event"]["result"], "success")

            exit_code, stdout, stderr = self.run_cli(
                ["observer", "target-remove", str(project), "--target-id", "ws012-writer", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertTrue(json.loads(stdout)["changed"])
            after = {
                path.relative_to(project).as_posix(): path.read_bytes()
                for path in project.rglob("*")
                if path.is_file()
            }
            self.assertEqual(after, before)

    def test_cli_expected_target_recovery_restores_lost_runtime_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            set_args = [
                "observer",
                "expected-target-set",
                str(project),
                "--target-id",
                "ws012-writer",
                "--mode",
                "fixed_workstream",
                "--title",
                "WS012 Writer",
                "--automation-ref",
                "automation:ws012-writer",
                "--workstream",
                "WS012",
                "--continuation-task-id",
                "WS012",
                "--json",
            ]
            exit_code, stdout, stderr = self.run_cli(set_args)
            self.assertEqual(exit_code, 0, stderr)
            self.assertTrue(json.loads(stdout)["changed"])

            exit_code, stdout, stderr = self.run_cli(["observer", "targets", str(project), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(json.loads(stdout)["registry_health"]["status"], "incomplete")

            exit_code, stdout, stderr = self.run_cli(["observer", "target-recover", str(project), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            recovered = json.loads(stdout)
            self.assertEqual(recovered["recovered_target_ids"], ["ws012-writer"])
            self.assertEqual(recovered["registry_health"]["status"], "healthy")

            exit_code, stdout, stderr = self.run_cli(["observer", "target-recover", str(project), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            self.assertFalse(json.loads(stdout)["changed"])

    def test_cli_target_recover_reports_conflict_without_overwriting_registered_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            expected_args = [
                "observer",
                "expected-target-set",
                str(project),
                "--target-id",
                "ws086-writer",
                "--mode",
                "fixed_workstream",
                "--title",
                "WS086 Writer",
                "--automation-ref",
                "automation:ws086-writer",
                "--workstream",
                "WS086",
                "--continuation-task-id",
                "WS086-hourly-continuation",
                "--json",
            ]
            exit_code, stdout, stderr = self.run_cli(expected_args)
            self.assertEqual(exit_code, 0, stderr)
            self.assertTrue(json.loads(stdout)["changed"])

            target_args = [
                "observer",
                "target-set",
                str(project),
                "--target-id",
                "ws086-writer",
                "--mode",
                "fixed_workstream",
                "--title",
                "WS086 Writer",
                "--automation-ref",
                "automation:ws086-writer",
                "--workstream",
                "WS086",
                "--continuation-task-id",
                "WS086",
                "--json",
            ]
            exit_code, stdout, stderr = self.run_cli(target_args)
            self.assertEqual(exit_code, 0, stderr)

            exit_code, stdout, stderr = self.run_cli(["observer", "target-recover", str(project), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertFalse(payload["changed"])
            self.assertEqual(payload["registry_health"]["status"], "conflict")
            self.assertIn("conflicts", payload["message"])
            self.assertEqual(payload["registry"]["targets"][0]["continuation_task_id"], "WS086")

    def test_cli_expected_target_remove_reports_live_registration_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            common = [
                str(project),
                "--target-id",
                "ws012-writer",
                "--mode",
                "fixed_workstream",
                "--title",
                "WS012 Writer",
                "--automation-ref",
                "automation:ws012-writer",
                "--workstream",
                "WS012",
                "--continuation-task-id",
                "WS012",
                "--json",
            ]
            exit_code, _stdout, stderr = self.run_cli(["observer", "expected-target-set", *common])
            self.assertEqual(exit_code, 0, stderr)
            exit_code, _stdout, stderr = self.run_cli(["observer", "target-set", *common])
            self.assertEqual(exit_code, 0, stderr)

            exit_code, stdout, stderr = self.run_cli(
                ["observer", "expected-target-remove", str(project), "--target-id", "ws012-writer", "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["changed"])
            self.assertEqual(payload["registry_health"]["status"], "conflict")
            self.assertEqual(payload["registry_health"]["withdrawn_registered_target_ids"], ["ws012-writer"])
            self.assertIn("remains registered", payload["message"])

    def test_cli_project_overview_decision_is_evidence_backed_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            exit_code, stdout, _stderr = self.run_cli(
                [
                    "observer",
                    "project-overview-set",
                    str(project),
                    "--decision",
                    "enabled",
                    "--reason",
                    "Authority is unified.",
                    "--json",
                ]
            )
            self.assertNotEqual(exit_code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["error_code"], "observer_target_registry_invalid")

    def test_cli_target_mutations_refuse_credential_like_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            exit_code, stdout, _stderr = self.run_cli(
                [
                    "observer",
                    "target-set",
                    str(project),
                    "--target-id",
                    "secret-target",
                    "--mode",
                    "fixed_workstream",
                    "--title",
                    "password=do-not-store",
                    "--automation-ref",
                    "automation:secret-target",
                    "--workstream",
                    "WS012",
                    "--json",
                ]
            )
            self.assertNotEqual(exit_code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["error_code"], "observer_sensitive_value_refused")

            exit_code, stdout, stderr = self.run_cli(
                [
                    "observer",
                    "project-overview-set",
                    str(project),
                    "--decision",
                    "enabled",
                    "--reason",
                    "Authority is unified.",
                    "--evidence-ref",
                    "docs/ai/active/Task_Plan.md",
                    "--authority-fingerprint",
                    "sha256:authority",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["project_overview"]["decision"], "enabled")
            self.assertEqual(payload["project_overview"]["authority_fingerprint"], "sha256:authority")


if __name__ == "__main__":
    unittest.main()
