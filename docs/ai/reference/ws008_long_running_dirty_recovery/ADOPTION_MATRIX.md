# WS008.5 Generated-Protocol Adoption Matrix

## Purpose

Record the real pre-release adoption evidence for the long-running continuation protocol. This file does not copy the generic state machine and does not modify external Scheduled Task product state. The generic protocol authority is `acf continuation prompt`; project wrappers retain only fixed identity plus project-specific constraints.

## Real-project matrix

| Project / task | Fixed worktree | Existing continuation task-id | Pre-release observation | Generated-protocol adoption result |
|---|---|---|---|---|
| FCC WS079 | `C:\PROJECT\fcc_workspace_worktrees\ws079-petrosim-model-builder` | `WS079` | Existing generation-2 state is readable; expired running round currently has legacy workspace provenance missing plus reconciliation-required evidence. | WS008 development `acf continuation prompt` renders the complete 4F protocol in place without re-init and preserves the E118 Temperature-only scientific next action. Do not mutate the live task until its existing recovery blockers are reconciled. |
| FCC WS080 | `C:\PROJECT\fcc_workspace_worktrees\ws080-fcc-mechanistic-model` | `ws080-fcc-mechanistic-hourly` | Existing generation-5 state is readable; worktree has task WIP from the interrupted source-identity round and legacy workspace provenance is absent. | WS008 development prompt renders the complete 4F protocol in place and preserves the per-CN heteroatom/metals source-first next action. The wrapper must retain the real task-id alias rather than invent `WS080`. |
| FCC WS086 | `C:\PROJECT\fcc_workspace_worktrees\ws086-lmtr-three-start-execution` | `WS086-hourly-continuation` | Existing generation-3 state is readable and Git clean; one prepared Campaign collect effect remains unresolved, so formal reconciliation is still required before new live work. | WS008 development prompt renders the complete 4F protocol in place and preserves the frozen round11 L1 scientific/runtime boundary. The wrapper must retain the real task-id alias rather than invent `WS086`. |
| AStockT_AI WS003 | `E:\PROJECT\AStockT_AI_worktrees\ws003-fresh-date-paper` | `WS003` | Worktree is clean and current stable ACF v0.0.3.61 reports `can_claim=true`. Its generated prompt is still the old pre-4F protocol. The external project's Autonomous_Execution authority also embeds the older `doctor -> can_claim -> claim -> clean checkpoint -> release` generic state machine. | Cutover is intentionally deferred until the new stable ACF is package-smoked and installed on qdspc. Then replace the copied generic continuation steps in that authority file with “doctor + consume current `acf continuation prompt`” authority and keep only AStock-specific project orchestration/risk/test constraints. |

## Adoption rules frozen by the smoke

1. Existing continuation task identity is authoritative. A wrapper must not assume task-id equals Workstream ID; WS080 and WS086 prove real aliases are already in use.
2. Existing state must be consumed in place. Adoption does not use `init --force` and does not erase unresolved workspace/effect/recovery evidence.
3. A project-specific next action remains local task state; only the generic contention/recovery protocol is centralized in generated prompt.
4. External Scheduled Task prompt text is product-side state, not Git authority. Pre-release testing records compatibility here; actual wrapper cutover happens only after the released ACF that generates 4F is installed on that machine.
5. Dirty or expired real tasks are not repaired merely to demonstrate adoption. WS079/WS080/WS086 remain fail-closed according to their existing evidence until their own runners formally reconcile them.

## Release cutover checklist

- Package/release smoke the WS008 candidate and install the resulting stable ACF on the FCC host and qdspc.
- Re-run `continuation doctor` and `continuation prompt` on the four exact task identities above; require the generated prompt to contain attempt/challenge, read-only probe, authenticated owner response, timeout forfeiture candidate, formal reconcile/recover, workspace ownership and commitless handoff semantics.
- Update the AStockT_AI Autonomous_Execution authority so it no longer freezes a duplicate generic continuation state machine.
- Update the external Scheduled Task wrappers to keep only fixed project/worktree/branch/task identity and project-specific Runtime/scientific/permission/validation constraints; do not copy the generated protocol body.
- Do not replay or repair WS079/WS080/WS086 scientific/runtime work as part of protocol adoption.

