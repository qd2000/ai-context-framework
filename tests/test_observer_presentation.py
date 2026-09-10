from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import acf

from ai_context_framework.observer import derive_snapshot_alerts, resolve_observer_project
from ai_context_framework.observer_dashboard import render_primary_visualization, render_relation_diagram
from ai_context_framework.observer_presentation import (
    OBSERVER_PRIMARY_VISUALIZATION_SCHEMA,
    ObserverPresentationConcurrencyError,
    ObserverPresentationError,
    ObserverPresentationSemanticEscalationRequired,
    ObserverPresentationSourceMismatch,
    ObserverPresentationViewChanged,
    add_durable_rule,
    add_one_shot_review_request,
    apply_transient_patch,
    apply_semantic_review,
    clear_transient_patch,
    presentation_status,
    read_presentation_state,
    target_presentation_fingerprint,
    target_semantic_source_fingerprint,
    withdraw_durable_rule,
)
from ai_context_framework.observer_storage import SemanticSensitiveValueError, render_dashboard_html


class ObserverPresentationStateTests(unittest.TestCase):
    def make_project(self, root: Path):
        return SimpleNamespace(
            project_id="project-test",
            observer_dir=root / "observer",
            canonical_root=root / "project",
        )

    def test_relation_diagram_uses_reviewed_current_status_for_legacy_narrative(self):
        nodes = [
            {"id": "h1", "title": "H1", "status": "current", "summary": "Map-first visual Gate"},
            {"id": "h2", "title": "H2", "status": "future", "summary": "Run history"},
        ]
        edges = [{"from": "h1", "to": "h2", "label": "next"}]

        legacy_html = render_relation_diagram(nodes, edges, title="Legacy reviewed route")
        self.assertIn('class="diagram-node tone-muted is-current" data-node-id="h1"', legacy_html)
        self.assertIn(">当前</text>", legacy_html)
        self.assertIn(">后续阶段</text>", legacy_html)
        self.assertNotIn(">future</text>", legacy_html)
        self.assertIn(">下一步</text>", legacy_html)
        self.assertNotIn(">next</text>", legacy_html)
        self.assertIn("<title>h2: H2 · 后续阶段 · Run history</title>", legacy_html)
        self.assertNotIn("· future ·", legacy_html)

        architecture_html = render_relation_diagram(
            nodes,
            [{"from": "h1", "to": "h2", "label": "observed_by"}],
            title="Architecture relation",
        )
        self.assertIn(">由其观察</text>", architecture_html)
        self.assertNotIn(">observed_by</text>", architecture_html)

        explicit_empty_html = render_relation_diagram(
            nodes,
            edges,
            title="Explicit current-node override",
            current_node_ids=set(),
        )
        self.assertNotIn('is-current" data-node-id="h1"', explicit_empty_html)
        self.assertNotIn('class="diagram-current"', explicit_empty_html)

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
            "current_node_refs": ["p2"],
            "why_now": "P1.5 已冻结合同，当前需要落地 runtime 语义。",
            "recent_proof": ["P1.5 focused/full tests 已通过。"],
            "next_logic": "验证 one-shot、durable rule 与独立 stale 后再进入 P3。",
            "next_node_refs": ["p3"],
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
        narrative: dict[str, object] | None = None,
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
            narrative=narrative or self.narrative(),
            problems=problems or [],
            consume_one_shot_request_ids=consume or [],
        )

    def primary_visualization(self, kind: str) -> dict[str, object]:
        common = {
            "schema_version": OBSERVER_PRIMARY_VISUALIZATION_SCHEMA,
            "kind": kind,
            "title": "当前任务主可视化",
            "primary_progress_question": "当前真正推进到了哪里？",
            "reason": "Fresh authority 表明该视图最直接回答当前进展问题。",
            "evidence_refs": ["plan:h1-v1.2"],
            "confidence": "high",
        }
        if kind == "metric_trend":
            common["spec"] = {
                "x_label": "迭代",
                "y_label": "目标函数",
                "direction": "minimize",
                "series": [
                    {
                        "id": "objective",
                        "title": "当前目标函数",
                        "unit": "",
                        "points": [
                            {"x": 1, "y": 10.0, "label": "起点", "evidence_refs": ["run:g1"]},
                            {"x": 2, "y": 8.5, "label": "当前", "evidence_refs": ["run:g2"]},
                        ],
                    }
                ],
            }
        elif kind == "status_matrix":
            common["spec"] = {
                "items": [
                    {
                        "id": "tee",
                        "title": "Tee",
                        "status": "completed",
                        "summary": "已验证",
                        "evidence_refs": ["test:tee"],
                    },
                    {
                        "id": "column",
                        "title": "Column",
                        "status": "active",
                        "summary": "当前收敛处理中",
                        "evidence_refs": ["run:column"],
                    },
                ],
                "current_item_refs": ["column"],
            }
        else:
            common["spec"] = {
                "nodes": [
                    {
                        "id": "current",
                        "title": "当前步骤",
                        "status": "active",
                        "summary": "正在推进",
                        "evidence_refs": ["run:current"],
                    },
                    {
                        "id": "next",
                        "title": "下一步骤",
                        "status": "future",
                        "summary": "等待当前步骤完成",
                        "evidence_refs": ["plan:next"],
                    },
                ],
                "edges": [
                    {
                        "from": "current",
                        "to": "next",
                        "label": "next",
                        "evidence_refs": ["plan:edge"],
                    }
                ],
                "current_node_refs": ["current"],
                "next_node_refs": ["next"],
            }
        return common

    def test_primary_visualization_contract_validates_and_renders_all_v12_archetypes(self):
        expected_fragments = {
            "metric_trend": 'class="metric-trend-svg"',
            "status_matrix": 'class="status-matrix"',
            "process_flow": 'class="relation-diagram"',
            "roadmap": 'class="relation-diagram"',
        }
        for kind, fragment in expected_fragments.items():
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                project = self.make_project(Path(tmp))
                view = self.make_view("ws012-writer", "WS012")
                narrative = self.narrative()
                narrative["primary_visualization"] = self.primary_visualization(kind)
                target_state, _ = self.apply_review(
                    project,
                    view,
                    expected_target_revision=0,
                    narrative=narrative,
                )
                primary = target_state["current_review"]["narrative"]["primary_visualization"]
                self.assertEqual(primary["kind"], kind)
                self.assertEqual(primary["primary_progress_question"], "当前真正推进到了哪里？")
                html = render_primary_visualization(primary)
                self.assertIn(f'data-primary-visualization-kind="{kind}"', html)
                self.assertIn(fragment, html)

    def test_metric_trend_rejects_nonfinite_or_unbound_points(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            view = self.make_view("ws012-writer", "WS012")
            narrative = self.narrative()
            primary = self.primary_visualization("metric_trend")
            primary["spec"]["series"][0]["points"][0]["y"] = float("nan")
            narrative["primary_visualization"] = primary
            with self.assertRaises(ObserverPresentationError):
                self.apply_review(project, view, expected_target_revision=0, narrative=narrative)

            primary = self.primary_visualization("metric_trend")
            primary["spec"]["series"][0]["points"][0]["evidence_refs"] = []
            narrative["primary_visualization"] = primary
            with self.assertRaises(ObserverPresentationError):
                self.apply_review(project, view, expected_target_revision=0, narrative=narrative)

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

    def test_target_source_fingerprint_keeps_source_divergence_fail_visible(self):
        view = self.make_view("ws012-writer", "WS012")
        consistent = target_semantic_source_fingerprint(view)
        view["workstreams"][0]["source_consistency"] = "divergent"
        divergent = target_semantic_source_fingerprint(view)
        self.assertNotEqual(consistent, divergent)


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

    def test_cli_target_status_and_semantic_review_do_not_build_full_project_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_cli_project(Path(tmp))
            review_input = Path(tmp) / "review-target-scoped.json"
            review_input.write_text(
                json.dumps({"narrative": self.narrative(), "problems": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            with mock.patch(
                "ai_context_framework.observer.capture_project_worktrees",
                side_effect=AssertionError("target-local presentation path must not build a full project snapshot"),
            ):
                exit_code, stdout, stderr = self.run_cli(
                    ["observer", "presentation-status", str(project), "--json"]
                )
                self.assertEqual(exit_code, 0, stderr)
                status = json.loads(stdout)["presentation"]["targets"][0]
                exit_code, _stdout, stderr = self.run_cli(
                    [
                        "observer",
                        "semantic-review-apply",
                        str(project),
                        "--target-id",
                        "ws012-writer",
                        "--review-id",
                        "review-target-scoped",
                        "--expected-target-revision",
                        "0",
                        "--source-fingerprint",
                        status["source_fingerprint"],
                        "--authority-fingerprint",
                        "authority:target-scoped",
                        "--authority-reread",
                        "--decision",
                        "rebuild",
                        "--reason",
                        "Target-local authority was reread against fresh scoped facts.",
                        "--evidence-ref",
                        "test:target-scoped",
                        "--presentation-type",
                        "roadmap",
                        "--input",
                        str(review_input),
                        "--json",
                    ]
                )
                self.assertEqual(exit_code, 0, stderr)

    def test_cli_target_scoped_status_detects_source_drift_without_staling_other_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_cli_project(Path(tmp))
            exit_code, _stdout, stderr = self.run_cli(
                [
                    "observer",
                    "target-set",
                    str(project),
                    "--target-id",
                    "ws013-writer",
                    "--mode",
                    "fixed_workstream",
                    "--title",
                    "WS013 Writer",
                    "--automation-ref",
                    "automation:ws013-writer",
                    "--workstream",
                    "WS013",
                    "--continuation-task-id",
                    "WS013",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            details = project / "docs" / "ai" / "active" / "workstreams"
            details.mkdir(parents=True, exist_ok=True)
            ws012 = details / "WS012.md"
            ws013 = details / "WS013.md"
            ws012.write_text(
                "---\nid: WS012\ntype: Maintenance\nstatus: Active\nattention: Now\ntitle: WS012\n---\n# WS012\n\n## 目标\n\nInitial WS012 goal.\n",
                encoding="utf-8",
            )
            ws013.write_text(
                "---\nid: WS013\ntype: Task\nstatus: Active\nattention: Now\ntitle: WS013\n---\n# WS013\n\n## 目标\n\nStable WS013 goal.\n",
                encoding="utf-8",
            )
            exit_code, stdout, stderr = self.run_cli(
                ["observer", "presentation-status", str(project), "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            before_rows = {
                row["target_id"]: row
                for row in json.loads(stdout)["presentation"]["targets"]
            }
            ws012.write_text(
                "---\nid: WS012\ntype: Maintenance\nstatus: Active\nattention: Now\ntitle: WS012\n---\n# WS012\n\n## 目标\n\nChanged WS012 goal after fresh authority evidence.\n",
                encoding="utf-8",
            )
            exit_code, stdout, stderr = self.run_cli(
                ["observer", "presentation-status", str(project), "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            after_rows = {
                row["target_id"]: row
                for row in json.loads(stdout)["presentation"]["targets"]
            }
            self.assertNotEqual(
                before_rows["ws012-writer"]["source_fingerprint"],
                after_rows["ws012-writer"]["source_fingerprint"],
            )
            self.assertEqual(
                before_rows["ws013-writer"]["source_fingerprint"],
                after_rows["ws013-writer"]["source_fingerprint"],
            )

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

    def test_cli_transient_patch_requires_canonical_current_before_mutating_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_cli_project(Path(tmp))
            exit_code, stdout, stderr = self.run_cli(
                ["observer", "presentation-status", str(project), "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            status = json.loads(stdout)["presentation"]["targets"][0]
            review_input = Path(tmp) / "review-preflight.json"
            review_input.write_text(
                json.dumps({"narrative": self.narrative(), "problems": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            exit_code, _stdout, stderr = self.run_cli(
                [
                    "observer",
                    "semantic-review-apply",
                    str(project),
                    "--target-id",
                    "ws012-writer",
                    "--review-id",
                    "review-preflight",
                    "--expected-target-revision",
                    "0",
                    "--source-fingerprint",
                    status["source_fingerprint"],
                    "--authority-fingerprint",
                    "authority:p3",
                    "--authority-reread",
                    "--decision",
                    "presentation_change",
                    "--reason",
                    "Authority reviewed before presentation-only maintenance.",
                    "--evidence-ref",
                    "plan:p3",
                    "--presentation-type",
                    "roadmap",
                    "--input",
                    str(review_input),
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            exit_code, stdout, stderr = self.run_cli(
                ["observer", "presentation-status", str(project), "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            current = json.loads(stdout)["presentation"]["targets"][0]

            exit_code, stdout, _stderr = self.run_cli(
                [
                    "observer",
                    "transient-patch-apply",
                    str(project),
                    "--target-id",
                    "ws012-writer",
                    "--patch-id",
                    "patch-no-current",
                    "--expected-target-revision",
                    str(current["target_revision"]),
                    "--expected-presentation-revision",
                    str(current["presentation_revision"]),
                    "--presentation-fingerprint",
                    current["presentation_fingerprint"],
                    "--reviewed-intent",
                    "Only change dashboard density.",
                    "--scope",
                    "presentation only",
                    "--rationale",
                    "A canonical current snapshot must exist before a deterministic rerender can be promised.",
                    "--evidence-ref",
                    "test:preflight",
                    "--density",
                    "detailed",
                    "--json",
                ]
            )
            self.assertNotEqual(exit_code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["error_code"], "observer_presentation_invalid")
            after = read_presentation_state(resolve_observer_project(project))["targets"]["ws012-writer"]
            self.assertEqual(after["revision"], current["target_revision"])
            self.assertIsNone(after["active_transient_patch"])

    def test_cli_transient_patch_rerenders_without_creating_new_snapshot_or_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_cli_project(Path(tmp))
            exit_code, _stdout, stderr = self.run_cli(["observer", "snapshot", str(project), "--json"])
            self.assertEqual(exit_code, 0, stderr)
            observer_project = resolve_observer_project(project)
            current_path = observer_project.observer_dir / "state" / "current.json"
            runs_path = observer_project.observer_dir / "state" / "runs.jsonl"
            current_before = current_path.read_bytes()
            runs_before = runs_path.read_bytes()

            exit_code, stdout, stderr = self.run_cli(
                ["observer", "presentation-status", str(project), "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            status = json.loads(stdout)["presentation"]["targets"][0]
            review_input = Path(tmp) / "review-rerender.json"
            review_input.write_text(
                json.dumps({"narrative": self.narrative(), "problems": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            exit_code, _stdout, stderr = self.run_cli(
                [
                    "observer",
                    "semantic-review-apply",
                    str(project),
                    "--target-id",
                    "ws012-writer",
                    "--review-id",
                    "review-rerender",
                    "--expected-target-revision",
                    "0",
                    "--source-fingerprint",
                    status["source_fingerprint"],
                    "--authority-fingerprint",
                    "authority:p3",
                    "--authority-reread",
                    "--decision",
                    "presentation_change",
                    "--reason",
                    "Authority reviewed for the current canonical target facts.",
                    "--evidence-ref",
                    "plan:p3",
                    "--presentation-type",
                    "roadmap",
                    "--input",
                    str(review_input),
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            exit_code, stdout, stderr = self.run_cli(
                ["observer", "presentation-status", str(project), "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            current = json.loads(stdout)["presentation"]["targets"][0]

            exit_code, stdout, stderr = self.run_cli(
                [
                    "observer",
                    "transient-patch-apply",
                    str(project),
                    "--target-id",
                    "ws012-writer",
                    "--patch-id",
                    "patch-rerender",
                    "--expected-target-revision",
                    str(current["target_revision"]),
                    "--expected-presentation-revision",
                    str(current["presentation_revision"]),
                    "--presentation-fingerprint",
                    current["presentation_fingerprint"],
                    "--reviewed-intent",
                    "Temporarily emphasize route and run evidence.",
                    "--scope",
                    "presentation only",
                    "--rationale",
                    "Human inspection of Dashboard V2.",
                    "--evidence-ref",
                    "test:rerender",
                    "--density",
                    "detailed",
                    "--emphasize-section",
                    "route",
                    "--emphasize-section",
                    "runs",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            payload = json.loads(stdout)
            self.assertEqual(payload["event"]["event_kind"], "transient_patch_applied")
            self.assertEqual(current_path.read_bytes(), current_before)
            self.assertEqual(runs_path.read_bytes(), runs_before)
            dashboard = Path(payload["dashboard"]["path"])
            html = dashboard.read_text(encoding="utf-8")
            self.assertIn("展示调整详情", html)
            self.assertIn("patch-rerender", html)
            self.assertIn("density-detailed", html)

            exit_code, stdout, stderr = self.run_cli(
                ["observer", "presentation-status", str(project), "--json"]
            )
            self.assertEqual(exit_code, 0, stderr)
            patched = json.loads(stdout)["presentation"]["targets"][0]
            exit_code, stdout, stderr = self.run_cli(
                [
                    "observer",
                    "transient-patch-clear",
                    str(project),
                    "--target-id",
                    "ws012-writer",
                    "--expected-target-revision",
                    str(patched["target_revision"]),
                    "--expected-presentation-revision",
                    str(patched["presentation_revision"]),
                    "--presentation-fingerprint",
                    patched["presentation_fingerprint"],
                    "--reason",
                    "Inspection finished.",
                    "--evidence-ref",
                    "test:rerender-clear",
                    "--json",
                ]
            )
            self.assertEqual(exit_code, 0, stderr)
            self.assertEqual(json.loads(stdout)["event"]["event_kind"], "transient_patch_cleared")
            self.assertEqual(current_path.read_bytes(), current_before)
            self.assertEqual(runs_path.read_bytes(), runs_before)

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

    def test_transient_patch_uses_exact_presentation_view_and_clears_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            view = self.make_view("ws012-writer", "WS012")
            target_state, _ = self.apply_review(
                project,
                view,
                expected_target_revision=0,
                review_id="review-p3-base",
            )
            self.assertEqual(target_state["revision"], 1)
            self.assertEqual(target_state["presentation_revision"], 1)
            base_fingerprint = target_presentation_fingerprint(target_state)

            target_state, event = apply_transient_patch(
                project,
                target_view=view,
                patch_id="patch-density",
                expected_target_revision=1,
                expected_presentation_revision=1,
                expected_presentation_fingerprint=base_fingerprint,
                reviewed_intent="临时提高当前路线与问题的可见性。",
                scope="target presentation only",
                rationale="当前人工复核需要更高信息密度，但不改变路线事实。",
                evidence_refs=["user:presentation-review", "review:review-p3-base"],
                density="detailed",
                presentation_type="roadmap",
                emphasize_sections=["route", "problems", "runs"],
            )
            self.assertEqual(event["event_kind"], "transient_patch_applied")
            self.assertEqual(target_state["revision"], 2)
            self.assertEqual(target_state["presentation_revision"], 2)
            self.assertEqual(target_state["active_transient_patch"]["patch_id"], "patch-density")
            self.assertNotEqual(target_presentation_fingerprint(target_state), base_fingerprint)

            current_fingerprint = target_presentation_fingerprint(target_state)
            target_state, event = clear_transient_patch(
                project,
                target_id="ws012-writer",
                expected_target_revision=2,
                expected_presentation_revision=2,
                expected_presentation_fingerprint=current_fingerprint,
                reason="人工检查完成，恢复正式语义复核定义的默认展示。",
                evidence_refs=["review:transient-patch-complete"],
            )
            self.assertEqual(event["event_kind"], "transient_patch_cleared")
            self.assertEqual(target_state["revision"], 3)
            self.assertEqual(target_state["presentation_revision"], 3)
            self.assertIsNone(target_state["active_transient_patch"])

    def test_transient_patch_rejects_stale_presentation_view_even_with_current_target_revision(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            view = self.make_view("ws012-writer", "WS012")
            target_state, _ = self.apply_review(
                project,
                view,
                expected_target_revision=0,
                review_id="review-view-concurrency",
            )
            old_presentation_revision = target_state["presentation_revision"]
            old_fingerprint = target_presentation_fingerprint(target_state)
            target_state, _ = add_durable_rule(
                project,
                target_id="ws012-writer",
                rule_id="rule-current-position",
                expected_target_revision=1,
                reviewed_intent="长期突出当前位置。",
                scope="current position presentation",
                rationale="长期 human-first readability requirement.",
                evidence_refs=["authority:p3"],
            )
            self.assertEqual(target_state["revision"], 2)
            self.assertEqual(target_state["presentation_revision"], old_presentation_revision + 1)

            with self.assertRaises(ObserverPresentationViewChanged):
                apply_transient_patch(
                    project,
                    target_view=view,
                    patch_id="patch-stale-view",
                    expected_target_revision=2,
                    expected_presentation_revision=old_presentation_revision,
                    expected_presentation_fingerprint=old_fingerprint,
                    reviewed_intent="基于旧展示状态做修改。",
                    scope="presentation only",
                    rationale="必须 fail closed。",
                    evidence_refs=["test:stale-presentation"],
                )

    def test_transient_patch_escalates_semantic_risk_without_persisting_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            view = self.make_view("ws012-writer", "WS012")
            target_state, _ = self.apply_review(
                project,
                view,
                expected_target_revision=0,
                review_id="review-semantic-risk",
            )
            fingerprint = target_presentation_fingerprint(target_state)
            with self.assertRaises(ObserverPresentationSemanticEscalationRequired) as raised:
                apply_transient_patch(
                    project,
                    target_view=view,
                    patch_id="patch-route-order",
                    expected_target_revision=1,
                    expected_presentation_revision=1,
                    expected_presentation_fingerprint=fingerprint,
                    reviewed_intent="把未来节点放到当前节点前面。",
                    scope="route order",
                    rationale="该请求会改变语义，不允许作为展示 patch。",
                    evidence_refs=["user:route-change-request"],
                    semantic_risk_signals=["route order would change"],
                )
            self.assertEqual(raised.exception.signals, ["route order would change"])
            persisted = read_presentation_state(project)["targets"]["ws012-writer"]
            self.assertIsNone(persisted["active_transient_patch"])
            self.assertEqual(persisted["revision"], 1)

    def test_transient_patch_rejects_semantic_source_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            original = self.make_view("ws012-writer", "WS012")
            target_state, _ = self.apply_review(
                project,
                original,
                expected_target_revision=0,
                review_id="review-source-base",
            )
            changed = self.make_view(
                "ws012-writer",
                "WS012",
                stage="P3",
                next_action="Implement a newer route decision",
            )
            with self.assertRaises(ObserverPresentationSourceMismatch):
                apply_transient_patch(
                    project,
                    target_view=changed,
                    patch_id="patch-stale-semantics",
                    expected_target_revision=1,
                    expected_presentation_revision=1,
                    expected_presentation_fingerprint=target_presentation_fingerprint(target_state),
                    reviewed_intent="只调整展示。",
                    scope="presentation only",
                    rationale="源事实已经变化时必须先重新语义复核。",
                    evidence_refs=["test:source-drift"],
                )

    def test_semantic_review_expires_active_transient_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            view = self.make_view("ws012-writer", "WS012")
            target_state, _ = self.apply_review(
                project,
                view,
                expected_target_revision=0,
                review_id="review-before-transient",
            )
            target_state, _ = apply_transient_patch(
                project,
                target_view=view,
                patch_id="patch-before-review",
                expected_target_revision=1,
                expected_presentation_revision=1,
                expected_presentation_fingerprint=target_presentation_fingerprint(target_state),
                reviewed_intent="暂时突出问题。",
                scope="problem presentation",
                rationale="下一次正式 Map Review 前的临时视觉调整。",
                evidence_refs=["review:temporary"],
                emphasize_sections=["problems"],
            )
            self.assertIsNotNone(target_state["active_transient_patch"])

            target_state, event = self.apply_review(
                project,
                view,
                expected_target_revision=2,
                review_id="review-after-transient",
            )
            self.assertIsNone(target_state["active_transient_patch"])
            self.assertEqual(target_state["presentation_revision"], 3)
            self.assertEqual(event["expired_transient_patch"]["patch_id"], "patch-before-review")

    def test_dashboard_v2_renders_human_first_story_and_transient_presentation(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            view = self.make_view("ws012-writer", "WS012")
            problem = {
                "problem_id": "problem-dashboard-v2",
                "title": "当前路线受阻",
                "summary": "需要调整当前步骤后继续。",
                "expectedness": "unexpected",
                "handler": "agent_self",
                "scope_relation": "in_scope",
                "blocking_impact": "blocks_current_step",
                "plan_impact": "route_change",
                "status": "working",
                "route_ref": "route:observer-v2",
                "node_ref": "p2",
                "evidence_refs": ["runtime:dashboard-v2-problem"],
            }
            target_state, _ = self.apply_review(
                project,
                view,
                expected_target_revision=0,
                review_id="review-dashboard-v2",
                problems=[problem],
            )
            target_state, _ = apply_transient_patch(
                project,
                target_view=view,
                patch_id="patch-dashboard-v2",
                expected_target_revision=1,
                expected_presentation_revision=1,
                expected_presentation_fingerprint=target_presentation_fingerprint(target_state),
                reviewed_intent="临时强化路线、问题与运行历史。",
                scope="dashboard target presentation",
                rationale="人工检查 P3 可读性。",
                evidence_refs=["review:p3-dashboard"],
                density="detailed",
                presentation_type="hybrid",
                emphasize_sections=["route", "problems", "runs"],
            )
            semantic_status = presentation_status(project, {"targets": [view]})["targets"][0]
            view["semantic_review"] = semantic_status
            latest_run = {
                "run_id": "continuation-g81-scheduled-writer-81",
                "source": "continuation_round",
                "generation": 81,
                "runner_id": "scheduled-writer-81",
                "status": "completed",
                "result": "success",
                "started_at": "2026-09-01T00:00:00Z",
                "finished_at": "2026-09-01T00:10:00Z",
                "last_activity_at": "2026-09-01T00:10:00Z",
                "duration_seconds": 600.0,
                "phase": "executing",
                "major_outcome": "Validated map-first route.",
                "route_ref": "route:h1-map-first",
                "evidence_refs": [
                    "physical-execution:g81-map-first:exit:0",
                    "guard:WS012-file-scoped-pass",
                ],
            }
            view["runs"] = [latest_run]
            view["latest_run"] = latest_run
            current = {
                "observed_at": "2026-09-01T00:00:00Z",
                "alerts": [],
                "workstreams": view["workstreams"],
                "continuations": view["continuations"],
                "semantic": {"status": "current"},
                "targets": {
                    "targets": [view],
                    "project_overview": {"decision": "disabled", "reason": "Single target test", "evidence_refs": ["test:p3"]},
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
            self.assertIn('class="target-map-summary"', html)
            self.assertIn('class="target-story target-map-first"', html)
            self.assertIn("最终目标", html)
            self.assertIn("完整推进路线", html)
            self.assertIn("当前", html)
            self.assertIn("最近实质进展", html)
            self.assertIn("当前问题与影响", html)
            self.assertIn("处理者：Agent 自行处理", html)
            self.assertIn("阻塞影响：阻塞当前步骤", html)
            self.assertIn("计划影响：需要调整路线", html)
            self.assertIn("状态：处理中", html)
            self.assertNotIn("处理者：agent_self", html)
            self.assertIn("下一步", html)
            self.assertIn('class="relation-diagram"', html)
            self.assertIn('data-edge-from="p2" data-edge-to="p3"', html)
            self.assertIn('x1="248.0" y1="100.0" x2="308.0" y2="100.0"', html)
            self.assertNotIn('x1="153.0" y1="100.0" x2="403.0" y2="100.0"', html)
            self.assertIn('class="diagram-node tone-active is-current" data-node-id="p2"', html)
            self.assertIn('class="diagram-node tone-muted is-next" data-node-id="p3"', html)
            self.assertIn(">当前</text>", html)
            self.assertIn(">下一</text>", html)
            self.assertIn("目标完整路线关系图", html)
            self.assertIn("执行健康", html)
            self.assertIn("人工介入", html)
            self.assertIn("Agent 运行记录", html)
            self.assertIn("来源：Writer 持续执行轮次", html)
            self.assertIn("generation 81", html)
            self.assertIn("runner scheduled-writer-81", html)
            self.assertIn("路线关联", html)
            self.assertIn("<code>route:h1-map-first</code>", html)
            self.assertIn("证据覆盖：2 条", html)
            self.assertIn("physical-execution:g81-map-first:exit:0", html)
            self.assertIn("<strong>成功</strong>", html)
            self.assertIn("展示调整详情", html)
            self.assertIn("patch-dashboard-v2", html)
            self.assertIn("density-detailed", html)
            self.assertIn('data-story-section="route"', html)
            self.assertIn("is-emphasized", html)

    def test_dashboard_alert_severity_is_human_first_chinese(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            current = {
                "observed_at": "2026-09-01T00:00:00Z",
                "alerts": [],
                "workstreams": [],
                "continuations": [],
                "semantic": {"status": "current"},
                "targets": {"targets": []},
            }

            html = render_dashboard_html(
                project,
                current=current,
                status={"data_age": {"state": "fresh"}},
                machine_events=[],
                interpretations=[],
                glossary={"terms": {}},
                self_health_alerts=[
                    {
                        "alert_key": "test:warning",
                        "severity": "warning",
                        "title": "语义需要复核",
                        "explanation": "底层 authority 已发生变化。",
                    }
                ],
            )

            self.assertIn('<div class="muted">需要关注</div>', html)
            self.assertNotIn('<div class="muted">WARNING</div>', html)

    def test_dashboard_run_history_keeps_runs_beyond_default_visible_window_accessible(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            view = self.make_view("ws012-writer", "WS012")
            view["runs"] = [
                {
                    "run_id": f"run-{index:02d}",
                    "status": "completed",
                    "started_at": f"2026-09-01T{index:02d}:00:00Z",
                    "finished_at": f"2026-09-01T{index:02d}:10:00Z",
                    "last_activity_at": f"2026-09-01T{index:02d}:10:00Z",
                    "duration_seconds": 600.0,
                    "phase": f"phase-{index:02d}",
                    "major_outcome": f"outcome-{index:02d}",
                    "route_ref": f"route:phase-{index:02d}",
                }
                for index in range(15)
            ]
            view["runs"][-1].update(
                source="continuation_round",
                generation=81,
                runner_id="scheduled-writer-81",
            )
            view["runs"][-2].update(source="observer_marker", result="failed")
            view["latest_run"] = view["runs"][-1]
            current = {
                "observed_at": "2026-09-01T15:00:00Z",
                "alerts": [],
                "workstreams": view["workstreams"],
                "continuations": view["continuations"],
                "semantic": {"status": "current"},
                "targets": {
                    "targets": [view],
                    "project_overview": {
                        "decision": "disabled",
                        "reason": "Single target test",
                        "evidence_refs": ["test:run-history"],
                    },
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

            self.assertIn("共 15 次可归属运行", html)
            self.assertIn("默认显示最近 6 次", html)
            self.assertIn('class="target-run-history-archive"', html)
            self.assertIn("查看更早 9 次运行", html)
            for index in range(15):
                self.assertIn(f"run-{index:02d}", html)
            self.assertLess(html.index("run-14"), html.index("run-09"))
            self.assertLess(html.index("查看更早 9 次运行"), html.index("run-08"))
            self.assertIn("来源：Writer 持续执行轮次", html)
            self.assertIn("generation 81", html)
            self.assertIn("runner scheduled-writer-81", html)
            self.assertIn("来源：显式自动任务运行标记", html)
            self.assertIn("<code>route:phase-14</code>", html)
            self.assertIn("<strong>失败</strong>", html)
            self.assertIn("<strong>已完成</strong>", html)
            self.assertIn("证据覆盖：0 条", html)
            self.assertIn("尚无可归属 evidence_ref", html)

    def test_integrated_presentation_lifecycles_do_not_resurrect_transient_guidance(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            view = self.make_view("ws012-writer", "WS012")
            target_state, _ = add_one_shot_review_request(
                project,
                target_id="ws012-writer",
                request_id="request-next-review",
                expected_target_revision=0,
                reviewed_intent="下一次 Map Review 重新判断当前路线的视觉结构。",
                scope="target route semantics",
                rationale="一次性检查当前阶段变化后的路线表达。",
                evidence_refs=["user:one-shot"],
            )
            target_state, _ = add_durable_rule(
                project,
                target_id="ws012-writer",
                rule_id="rule-why-now",
                expected_target_revision=1,
                reviewed_intent="长期保留 why-now 与 next-logic 的 human-first 表达。",
                scope="target narrative",
                rationale="长期可读性规则。",
                evidence_refs=["user:durable-rule"],
            )
            self.assertEqual(target_state["revision"], 2)
            self.assertEqual(target_state["presentation_revision"], 1)

            target_state, event = self.apply_review(
                project,
                view,
                expected_target_revision=2,
                review_id="review-integrated",
                consume=["request-next-review"],
            )
            self.assertEqual(event["event_kind"], "semantic_review_applied")
            self.assertEqual(target_state["one_shot_requests"], [])
            self.assertEqual(target_state["current_review"]["active_durable_rule_ids"], ["rule-why-now"])
            self.assertEqual(target_state["presentation_revision"], 2)

            target_state, _ = apply_transient_patch(
                project,
                target_view=view,
                patch_id="patch-integrated",
                expected_target_revision=3,
                expected_presentation_revision=2,
                expected_presentation_fingerprint=target_presentation_fingerprint(target_state),
                reviewed_intent="本次人工验收临时突出最近证据。",
                scope="recent proof presentation",
                rationale="只对当前人工检查有效。",
                evidence_refs=["acceptance:transient"],
                emphasize_sections=["recent_proof"],
            )
            self.assertEqual(target_state["active_transient_patch"]["patch_id"], "patch-integrated")

            target_state, _ = clear_transient_patch(
                project,
                target_id="ws012-writer",
                expected_target_revision=4,
                expected_presentation_revision=3,
                expected_presentation_fingerprint=target_presentation_fingerprint(target_state),
                reason="一次性人工验收结束。",
                evidence_refs=["acceptance:transient-cleared"],
            )
            self.assertIsNone(target_state["active_transient_patch"])
            self.assertEqual(target_state["one_shot_requests"], [])
            self.assertEqual(
                [row["rule_id"] for row in target_state["durable_rules"] if row["status"] == "active"],
                ["rule-why-now"],
            )

            target_state, _ = withdraw_durable_rule(
                project,
                target_id="ws012-writer",
                rule_id="rule-why-now",
                expected_target_revision=5,
                reason="长期规则已被最新 authority 取消。",
                evidence_refs=["authority:durable-rule-withdrawn"],
            )
            self.assertIsNone(target_state["active_transient_patch"])
            self.assertEqual(target_state["one_shot_requests"], [])
            self.assertEqual(
                [row for row in target_state["durable_rules"] if row["status"] == "active"],
                [],
            )
            event_kinds = [
                json.loads(line)["event_kind"]
                for line in (project.observer_dir / "presentation" / "events.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertIn("one_shot_request_added", event_kinds)
            self.assertIn("durable_rule_added", event_kinds)
            self.assertIn("semantic_review_applied", event_kinds)
            self.assertIn("transient_patch_applied", event_kinds)
            self.assertIn("transient_patch_cleared", event_kinds)
            self.assertIn("durable_rule_withdrawn", event_kinds)

    def test_dashboard_v2_keeps_stale_target_semantics_fail_visible(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            original = self.make_view("ws012-writer", "WS012")
            self.apply_review(
                project,
                original,
                expected_target_revision=0,
                review_id="review-before-drift",
            )
            changed = self.make_view(
                "ws012-writer",
                "WS012",
                stage="P3-route-changed",
                next_action="Use a different route",
            )
            changed["semantic_review"] = presentation_status(
                project,
                {"targets": [changed]},
            )["targets"][0]
            current = {
                "observed_at": "2026-09-01T00:00:00Z",
                "alerts": [],
                "workstreams": changed["workstreams"],
                "continuations": changed["continuations"],
                "semantic": {"status": "current"},
                "targets": {
                    "targets": [changed],
                    "project_overview": {"decision": "disabled", "reason": "Single target test", "evidence_refs": ["test:stale"]},
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
            self.assertIn("目标路线已陈旧", html)
            self.assertIn("当前路线不能作为最新事实展示", html)
            self.assertIn("主区保持紧凑", html)
            self.assertNotIn('class="target-route-main"', html)
            self.assertIn("历史路线版本 / 归档地图", html)
            self.assertIn("review-before-drift", html)
            self.assertIn("此版本仅用于历史追溯，不代表当前状态", html)
            self.assertIn("历史路线版本 review-before-drift", html)

    def test_dashboard_archives_prior_semantic_review_without_mixing_it_into_current_map(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            first = self.make_view("ws012-writer", "WS012")
            self.apply_review(
                project,
                first,
                expected_target_revision=0,
                review_id="review-history-one",
            )
            second = self.make_view(
                "ws012-writer",
                "WS012",
                stage="P3",
                next_action="Validate current relationship map",
            )
            self.apply_review(
                project,
                second,
                expected_target_revision=1,
                review_id="review-history-two",
            )
            second["semantic_review"] = presentation_status(
                project,
                {"targets": [second]},
            )["targets"][0]
            current = {
                "observed_at": "2026-09-01T00:00:00Z",
                "alerts": [],
                "workstreams": second["workstreams"],
                "continuations": second["continuations"],
                "semantic": {"status": "current"},
                "targets": {
                    "targets": [second],
                    "project_overview": {
                        "decision": "disabled",
                        "reason": "Single target test",
                        "evidence_refs": ["test:semantic-history"],
                    },
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

            self.assertIn('class="target-story target-map-first"', html)
            self.assertIn("完整推进路线", html)
            self.assertIn("review-history-two", html)
            self.assertIn("历史路线版本 / 归档地图", html)
            self.assertIn("review-history-one", html)
            self.assertIn("历史路线版本 review-history-one", html)
            self.assertNotIn("历史路线版本 review-history-two", html)
            self.assertIn('data-history-version-picker="ws012-writer"', html)
            self.assertIn('data-history-version="review-history-one"', html)
            self.assertIn('value="review-history-one"', html)
            self.assertIn("当前路线图保持在上方，可选择一个历史版本并排对照", html)
            self.assertIn("禁用脚本时仍完整展示全部归档版本", html)
            self.assertIn("item.dataset.historyVersion!==selected", html)

    def test_dashboard_history_browser_can_select_two_archived_versions_for_side_by_side_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            first = self.make_view("ws012-writer", "WS012", stage="H1-a", next_action="First route")
            first_narrative = self.narrative()
            first_narrative["route_nodes"][0]["status"] = "completed"
            self.apply_review(
                project,
                first,
                expected_target_revision=0,
                review_id="review-history-a",
                narrative=first_narrative,
            )
            second = self.make_view("ws012-writer", "WS012", stage="H1-b", next_action="Second route")
            second_narrative = self.narrative()
            second_narrative["route_nodes"].append(
                {"id": "p4", "title": "P4", "status": "future", "summary": "dogfood", "evidence_refs": ["plan:p4"]}
            )
            second_narrative["route_edges"].append({"from": "p3", "to": "p4", "label": "next"})
            self.apply_review(
                project,
                second,
                expected_target_revision=1,
                review_id="review-history-b",
                narrative=second_narrative,
            )
            current_view = self.make_view("ws012-writer", "WS012", stage="H1-current", next_action="Current route")
            self.apply_review(
                project,
                current_view,
                expected_target_revision=2,
                review_id="review-current",
            )
            current_view["semantic_review"] = presentation_status(
                project,
                {"targets": [current_view]},
            )["targets"][0]
            current = {
                "observed_at": "2026-09-01T00:00:00Z",
                "alerts": [],
                "workstreams": current_view["workstreams"],
                "continuations": current_view["continuations"],
                "semantic": {"status": "current"},
                "targets": {
                    "targets": [current_view],
                    "project_overview": {
                        "decision": "disabled",
                        "reason": "Single target test",
                        "evidence_refs": ["test:semantic-history-compare"],
                    },
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

            self.assertIn('data-history-version-compare="ws012-writer"', html)
            self.assertIn("历史版本并排对比", html)
            self.assertIn('data-history-version-compare-a', html)
            self.assertIn('data-history-version-compare-b', html)
            self.assertIn('value="review-history-b" selected', html)
            self.assertIn('value="review-history-a" selected', html)
            self.assertIn('data-history-version="review-history-a"', html)
            self.assertIn('data-history-version="review-history-b"', html)
            self.assertIn("is-history-compare-active", html)
            self.assertIn("new Set([first.value,second.value])", html)
            self.assertIn("不会改写当前路线或自动推断节点等价关系", html)
            self.assertIn('data-history-compare-facts=', html)
            self.assertIn('&quot;p4&quot;', html)
            self.assertIn("稳定 ID 差异", html)
            self.assertIn("statusChanges", html)
            self.assertIn("仅 A 有关系", html)
            self.assertIn("并排原始归档仍保持可读", html)

    def test_dashboard_keeps_current_semantics_visible_when_history_journal_is_corrupt(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            view = self.make_view("ws012-writer", "WS012")
            self.apply_review(
                project,
                view,
                expected_target_revision=0,
                review_id="review-current-with-bad-history",
            )
            events_path = project.observer_dir / "presentation" / "events.jsonl"
            with events_path.open("a", encoding="utf-8") as handle:
                handle.write("{not-json}\n")
            view["semantic_review"] = presentation_status(
                project,
                {"targets": [view]},
            )["targets"][0]
            current = {
                "observed_at": "2026-09-01T00:00:00Z",
                "alerts": [],
                "workstreams": view["workstreams"],
                "continuations": view["continuations"],
                "semantic": {"status": "current"},
                "targets": {
                    "targets": [view],
                    "project_overview": {
                        "decision": "disabled",
                        "reason": "Single target test",
                        "evidence_refs": ["test:history-local-degrade"],
                    },
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

            self.assertIn('class="target-story target-map-first"', html)
            self.assertIn("完整推进路线", html)
            self.assertIn("review-current-with-bad-history", html)
            self.assertIn("历史路线暂不可读", html)
            self.assertIn("cannot read observer presentation history line", html)

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

    def test_semantic_review_rejects_dangling_current_and_problem_node_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = self.make_project(Path(tmp))
            view = self.make_view("ws012-writer", "WS012")
            narrative = self.narrative()
            narrative["current_node_refs"] = ["missing-node"]
            with self.assertRaisesRegex(ObserverPresentationError, "current_node_refs.*unknown route node"):
                apply_semantic_review(
                    project,
                    target_view=view,
                    expected_target_revision=0,
                    expected_source_fingerprint=target_semantic_source_fingerprint(view),
                    review_id="review-dangling-current",
                    authority_fingerprint="authority:sha256:dangling-current",
                    authority_reread=True,
                    decision="patch",
                    reason="Validate explicit current-position binding.",
                    evidence_refs=["test:dangling-current"],
                    map_relevant_signals=["current position changed"],
                    presentation_type="roadmap",
                    narrative=narrative,
                    problems=[],
                )

            problem = {
                "problem_id": "problem-dangling",
                "title": "Dangling problem",
                "summary": "Problem must bind to a real route node.",
                "expectedness": "unexpected",
                "handler": "agent_self",
                "scope_relation": "in_scope",
                "blocking_impact": "degrading",
                "plan_impact": "local_adjustment",
                "status": "working",
                "node_ref": "missing-node",
                "evidence_refs": ["test:dangling-problem"],
            }
            with self.assertRaisesRegex(ObserverPresentationError, "problem node_ref.*unknown route node"):
                apply_semantic_review(
                    project,
                    target_view=view,
                    expected_target_revision=0,
                    expected_source_fingerprint=target_semantic_source_fingerprint(view),
                    review_id="review-dangling-problem",
                    authority_fingerprint="authority:sha256:dangling-problem",
                    authority_reread=True,
                    decision="patch",
                    reason="Validate problem-to-route binding.",
                    evidence_refs=["test:dangling-problem"],
                    map_relevant_signals=["problem binding changed"],
                    presentation_type="roadmap",
                    narrative=self.narrative(),
                    problems=[problem],
                )

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
