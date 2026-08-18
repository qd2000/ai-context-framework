# WS008.5 Generated-Protocol Adoption Matrix

## Purpose

Record the real pre-release compatibility evidence and completed v0.0.3.63 cutover for the long-running continuation protocol. This file does not copy the generic state machine. The generic protocol authority is `acf continuation prompt`; project wrappers retain only fixed identity plus project-specific constraints.

## Real-project matrix

| Project / task | Fixed worktree | Existing continuation task-id | Initial observation | Final generated-protocol adoption result |
|---|---|---|---|---|
| FCC WS079 | `C:\PROJECT\fcc_workspace_worktrees\ws079-petrosim-model-builder` | `WS079` | Existing generation-2 state is readable; expired running round has legacy workspace provenance/effect reconciliation evidence. | Laptop global ACF v0.0.3.63 renders the full generated protocol in place and preserves the E118 Temperature-only scientific next action. Existing recovery blockers remain untouched. FCC human wrapper authority was migrated in commit `ae0d6806`; the saved WS079 Scheduled Task wrapper already calls doctor/prompt and declares generated protocol authority. |
| FCC WS080 | `C:\PROJECT\fcc_workspace_worktrees\ws080-fcc-mechanistic-model` | `ws080-fcc-mechanistic-hourly` | Existing generation-5 state is readable; interrupted source-identity WIP and legacy provenance evidence remain. | Laptop global ACF v0.0.3.63 renders the full generated protocol in place and preserves the per-CN heteroatom/metals next action. The real task-id alias remains unchanged. FCC wrapper authority is commit `ae0d6806`; the saved WS080 Scheduled Task wrapper already consumes doctor/prompt generated authority. |
| FCC WS086 | `C:\PROJECT\fcc_workspace_worktrees\ws086-lmtr-three-start-execution` | `WS086-hourly-continuation` | Existing generation-3 state is readable; one prepared Campaign collect effect remains unresolved. | Laptop global ACF v0.0.3.63 renders the full generated protocol in place and preserves the frozen round11 L1 boundary. The real task-id alias remains unchanged and the unresolved effect remains fail-closed. FCC wrapper authority is commit `ae0d6806`; the saved WS086 Scheduled Task wrapper already consumes doctor/prompt generated authority. |
| AStockT_AI WS003 | `E:\PROJECT\AStockT_AI_worktrees\ws003-fresh-date-paper` | `WS003` | Before release qdspc ran ACF v0.0.3.61 and generated the old pre-4F protocol; the project Autonomous_Execution authority also duplicated the older generic state machine. | qdspc was upgraded from v0.0.3.61 to PyPI v0.0.3.63. Installed-state doctor reports `can_claim=true` and prompt renders the full generated protocol while preserving the T004 readiness-audit next action. The AStock Autonomous_Execution authority was migrated in commit `53a7b80`; the saved AStock Scheduled Task wrapper already calls doctor/prompt and treats generated protocol as authoritative. The unrelated main-checkout untracked file was preserved. |

## Adoption rules frozen by the smoke

1. Existing continuation task identity is authoritative. A wrapper must not assume task-id equals Workstream ID; WS080 and WS086 prove real aliases are already in use.
2. Existing state must be consumed in place. Adoption does not use `init --force` and does not erase unresolved workspace/effect/recovery evidence.
3. A project-specific next action remains local task state; only the generic contention/recovery protocol is centralized in generated prompt.
4. External Scheduled Task prompt text is product-side state, not Git authority. Cutover verification checks that the saved wrapper consumes `doctor + prompt`; it does not duplicate or mutate the generated protocol body when the existing wrapper is already compliant.
5. Dirty or expired real tasks are not repaired merely to demonstrate adoption. WS079/WS080/WS086 remain fail-closed according to their existing evidence until their own runners formally reconcile them.

## Completed release cutover evidence

- v0.0.3.63 release checkpoint: `826e212382caf55245b6661f072020e509a29aed`.
- Full repository release gate passed: template/strict, minimal smoke, full unittest, full upgrade matrix, wheel/sdist build, and isolated wheel/sdist `uv tool install -> acf --version -> init -> check` smoke.
- Annotated tag `v0.0.3.63` was pushed and Trusted Publishing completed. Public PyPI metadata exposes both `ai_context_framework-0.0.3.63-py3-none-any.whl` and `ai_context_framework-0.0.3.63.tar.gz`.
- Lenovo/laptop global ACF was upgraded from v0.0.3.62 to v0.0.3.63 from the exact release checkpoint wheel. qdspc was upgraded from v0.0.3.61 to PyPI v0.0.3.63.
- Installed-state `doctor`/`prompt` re-smoke passed on WS079, WS080, WS086 and AStockT_AI WS003 without force re-init or modification of their scientific/runtime state.
- FCC project wrapper authority migrated in `ae0d6806`; AStockT_AI project wrapper authority migrated in `53a7b80`.
- Existing saved Scheduled Task wrappers for WS079, WS080, WS086 and AStockT_AI were verified to call `acf continuation doctor` + `acf continuation prompt` and treat generated protocol as generic authority; no redundant product-side rewrite was required.
- WS079/WS080/WS086 recovery/scientific blockers were deliberately not repaired or replayed as part of protocol adoption.
