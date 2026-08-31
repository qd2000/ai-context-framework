import json
import os
import tempfile
import unittest
from pathlib import Path

from ai_context_framework import closeout_authorization as auth


class CloseoutAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self._old_acf_home = os.environ.get("ACF_HOME")
        self._acf_home = tempfile.TemporaryDirectory()
        os.environ["ACF_HOME"] = self._acf_home.name
        self._project = tempfile.TemporaryDirectory()
        self.project_root = Path(self._project.name)
        self.context_root = self.project_root / "docs" / "ai"
        (self.context_root / "active" / "workstreams").mkdir(parents=True)
        self._write_workstream("WS001", workstream_type="Task", goal="Initial goal")
        self._write_workstream("WS002", workstream_type="Task", goal="Second goal")

    def tearDown(self):
        self._project.cleanup()
        if self._old_acf_home is None:
            os.environ.pop("ACF_HOME", None)
        else:
            os.environ["ACF_HOME"] = self._old_acf_home
        self._acf_home.cleanup()

    def _write_workstream(self, workstream_id, *, workstream_type="Task", goal="Goal"):
        path = self.context_root / "active" / "workstreams" / f"{workstream_id}.md"
        path.write_text(
            "---\n"
            f"id: {workstream_id}\n"
            f"type: {workstream_type}\n"
            "status: Active\n"
            f"title: {workstream_id}\n"
            "owner: tester\n"
            "---\n\n"
            "## Goal\n\n"
            f"{goal}\n\n"
            "## Activity Log\n\n"
            "- volatile observation\n",
            encoding="utf-8",
        )
        return path

    def _identity(self, workstream_id="WS001", *, action=None):
        return auth.workstream_identity(self.context_root, workstream_id, action=action)

    def _resolve(self, workstream_id="WS001", action="ready"):
        identity = self._identity(workstream_id, action=action)
        return auth.resolve_authorization(
            self.project_root,
            workstream_id=workstream_id,
            workstream_type=identity["type"],
            workstream_class_name=identity["class"],
            action=action,
            workstream_fingerprint=identity["fingerprint"],
        )

    def _policy(self, **overrides):
        values = {
            "decision": "auto",
            "actions": ["ready", "merge", "done", "archive"],
            "actor": "human-owner",
            "authority_source": "user-authority:test",
            "evidence_refs": ["evidence:test-policy"],
            "workstream_class_name": "ordinary",
        }
        values.update(overrides)
        return auth.record_policy(self.project_root, **values)

    def _approval(self, *, workstream_id="WS001", action="ready", **overrides):
        identity = self._identity(workstream_id, action=action)
        values = {
            "workstream_id": workstream_id,
            "workstream_type": identity["type"],
            "workstream_class_name": identity["class"],
            "action": action,
            "workstream_fingerprint": identity["fingerprint"],
            "actor": "human-owner",
            "authority_source": "user-authority:test",
            "evidence_refs": ["evidence:test-approval"],
        }
        values.update(overrides)
        return auth.record_approval(self.project_root, **values)

    def test_missing_ledger_fails_closed(self):
        resolution = self._resolve()
        self.assertFalse(resolution["authorized"])
        self.assertEqual(resolution["disposition"], "approval_required")
        self.assertIsNone(resolution["effective_policy"])
        self.assertIsNone(resolution["approval"])

    def test_long_lived_ordinary_policy_auto_authorizes_matching_actions(self):
        written = self._policy()
        resolution = self._resolve(action="done")
        self.assertTrue(resolution["authorized"])
        self.assertEqual(resolution["disposition"], "auto_authorized")
        self.assertEqual(resolution["effective_policy"]["record_id"], written["event"]["record_id"])

    def test_workstream_specific_manual_policy_overrides_broad_auto_policy(self):
        self._policy()
        manual = self._policy(
            decision="manual",
            actions=["ready"],
            workstream_id="WS001",
            workstream_class_name=None,
            evidence_refs=["evidence:manual-override"],
        )
        resolution = self._resolve(action="ready")
        self.assertFalse(resolution["authorized"])
        self.assertEqual(resolution["disposition"], "approval_required")
        self.assertEqual(resolution["effective_policy"]["record_id"], manual["event"]["record_id"])

        approval = self._approval(action="ready")
        approved = self._resolve(action="ready")
        self.assertTrue(approved["authorized"])
        self.assertEqual(approved["disposition"], "human_approved")
        self.assertEqual(approved["approval"]["record_id"], approval["event"]["record_id"])
        self.assertEqual(approved["approval"]["workstream_type"], "Task")
        self.assertEqual(approved["approval"]["workstream_class"], "ordinary")

    def test_approval_does_not_transfer_to_other_action_or_workstream(self):
        self._approval(workstream_id="WS001", action="ready")
        self.assertEqual(self._resolve("WS001", "ready")["disposition"], "human_approved")
        self.assertEqual(self._resolve("WS001", "done")["disposition"], "approval_required")
        self.assertEqual(self._resolve("WS002", "ready")["disposition"], "approval_required")

    def test_revoked_and_superseded_policy_no_longer_authorizes(self):
        first = self._policy(actions=["ready"])
        auth.revoke_record(
            self.project_root,
            record_id=first["event"]["record_id"],
            actor="human-owner",
            authority_source="user-authority:revoke",
            evidence_refs=["evidence:revoke"],
        )
        self.assertEqual(self._resolve(action="ready")["disposition"], "approval_required")

        second = self._policy(actions=["ready"])
        third = self._policy(
            decision="manual",
            actions=["ready"],
            supersedes=[second["event"]["record_id"]],
            evidence_refs=["evidence:supersede"],
        )
        resolution = self._resolve(action="ready")
        self.assertEqual(resolution["disposition"], "approval_required")
        self.assertEqual(resolution["effective_policy"]["record_id"], third["event"]["record_id"])

    def test_stale_approval_is_rejected_after_material_authority_change(self):
        approval = self._approval(action="ready")
        before = self._resolve(action="ready")
        self.assertEqual(before["disposition"], "human_approved")

        self._write_workstream("WS001", workstream_type="Task", goal="Materially changed goal")
        after = self._resolve(action="ready")
        self.assertEqual(after["disposition"], "approval_required")
        self.assertIn(approval["event"]["record_id"], after["stale_approval_record_ids"])

    def test_activity_log_only_change_does_not_stale_approval(self):
        self._approval(action="ready")
        path = self.context_root / "active" / "workstreams" / "WS001.md"
        original = path.read_text(encoding="utf-8")
        path.write_text(original + "- another volatile observation\n", encoding="utf-8")
        self.assertEqual(self._resolve(action="ready")["disposition"], "human_approved")

    def test_merge_approval_survives_deterministic_merge_start_transition(self):
        path = self._write_workstream("WS001", workstream_type="Maintenance", goal="Initial goal")
        ready_text = path.read_text(encoding="utf-8").replace(
            "status: Active\n",
            "status: ReadyToMerge\n",
        ).replace(
            "## Activity Log\n",
            "## 当前发现\n\nReady to merge.\n\n## Activity Log\n",
        )
        path.write_text(ready_text, encoding="utf-8")

        approval = self._approval(action="merge")
        self.assertEqual(self._resolve(action="merge")["disposition"], "human_approved")

        merging_text = path.read_text(encoding="utf-8").replace(
            "status: ReadyToMerge\n",
            "status: Merging\n",
        ).replace(
            "Ready to merge.",
            "Merge execution started.",
        )
        path.write_text(merging_text, encoding="utf-8")
        during_merge = self._resolve(action="merge")
        self.assertEqual(during_merge["disposition"], "human_approved")
        self.assertEqual(during_merge["approval"]["record_id"], approval["event"]["record_id"])

        path.write_text(
            path.read_text(encoding="utf-8").replace("Initial goal", "Materially changed goal"),
            encoding="utf-8",
        )
        after_material_change = self._resolve(action="merge")
        self.assertEqual(after_material_change["disposition"], "approval_required")
        self.assertIn(
            approval["event"]["record_id"],
            after_material_change["stale_approval_record_ids"],
        )

    def test_explicit_deny_policy_blocks_even_when_approval_exists(self):
        self._approval(action="ready")
        deny = self._policy(
            decision="deny",
            actions=["ready"],
            workstream_id="WS001",
            workstream_class_name=None,
            evidence_refs=["evidence:deny"],
        )
        resolution = self._resolve(action="ready")
        self.assertFalse(resolution["authorized"])
        self.assertEqual(resolution["disposition"], "denied")
        self.assertEqual(resolution["effective_policy"]["record_id"], deny["event"]["record_id"])

    def test_unknown_schema_requires_explicit_migration_instead_of_guessing(self):
        path = auth.ledger_path(self.project_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"schema_version":"legacy","revision":0,"events":[]}', encoding="utf-8")
        with self.assertRaises(auth.CloseoutAuthorizationError) as ctx:
            auth.load_ledger(self.project_root)
        self.assertEqual(ctx.exception.code, "closeout_authorization_migration_required")

    def test_tampered_ledger_revision_fails_closed(self):
        self._policy(actions=["ready"])
        path = auth.ledger_path(self.project_root)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["revision"] += 1
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(auth.CloseoutAuthorizationError) as ctx:
            auth.load_ledger(self.project_root)
        self.assertEqual(ctx.exception.code, "closeout_authorization_ledger_invalid")

    def test_tampered_policy_payload_fails_closed(self):
        self._policy(actions=["ready"])
        path = auth.ledger_path(self.project_root)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["events"][0]["actions"] = ["ready", "not-a-closeout-action"]
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(auth.CloseoutAuthorizationError) as ctx:
            auth.load_ledger(self.project_root)
        self.assertEqual(ctx.exception.code, "closeout_authorization_ledger_invalid")

    def test_tampered_revocation_target_fails_closed(self):
        first = self._policy(actions=["ready"])
        auth.revoke_record(
            self.project_root,
            record_id=first["event"]["record_id"],
            actor="human-owner",
            authority_source="user-authority:revoke",
            evidence_refs=["evidence:revoke"],
        )
        path = auth.ledger_path(self.project_root)
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["events"][1]["target_record_id"] = "cap-does-not-exist"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(auth.CloseoutAuthorizationError) as ctx:
            auth.load_ledger(self.project_root)
        self.assertEqual(ctx.exception.code, "closeout_authorization_ledger_invalid")


if __name__ == "__main__":
    unittest.main()
