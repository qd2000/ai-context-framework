# WS012 Historical Activity and Evidence through 2026-09-10

This archive preserves closed or superseded WS012 evidence and Activity Log entries that were moved out of the active Workstream packet on 2026-09-12 to reduce recurring context load. WS012 is now terminal; its final authority is preserved in `docs/ai/archive/workstreams/WS012.md`, while remaining Observer-retirement work is owned by WS013 and its current plan.

## Historical / superseded evidence

- `commit:8a39947` / `merge:d5b66cd6e84630135a5c8f75fe43306841417350` / `origin/tag:v0.0.3.83`
- `pypi:ai-context-framework:0.0.3.83` / `acf-version:0.0.3.83`
- `reconcile:f2590f3c-a305-434f-aa2d-8cd1cf6d394c`
- `recovery:62fa69dd-55da-4c59-b5ac-6bf3c089e927`
- `observer:revision-171:production-pre-maintenance`
- `observer:revision-173:v083-installed-maintenance`
- `observer:revision-175:v083-first-production-acceptance-failed-narrative-refresh`
- `observer:revision-177:v083-production-acceptance-sample-1`
- `observer:revision-179:v083-production-acceptance-sample-2`
- `observer:revision-182:v083-production-acceptance-sample-3`
- `observer:revision-184:v083-production-acceptance-sample-4`
- `observer:revision-186:v083-production-acceptance-sample-5`
- `observer:revision-189:v083-production-acceptance-sample-6`
- `issue:c25239f33af6982051fa:resolved`
- `issue:5067de152f19558f2d8b:upgrade-path-resolution`
- `issue:530d8683b093945f0b4a:resolved-production-revision-177`
- `github-actions:32984611066:v0.0.3.84:completed-cancelled`
- `pypi:ai-context-framework:0.0.3.84:not-found` / `reconcile:trusted-publishing:failed`
- `issue:2571acfc1377ae41f0ce:immediate-fenced-credential-transport`
- `issue:590e29d4596887eacaa6:same-root-ws080`
- `issue:517bb8cb2f78705383de:same-root-ws080`
- `issue:a315b38f1c4bf13b429e:same-root-ws079`

## Activity Log through 2026-09-10

- 2026-08-24T15:49:22+08:00: write_scope += assigned: ai_context_framework/version.py, assigned: pyproject.toml, assigned: uv.lock, assigned: ai_context_framework.egg-info/PKG-INFO; reason: Prepare the next stable patch release for the verified Observer source-authority fix.

- 2026-08-24T17:35:06+08:00: read_scope += ai_context_framework/worktree_service.py, tests/test_worktree_cli.py; write_scope += assigned: ai_context_framework/worktree_service.py, assigned: tests/test_worktree_cli.py; reason: Fix high-severity WS012 dogfood issue f452e16c7f63ca76976b: long-lived Workstream reattach writes a future reservation_commit and then worktree sync deadlocks with reservation_commit_not_ancestor; add deterministic regression and minimal lifecycle fix.

- 2026-08-24T20:29:44+08:00: write_scope += assigned: ai_context_framework/worktree_resilient_merge.py, assigned: ai_context_framework/runtime.py, assigned: tests/test_cli.py; reason: Fix reusable post-release Maintenance reactivation gap 51136959d308fa2aec58 and integration cleanup stat-only bug ffa2b2eafd58b66dba29.

- 2026-08-25T10:13:22+08:00: write_scope += assigned: ai_context_framework/continuation_directives.py, assigned: ai_context_framework/commands/continuation.py, assigned: ai_context_framework/commands/continuation_workspace.py, assigned: tests/test_continuation_cli.py; reason: Implement WS012.3 continuation directive CLI/storage/prompt/heartbeat contracts and regression tests.

- 2026-08-25T10:18:53+08:00: write_scope += assigned: ai_context_framework/commands/continuation_directives.py; reason: Keep WS012.3 directive command adapter modular and within package size/review boundaries.

- 2026-08-25T10:23:22+08:00: write_scope += assigned: ai_context_framework/continuation_inventory.py; reason: Include directive journal in continuation schema/migration preservation evidence.

- 2026-08-25T15:28:19+08:00: write_scope += assigned: ai_context_framework.egg-info/SOURCES.txt; reason: Track generated package source manifest entries for the new continuation directive modules so the v0.0.3.81 sdist metadata matches delivered package sources.

