"""Contract and behaviour tests for `acf clock now`."""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MINUTE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")


def known_instant(offset_hours: float, *, minute_offset: float = 0) -> datetime:
    return datetime(2026, 9, 20, 18, 6, 14, tzinfo=timezone(timedelta(hours=offset_hours, minutes=minute_offset)))


class ClockPayloadTests(unittest.TestCase):
    def test_payload_matches_minute_precision_for_a_known_instant(self):
        from ai_context_framework.commands.clock import clock_now_payload

        payload = clock_now_payload(known_instant(8))
        self.assertEqual(payload["command"], "clock now")
        self.assertEqual(payload["datetime"], "2026-09-20 18:06")
        self.assertEqual(payload["date"], "2026-09-20")
        self.assertEqual(payload["time"], "18:06")
        self.assertEqual(payload["utc_offset"], "+08:00")
        self.assertEqual(payload["iso_local"], "2026-09-20T18:06:14+08:00")
        self.assertEqual(payload["utc"], "2026-09-20T10:06:14Z")

    def test_payload_supports_negative_half_hour_offsets(self):
        from ai_context_framework.commands.clock import clock_now_payload

        payload = clock_now_payload(known_instant(-5, minute_offset=-30))
        self.assertEqual(payload["utc_offset"], "-05:30")
        self.assertEqual(payload["datetime"], "2026-09-20 18:06")
        self.assertEqual(payload["utc"], "2026-09-20T23:36:14Z")

    def test_default_instant_is_current_local_minute(self):
        from ai_context_framework.commands.clock import clock_now_payload

        payload = clock_now_payload()
        self.assertRegex(str(payload["datetime"]), MINUTE_PATTERN)
        self.assertRegex(str(payload["utc_offset"]), r"^[+-]\d{2}:\d{2}$")


class ClockCommandTests(unittest.TestCase):
    def test_human_output_is_the_bare_minute_stamp(self):
        from ai_context_framework.commands import clock as clock_commands

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = clock_commands.clock_now_command(Namespace(json=False), now=known_instant(8))
        self.assertEqual(exit_code, 0)
        self.assertEqual(buffer.getvalue().strip(), "2026-09-20 18:06")

    def test_json_output_satisfies_the_ai_facing_contract(self):
        from ai_context_framework.commands import clock as clock_commands

        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = clock_commands.clock_now_command(Namespace(json=True), now=known_instant(8))
        payload = json.loads(buffer.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["schema_version"], 1)
        self.assertIs(payload["ok"], True)
        self.assertIsNone(payload["error_code"])
        self.assertIsInstance(payload["next_actions"], list)
        self.assertEqual(payload["command"], "clock now")
        self.assertEqual(payload["datetime"], "2026-09-20 18:06")

    def test_runtime_binds_the_command_handler(self):
        from ai_context_framework import runtime
        from ai_context_framework.commands import clock as clock_commands

        args = runtime.build_parser().parse_args(["clock", "now"])
        self.assertIs(args.func, clock_commands.clock_now_command)

    def test_runs_in_a_directory_without_a_context_root(self):
        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        with tempfile.TemporaryDirectory(prefix="acf-clock-") as tmp:
            env["ACF_HOME"] = str(Path(tmp) / "acf-home")
            completed = subprocess.run(
                [sys.executable, str(ROOT / "acf.py"), "clock", "now"],
                cwd=tmp,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertRegex(completed.stdout.strip(), MINUTE_PATTERN)


if __name__ == "__main__":
    unittest.main()
