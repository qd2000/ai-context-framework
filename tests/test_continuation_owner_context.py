from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_context_framework import continuation_owner_context


class ContinuationOwnerContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.root = Path(self._temp.name).resolve()
        self.task_dir = self.root / "task"
        self.task_dir.mkdir()

    def tearDown(self) -> None:
        self._temp.cleanup()

    def create_context(self):
        return continuation_owner_context.create_owner_context(
            self.task_dir,
            workspace_root=self.root,
            task_id="WS900",
            lease_id="lease-1",
            generation=1,
            runner_id="runner-a",
            credential="a" * 64,
            created_at="2026-09-14T00:00:00Z",
        )

    def load_context(self, handle: Path):
        return continuation_owner_context.load_owner_context(
            handle,
            self.task_dir,
            workspace_root=self.root,
            task_id="WS900",
        )

    def test_owner_context_regular_file_loads_from_single_link(self) -> None:
        context = self.create_context()
        loaded = self.load_context(context.handle)
        self.assertEqual(context.context_id, loaded.context_id)
        self.assertEqual(1, context.handle.stat().st_nlink)

    def test_owner_context_handle_symlink_is_refused(self) -> None:
        context = self.create_context()
        target = self.root / "moved-owner-context.json"
        context.handle.replace(target)
        try:
            os.symlink(target, context.handle)
        except OSError as exc:
            self.skipTest(f"symlink creation unavailable: {exc}")
        with self.assertRaises(continuation_owner_context.OwnerContextError) as raised:
            self.load_context(context.handle)
        self.assertEqual("owner_context_binding_mismatch", raised.exception.code)

    def test_owner_context_hardlink_is_refused(self) -> None:
        context = self.create_context()
        second_link = context.handle.with_name("hardlink-copy.json")
        try:
            os.link(context.handle, second_link)
        except OSError as exc:
            self.skipTest(f"hardlink creation unavailable: {exc}")
        with self.assertRaises(continuation_owner_context.OwnerContextError) as raised:
            self.load_context(context.handle)
        self.assertEqual("owner_context_binding_mismatch", raised.exception.code)

    @unittest.skipIf(os.name == "nt", "POSIX owner/mode validation")
    def test_owner_context_relaxed_permissions_are_refused(self) -> None:
        context = self.create_context()
        os.chmod(context.handle, 0o644)
        with self.assertRaises(continuation_owner_context.OwnerContextError) as raised:
            self.load_context(context.handle)
        self.assertEqual("owner_context_binding_mismatch", raised.exception.code)

    @unittest.skipIf(os.name == "nt", "POSIX owner/mode validation")
    def test_owner_context_directory_relaxed_permissions_are_refused(self) -> None:
        context = self.create_context()
        os.chmod(context.handle.parent, 0o755)
        with self.assertRaises(continuation_owner_context.OwnerContextError) as raised:
            self.load_context(context.handle)
        self.assertEqual("owner_context_unavailable", raised.exception.code)

    def test_owner_context_parent_link_or_reparse_is_refused_before_create_or_enumerate(self) -> None:
        linked_task = self.root / "linked-task"
        linked_task.mkdir()
        external = self.root / "external-owner-contexts"
        external.mkdir()
        capability_dir = linked_task / continuation_owner_context.OWNER_CONTEXT_DIRECTORY

        if os.name == "nt":
            result = subprocess.run(
                ["cmd.exe", "/d", "/c", "mklink", "/J", str(capability_dir), str(external)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                self.skipTest(f"junction creation unavailable: {result.stderr or result.stdout}")
        else:
            os.symlink(external, capability_dir, target_is_directory=True)

        sentinel = external / "ctx-00000000000000000000000000000000.json"
        sentinel.write_text("do not touch", encoding="utf-8")
        with self.assertRaises(continuation_owner_context.OwnerContextError) as raised:
            continuation_owner_context.create_owner_context(
                linked_task,
                workspace_root=self.root,
                task_id="WS900",
                lease_id="lease-1",
                generation=1,
                runner_id="runner-a",
                credential="a" * 64,
                created_at="2026-09-14T00:00:00Z",
            )
        self.assertEqual("owner_context_binding_mismatch", raised.exception.code)
        self.assertEqual(
            0,
            continuation_owner_context.revoke_other_owner_contexts(
                linked_task,
                keep=capability_dir / "ctx-keep.json",
            ),
        )
        self.assertEqual("do not touch", sentinel.read_text(encoding="utf-8"))

    def test_legacy_token_cleanup_failure_rolls_back_new_owner_context(self) -> None:
        credential = "a" * 64
        legacy_file = self.root / "legacy-owner.token"
        legacy_file.write_text(credential + "\n", encoding="utf-8")
        if os.name != "nt":
            os.chmod(legacy_file, 0o600)
        original_unlink = Path.unlink

        def selective_unlink(path: Path, *args, **kwargs):
            if path == legacy_file:
                raise OSError("simulated legacy cleanup failure")
            return original_unlink(path, *args, **kwargs)

        with patch.object(Path, "unlink", autospec=True, side_effect=selective_unlink):
            with self.assertRaises(continuation_owner_context.OwnerContextError) as raised:
                continuation_owner_context.migrate_legacy_token_file(
                    self.task_dir,
                    legacy_token_file=legacy_file,
                    workspace_root=self.root,
                    task_id="WS900",
                    lease_id="lease-1",
                    generation=1,
                    runner_id="runner-a",
                    credential_verifier=hashlib.sha256(credential.encode("utf-8")).hexdigest(),
                    created_at="2026-09-14T00:00:00Z",
                )
        self.assertEqual("owner_context_migration_cleanup_failed", raised.exception.code)
        self.assertTrue(legacy_file.exists())
        owner_dir = self.task_dir / continuation_owner_context.OWNER_CONTEXT_DIRECTORY
        self.assertEqual([], list(owner_dir.glob("ctx-*.json")) if owner_dir.exists() else [])


if __name__ == "__main__":
    unittest.main()
