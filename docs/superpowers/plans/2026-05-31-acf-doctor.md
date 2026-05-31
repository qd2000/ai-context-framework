# ACF Doctor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Status:** Completed in `v0.0.3.47`; this file is retained as the historical implementation plan.

**Goal:** Build `acf doctor` as an AI-friendly and human-friendly context health command that detects semantic drift and applies safe mechanical repairs.

**Architecture:** Add a doctor function cluster to `acf.py` that reuses existing Markdown/table/front-matter helpers and emits the existing JSON contract. The first implementation supports single-project and multi-project read-only diagnosis plus safe repair for task focus and terminal Workstream authority scope cleanup; evidence findings are reported but do not rewrite semantic authority files.

**Tech Stack:** Python standard library, argparse CLI, unittest test suite.

---

### Task 1: Add Doctor Design Documentation

**Files:**
- Create: `docs/ai/reference/Doctor_Reconcile_Design.md`
- Create: `docs/superpowers/plans/2026-05-31-acf-doctor.md`

- [x] **Step 1: Write the design spec**

Create `docs/ai/reference/Doctor_Reconcile_Design.md` with sections for status, goals, non-goals, command shape, architecture, finding schema, first rule set, three-project acceptance samples, implementation boundaries, and tests.

- [x] **Step 2: Write this implementation plan**

Create `docs/superpowers/plans/2026-05-31-acf-doctor.md` with concrete TDD tasks and verification commands.

- [x] **Step 3: Check document links**

Run: `uv run acf check docs/ai --strict --json`

Expected: exit 0 with no check errors.

### Task 2: Add Red Tests for Doctor Read-Only Findings

**Files:**
- Modify: `tests/test_cli.py`

- [x] **Step 1: Add a test for task focus pointing to Done**

Add a test that initializes a minimal context, creates a plan where `T001` is `Done` and `## 当前焦点` is `T001`, runs `acf doctor --json`, and asserts a finding with code `plan_focus_points_to_done_task`.

- [x] **Step 2: Add a test for Current_Task pointing to a Done task**

Add a test that starts `T001`, marks the task row Done while leaving Current_Task Active, runs `acf doctor --json`, and asserts a finding with code `current_task_points_to_done_task`.

- [x] **Step 3: Add a test for multi-project doctor**

Create two temporary contexts, make one clean and one with done focus, run `acf doctor --projects <ctx1> <ctx2> --json`, and assert each project has an independent result.

- [x] **Step 4: Verify red**

Run: `uv run python -m unittest tests.test_cli.CliTests.test_doctor_reports_plan_focus_points_to_done_task tests.test_cli.CliTests.test_doctor_reports_current_task_points_to_done_task tests.test_cli.CliTests.test_doctor_projects_reports_each_context -v`

Expected: FAIL because `doctor` is not registered.

### Task 3: Implement Doctor Read-Only Command

**Files:**
- Modify: `acf.py`

- [x] **Step 1: Add doctor data builders**

Add helper functions:

```python
def doctor_finding(code, severity, domain, message, authority, locations, evidence, repair_mode, safe_to_apply, suggested_actions):
    return {
        "code": code,
        "severity": severity,
        "domain": domain,
        "message": message,
        "authority": authority,
        "locations": list(locations),
        "evidence": list(evidence),
        "repair_mode": repair_mode,
        "safe_to_apply": safe_to_apply,
        "suggested_actions": list(suggested_actions),
    }
```

- [x] **Step 2: Add task lifecycle collectors**

Implement collectors that read `active/Task_Plan.md` and `active/Current_Task.md`, using existing `read_task_rows()`, `extract_heading_value()`, and `extract_current_task_status()`.

- [x] **Step 3: Add command payload**

Implement `doctor_single_context_payload()` and `doctor_command()` with top-level fields `schema_version`, `command`, `ok`, `context`, `profile`, `strict`, `fix`, `changed_files`, `summary`, `findings`, `check`, `error_code`, and `next_actions`.

- [x] **Step 4: Register parser**

