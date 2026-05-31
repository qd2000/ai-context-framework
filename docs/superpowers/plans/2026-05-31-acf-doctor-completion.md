# ACF Doctor Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Status:** Completed in `v0.0.3.47`; this file is retained as the historical implementation plan.

**Goal:** Complete the next doctor capability layer: human reports, semantic writeback drafts, broader no-judgment findings, and safe generated/index repairs.

**Architecture:** Extend the existing doctor function cluster in `acf.py`. Findings remain read-only. Only generated/index sync and already-safe mechanical edits are auto-applied; semantic updates are written as reviewable drafts.

**Tech Stack:** Python standard library, argparse CLI, unittest.

---

### Task 1: Report and Semantic Draft Outputs

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `acf.py`

- [x] Add red tests for `acf doctor <ctx> --report --today YYYY-MM-DD --json`, expecting `worklog/doctor-reports/YYYY-MM-DD.md`, `report_path`, `planned_report` on dry-run, and an explicit clean report when no findings exist.
- [x] Add red tests for `acf doctor <ctx> --draft-semantic --today YYYY-MM-DD --json`, expecting `worklog/writeback-drafts/YYYY-MM-DD-doctor.md`, `draft_path`, and only `draft_only` / `evidence_fix` findings in the draft.
- [x] Add parser flags `--report`, `--draft-semantic`, `--force`.
- [x] Implement `render_doctor_report()` and `render_doctor_semantic_draft()`.
- [x] Refuse overwriting report/draft unless `--force`; support `--dry-run` without writing.

### Task 2: Additional Read-Only Findings

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `acf.py`

- [x] Add red tests for `plan_current_task_status_mismatch`, `current_task_wrong_completion_target`, `terminal_workstream_keep_active_expired`, `source_index_missing_file`, `context_too_thick`, `root_probe_outputs_detected`, and `active_terminal_workstreams_excessive`.
- [x] Implement collectors using existing helpers: `extract_heading_value`, `safe_section_body`, `parse_workstream_index`, `read_workstream_detail`, `parse_markdown_table_rows`, and `resolve_ref`.
- [x] Keep these findings read-only or draft-only unless explicitly listed as safe repair.

### Task 3: Safe Generated/Index Repairs

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `acf.py`

- [x] Add red tests for `workstream_index_detail_status_mismatch` and `archive_index_missing_workstream`.
- [x] Implement findings by comparing planned synced Workstream index and planned generated Archive index with current text.
- [x] Extend `--fix safe` to write `active/Workstreams.md` and `archive/Archive_Index.md` only when the generated/index block can be updated deterministically.
- [x] Preserve dry-run changed files and `--check-after` behavior.

### Task 4: Docs and Verification

**Files:**
- Modify: `README.md`
- Modify: `docs/ai/reference/System_Manual.md`
- Modify: `docs/Automation.md`
- Modify: `docs/ai/reference/Doctor_Reconcile_Design.md`
- Modify: version metadata if required

- [x] Document implemented `--report`, `--draft-semantic`, `--force`, additional findings, and safe repair boundaries.
- [x] Run `uv run python -m py_compile acf.py tests\test_cli.py tests\test_upgrade_matrix.py scripts\minimal_smoke.py scripts\upgrade_matrix.py`.
- [x] Run `uv run acf check template`.
- [x] Run `uv run acf check --strict`.
- [x] Run `uv run python -m unittest`.
- [x] Run `uv run acf version show --json` and update version if public CLI behavior changed.
