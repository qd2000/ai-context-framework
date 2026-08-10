from __future__ import annotations

import json
import os
import socket
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ai_context_framework.git_support import atomic_write_json, lock_path
from ai_context_framework.worktree_merge_contracts import MergeRetryPolicy
from ai_context_framework.worktree_retry import (
    acquire_lock_with_wait,
    refresh_lock,
    release_owned_lock,
    retry_delay,
)


class WorktreeRetryTests(unittest.TestCase):
    def test_retry_delay_is_bounded_and_deterministic(self):
        policy = MergeRetryPolicy(
            initial_delay_seconds=0.5,
            max_delay_seconds=4.0,
            jitter_ratio=0.2,
        )
        values = [retry_delay(policy, index, seed="operation") for index in range(8)]
        self.assertEqual(values, [retry_delay(policy, index, seed="operation") for index in range(8)])
        self.assertTrue(all(value >= 0 for value in values))
        self.assertLessEqual(max(values), 4.8)

    def test_lock_acquire_refresh_and_owned_release(self):
        with tempfile.TemporaryDirectory() as root:
            common = Path(root)
            policy = MergeRetryPolicy(lock_wait_timeout_seconds=0, jitter_ratio=0)
            lease, waits = acquire_lock_with_wait(
                common,
                key="primary-promotion",
                operation_id="op-1",
                command="worktree.merge",
                target_key="WS001",
                policy=policy,
                timeout_seconds=0,
            )
            self.assertEqual(waits, 0)
            refresh_lock(lease, state="PROMOTING")
            payload = json.loads(lease.path.read_text(encoding="utf-8"))
            self.assertEqual(payload["state"], "PROMOTING")
            self.assertTrue(release_owned_lock(lease))
            self.assertFalse(lease.path.exists())

    def test_live_lock_times_out_without_breaking_it(self):
        with tempfile.TemporaryDirectory() as root:
            common = Path(root)
            path = lock_path(common, "primary-promotion")
            atomic_write_json(
                path,
                {
                    "schema_version": "acf.git_lock.v2",
                    "operation_id": "holder",
                    "pid": os.getpid(),
                    "hostname": socket.gethostname(),
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "heartbeat_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            policy = MergeRetryPolicy(
                lock_wait_timeout_seconds=0,
                initial_delay_seconds=0.01,
                max_delay_seconds=0.01,
                jitter_ratio=0,
            )
            with self.assertRaisesRegex(SystemExit, "worktree_operation_lock_timeout"):
                acquire_lock_with_wait(
                    common,
                    key="primary-promotion",
                    operation_id="waiter",
                    command="worktree.merge",
                    target_key="WS002",
                    policy=policy,
                    timeout_seconds=0,
                )
            self.assertTrue(path.is_file())

    def test_dead_same_host_stale_lock_is_quarantined(self):
        with tempfile.TemporaryDirectory() as root:
            common = Path(root)
            path = lock_path(common, "primary-promotion")
            old = datetime.now(timezone.utc) - timedelta(hours=1)
            atomic_write_json(
                path,
                {
                    "schema_version": "acf.git_lock.v2",
                    "operation_id": "dead-holder",
                    "pid": 2147483000,
                    "hostname": socket.gethostname(),
                    "created_at": old.isoformat(),
                    "heartbeat_at": old.isoformat(),
                },
            )
            policy = MergeRetryPolicy(
                lock_wait_timeout_seconds=0,
                initial_delay_seconds=0.01,
                max_delay_seconds=0.01,
                jitter_ratio=0,
            )
            lease, _waits = acquire_lock_with_wait(
                common,
                key="primary-promotion",
                operation_id="new-holder",
                command="worktree.merge",
                target_key="WS001",
                policy=policy,
                timeout_seconds=0,
                stale_ttl_seconds=1,
            )
            stale = list((common / "acf" / "stale-locks").glob("*.lock"))
            self.assertEqual(len(stale), 1)
            self.assertEqual(json.loads(lease.path.read_text(encoding="utf-8"))["operation_id"], "new-holder")
            release_owned_lock(lease)


if __name__ == "__main__":
    unittest.main()
