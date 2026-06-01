# Workstream Ready Human Approval Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent agents from marking a Workstream `ReadyToMerge` unless a human explicitly approves the transition.

**Architecture:** Add a CLI-only hard gate to `acf workstream ready`: the command requires `--human-approved` before running the existing state, merge-request, stage, and check-after validations. This keeps the data model unchanged and avoids giving agents a frontmatter field they could edit themselves.

**Tech Stack:** Python standard library, argparse CLI, unittest test suite.

**Status:** Completed.

---

### Task 1: Add Red Tests for Human Approval Gate

**Files:**
- Modify: `tests/test_cli.py`

- [x] **Step 1: Add a failing test that ready without approval is rejected**

Add this test near the existing workstream ready tests:

```python
    def test_workstream_ready_requires_human_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ctx"
            self.init_minimal_workstream_context(target)
            self.add_workstream(target, "WS002")
            self.assertEqual(self.run_cli(["workstream", "set", "WS002", str(target), "--status", "Active"]), 0)
            self.assertEqual(
                self.run_cli(
                    [
                        "workstream",
                        "merge-request",
                        "WS002",
                        str(target),
                        "--target",
                        "active/Context.md",
                        "--summary",
                        "No authority change required.",
                        "--verification",
                        "Unit test fixture.",
                    ]
                ),
                0,
            )

            exit_code, stdout, _stderr = self.run_cli_output(
                ["workstream", "ready", "WS002", str(target), "--json"]
            )

            self.assertNotEqual(exit_code, 0)
            payload = json.loads(stdout)
            self.assert_failure_json_contract(payload, "workstream_human_approval_required", "workstream")
            self.assertIn("--human-approved", payload["message"])
            self.assertIn("--human-approved", " ".join(payload["next_actions"]))

            detail_text = (target / "active" / "workstreams" / "WS002.md").read_text(encoding="utf-8")
            self.assertIn("status: Active", detail_text)
```

- [x] **Step 2: Add a passing-path expectation using the new flag**

Update existing ready success calls from:

```python
["workstream", "ready", "WS002", str(target), "--json"]
```

to:

```python
["workstream", "ready", "WS002", str(target), "--human-approved", "--json"]
```

For non-JSON helper calls, update from:

```python
["workstream", "ready", workstream_id, str(target)]
```

to:

```python
["workstream", "ready", workstream_id, str(target), "--human-approved"]
```

- [x] **Step 3: Verify red**

Run: `uv run python -m unittest tests.test_cli.CliTests.test_workstream_ready_requires_human_approval -v`

Expected: FAIL because `workstream_human_approval_required` does not exist yet or ready succeeds without requiring `--human-approved`.

### Task 2: Implement Minimal CLI Gate

**Files:**
- Modify: `acf.py`

- [x] **Step 1: Add error guidance**

In `next_actions_for_error`, add:

```python
    if error_code == "workstream_human_approval_required":
        return ["Ask the human owner to confirm completion, then rerun with `--human-approved`."]
```

- [x] **Step 2: Enforce the gate before existing ready checks**

At the start of `workstream_ready_command`, after `detail` and `current_status` are loaded, add:

```python
    if not getattr(args, "human_approved", False):
        raise SystemExit(f"workstream_human_approval_required: {args.id} ready requires --human-approved")
```

- [x] **Step 3: Add argparse flag**

In the `workstream ready` parser setup, add before `add_write_arguments(workstream_ready_parser)`:

```python
    workstream_ready_parser.add_argument(
        "--human-approved",
        action="store_true",
        help="confirm that a human explicitly approved marking this Workstream ReadyToMerge",
    )
```

- [x] **Step 4: Verify green for targeted test**

Run: `uv run python -m unittest tests.test_cli.CliTests.test_workstream_ready_requires_human_approval -v`

Expected: PASS.

### Task 3: Update Existing Ready Tests and Full Verification

**Files:**
- Modify: `tests/test_cli.py`

- [x] **Step 1: Update all intentional ready-success calls**

Every test path that expects `ReadyToMerge` success must pass `--human-approved`. Tests that validate missing merge request or invalid transition may omit `--human-approved` only if they are intentionally checking the new human approval gate first; otherwise include the flag to reach the older validation.

- [x] **Step 2: Run CLI test suite**

Run: `uv run python -m unittest tests.test_cli -v`

Expected: PASS.

- [x] **Step 3: Run repository-required checks**

Run: `uv run acf check template`

Expected: PASS.

Run: `uv run acf check --strict`

Expected: PASS.

Run: `uv run python -m unittest`

Expected: PASS.

---

### Self-Review

- Spec coverage: The plan implements default-on hard gate and the selected `--human-approved` release mechanism.
- Placeholder scan: No placeholders remain.
- Scope check: One CLI behavior change, no data model migration or template rewrite required.