- 2026-08-25T15:29:40+08:00: write_scope += assigned: docs/ai/active/Workstreams.md, assigned: docs/ai/active/workstreams/WS012.md; reason: ACF-managed scope expansion updates the Workstream index and WS012 detail themselves; include those generated control documents so the current owner can classify and commit the audited scope change without treating it as unrelated dirty state.

- 2026-08-25T22:21:48+08:00: write_scope += assigned: scripts/update_acf.ps1, assigned: scripts/install_acf.ps1, assigned: tests/test_install_scripts.py; reason: Current-stable Windows uv-tool lock/half-broken upgrade root cause affects both WS079 and WS086; batch maintenance requires safe preflight/update script hardening and regression coverage.

- 2026-08-26T00:15:20+08:00: write_scope += assigned: ai_context_framework/commands/continuation_issue.py; reason: Split continuation issue CLI adapter from oversized continuation/runtime modules to satisfy the agent-friendly package size release gate without changing behavior.

- 2026-08-26T18:30:32+08:00: write_scope += assigned: ai_context_framework/continuation_directive_archive.py; reason: WS012.3A P2 requires a dedicated crash-safe terminal directive rollover/archive module so continuation_directives.py remains bounded and reviewable.

- 2026-08-27T05:31:00+08:00: current-stable global issue triage promoted the WS079/WS080 fenced-owner credential transport cluster to Immediate. Preserve the already-merged/tagged v0.0.3.84 publishing identity without replay; implement a backward-compatible local fence-token file handle as the next stable maintenance candidate, then restart final Production Observer acceptance from the newest stable baseline containing this repair.

- 2026-08-30T22:36:07+08:00: write_scope += assigned: ai_context_framework/commands/workstream.py, assigned: ai_context_framework/closeout_authorization.py, assigned: tests/test_closeout_authorization.py; reason: P0 closeout authorization resolver requires shared Workstream closeout command integration plus an isolated deterministic authorization ledger/resolver and focused regression tests.

- 2026-08-31T00:37:35+08:00: write_scope += assigned: ai_context_framework/commands/workstream_authorization.py; reason: Split closeout authorization CLI adapters from commands/workstream.py so the new P0 resolver stays within the repository <=2000-line agent-friendly module release gate.

- 2026-08-31T03:28:48+08:00: write_scope += assigned: ai_context_framework/json_contract.py; reason: P0 closeout authorization resolver must classify denied/ledger/migration/lock failures consistently for AI-facing JSON and must not retain legacy naked --human-approved next-action guidance in low-level worktree closeout paths.

- 2026-08-31T06:40:08+08:00: write_scope += authority: docs/ai/reference/Workstream_Design.md, assigned: tests/test_context_matrix.py, assigned: tests/test_worktree_resilient_merge.py, assigned: scripts/minimal_smoke.py, assigned: scripts/worktree_release_smoke.py; reason: P0 closeout authorization resolver changes current Workstream lifecycle authority and release/install smoke fixtures; update current design plus tests/smokes to consume durable authorization instead of naked --human-approved.

- 2026-08-31T08:32:00+08:00: P0 closeout authorization resolver reached checkpoint validation: durable user-level auto/manual/deny policy and per-Workstream/action approval evidence are separated; ready/merge/done/archive and low-level worktree merge/close consume the shared resolver; naked --human-approved cannot self-satisfy the Gate; ledger schema/tamper/migration and stale/non-transfer/revocation paths fail closed. Validation passed: 13 focused authorization tests, 362 closeout/context/worktree/CLI integration tests, targeted Ready/merge-start/worktree bypass tests, candidate minimal smoke, candidate worktree release smoke, `acf check --strict`, template check, file-scoped WS012 guard, and `git diff --check`. Next implementation authority advances to Observer V2 P1 Target Registry/run history after this checkpoint is persisted.

- 2026-08-31T08:37:23+08:00: write_scope += assigned: ai_context_framework/observer_targets.py, assigned: tests/test_observer_targets.py; reason: Observer V2 P1 Target Registry and target-local run projection require a dedicated product module and focused test module without exceeding existing 2000-line observer/test modules.

- 2026-08-31T19:27:27+08:00: Observer V2 P1 reached audited checkpoint `200c75f989319ae708acdf3ce8e4f8b4dfe1c1bc`: explicit Target Registry, target-local scope/tabs, truthful run timing/history and conditional Project Overview decision state; validation passed 58 focused Observer tests, 615 full unit tests, file-scoped WS012 guard, strict/template checks and `git diff --check`.

