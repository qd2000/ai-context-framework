from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
