from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

import acf

from ai_context_framework.observer import derive_snapshot_alerts
from ai_context_framework.observer_presentation import (
    ObserverPresentationConcurrencyError,
    ObserverPresentationError,
    ObserverPresentationSourceMismatch,
    add_durable_rule,
    add_one_shot_review_request,
    apply_semantic_review,
    presentation_status,
    read_presentation_state,
    target_semantic_source_fingerprint,
    withdraw_durable_rule,
)
from ai_context_framework.observer_storage import SemanticSensitiveValueError


class ObserverPresentationStateTests(unittest.TestCase):
    def make_project(self, root: Path):
        return SimpleNamespace(
            project_id="project-test",
            observer_dir=root / "observer",
            canonical_root=root / "project",
        )

    def make_view(
        self,
        target_id: str,
        workstream_id: str,
        *,
        stage: str = "P2",
        next_action: str = "Implement semantic lifecycle",
        health: str = "healthy",
    ) -> dict[str, object]:
        return {
            "target": {
                "target_id": target_id,
                "mode": "fixed_workstream",
                "title": f"{workstream_id} Writer",
                "automation_ref": f"automation:{target_id}",
                "workstream_id": workstream_id,
                "continuation_task_id": workstream_id,
                "route_ref": "route:observer-v2",
            },
            "workstreams": [
                {
                    "id": workstream_id,
                    "title": f"{workstream_id} maintenance",
                    "status": "Active",
                    "attention": "Now",
                    "goal": "Keep Observer truthful",
                    "source_consistency": "consistent",
                    "machine_state": {
                        "execution": "running",
                        "health": health,
                        "health_reasons": [],
                    },
                }
            ],
            "continuations": [
                {
                    "task_id": workstream_id,
                    "workstream_id": workstream_id,
                    "stage": stage,
                    "status": "running",
                    "objective": "Observer V2",
                    "next_action": next_action,
                    "latest_round": {
                        "generation": 81,
                        "phase": "executing",
                        "milestone": "p2",
                        "evidence_refs": ["git:abc"],
                    },
                    "effects": {"unresolved_count": 0},
                }
            ],
            "runs": [],
            "latest_run": None,
        }

    def narrative(self) -> dict[str, object]:
        return {
            "overall_goal": "让注册目标以可审计方式持续推进。",
            "route_summary": "P1 目标注册 → P2 语义生命周期 → P3 展示 → P4 dogfood。",
            "current_position": "P2 semantic lifecycle",
            "why_now": "P1.5 已冻结合同，当前需要落地 runtime 语义。",
            "recent_proof": ["P1.5 focused/full tests 已通过。"],
            "next_logic": "验证 one-shot、durable rule 与独立 stale 后再进入 P3。",
            "evidence_refs": ["docs/ai/reference/ws012_project_observer_operational_dogfood/PLAN.md"],
            "route_nodes": [
                {
                    "id": "p2",
                    "title": "P2",
                    "status": "active",
                    "summary": "semantic lifecycle",
                    "evidence_refs": ["plan:p2"],
                },
                {
                    "id": "p3",
                    "title": "P3",
                    "status": "future",
                    "summary": "dashboard v2",
                    "evidence_refs": ["plan:p3"],
                },
            ],
            "route_edges": [{"from": "p2", "to": "p3", "label": "validated semantics"}],
        }

    def apply_review(
        self,
        project,
        view,
        *,
        expected_target_revision: int,
        review_id: str = "review-001",
        decision: str = "patch",
        consume: list[str] | None = None,
        problems: list[dict[str, object]] | None = None,
        authority_reread: bool = True,
        signals: list[str] | None = None,
    ):
        return apply_semantic_review(
            project,
            target_view=view,
            expected_target_revision=expected_target_revision,
            expected_source_fingerprint=target_semantic_source_fingerprint(view),
            review_id=review_id,
            authority_fingerprint="authority:sha256:001",
            authority_reread=authority_reread,
            decision=decision,
            reason="Authority and current route were reviewed against fresh evidence.",
            evidence_refs=["plan:p2", "continuation:g81"],
            map_relevant_signals=signals or ["current stage changed to P2"],
            presentation_type="roadmap",
            narrative=self.narrative(),
            problems=problems or [],
            consume_one_shot_request_ids=consume or [],
        )

    def test_empty_state_does_not_create_observer_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            state = read_presentation_state(project)
            self.assertEqual(state["revision"], 0)
            self.assertEqual(state["targets"], {})
            self.assertFalse(project.observer_dir.exists())

    def test_target_semantic_staleness_alert_is_target_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            snapshot = {
                "observed_at": "2026-09-01T00:00:00Z",
                "snapshot_consistency": {"state": "stable"},
                "project_narrative": {"status": "current"},
                "presentation": {
                    "targets": [
                        {
                            "target_id": "ws012-writer",
                            "semantic_status": "current",
                            "source_fingerprint": "current-a",
                            "current_review": {"review_id": "review-a", "source_fingerprint": "current-a"},
                            "active_one_shot_requests": [],
                        },
                        {
                            "target_id": "ws080-writer",
                            "semantic_status": "stale",
                            "source_fingerprint": "current-b",
                            "current_review": {"review_id": "review-b", "source_fingerprint": "stored-b"},
                            "active_one_shot_requests": [],
                        },
                    ]
                },
                "workstreams": [],
                "continuations": [],
            }
            alerts = derive_snapshot_alerts(project, snapshot)
            keys = {row["alert_key"] for row in alerts}
            self.assertIn("target:ws080-writer:semantic-review-stale", keys)
            self.assertNotIn("target:ws012-writer:semantic-review-stale", keys)

    def test_active_one_shot_request_is_fail_visible_until_semantic_review_consumes_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            snapshot = {
                "observed_at": "2026-09-01T00:00:00Z",
                "snapshot_consistency": {"state": "stable"},
                "project_narrative": {"status": "current"},
                "presentation": {
                    "targets": [
                        {
                            "target_id": "ws012-writer",
                            "semantic_status": "current",
                            "source_fingerprint": "current-a",
                            "current_review": {"review_id": "review-a", "source_fingerprint": "current-a"},
                            "active_one_shot_requests": [{"request_id": "request-map"}],
                        }
                    ]
                },
                "workstreams": [],
                "continuations": [],
            }
            alerts = derive_snapshot_alerts(project, snapshot)
            self.assertIn(
                "target:ws012-writer:map-review-request-pending",
                {row["alert_key"] for row in alerts},
            )