- 2026-08-31T19:28:12+08:00: directive revision 32 authority refresh established P1.5 as the mandatory next stage before P2: sufficient Writer and Production Observer wrapper contracts with named project/task extensions, stable Writer runtime-generated continuation authority boundary, hard semantic-review/anti-laziness evidence rules, and interactive presentation-maintenance transient/one-shot/durable lifecycles with optimistic concurrency and anti-resurrection semantics.

- 2026-08-31T19:37:32+08:00: write_scope += assigned: ai_context_framework/automation_contracts.py, assigned: tests/test_automation_contracts.py; reason: P1.5 Automation / Prompt Execution Contract needs a dedicated reviewable product contract module and focused regression module without bloating continuation or Observer command modules.

- 2026-09-01T02:28:00+08:00: generation 80 recovered stale generation 79 through formal challenge timeout + receipt-backed reconcile, then audited P1.5/P2/P3 dependencies. The previous serial Gate was circular because it required interactive presentation runtime acceptance before P2 while PLAN assigns semantic lifecycle runtime to P2 and the derived presentation surface to P3. PLAN/Workstream now separate P1.5 structural exit-to-P2 readiness, P2/P3 runtime implementation, sibling-task operational migration, and integrated pre-P4/release acceptance without dropping any original acceptance requirement.

- 2026-09-01T02:34:22+08:00: write_scope += assigned: ai_context_framework/observer_presentation.py, assigned: tests/test_observer_presentation.py; reason: Observer V2 P2 needs a dedicated semantic-review and presentation-maintenance lifecycle runtime module plus focused regression tests without bloating observer_storage.py or the existing oversized Observer CLI test module.

- 2026-09-01T02:35:25+08:00: write_scope += assigned: ai_context_framework/commands/observer_presentation.py; reason: Keep the new Observer P2 presentation-maintenance CLI adapter isolated from commands/observer.py while the storage/lifecycle implementation remains in observer_presentation.py.

- 2026-09-01T06:27:33+08:00: generation 84 formally recovered stale generation 83 after challenge timeout using reconcile receipt `f320d837-e923-4f5b-9e4d-4039fa709f38`; the only unresolved local validation effect was terminalized from durable evidence showing 640 full unit tests passed. P2 semantic lifecycle then reached product checkpoint `3fcac2815ee12003e17963a1f59c3669b5de38fd`. Fresh validation passed 83 P2/Observer/Target/automation-contract focused tests, 8 package-skeleton tests, file-scoped WS012 guard, strict/template checks and `git diff --check`. P2 semantic review / one-shot / durable-rule / independent-staleness / Map Review / narrative/problem semantics are validated; implementation authority advances to P3 transient derived-presentation maintenance + deterministic re-render + Dashboard V2 integration. Sibling Scheduled Task wrapper migration/read-back and integrated three-lifecycle acceptance remain mandatory pre-P4/release Gates; no installed-state or Production acceptance is claimed by this checkpoint.

- 2026-09-01T10:30:00+08:00: generation 88 formally recovered stale generation 87 after authenticated challenge timeout using reconcile receipt `bf489b27-8bc9-4916-bbdc-849d2364fd0c`; no unresolved effect required replay and current P3 product checkpoint is `0e2137f9af74a9dda38553814e168f17745ea5f3`. Fresh `tests.test_observer_presentation` validation passed 28/28, covering one-shot consume/anti-reconsume, durable supersede/withdraw, transient revision/fingerprint concurrency, deterministic Dashboard re-render without a new snapshot/run, semantic-risk Map Review escalation, transient expiry/cleanup, stale fail-visible rendering, and integrated anti-resurrection. P3 internal product/runtime Gate is therefore complete at candidate level; no installed-state or Production acceptance is claimed. The next mandatory pre-P4/release Gate remains sibling Scheduled Task same-task wrapper migration with exact-before → deterministic same-task update → exact-after read-back. Current scheduled context has inventory/read-back but no sibling mutation authority, so that boundary stays fail-visible and duplicate-task creation is forbidden.

- 2026-09-01T22:28:06+08:00: write_scope += assigned: ai_context_framework/observer_target_projection.py, assigned: tests/test_observer_target_projection.py; reason: P4 real-project dogfood directive dir-80ce80bfea524bfc9c43 exposed a reusable target-local Observer performance/orphan-session defect. Isolate the fresh target-scoped fact projection and focused regression tests in bounded modules instead of pushing observer.py beyond the repository module-size gate.