Add `doctor` to `build_parser()` with path, `--projects`, `--strict`, `--fix`, `--today`, `--check-after`, `--dry-run`, and `--json`.

- [x] **Step 5: Verify green for read-only tests**

Run the three doctor read-only tests from Task 2.

Expected: PASS.

### Task 4: Add Red Tests for Safe Fixes

**Files:**
- Modify: `tests/test_cli.py`

- [x] **Step 1: Add a safe fix test for plan focus**

Test that `acf doctor <ctx> --fix safe --json` changes `## 当前焦点` from a Done task to `无。` when no next task exists, and reports `changed_files`.

- [x] **Step 2: Add a dry-run safe fix test**

Test that `acf doctor <ctx> --fix safe --dry-run --json` reports the same planned `changed_files` but does not modify the file.

- [x] **Step 3: Add a safe fix test for terminal Workstream assigned authority**

Create a workstream with `status: Done`, `merge_resolution: merged`, and `write_scope` containing `assigned: active/Context.md`; run `acf doctor --fix safe --json`; assert the assigned authority entry is removed and a finding with code `terminal_workstream_assigned_authority` appears.

- [x] **Step 4: Verify red**

Run the new safe fix tests.

Expected: FAIL because fix execution is not implemented.

### Task 5: Implement Safe Fix Executor

**Files:**
- Modify: `acf.py`

- [x] **Step 1: Add repair planning**

Add repair plans for `plan_focus_points_to_done_task` and `terminal_workstream_assigned_authority`.

- [x] **Step 2: Implement plan focus fix**

If current focus points to a terminal task, set focus to `无。` only when `recommended_next_task(rows)` returns no unfinished task. If another task can be recommended, keep the current focus unchanged and report a `draft_only` finding.

- [x] **Step 3: Implement Workstream authority cleanup**

For terminal Workstreams, remove `assigned:` entries whose normalized path is an authority path. Preserve non-authority assigned entries and all other scope entries.

- [x] **Step 4: Wire changed_files and dry-run**

In dry-run, report planned files without writing. In non-dry-run, write files and optionally run `maybe_check_after()`.

- [x] **Step 5: Verify green for safe fix tests**

Run all doctor tests.

Expected: PASS.

### Task 6: Add Evidence Findings and Multi-Project Acceptance Coverage

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `acf.py`

- [x] **Step 1: Add red tests for generic data source evidence findings**

Create fixture files and context references for two generic duplicate paths, for example `data/source.csv` and `thesis_ch4/data/source.csv`; assert `duplicate_data_hash_confirmed` when both exist with the same SHA256. Create another declared pair where one side is missing and assert `declared_duplicate_missing`.

- [x] **Step 2: Implement conservative source scanning**

Scan `active/Context.md`, `reference/Sources_Index.md`, and `reference/Decisions_Index.md` for local path pairs explicitly mentioned in the same paragraph or table row. If both paths exist with equal SHA256, emit `duplicate_data_hash_confirmed`. If a path is mentioned but missing, emit `declared_duplicate_missing`. Do not write semantic files in this task.

- [x] **Step 3: Verify evidence tests**

Run the new evidence tests.

Expected: PASS.

### Task 7: Documentation Sync and Verification

**Files:**
- Modify: `docs/ai/reference/System_Manual.md`
- Modify: `docs/Automation.md`
- Modify: `pyproject.toml` / version metadata if version policy requires it
- Optionally modify: `README.md`

- [x] **Step 1: Document `acf doctor` in System Manual**

Add command purpose, examples, fix levels, and JSON fields.

- [x] **Step 2: Update Automation route**

Add `acf doctor --strict --json` as the recommended context health command before and after major maintenance.

- [x] **Step 3: Run verification**

Run:

```bash
uv run python -m py_compile acf.py tests/test_cli.py
uv run acf check template
uv run acf check --strict
uv run python -m unittest
```

Expected: all exit 0.

- [x] **Step 4: Decide version update**

Run `uv run acf version show --json`; because `acf doctor` is a new public CLI command, update version metadata if the current project version policy requires it.