class ObserverPresentationCliTests(ObserverPresentationStateTests):
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

    def make_cli_project(self, root: Path) -> Path:
        project = root / "project"
        context = project / "docs" / "ai"
        exit_code, _stdout, stderr = self.run_cli(["init", str(context), "--profile", "minimal", "--json"])
        self.assertEqual(exit_code, 0, stderr)
        exit_code, _stdout, stderr = self.run_cli(
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
        return project

    def test_cli_presentation_status_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_cli_project(Path(tmp))
            state_path = Path(os.environ["ACF_HOME"]) / "projects"
            before = {
                path: path.read_bytes()
                for path in state_path.rglob("*")
                if path.is_file()
            }
            exit_code, stdout, stderr = self.run_cli(
                ["observer", "presentation-status", str(project), "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertTrue(payload["ok"])
            row = payload["presentation"]["targets"][0]
            self.assertEqual(row["target_id"], "ws012-writer")
            self.assertEqual(row["semantic_status"], "not_reviewed")
            after = {
                path: path.read_bytes()
                for path in state_path.rglob("*")
                if path.is_file()
            }
            self.assertEqual(before, after)

    def test_cli_one_shot_and_semantic_review_consume_with_exact_revision_and_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_cli_project(Path(tmp))
            exit_code, stdout, stderr = self.run_cli(
                ["observer", "presentation-status", str(project), "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            status = json.loads(stdout)["presentation"]["targets"][0]
            source_fingerprint = status["source_fingerprint"]
            exit_code, stdout, stderr = self.run_cli(
                [
                    "observer",
                    "review-request-add",
                    str(project),
                    "--target-id",
                    "ws012-writer",
                    "--request-id",
                    "request-layout",
                    "--expected-target-revision",
                    "0",
                    "--reviewed-intent",
                    "下次 Map Review 重新判断路线层级。",
                    "--scope",
                    "target route presentation semantics",
                    "--rationale",
                    "当前路线尚未形成正式 target narrative。",
                    "--evidence-ref",
                    "plan:p2",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(json.loads(stdout)["target_state"]["revision"], 1)

            review_input = Path(tmp) / "review.json"
            review_input.write_text(
                json.dumps(
                    {
                        "narrative": {
                            "overall_goal": "验证目标语义生命周期。",
                            "route_summary": "P2 → P3",
                            "current_position": "P2",
                            "why_now": "P1.5 contract 已冻结。",
                            "recent_proof": ["P1.5 tests passed"],
                            "next_logic": "完成 semantic lifecycle 后进入 P3。",
                            "evidence_refs": ["plan:p2"],
                            "route_nodes": [
                                {
                                    "id": "p2",
                                    "title": "P2",
                                    "status": "active",
                                    "summary": "semantic lifecycle",
                                    "evidence_refs": ["plan:p2"],
                                }
                            ],
                            "route_edges": [],
                        },
                        "problems": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            exit_code, stdout, stderr = self.run_cli(
                [
                    "observer",
                    "semantic-review-apply",
                    str(project),
                    "--target-id",
                    "ws012-writer",
                    "--review-id",
                    "review-cli-1",
                    "--expected-target-revision",
                    "1",
                    "--source-fingerprint",
                    source_fingerprint,
                    "--authority-fingerprint",
                    "authority:p2",
                    "--authority-reread",
                    "--decision",
                    "rebuild",
                    "--reason",
                    "Authority was reviewed and the target route is now explicit.",
                    "--evidence-ref",
                    "plan:p2",
                    "--map-relevant-signal",
                    "new target narrative",
                    "--presentation-type",
                    "roadmap",
                    "--input",
                    str(review_input),
                    "--consume-one-shot",
                    "request-layout",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["target_state"]["one_shot_requests"], [])
            self.assertEqual(payload["target_state"]["current_review"]["review_id"], "review-cli-1")

            exit_code, stdout, stderr = self.run_cli(
                ["observer", "presentation-status", str(project), "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            current = json.loads(stdout)["presentation"]["targets"][0]
            self.assertEqual(current["semantic_status"], "current")
            self.assertEqual(current["active_one_shot_requests"], [])

    def test_cli_stale_target_revision_fails_closed_without_overwriting_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_cli_project(Path(tmp))
            first = [
                "observer",
                "presentation-rule-add",
                str(project),
                "--target-id",
                "ws012-writer",
                "--rule-id",
                "rule-1",
                "--expected-target-revision",
                "0",
                "--reviewed-intent",
                "Keep current position visible.",
                "--scope",
                "target route",
                "--rationale",
                "Long-term readability.",
                "--evidence-ref",
                "plan:p2",
                "--json",
            ]
            exit_code, _stdout, stderr = self.run_cli(first)
            self.assertEqual(exit_code, 0, stderr)
            exit_code, stdout, _stderr = self.run_cli(
                [
                    "observer",
                    "presentation-rule-add",
                    str(project),
                    "--target-id",
                    "ws012-writer",
                    "--rule-id",
                    "rule-stale",
                    "--expected-target-revision",
                    "0",
                    "--reviewed-intent",
                    "Stale write",
                    "--scope",
                    "target route",
                    "--rationale",
                    "Must fail closed.",
                    "--evidence-ref",
                    "test:stale",
                    "--json",
                ]
            )
            self.assertNotEqual(exit_code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["error_code"], "observer_presentation_revision_changed")
            state_files = list(Path(os.environ["ACF_HOME"]).rglob("presentation/state.json"))
            self.assertEqual(len(state_files), 1)
            state = json.loads(state_files[0].read_text(encoding="utf-8"))
            rules = state["targets"]["ws012-writer"]["durable_rules"]
            self.assertEqual([row["rule_id"] for row in rules], ["rule-1"])

    def test_target_semantic_staleness_is_independent_between_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            ws012 = self.make_view("ws012-writer", "WS012")
            ws080 = self.make_view("ws080-writer", "WS080")
            self.apply_review(project, ws012, expected_target_revision=0, review_id="review-ws012")
            self.apply_review(project, ws080, expected_target_revision=0, review_id="review-ws080")

            status = presentation_status(project, {"targets": [ws012, ws080]})
            self.assertEqual(
                {row["target_id"]: row["semantic_status"] for row in status["targets"]},
                {"ws012-writer": "current", "ws080-writer": "current"},
            )

            changed_ws080 = self.make_view(
                "ws080-writer",
                "WS080",
                stage="P2-recovery",
                next_action="Recover runtime effect",
                health="warning",
            )
            status = presentation_status(project, {"targets": [ws012, changed_ws080]})
            by_id = {row["target_id"]: row for row in status["targets"]}
            self.assertEqual(by_id["ws012-writer"]["semantic_status"], "current")
            self.assertEqual(by_id["ws080-writer"]["semantic_status"], "stale")

    def test_one_shot_request_is_consumed_once_and_removed_from_active_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            view = self.make_view("ws012-writer", "WS012")
            target_state, _event = add_one_shot_review_request(
                project,
                target_id="ws012-writer",
                request_id="request-map-layout",
                expected_target_revision=0,
                reviewed_intent="下次正式语义复核时重新判断主线与分支的视觉关系。",
                scope="target route presentation semantics",
                rationale="当前阶段由 P1.5 进入 P2，旧路线强调关系可能失真。",
                evidence_refs=["user:directive", "plan:p2"],
            )
            self.assertEqual(target_state["revision"], 1)
            self.assertEqual(len(target_state["one_shot_requests"]), 1)

            target_state, event = self.apply_review(
                project,
                view,
                expected_target_revision=1,
                review_id="review-consume",
                consume=["request-map-layout"],
            )
            self.assertEqual(target_state["one_shot_requests"], [])
            review = target_state["current_review"]
            self.assertEqual(review["consumed_one_shot_request_ids"], ["request-map-layout"])
            self.assertEqual(event["event_kind"], "semantic_review_applied")

            with self.assertRaises(ObserverPresentationError):
                self.apply_review(
                    project,
                    view,
                    expected_target_revision=2,
                    review_id="review-reconsume",
                    consume=["request-map-layout"],
                )

            event_rows = [
                json.loads(line)
                for line in (project.observer_dir / "presentation" / "events.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            review_event = next(row for row in event_rows if row["event_kind"] == "semantic_review_applied")
            consumed = review_event["review"]["consumed_one_shot_requests"]
            self.assertEqual(consumed[0]["request_id"], "request-map-layout")
            self.assertEqual(consumed[0]["status"], "consumed")

    def test_durable_rule_supports_supersede_and_withdraw_without_resurrection(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            target_state, _ = add_durable_rule(
                project,
                target_id="ws012-writer",
                rule_id="rule-1",
                expected_target_revision=0,
                reviewed_intent="主路线必须直接展示当前位置和下一步。",
                scope="target route cards",
                rationale="这是长期 human-first 信息要求。",
                evidence_refs=["plan:dashboard-v2"],
            )
            self.assertEqual(target_state["durable_rules"][0]["status"], "active")

            target_state, _ = add_durable_rule(
                project,
                target_id="ws012-writer",
                rule_id="rule-2",
                expected_target_revision=1,
                reviewed_intent="主路线必须展示当前位置、why-now 与下一步理由。",
                scope="target route cards",
                rationale="新规则完整替代旧规则。",
                evidence_refs=["plan:dashboard-v2", "user:refinement"],
                supersedes="rule-1",
            )
            by_id = {row["rule_id"]: row for row in target_state["durable_rules"]}
            self.assertEqual(by_id["rule-1"]["status"], "superseded")
            self.assertEqual(by_id["rule-1"]["superseded_by"], "rule-2")
            self.assertEqual(by_id["rule-2"]["status"], "active")

            target_state, _ = withdraw_durable_rule(
                project,
                target_id="ws012-writer",
                rule_id="rule-2",
                expected_target_revision=2,
                reason="Authority no longer requires this long-term presentation rule.",
                evidence_refs=["authority:withdrawn"],
            )
            by_id = {row["rule_id"]: row for row in target_state["durable_rules"]}
            self.assertEqual(by_id["rule-2"]["status"], "withdrawn")
            status = presentation_status(
                project,
                {"targets": [self.make_view("ws012-writer", "WS012")]},
            )["targets"][0]
            self.assertEqual(status["active_durable_rules"], [])

    def test_target_revision_optimistic_concurrency_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            add_one_shot_review_request(
                project,
                target_id="ws012-writer",
                request_id="request-1",
                expected_target_revision=0,
                reviewed_intent="Review layout",
                scope="map",
                rationale="Authority changed",
                evidence_refs=["plan:p2"],
            )
            with self.assertRaises(ObserverPresentationConcurrencyError) as raised:
                add_durable_rule(
                    project,
                    target_id="ws012-writer",
                    rule_id="rule-stale",
                    expected_target_revision=0,
                    reviewed_intent="Keep route visible",
                    scope="map",
                    rationale="Long-term readability",
                    evidence_refs=["plan:p2"],
                )
            self.assertEqual(raised.exception.current, 1)

    def test_semantic_review_rejects_source_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            original = self.make_view("ws012-writer", "WS012")
            changed = self.make_view("ws012-writer", "WS012", next_action="Different plan")
            with self.assertRaises(ObserverPresentationSourceMismatch):
                apply_semantic_review(
                    project,
                    target_view=changed,
                    expected_target_revision=0,
                    expected_source_fingerprint=target_semantic_source_fingerprint(original),
                    review_id="review-drift",
                    authority_fingerprint="authority:1",
                    authority_reread=True,
                    decision="patch",
                    reason="Fresh review",
                    evidence_refs=["plan:p2"],
                    map_relevant_signals=["next action changed"],
                    presentation_type="roadmap",
                    narrative=self.narrative(),
                )

    def test_map_relevant_signal_requires_authority_reread(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            view = self.make_view("ws012-writer", "WS012")
            with self.assertRaisesRegex(ObserverPresentationError, "authority reread"):
                self.apply_review(
                    project,
                    view,
                    expected_target_revision=0,
                    authority_reread=False,
                    signals=["architecture changed"],
                )

    def test_route_impacting_problem_cannot_be_hidden_behind_unchanged_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            view = self.make_view("ws012-writer", "WS012")
            problem = {
                "problem_id": "problem-route",
                "title": "主路线失效",
                "summary": "当前依赖变化使旧路线顺序不再成立。",
                "expectedness": "unexpected",
                "handler": "agent_self",
                "scope_relation": "in_scope",
                "blocking_impact": "blocks_current_step",
                "plan_impact": "route_change",
                "status": "working",
                "route_ref": "route:observer-v2",
                "node_ref": "p2",
                "evidence_refs": ["runtime:problem"],
            }
            with self.assertRaisesRegex(ObserverPresentationError, "map-changing"):
                self.apply_review(
                    project,
                    view,
                    expected_target_revision=0,
                    decision="unchanged",
                    problems=[problem],
                )

            target_state, _ = self.apply_review(
                project,
                view,
                expected_target_revision=0,
                decision="rebuild",
                problems=[problem],
            )
            self.assertEqual(target_state["current_review"]["problems"][0]["plan_impact"], "route_change")

    def test_other_project_problem_requires_transfer_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            view = self.make_view("ws012-writer", "WS012")
            problem = {
                "problem_id": "problem-foreign",
                "title": "Foreign dependency",
                "summary": "Another project must provide the fix.",
                "expectedness": "unexpected",
                "handler": "other_project",
                "scope_relation": "external_dependency",
                "blocking_impact": "degrading",
                "plan_impact": "local_adjustment",
                "status": "transferred",
                "evidence_refs": ["issue:foreign"],
            }
            with self.assertRaisesRegex(ObserverPresentationError, "transfer_ref"):
                self.apply_review(
                    project,
                    view,
                    expected_target_revision=0,
                    decision="patch",
                    problems=[problem],
                )

    def test_sensitive_value_is_refused_before_persisting(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            with self.assertRaises(SemanticSensitiveValueError):
                add_one_shot_review_request(
                    project,
                    target_id="ws012-writer",
                    request_id="request-secret",
                    expected_target_revision=0,
                    reviewed_intent="password=do-not-store",
                    scope="map",
                    rationale="unsafe",
                    evidence_refs=["user:request"],
                )
            self.assertFalse(project.observer_dir.exists())


if __name__ == "__main__":
    unittest.main()