- 2026-09-01T22:30:00+08:00: generation 98 implemented the first P0 target-read reliability slice from directive `dir-80ce80bfea524bfc9c43`: target presentation-status/semantic-review validation now uses a fresh target-scoped projection rather than full project snapshot; source-divergence remains part of the target fingerprint, sibling-target drift remains isolated, and reusable issue `8cca72c511607c67f707` records the product defect. Shared `git_support.run_git` timeout semantics were deliberately left unchanged pending real FCC scoped-read evidence; global timeout changes are not accepted as a shortcut.

- 2026-09-01T23:29:00+08:00: generation 99 recovered generation 98 only after authenticated challenge timeout + receipt-bound reconcile, retained its fully classified WIP, and consumed supplemental directive `dir-3f925bb148c049588321` as the same P0 product defect. Durable authority now requires a bounded fail-visible Observer target-read worker around existing project/Git/path semantics rather than a shared Git timeout: `target-set` project resolution and target-local status/review projections have a finite deadline, timeout cleanup is scoped to the exact worker PID/process tree, stdout machine JSON remains separate from stderr diagnostics, and no fallback facts may be synthesized. Acceptance remains repeated isolated real FCC terminal/no-orphan dogfood before both transient directives can resolve.

- 2026-09-02T08:28:00+08:00: generation 107 formally recovered stale generation 106 after challenge `360a0ca3-7bf0-4e75-a3f0-55b01c0d02e3` timed out and reconcile receipt `d1b796f1-3257-490a-8770-3649e7a9bab1` proved effects terminal / HEAD unchanged. The abandoned 07:32 isolated FCC `target-set` tree was then cleaned only by its verified root PID `51908` with descendant-scoped termination; all known descendants were confirmed terminal. Fresh diagnostics narrowed the remaining product defect from generic Git/path slowness to an unbounded **worker process-creation boundary**: the stuck innermost Python had no worker descendant and only one waiting thread, while fresh FCC project/Git resolution and a real bounded-worker round trip remained sub-second; Windows `Popen.communicate()` would already have created pipe-reader threads if execution had reached the post-spawn timeout. Candidate now includes the spawn itself inside the same total deadline via a daemon launch helper, fails visible if `Popen` does not return, and exact-tree cleans any process that materializes after cancellation. Focused target-projection tests pass 9/9 including spawn-timeout/late-cleanup and real-worker terminality; full/guard/checkpoint plus repeated real FCC terminal/no-orphan acceptance remain required before directive or issue resolution.

- 2026-09-03T11:32:03+08:00: write_scope += assigned: ai_context_framework/runtime_parts/core.py; reason: Contain the cross-project user-level ACF state-loss incident by hardening the destructive init/simplify --force target guard at its canonical ensure_clean_target implementation; focused regression requires this runtime-part source in WS012 scope.

- 2026-09-03T20:35:36+08:00: write_scope += assigned: ai_context_framework/continuation_workspace.py; reason: Fix reusable post-state-loss recovery deadlock: supported audited adoption must be able to promote durable surviving WS012 WIP that continuation init captured as baseline_external.

- 2026-09-05T22:28:45+08:00: write_scope += assigned: ai_context_framework/continuation_execution.py, assigned: ai_context_framework/commands/continuation_execution.py, assigned: tests/test_continuation_execution.py; reason: P0 continuation liveness issue d3456d0b5cf5c261652d needs a bounded physical-execution supervisor/probe and focused regression module without bloating existing continuation modules.

- 2026-09-06T19:36:14+08:00: write_scope += assigned: ai_context_framework/commands/continuation_release.py; reason: Scheduled Writer graceful running handoff needs a dedicated bounded release adapter so continuation.py/runtime.py remain within the <=2000-line release gate.

- 2026-09-07T19:27:10+08:00: write_scope += assigned: ai_context_framework/commands/continuation_coordination.py, assigned: ai_context_framework/continuation_coordination.py; reason: Current durable WS012 authority requires tool-backed blocking coordination wait/await in the same successor continuation closure.

- 2026-09-08T09:22:16+08:00: write_scope += assigned: ai_context_framework/commands/continuation_workspace_parsers.py; reason: Split deterministic workspace/configure CLI parser registration out of the 2019-line command module so the package remains agent-friendly below the 2000-line release gate without changing continuation state semantics.

