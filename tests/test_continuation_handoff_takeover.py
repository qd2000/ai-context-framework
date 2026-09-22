"""Ownerless dirty-WIP agent-first takeover (WS019).

These tests cover the narrow path where a graceful ownerless handoff is followed
by task-owned WIP drift: ACF must keep blocking a normal claim, let the same
runner review the preserved scene in bulk, and then accept the reviewed WIP in
one atomic claim without touching a single workspace byte.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

import acf
from ai_context_framework import continuation_handoff_review

REVIEW_SCHEMA = "acf.continuation.workspace-handoff-review.v1"
TAKEOVER_SCHEMA = "acf.continuation.workspace-handoff-takeover.v1"


def _entry(path: str, status: str, digest: str) -> dict[str, str]:
    return {
        "schema_version": "acf.continuation.workspace-entry.v1",
        "path": path,
        "status": status,
        "digest": digest,
    }


class HandoffTakeoverModelTests(unittest.TestCase):
    """Mechanical rules the CLI cannot easily reach."""

    def _manifest(
        self,
        *,
        task_owned: list[dict[str, str]],
        intents: list[str],
        generation: int = 3,
    ) -> dict[str, Any]:
        return {
            "schema_version": "acf.continuation.workspace.v3",
            "task_id": "WS900",
            "baseline_head": "head-1",
            "generation": generation,
            "baseline_external": [],
            "write_intents": list(intents),
            "task_owned": list(task_owned),
            "unexpected_nonoverlap": [],
            "conflicts": [],
            "last_observed_at": "2026-09-22T00:00:00+00:00",
            "adoption_receipt": None,
        }

    def _snapshot(
        self,
        *,
        entries: list[dict[str, str]],
        head: str = "head-1",
    ) -> dict[str, Any]:
        return {
            "head": head,
            "entries": list(entries),
            "stat_only_paths": [],
            "legacy_digest_aliases": {},
        }

    def _bundle(
        self,
        manifest: dict[str, Any],
        snapshot: dict[str, Any],
        *,
        scopes: list[str] | None = None,
    ) -> dict[str, Any]:
        return continuation_handoff_review.build_handoff_review_bundle(
            manifest,
            task_id="WS900",
            runner_id="runner-a",
            snapshot=snapshot,
            now="2026-09-22T00:00:00+00:00",
            allowed_scopes=list(scopes or []),
            candidate_paths={"src/a.py": ["src/a.py"]},
        )

    def _decide(
        self,
        bundle: dict[str, Any],
        action: str,
        *,
        paths: list[str] | None = None,
    ) -> dict[str, Any]:
        decided = dict(bundle)
        decided["decisions"] = [
            {
                "action": action,
                "paths": (
                    list(paths)
                    if paths is not None
                    else [item["path"] for item in bundle["entries"]]
                ),
                "reason": "reviewed by the owning agent",
                "evidence_refs": ["diff-review:group-1"],
            }
        ]
        return decided

    def _apply(
        self,
        manifest: dict[str, Any],
        snapshot: dict[str, Any],
        review: dict[str, Any],
        *,
        scopes: list[str] | None = None,
        accepted_head: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        return continuation_handoff_review.apply_handoff_review(
            manifest,
            task_id="WS900",
            runner_id="runner-a",
            snapshot=snapshot,
            review=review,
            allowed_scopes=list(scopes or []),
            candidate_paths={"src/a.py": ["src/a.py"]},
            accepted_head=accepted_head,
            receipt_id="receipt-1",
            now="2026-09-22T00:00:00+00:00",
            new_generation=4,
        )

    def test_review_bundle_binds_fingerprints_and_groups_paths(self) -> None:
        manifest = self._manifest(
            task_owned=[
                _entry("src/a.py", "M", "a" * 64),
                _entry("src/nested/b.py", "M", "b" * 64),
            ],
            intents=["src/a.py", "src/nested/b.py"],
        )
        snapshot = self._snapshot(
            entries=[_entry("src/a.py", "M", "c" * 64), _entry("src/nested/b.py", "M", "d" * 64)]
        )
        bundle = self._bundle(manifest, snapshot, scopes=["src/**"])
        self.assertEqual(REVIEW_SCHEMA, bundle["schema_version"])
        self.assertEqual(2, bundle["total_entries"])
        self.assertEqual(3, bundle["source_generation"])
        self.assertEqual("head-1", bundle["current_head"])
        self.assertEqual(["src/a.py", "src/nested/b.py"], [item["path"] for item in bundle["entries"]])
        for item in bundle["entries"]:
            self.assertEqual("content_changed", item["change_kind"])
            self.assertTrue(item["intent_covered"])
            self.assertTrue(item["inside_workstream_scope"])
            self.assertEqual({"added": 0, "deleted": 0}, item["diff_stat"])
        self.assertEqual(2, len(bundle["groups"]))
        self.assertEqual(1, bundle["groups"][0]["path_count"])
        moved = self._snapshot(
            entries=[_entry("src/a.py", "M", "e" * 64), _entry("src/nested/b.py", "M", "d" * 64)]
        )
        self.assertNotEqual(
            bundle["observation_digest"],
            self._bundle(manifest, moved, scopes=["src/**"])["observation_digest"],
        )

    def test_pagination_does_not_truncate_the_decision_draft(self) -> None:
        manifest = self._manifest(
            task_owned=[_entry(f"src/f{index}.py", "M", f"{index:064d}") for index in range(5)],
            intents=["src"],
        )
        snapshot = self._snapshot(
            entries=[_entry(f"src/f{index}.py", "M", f"{index + 10:064d}") for index in range(5)]
        )
        bundle = self._bundle(manifest, snapshot)
        self.assertEqual(5, len(bundle["entries"]))
        first = continuation_handoff_review.paginate_review_bundle(bundle, page=1, page_size=2)
        self.assertEqual(2, len(first["entries"]))
        self.assertEqual(3, first["total_pages"])
        self.assertEqual(5, first["total_entries"])
        last = continuation_handoff_review.paginate_review_bundle(bundle, page=3, page_size=2)
        self.assertEqual(1, len(last["entries"]))
        self.assertEqual(5, len(bundle["entries"]))
        with self.assertRaises(continuation_handoff_review.ContinuationWorkspaceError):
            continuation_handoff_review.paginate_review_bundle(bundle, page=0)

    def test_inheriting_a_path_without_retained_intent_is_refused(self) -> None:
        manifest = self._manifest(task_owned=[_entry("src/a.py", "M", "a" * 64)], intents=[])
        snapshot = self._snapshot(entries=[_entry("src/a.py", "M", "c" * 64)])
        bundle = self._bundle(manifest, snapshot)
        with self.assertRaises(continuation_handoff_review.ContinuationWorkspaceError) as caught:
            self._apply(manifest, snapshot, self._decide(bundle, "inherit_for_triage"))
        self.assertEqual("workspace_handoff_review_conflict_mismatch", caught.exception.code)

    def test_inherit_outside_workstream_scope_is_refused(self) -> None:
        manifest = self._manifest(
            task_owned=[_entry("src/a.py", "M", "a" * 64)], intents=["src/a.py"]
        )
        snapshot = self._snapshot(entries=[_entry("src/a.py", "M", "c" * 64)])
        bundle = self._bundle(manifest, snapshot, scopes=["other/**"])
        self.assertFalse(bundle["entries"][0]["inside_workstream_scope"])
        with self.assertRaises(continuation_handoff_review.ContinuationWorkspaceError) as caught:
            self._apply(
                manifest,
                snapshot,
                self._decide(bundle, "inherit_for_triage"),
                scopes=["other/**"],
            )
        self.assertEqual("workspace_handoff_review_scope_conflict", caught.exception.code)

    def test_preserve_external_refuses_scope_or_intent_overlap(self) -> None:
        manifest = self._manifest(
            task_owned=[_entry("src/a.py", "M", "a" * 64)], intents=["src/a.py"]
        )
        snapshot = self._snapshot(entries=[_entry("src/a.py", "M", "c" * 64)])
        bundle = self._bundle(manifest, snapshot, scopes=["src/**"])
        with self.assertRaises(continuation_handoff_review.ContinuationWorkspaceError) as caught:
            self._apply(
                manifest,
                snapshot,
                self._decide(bundle, "preserve_external"),
                scopes=["src/**"],
            )
        self.assertEqual("workspace_handoff_review_scope_conflict", caught.exception.code)
        unscoped = self._bundle(manifest, snapshot)
        with self.assertRaises(continuation_handoff_review.ContinuationWorkspaceError) as caught:
            self._apply(manifest, snapshot, self._decide(unscoped, "preserve_external"))
        self.assertEqual("workspace_handoff_review_scope_conflict", caught.exception.code)

    def test_semantic_clean_requires_the_path_to_be_absent_from_snapshot(self) -> None:
        manifest = self._manifest(
            task_owned=[_entry("src/a.py", "M", "a" * 64)], intents=["src/a.py"]
        )
        snapshot = self._snapshot(entries=[_entry("src/a.py", "M", "c" * 64)])
        bundle = self._bundle(manifest, snapshot)
        with self.assertRaises(continuation_handoff_review.ContinuationWorkspaceError) as caught:
            self._apply(manifest, snapshot, self._decide(bundle, "semantic_clean"))
        self.assertEqual("workspace_handoff_review_conflict_mismatch", caught.exception.code)

    def test_semantic_clean_accepts_a_path_that_is_no_longer_dirty(self) -> None:
        manifest = self._manifest(
            task_owned=[_entry("src/a.py", "M", "a" * 64)], intents=["src/a.py"]
        )
        snapshot = self._snapshot(entries=[])
        bundle = self._bundle(manifest, snapshot)
        self.assertEqual("disappeared", bundle["entries"][0]["change_kind"])
        manifest2, receipt = self._apply(
            manifest, snapshot, self._decide(bundle, "semantic_clean")
        )
        self.assertEqual([], manifest2["task_owned"])
        self.assertEqual([], manifest2["write_intents"])
        self.assertEqual(["src/a.py"], receipt["cleaned_paths"])
        self.assertEqual(TAKEOVER_SCHEMA, receipt["schema_version"])

    def test_unrelated_workspace_conflict_stays_fail_closed(self) -> None:
        manifest = self._manifest(task_owned=[_entry("src/a.py", "M", "a" * 64)], intents=[])
        snapshot = self._snapshot(entries=[_entry("src/a.py", "M", "c" * 64)])
        bundle = self._bundle(manifest, snapshot)
        with self.assertRaises(continuation_handoff_review.ContinuationWorkspaceError) as caught:
            self._apply(manifest, snapshot, self._decide(bundle, "preserve_external"))
        self.assertEqual("workspace_handoff_review_conflict_mismatch", caught.exception.code)

    def test_runner_mismatch_is_refused(self) -> None:
        manifest = self._manifest(
            task_owned=[_entry("src/a.py", "M", "a" * 64)], intents=["src/a.py"]
        )
        snapshot = self._snapshot(entries=[_entry("src/a.py", "M", "c" * 64)])
        bundle = self._bundle(manifest, snapshot)
        with self.assertRaises(continuation_handoff_review.ContinuationWorkspaceError) as caught:
            continuation_handoff_review.apply_handoff_review(
                manifest,
                task_id="WS900",
                runner_id="runner-b",
                snapshot=snapshot,
                review=self._decide(bundle, "inherit_for_triage"),
                receipt_id="receipt-1",
                now="2026-09-22T00:00:00+00:00",
                new_generation=4,
            )
        self.assertEqual("workspace_handoff_review_runner_mismatch", caught.exception.code)

    def test_stale_review_is_refused_after_the_scene_changes(self) -> None:
        manifest = self._manifest(
            task_owned=[_entry("src/a.py", "M", "a" * 64)], intents=["src/a.py"]
        )
        snapshot = self._snapshot(entries=[_entry("src/a.py", "M", "c" * 64)])
        bundle = self._bundle(manifest, snapshot)
        moved = self._snapshot(entries=[_entry("src/a.py", "M", "f" * 64)])
        with self.assertRaises(continuation_handoff_review.ContinuationWorkspaceError) as caught:
            self._apply(manifest, moved, self._decide(bundle, "inherit_for_triage"))
        self.assertEqual("workspace_handoff_review_stale", caught.exception.code)

    def test_head_drift_requires_explicit_acceptance(self) -> None:
        manifest = self._manifest(
            task_owned=[_entry("src/a.py", "M", "a" * 64)], intents=["src/a.py"]
        )
        snapshot = self._snapshot(entries=[_entry("src/a.py", "M", "c" * 64)])
        bundle = self._bundle(manifest, snapshot)
        drifted = self._snapshot(entries=[_entry("src/a.py", "M", "c" * 64)], head="head-2")
        with self.assertRaises(continuation_handoff_review.ContinuationWorkspaceError) as caught:
            self._apply(manifest, drifted, self._decide(bundle, "inherit_for_triage"))
        self.assertEqual("workspace_handoff_review_head_unaccepted", caught.exception.code)
        accepted = self._decide(bundle, "inherit_for_triage")
        accepted["current_head"] = "head-2"
        manifest2, receipt = self._apply(manifest, drifted, accepted, accepted_head="head-2")
        self.assertEqual("head-2", manifest2["baseline_head"])
        self.assertEqual("head-2", receipt["accepted_head"])

    def test_block_decision_keeps_the_task_blocked(self) -> None:
        manifest = self._manifest(
            task_owned=[_entry("src/a.py", "M", "a" * 64)], intents=["src/a.py"]
        )
        snapshot = self._snapshot(entries=[_entry("src/a.py", "M", "c" * 64)])
        bundle = self._bundle(manifest, snapshot)
        with self.assertRaises(continuation_handoff_review.ContinuationWorkspaceError) as caught:
            self._apply(manifest, snapshot, self._decide(bundle, "block"))
        self.assertEqual("workspace_handoff_review_blocked", caught.exception.code)

    def test_missing_duplicate_and_unexpected_paths_are_refused(self) -> None:
        manifest = self._manifest(
            task_owned=[_entry("src/a.py", "M", "a" * 64)], intents=["src/a.py"]
        )
        snapshot = self._snapshot(entries=[_entry("src/a.py", "M", "c" * 64)])
        bundle = self._bundle(manifest, snapshot)
        for paths in ([], ["src/other.py"], ["src/a.py", "src/a.py"], ["src", "src/a.py"]):
            with self.subTest(paths=paths):
                with self.assertRaises(continuation_handoff_review.ContinuationWorkspaceError) as caught:
                    self._apply(
                        manifest,
                        snapshot,
                        self._decide(bundle, "inherit_for_triage", paths=paths),
                    )
                self.assertEqual("workspace_handoff_review_incomplete", caught.exception.code)

    def test_review_requires_actual_drift(self) -> None:
        manifest = self._manifest(
            task_owned=[_entry("src/a.py", "M", "a" * 64)], intents=["src/a.py"]
        )
        snapshot = self._snapshot(entries=[_entry("src/a.py", "M", "a" * 64)])
        with self.assertRaises(continuation_handoff_review.ContinuationWorkspaceError) as caught:
            self._bundle(manifest, snapshot)
        self.assertEqual("workspace_handoff_review_required", caught.exception.code)


class ContinuationHandoffTakeoverTests(unittest.TestCase):
    def setUp(self) -> None:
        self._home = tempfile.TemporaryDirectory()
        self._repo = tempfile.TemporaryDirectory()
        self.previous_home = os.environ.get("ACF_HOME")
        os.environ["ACF_HOME"] = self._home.name
        self.root = Path(self._repo.name).resolve()
        self._git("init", "-b", "main")
        self._git("config", "user.name", "ACF Continuation Test")
        self._git("config", "user.email", "acf-continuation@example.invalid")
        (self.root / "README.md").write_text("continuation\n", encoding="utf-8")
        self._git("add", "README.md")
        self._git("commit", "-m", "test: init")

    def tearDown(self) -> None:
        if self.previous_home is None:
            os.environ.pop("ACF_HOME", None)
        else:
            os.environ["ACF_HOME"] = self.previous_home
        self._repo.cleanup()
        self._home.cleanup()

    def _git(self, *args: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            self.fail(result.stderr or result.stdout)
        return result

    def run_json(self, args: list[str]) -> tuple[int, dict[str, Any], str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = acf.main([*args, "--json"])
        raw = stdout.getvalue().strip()
        self.assertTrue(raw, stderr.getvalue())
        return code, json.loads(raw), stderr.getvalue()

    def init_task(self, task_id: str = "WS900") -> dict[str, Any]:
        code, payload, stderr = self.run_json(
            [
                "continuation",
                "init",
                str(self.root),
                "--task-id",
                task_id,
                "--title",
                "Continuation test",
                "--objective",
                "Validate ownerless dirty WIP takeover.",
                "--next-action",
                "Run gate one.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{payload}")
        self.state_dir = Path(str(payload["state_dir"]))
        return payload

    def owner_flags(self, claim: dict[str, Any]) -> list[str]:
        owner_context = claim["owner_context"]
        self.assertIsInstance(owner_context, dict)
        return ["--owner-file", str(owner_context["handle"])]

    @staticmethod
    def _file_snapshot(paths: list[Path]) -> dict[Path, bytes | None]:
        return {path: path.read_bytes() if path.exists() else None for path in paths}

    def _assert_file_snapshot(self, expected: dict[Path, bytes | None]) -> None:
        for path, content in expected.items():
            with self.subTest(path=str(path)):
                if content is None:
                    self.assertFalse(path.exists())
                else:
                    self.assertTrue(path.is_file())
                    self.assertEqual(content, path.read_bytes())

    def _wip_paths(self, count: int) -> list[str]:
        return [f"src/takeover-{index:02d}.txt" for index in range(count)]

    def _drifted_handoff(
        self,
        *,
        task_id: str = "WS900",
        count: int = 3,
        runner_id: str = "runner-a",
        effect_key: str | None = None,
    ) -> tuple[str, list[str], dict[str, Any]]:
        """Claim, declare intent, create WIP, hand off, then drift the WIP."""

        paths = self._wip_paths(count)
        self.init_task(task_id)
        code, claim, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                task_id,
                "--runner-id",
                runner_id,
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{claim}")
        intent_args: list[str] = []
        for path_value in paths:
            intent_args.extend(["--path", path_value])
        code, intent, stderr = self.run_json(
            [
                "continuation",
                "workspace",
                "intent",
                str(self.root),
                "--task-id",
                task_id,
                *self.owner_flags(claim),
                *intent_args,
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{intent}")
        for path_value in paths:
            target = self.root / path_value
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"original {path_value}\n", encoding="utf-8")
        if effect_key is not None:
            code, prepared, stderr = self.run_json(
                [
                    "continuation",
                    "effect",
                    "prepare",
                    str(self.root),
                    "--task-id",
                    task_id,
                    *self.owner_flags(claim),
                    "--key",
                    effect_key,
                    "--kind",
                    "external-job",
                ]
            )
            self.assertEqual(0, code, f"{stderr}\n{prepared}")
        code, released, stderr = self.run_json(
            [
                "continuation",
                "release",
                str(self.root),
                "--task-id",
                task_id,
                *self.owner_flags(claim),
                "--handoff",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{released}")
        for path_value in paths:
            (self.root / path_value).write_text(f"changed {path_value}\n", encoding="utf-8")
        return task_id, paths, claim

    def _review(
        self,
        task_id: str,
        runner_id: str,
        draft_path: Path,
        *extra: str,
    ) -> tuple[int, dict[str, Any], str]:
        return self.run_json(
            [
                "continuation",
                "workspace",
                "review-handoff",
                str(self.root),
                "--task-id",
                task_id,
                "--runner-id",
                runner_id,
                "--draft-file",
                str(draft_path),
                *extra,
            ]
        )

    @staticmethod
    def _fill(draft_path: Path, decisions: list[dict[str, Any]]) -> dict[str, Any]:
        payload = json.loads(draft_path.read_text(encoding="utf-8"))
        payload["decisions"] = decisions
        draft_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return payload

    def _claim_with_review(
        self,
        task_id: str,
        runner_id: str,
        draft_path: Path,
        *extra: str,
    ) -> tuple[int, dict[str, Any], str]:
        return self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                task_id,
                "--runner-id",
                runner_id,
                "--handoff-review-file",
                str(draft_path),
                *extra,
            ]
        )

    @staticmethod
    def _inherit_all(bundle: dict[str, Any], reason: str = "Task-owned WIP worth preserving.") -> list[dict[str, Any]]:
        return [
            {
                "action": "inherit_for_triage",
                "paths": [item["path"] for item in bundle["entries"]],
                "reason": reason,
                "evidence_refs": ["task-plan:current-objective", "diff-review:all"],
            }
        ]

    def test_doctor_reports_reviewable_ownerless_handoff_drift(self) -> None:
        task_id, paths, _claim = self._drifted_handoff(count=4)
        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", task_id]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertFalse(doctor["can_claim"])
        self.assertIn("workspace_conflict", doctor["blocked_reasons"])
        self.assertIn("workspace_handoff_review_required", doctor["blocked_reasons"])
        workspace = doctor["workspace"]
        self.assertTrue(workspace["handoff_reviewable"])
        self.assertEqual(4, workspace["review_path_count"])
        self.assertEqual(sorted(paths), sorted(workspace["review_paths"]))
        self.assertTrue(workspace["observation_digest"])
        self.assertEqual([], doctor["state_compatibility"]["blocked_files"])
        joined = " ".join(doctor["next_actions"])
        self.assertIn("review-handoff", joined)
        self.assertIn("--handoff-review-file", joined)

    def test_same_runner_reviews_and_takes_over_twenty_dirty_wip_paths(self) -> None:
        task_id, paths, claim = self._drifted_handoff(count=20)
        draft_path = self.root.parent / "review-draft.json"
        files = [self.root / path_value for path_value in paths]
        before = self._file_snapshot(files)
        head_before = self._git("rev-parse", "HEAD").stdout.strip()
        status_before = self._git("status", "--porcelain=v1", "--untracked-files=all").stdout

        code, review, stderr = self._review(task_id, "runner-b", draft_path)
        self.assertEqual(0, code, f"{stderr}\n{review}")
        self.assertEqual("workspace_handoff_review_ready", review["status"])
        self.assertEqual(20, review["review_path_count"])
        self.assertTrue(draft_path.is_file())
        bundle = json.loads(draft_path.read_text(encoding="utf-8"))
        self.assertEqual(REVIEW_SCHEMA, bundle["schema_version"])
        self.assertEqual(20, bundle["total_entries"])
        self.assertEqual([], bundle["decisions"])
        self.assertTrue(bundle["groups"])

        self._fill(
            draft_path,
            [
                {
                    "action": "inherit_for_triage",
                    "paths": paths,
                    "reason": "All twenty paths belong to the current task and must be verified after takeover.",
                    "evidence_refs": ["task-plan:current-objective", "diff-review:group-1"],
                }
            ],
        )
        code, taken, stderr = self._claim_with_review(task_id, "runner-b", draft_path)
        self.assertEqual(0, code, f"{stderr}\n{taken}")
        self.assertGreater(int(taken["generation"]), int(claim["generation"]))
        takeover = taken["handoff_takeover"]
        self.assertEqual("accepted_for_triage", takeover["status"])
        self.assertEqual("triage_inherited_wip", takeover["required_initial_action"])
        self.assertEqual(20, takeover["inherited_dirty_wip_count"])
        self.assertEqual(sorted(paths), sorted(takeover["inherited_dirty_wip_paths"]))
        self.assertEqual([], takeover["preserved_external_paths"])
        self.assertEqual([], takeover["cleaned_paths"])
        self.assertEqual(sorted(paths), sorted(taken["workspace"]["task_owned_paths"]))

        self._assert_file_snapshot(before)
        self.assertEqual(head_before, self._git("rev-parse", "HEAD").stdout.strip())
        self.assertEqual(
            status_before,
            self._git("status", "--porcelain=v1", "--untracked-files=all").stdout,
        )

        receipt = json.loads((self.state_dir / "last_handoff_takeover.json").read_text(encoding="utf-8"))
        self.assertEqual(TAKEOVER_SCHEMA, receipt["schema_version"])
        self.assertEqual(takeover["receipt_id"], receipt["receipt_id"])
        self.assertEqual("runner-b", receipt["runner_id"])
        self.assertEqual(int(claim["generation"]), receipt["source_generation"])
        self.assertEqual(int(taken["generation"]), receipt["new_generation"])
        self.assertEqual(20, len(receipt["entries"]))
        self.assertEqual("inherit_for_triage", receipt["entries"][0]["decision"])
        self.assertTrue(receipt["review_file_digest"])

        # The new owner keeps working through the normal flow.
        (self.root / paths[0]).write_text("continued by new owner\n", encoding="utf-8")
        code, refreshed, stderr = self.run_json(
            [
                "continuation",
                "workspace",
                "refresh",
                str(self.root),
                "--task-id",
                task_id,
                *self.owner_flags(taken),
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{refreshed}")
        (self.root / paths[1]).unlink()
        (self.root / paths[2]).write_text("rewritten\n", encoding="utf-8")
        code, refreshed, stderr = self.run_json(
            [
                "continuation",
                "workspace",
                "refresh",
                str(self.root),
                "--task-id",
                task_id,
                *self.owner_flags(taken),
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{refreshed}")
        code, checkpoint, stderr = self.run_json(
            [
                "continuation",
                "checkpoint",
                str(self.root),
                "--task-id",
                task_id,
                *self.owner_flags(taken),
                "--stage",
                "triage",
                "--next-action",
                "Continue triaging inherited WIP.",
                "--verification",
                "Inherited WIP reviewed, one path reverted and one rewritten.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{checkpoint}")

    def test_prompt_surfaces_inherited_wip_and_review_actions(self) -> None:
        task_id, _paths, _claim = self._drifted_handoff(count=2)
        draft_path = self.root.parent / "review-draft.json"
        code, review, stderr = self._review(task_id, "runner-b", draft_path)
        self.assertEqual(0, code, f"{stderr}\n{review}")
        code, prompt, stderr = self.run_json(
            ["continuation", "prompt", str(self.root), "--task-id", task_id]
        )
        self.assertEqual(0, code, f"{stderr}\n{prompt}")
        self.assertIn("review-handoff", prompt["prompt"])
        self.assertIn("inherit_for_triage", prompt["prompt"])

        bundle = json.loads(draft_path.read_text(encoding="utf-8"))
        self._fill(draft_path, self._inherit_all(bundle))
        code, taken, stderr = self._claim_with_review(task_id, "runner-b", draft_path)
        self.assertEqual(0, code, f"{stderr}\n{taken}")
        code, prompt, stderr = self.run_json(
            [
                "continuation",
                "prompt",
                str(self.root),
                "--task-id",
                task_id,
                "--runner-id",
                "runner-b",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{prompt}")
        self.assertIn("Inherited uncommitted WIP requires triage", prompt["prompt"])
        self.assertIn("proven correct", prompt["prompt"])
        self.assertEqual("accepted_for_triage", prompt["handoff_takeover"]["status"])
        self.assertEqual(
            "triage_inherited_wip", prompt["handoff_takeover"]["required_initial_action"]
        )

    def test_review_handoff_refuses_when_no_drift_exists(self) -> None:
        task_id, paths, _claim = self._drifted_handoff(count=2)
        for path_value in paths:
            (self.root / path_value).write_text(f"original {path_value}\n", encoding="utf-8")
        draft_path = self.root.parent / "review-draft.json"
        code, payload, stderr = self._review(task_id, "runner-b", draft_path)
        self.assertEqual(3, code)
        self.assertEqual("workspace_handoff_review_required", payload["error_code"])

    def test_takeover_refuses_file_change_after_review(self) -> None:
        task_id, paths, _claim = self._drifted_handoff(count=2)
        draft_path = self.root.parent / "review-draft.json"
        code, review, stderr = self._review(task_id, "runner-b", draft_path)
        self.assertEqual(0, code, f"{stderr}\n{review}")
        bundle = json.loads(draft_path.read_text(encoding="utf-8"))
        self._fill(draft_path, self._inherit_all(bundle))
        (self.root / paths[0]).write_text("changed again after review\n", encoding="utf-8")
        code, payload, stderr = self._claim_with_review(task_id, "runner-b", draft_path)
        self.assertEqual(3, code, f"{stderr}\n{payload}")
        self.assertEqual("workspace_handoff_review_stale", payload["error_code"])
        self.assertTrue(payload["next_actions"])

    def test_takeover_refuses_runner_mismatch(self) -> None:
        task_id, _paths, _claim = self._drifted_handoff(count=2)
        draft_path = self.root.parent / "review-draft.json"
        code, _review, stderr = self._review(task_id, "runner-b", draft_path)
        self.assertEqual(0, code, f"{stderr}\n{_review}")
        bundle = json.loads(draft_path.read_text(encoding="utf-8"))
        self._fill(draft_path, self._inherit_all(bundle))
        code, payload, stderr = self._claim_with_review(task_id, "runner-c", draft_path)
        self.assertEqual(3, code)
        self.assertEqual("workspace_handoff_review_runner_mismatch", payload["error_code"])

    def test_takeover_refuses_missing_and_duplicated_paths(self) -> None:
        task_id, paths, _claim = self._drifted_handoff(count=3)
        draft_path = self.root.parent / "review-draft.json"
        code, _review, stderr = self._review(task_id, "runner-b", draft_path)
        self.assertEqual(0, code, f"{stderr}\n{_review}")
        self._fill(
            draft_path,
            [
                {
                    "action": "inherit_for_triage",
                    "paths": paths[:2],
                    "reason": "Missing one path.",
                    "evidence_refs": ["diff-review:partial"],
                }
            ],
        )
        code, payload, stderr = self._claim_with_review(task_id, "runner-b", draft_path)
        self.assertEqual(3, code)
        self.assertEqual("workspace_handoff_review_incomplete", payload["error_code"])

        self._fill(
            draft_path,
            [
                {
                    "action": "inherit_for_triage",
                    "paths": [*paths, paths[0]],
                    "reason": "Duplicate path.",
                    "evidence_refs": ["diff-review:dup"],
                }
            ],
        )
        code, payload, stderr = self._claim_with_review(task_id, "runner-b", draft_path)
        self.assertEqual(3, code)
        self.assertEqual("workspace_handoff_review_incomplete", payload["error_code"])

    def test_takeover_refuses_block_decision(self) -> None:
        task_id, paths, _claim = self._drifted_handoff(count=2)
        draft_path = self.root.parent / "review-draft.json"
        code, _review, stderr = self._review(task_id, "runner-b", draft_path)
        self.assertEqual(0, code, f"{stderr}\n{_review}")
        self._fill(
            draft_path,
            [
                {
                    "action": "block",
                    "paths": paths,
                    "reason": "Origin of these changes cannot be established.",
                    "evidence_refs": ["scope-review:unknown-origin"],
                }
            ],
        )
        code, payload, stderr = self._claim_with_review(task_id, "runner-b", draft_path)
        self.assertEqual(3, code)
        self.assertEqual("workspace_handoff_review_blocked", payload["error_code"])

    def test_takeover_refuses_semantic_clean_on_still_dirty_path(self) -> None:
        task_id, paths, _claim = self._drifted_handoff(count=2)
        draft_path = self.root.parent / "review-draft.json"
        code, _review, stderr = self._review(task_id, "runner-b", draft_path)
        self.assertEqual(0, code, f"{stderr}\n{_review}")
        self._fill(
            draft_path,
            [
                {
                    "action": "semantic_clean",
                    "paths": paths,
                    "reason": "Assumed already committed.",
                    "evidence_refs": ["git:assumed-clean"],
                }
            ],
        )
        code, payload, stderr = self._claim_with_review(task_id, "runner-b", draft_path)
        self.assertEqual(3, code)
        self.assertEqual("workspace_handoff_review_conflict_mismatch", payload["error_code"])

    def test_takeover_failure_leaves_manifest_lease_and_generation_unchanged(self) -> None:
        task_id, paths, claim = self._drifted_handoff(count=2)
        draft_path = self.root.parent / "review-draft.json"
        code, _review, stderr = self._review(task_id, "runner-b", draft_path)
        self.assertEqual(0, code, f"{stderr}\n{_review}")
        code, before, stderr = self.run_json(
            ["continuation", "workspace", "status", str(self.root), "--task-id", task_id]
        )
        self.assertEqual(0, code, f"{stderr}\n{before}")
        self._fill(
            draft_path,
            [
                {
                    "action": "inherit_for_triage",
                    "paths": paths[:1],
                    "reason": "Incomplete.",
                    "evidence_refs": ["diff-review:partial"],
                }
            ],
        )
        code, payload, stderr = self._claim_with_review(task_id, "runner-b", draft_path)
        self.assertEqual(3, code)
        code, after, stderr = self.run_json(
            ["continuation", "workspace", "status", str(self.root), "--task-id", task_id]
        )
        self.assertEqual(0, code, f"{stderr}\n{after}")
        self.assertEqual(before["workspace"]["generation"], after["workspace"]["generation"])
        self.assertEqual(
            before["workspace"]["manifest_digest"], after["workspace"]["manifest_digest"]
        )
        self.assertEqual("absent", after["lease"]["state"])
        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", task_id]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertFalse(doctor["can_claim"])
        self.assertEqual(int(claim["generation"]), int(doctor["control"]["generation"]))

    def test_normal_claim_stays_blocked_and_review_refuses_active_owner(self) -> None:
        task_id, _paths, _claim = self._drifted_handoff(count=2)
        draft_path = self.root.parent / "review-draft.json"
        code, _review, stderr = self._review(task_id, "runner-b", draft_path)
        self.assertEqual(0, code, f"{stderr}\n{_review}")
        bundle = json.loads(draft_path.read_text(encoding="utf-8"))
        self._fill(draft_path, self._inherit_all(bundle))

        code, payload, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                task_id,
                "--runner-id",
                "runner-b",
            ]
        )
        self.assertEqual(3, code)
        self.assertEqual("continuation_not_claimable", payload["error_code"])

        code, taken, stderr = self._claim_with_review(task_id, "runner-b", draft_path)
        self.assertEqual(0, code, f"{stderr}\n{taken}")
        code, payload, stderr = self._review(task_id, "runner-b", draft_path)
        self.assertEqual(3, code)
        self.assertEqual("workspace_handoff_review_owner_present", payload["error_code"])

    def test_takeover_refuses_unaccepted_head_drift(self) -> None:
        task_id, _paths, _claim = self._drifted_handoff(count=2)
        draft_path = self.root.parent / "review-draft.json"
        code, _review, stderr = self._review(task_id, "runner-b", draft_path)
        self.assertEqual(0, code, f"{stderr}\n{_review}")
        bundle = json.loads(draft_path.read_text(encoding="utf-8"))
        self._fill(draft_path, self._inherit_all(bundle))
        (self.root / "committed.txt").write_text("committed\n", encoding="utf-8")
        self._git("add", "committed.txt")
        self._git("commit", "-m", "test: advance HEAD during review")
        code, payload, stderr = self._claim_with_review(task_id, "runner-b", draft_path)
        self.assertEqual(3, code)
        self.assertEqual("workspace_handoff_review_head_unaccepted", payload["error_code"])

        head = self._git("rev-parse", "HEAD").stdout.strip()
        code, taken, stderr = self._claim_with_review(
            task_id, "runner-b", draft_path, "--accept-head", head
        )
        self.assertEqual(0, code, f"{stderr}\n{taken}")
        self.assertEqual("accepted_for_triage", taken["handoff_takeover"]["status"])

    def test_takeover_refuses_unresolved_effects(self) -> None:
        task_id, _paths, _claim = self._drifted_handoff(count=1, effect_key="takeover-job")
        draft_path = self.root.parent / "review-draft.json"
        code, payload, stderr = self._review(task_id, "runner-b", draft_path)
        self.assertEqual(3, code)
        self.assertEqual("workspace_handoff_review_effects_unresolved", payload["error_code"])
        self.assertTrue(payload["next_actions"])

    def test_unchanged_dirty_handoff_still_claims_directly(self) -> None:
        task_id, paths, claim = self._drifted_handoff(count=2)
        for path_value in paths:
            (self.root / path_value).write_text(f"original {path_value}\n", encoding="utf-8")
        code, doctor, stderr = self.run_json(
            ["continuation", "doctor", str(self.root), "--task-id", task_id]
        )
        self.assertEqual(0, code, f"{stderr}\n{doctor}")
        self.assertTrue(doctor["can_claim"])
        self.assertNotIn("workspace_handoff_review_required", doctor["blocked_reasons"])
        code, taken, stderr = self.run_json(
            [
                "continuation",
                "claim",
                str(self.root),
                "--task-id",
                task_id,
                "--runner-id",
                "runner-b",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{taken}")
        self.assertGreater(int(taken["generation"]), int(claim["generation"]))
        self.assertNotIn("handoff_takeover", taken)
        self.assertEqual(sorted(paths), sorted(taken["workspace"]["task_owned_paths"]))

    def test_cleanup_only_reconcile_handoff_still_works(self) -> None:
        task_id, paths, _claim = self._drifted_handoff(count=1)
        (self.root / paths[0]).unlink()
        code, reconciled, stderr = self.run_json(
            [
                "continuation",
                "workspace",
                "reconcile-handoff",
                str(self.root),
                "--task-id",
                task_id,
                "--cleanup",
                paths[0],
                "--evidence-ref",
                "commit:reviewed-closeout",
                "--reason",
                "Reviewed closeout removed the temporary task WIP after handoff.",
            ]
        )
        self.assertEqual(0, code, f"{stderr}\n{reconciled}")
        self.assertEqual("workspace_handoff_reconciled", reconciled["status"])
        self.assertTrue(reconciled["can_claim"])


if __name__ == "__main__":
    unittest.main()
