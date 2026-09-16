from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

from ai_context_framework import json_contract, runtime


class CliOwnerBoundaryTests(unittest.TestCase):
    def test_shared_parser_remains_available_from_runtime(self) -> None:
        self.assertIs(runtime.SafeArgumentParser, json_contract.SafeArgumentParser)
        self.assertIsInstance(runtime.build_parser(), json_contract.SafeArgumentParser)

    def test_retired_options_refuse_without_echo_in_json_or_text(self) -> None:
        placeholder = "NONAUTHORITY_PLACEHOLDER"
        for command in (("assert-owner",), ("effect", "prepare")):
            for option in ("--fence-token", "--lease-id", "--generation"):
                expected_error = (
                    "legacy_owner_transport_refused"
                    if option == "--fence-token" else "legacy_owner_assertion_refused"
                )
                for equals in (False, True):
                    for as_json in (False, True):
                        with self.subTest(command=command, option=option, equals=equals, as_json=as_json):
                            flags = [f"{option}={placeholder}"] if equals else [option, placeholder]
                            args = ["continuation", *command, *flags, *(["--json"] if as_json else [])]
                            stdout, stderr = io.StringIO(), io.StringIO()
                            with redirect_stdout(stdout), redirect_stderr(stderr):
                                code = runtime.main(args)
                            self.assertEqual(3, code)
                            self.assertNotIn(placeholder, stdout.getvalue() + stderr.getvalue())
                            if as_json:
                                payload = json.loads(stdout.getvalue())
                                self.assertFalse(payload["ok"])
                                self.assertEqual(expected_error, payload["error_code"])
                            else:
                                self.assertIn("ERROR:", stderr.getvalue())

    def test_unrelated_options_and_public_metadata_are_not_retired(self) -> None:
        arguments = ["--generation-count", "--lease-id-suffix", "--fence-token-file",
                     "generation", "page-2", "MIT", "8" * 64]
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = json_contract.refuse_retired_owner_arguments(arguments)
        self.assertIsNone(result)
        self.assertEqual("", stdout.getvalue() + stderr.getvalue())

    def test_first_retired_option_keeps_original_error_precedence(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = json_contract.refuse_retired_owner_arguments(
                ["continuation", "assert-owner", "--generation", "NOT_AUTHORITY",
                 "--fence-token", "ALSO_NOT_AUTHORITY", "--json"]
            )
        self.assertEqual(3, code)
        self.assertEqual("legacy_owner_assertion_refused", json.loads(stdout.getvalue())["error_code"])
        self.assertNotIn("NOT_AUTHORITY", stdout.getvalue())

    def test_runtime_detaches_child_tail_before_retired_boundary(self) -> None:
        child = ["python", "fixture.py", "--generation", "7", "--lease-id", "public-child-metadata"]
        observed = []

        def observe(args):
            observed.append(list(args.child_argv))
            return 0

        # Exercise runtime's real splitter/parser without claiming or spawning.
        with patch.object(runtime, "run_with_context_lock", side_effect=observe), \
             patch.object(runtime, "record_usage_event"), \
             patch.object(runtime.continuation_coordination_commands, "emit_pending_challenge_probe"):
            code = runtime.main([
                "continuation", "execution", "run", ".", "--task-id", "R2TEST",
                "--owner-file", "opaque-local-handle", "--key", "boundary-once", "--", *child,
            ])
        self.assertEqual(0, code)
        self.assertEqual([child], observed)

    def test_shared_parser_error_redacts_explicit_credential_assignment(self) -> None:
        parser = json_contract.SafeArgumentParser(prog="acf")
        stderr = io.StringIO()
        with redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            parser.error("api_key=synthetic-parser-canary")
        self.assertEqual(2, raised.exception.code)
        self.assertNotIn("synthetic-parser-canary", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