- 2026-09-08T15:23:32+08:00: write_scope += assigned: ai_context_framework/observer_dashboard.py; reason: Human-First Visualization Gate requires a bounded self-contained relationship-diagram renderer without pushing observer_storage.py beyond the repository 2000-line module gate.

- 2026-09-08T15:38:31+08:00: write_scope += assigned: docs/ai/reference/ws012_project_observer_operational_dogfood/OBSERVER_HTML_VISUALIZATION_PLAN.md; reason: Adopt user-confirmed Observer HTML v1.1 as the unique detailed WS012 Human-First visualization authority per pending directive dir-4dd0233543ac4a3b9202.

- 2026-09-09T19:35:00+08:00: generation 122 formally recovered stale generation 121 after an authenticated coordination wait reached its persisted deadline and fresh reconcile proved physical execution absent, HEAD unchanged, workspace classified, and effects unresolved=0. H1 visual acceptance remains open because the current DevSpace surface cannot directly inspect the g121 browser PNGs, so work pivoted to compatible expected-target integrity hardening: matching target IDs with divergent automation/workstream/continuation/route bindings now fail visible as `conflict`; `target-recover` never overwrites that live binding and reports the authority conflict explicitly. Focused validation passed 21/21 target registry tests and 44/44 Observer CLI tests; file-scoped WS012 guard and `git diff --check` passed.

- 2026-09-10T00:37:38+08:00: generation 127 completed the H2-adjacent focused Observer suite while H1 remained formally open: the Dashboard keeps every attributable Agent run accessible beyond the default recent-12 window, archives prior semantic reviews as historical route/map versions without mixing them into the current map, keeps current semantics usable when the historical presentation journal is corrupt, and validates explicit current/next/problem route bindings. This is adjacent implementation evidence only; it does not close the Human-First visual Gate or advance the formal stage to H2.

- 2026-09-10T01:34:40+08:00: generation 128 recovered stale generation 127 only after a tool-backed coordination wait crossed the persisted challenge deadline, fresh evidence proved physical execution absent / HEAD unchanged / workspace classified / unresolved effects zero, and receipt-backed reconcile/recover transferred ownership. With H1 still fail-visible open, the adjacent history browser gained a self-contained historical-version selector: the current route remains visible for comparison, selecting a historical version focuses that archive when JavaScript is available, and no-script rendering still exposes every archived version. Focused selector regression passed 1/1 and the full `tests.test_observer_presentation` module passed 38/38; no Production Observer refresh was performed by Maintenance.

- 2026-09-10T08:31:42+08:00: write_scope += assigned: ai_context_framework/observer_runtime_storage.py; reason: Current H1 candidate package-skeleton gate shows observer_storage.py at 2303 lines; split user-level path/history/lock primitives into a dedicated bounded storage module without changing Observer behavior.

- 2026-09-10T13:34:00+08:00: H1 manual visual review is explicitly FAIL (`dir-de45c52233d04c97af5d`). Latest authority now prioritizes visual information-architecture reconstruction over additional low-level feature expansion: make the target first screen genuinely map-first and progress-forward; separate route vs architecture views; keep main content Chinese-first; deduplicate current/why-now/next/scope; compact Agent run history; keep stale targets fail-visible with historical-map access; collapse provenance/IDs/schema/raw evidence; reduce vertical length; then render fresh real ACF + FCC Dashboards for a new user visual review. H1 remains open until a new manual PASS; do not create another Workstream, change schedulers, reopen continuation P0, or advance formal H2.

- 2026-09-10T16:28:40+08:00: generation 143 recovered stale generation 142 only after authenticated challenge `5cc2b1bd-84d4-4996-93e3-4de5dc53ffbf` reached its persisted timeout and fresh evidence proved physical execution absent, HEAD unchanged, workspace fully classified, and unresolved effects zero. Latest priority-100 directive `dir-41b8581a296544399208` is now synchronized into PLAN and the detailed visualization authority as Task-Semantic Visualization v1.2: one dominant target-semantic primary visualization selected from fresh authority, with `metric_trend / status_matrix / process_flow / compact roadmap` as the first generic archetypes; no project/target hardcoding; fresh ACF + FCC candidate dashboards and a new manual PASS remain mandatory to close H1. The existing large classified WIP must first reach a validated Git checkpoint at the earliest safe semantic boundary.
