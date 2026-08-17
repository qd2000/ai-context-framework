# WS007 Continuation Orphan Recovery Plan

## Objective

Upgrade ACF continuation from a TTL-only lease into a recoverable, model-agnostic execution protocol that can distinguish a live runner from a stale/orphan candidate, fence superseded owners, preserve durable external-effect identities, and reconcile interrupted rounds without replaying non-idempotent work.

The design must preserve long bounded Gates and normal lease renewal. It must not solve crashes by artificially shrinking scientific or engineering Gates.

## Confirmed production evidence

- **WS086 orphaned active lease:** scheduled runner `automation-20260817T1410` claimed a 120-minute lease, then completed exact waves, four Campaigns, collection and aggregation before the ChatGPT run ended prior to test/Git checkpoint/continuation checkpoint/release. A later runner lacked a formal orphan-recovery primitive.
- **External side effects can exist with clean Git and unchanged HEAD:** therefore the v0.0.3.60 expired-HEAD guard is necessary but insufficient for Runtime/Campaign/deployment/data side effects.
- **Current ownership is lease-id only:** `renew`, `checkpoint` and `release` validate the active `lease_id`, but there is no generation/fence token proving the caller is still the authorized owner after recovery.
- **WS079 waiting state regression:** a successful `checkpoint --status waiting_external` is overwritten by clean `release` defaulting to `ready`, which can cause premature re-claim of an external-wait Gate.

## Non-goals

- Do not make ACF a scheduler or resident agent daemon.
- Do not encode PetroSim-specific `submitted/terminal/collected` phases in the core state machine.
- Do not store transcripts or unbounded raw tool output.
- Do not let a stale heartbeat alone authorize takeover.
- Do not claim that ACF fencing can prevent an external process from bypassing ACF and writing directly; ACF fencing protects the continuation control protocol and must be asserted before protected non-idempotent operations.

## Target protocol

### Lease/liveness states

`doctor` should distinguish at least:

- `absent`
- `active_live`
- `active_stale` / `orphan_candidate`
- `expired`
- `invalid`

Stale means “requires reconciliation”, not “safe to steal”. The default threshold must be derived from heartbeat/renew timing and remain conservative enough for long tool calls.

### Ownership and fencing

Each round has a monotonically increasing `generation` plus a secret fence credential returned only to the owner. Durable state stores a hash/derivation, not the raw credential. Protected owner operations require the current generation and credential.

Recovery that supersedes a previous round creates generation `N+1`. A resurrected generation `N` runner must fail `heartbeat`, `renew`, `progress`, `effect update`, `checkpoint`, and `release`.

### Generic round phases

Core phases stay runtime-neutral, for example:

`claimed → executing → waiting_external/finalizing → reconciling → released`

Runtime-specific milestones belong in bounded effect records rather than the top-level phase enum.

### Durable effect journal

External/non-idempotent work uses a write-ahead contract:

1. `effect prepare` records deterministic identity before the side effect.
2. the external action executes using that identity;
3. `effect update` records observed durable milestones/evidence.

An effect record must remain bounded and contain only compact identity/status/evidence references, such as logical key, kind, deterministic external id, milestone/status, digest/path references and timestamps. Raw output is forbidden.

Recovery rules:

- known running/queued/uncertain effect → fail-closed `reconciling`;
- terminal/collected/aggregated evidence → reuse, never resubmit;
- prepared-only identity → reconcile against the external authority before deciding whether submit is safe;
- unknown write outcome → `reconciling`.

### Formal recovery commands

The exact CLI surface will be frozen in WS007.1, but the target capability set is:

- `acf continuation heartbeat`
- `acf continuation assert-owner`
- `acf continuation progress`
- `acf continuation effect prepare|update|list`
- `acf continuation reconcile`
- `acf continuation recover`

Agents must not manually impersonate the old owner by copying a lease id from `doctor` output.

## Fail-closed recovery matrix

| Observed state | Recovery decision |
|---|---|
| active + fresh heartbeat | no-op; current owner is live |
| active + stale heartbeat + dirty Git | reconciling |
| active + stale heartbeat + unexplained HEAD advance | reconciling |
| active + stale heartbeat + running/queued/unknown effect | reconciling |
| active + stale heartbeat + all effects proven terminal/reusable + Git explainable | eligible for explicit recover/fence |
| expired + no effect journal on legacy task + unchanged clean Git | preserve current conservative legacy recovery semantics until migration evidence is sufficient |
| expired + HEAD advanced without matching finalization evidence | reconciling |
| recovered generation N+1 + old generation N returns | all protected owner operations rejected |

## Crash-point test matrix

Deterministic failure injection must cover interruption after:

1. claim;
2. effect prepare;
3. external submit acknowledgement;
4. external terminal observation;
5. collect/artifact durable evidence;
6. aggregate/final artifact evidence;
7. Git commit;
8. continuation checkpoint;
9. immediately before release.

For every crash point, tests must state whether the next runner can recover automatically, must reconcile, or must wait for a live owner. No test may allow duplicate non-idempotent work.

## Backward compatibility

- Existing v0.0.3.61 `control.json`, `state.json`, `lease.json` and `last_run.json` directories must remain readable.
- Upgrade should be lazy/compatible; users must not need `continuation init --force` merely to adopt the new protocol.
- Legacy leases without heartbeat/generation must be classified conservatively.
- Existing `claim → renew → checkpoint → release` remains supported, with stronger owner assertions and migration defaults.
- A clean release without explicit `--final-status` must preserve an already checkpointed non-running state such as `waiting_external` instead of silently forcing `ready`.

## Acceptance gates

1. Next Scheduled Task can distinguish live vs stale/orphan candidate without waiting for full TTL.
2. Stale alone never authorizes takeover; reconciliation must prove safety.
3. Completed Runtime/Campaign/deployment/data side effects are reused and never replayed.
4. Unknown side effects, dirty Git, unexplained HEAD, or live/queued identities enter `reconciling`.
5. Recovery increments generation/fences the old owner; resurrected owner operations fail deterministically.
6. `waiting_external` survives clean release unless explicitly transitioned.
7. Long Gates continue to use normal heartbeat/renew and are not forced into smaller scientific units.
8. Existing v0.0.3.61 task state upgrades in place.
9. Focused tests plus full unittest, strict/template checks, release matrix and wheel/sdist smoke pass.
10. Real dogfood validates both the WS086 orphan/finalization case and the WS079 waiting-external case before merge/release.

## Stage plan

- **WS007.1** — freeze state machine, schemas, compatibility and failure matrix; add failing regression tests for confirmed v0.0.3.61 behavior.
- **WS007.2** — heartbeat, liveness classification, generation/fence ownership and old-runner rejection.
- **WS007.3** — generic bounded round progress and write-ahead durable effect journal.
- **WS007.4** — formal reconcile/recover CLI and recovery receipts.
- **WS007.5** — waiting-external preservation, lazy v1→v2 migration and secondary UX/issue-lifecycle fixes.
- **WS007.6** — full fault injection, WS079/WS086 dogfood, release gates, publish and merge.
