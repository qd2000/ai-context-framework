# WS008.5 Deterministic Failure Matrix

本矩阵是 WS008.5 的本地、确定性 failure-injection 证据。测试均在临时 Git 仓库与临时 `ACF_HOME` 中运行，不依赖真实平台超时或直接杀死 Agent；通过受控 lease/HEAD/workspace/effect 状态构造等价崩溃边界。

| 场景 | 期望安全行为 | 主要回归测试 |
|---|---|---|
| 2h+ long-running Gate，多次 heartbeat/renew | heartbeat 只刷新 liveness、不延长 TTL；renew 延长 TTL；整个 Gate 保持同一 fenced generation | `test_ws008_long_running_round_survives_two_hour_simulated_heartbeat_renew_cycles` |
| stale/crash，Git clean | fresh owner 不可被抢占；stale/expired owner 只有在 formal reconcile 证据满足后才可 recover | `test_reconcile_never_steals_a_fresh_active_owner`; `test_expired_running_lease_can_be_recovered_from_clean_checkpoint` |
| stale/crash，存在可归属 runner WIP | 可证明 task-owned/runner-owned WIP 随 generation+1 继承，不要求先恢复 clean | `test_ws008_stale_owner_reconcile_can_preserve_attributable_dirty_wip` |
| crash 同时存在 external dirty | non-overlap external dirty 保留且不进入本任务提交/恢复所有权 | `test_ws008_stale_owner_reconcile_can_preserve_attributable_dirty_wip`; `test_ws008_release_preserves_unrelated_external_dirty_without_reconciling` |
| write intent 与受保护 external dirty overlap | 在具体 path 层 fail-closed，不使用 blanket `worktree_dirty` | `test_ws008_write_intent_rejects_protected_external_dirty_overlap` |
| ownerless task-owned digest 漂移 | 下一 owner claim 被 `workspace_conflict/task_owned_handoff_drift` 阻塞 | `test_ownerless_task_owned_drift_blocks_next_claim_by_provenance` |
| crash 后 HEAD advance | 默认 `head_change_unaccepted`；只有显式核验并接受该 HEAD 后才可继续 recovery | `test_crash_point_failure_matrix_classifies_wait_reconcile_and_recover`; `test_expired_running_lease_with_advanced_head_requires_reconciliation` |
| crash 时 effect prepared/active/unknown | effect identity 保留且禁止重复提交；formal reconcile 保持 blocked，直到获得终态证据 | `test_crash_point_failure_matrix_classifies_wait_reconcile_and_recover`; `test_reconcile_blocks_unresolved_effects_and_blocked_receipt_cannot_recover` |
| challenge timeout 后 recover 与旧 owner ACK 竞态 | timeout 只产生 ownership-forfeiture candidate；coordination digest + state lock + generation fencing 保证最多一个 writer | `test_ws008_timed_out_challenge_can_authorize_fenced_recovery_without_death_claim`; `test_ws008_owner_ack_after_reconcile_stales_challenge_backed_recovery` |
| recover 后旧 generation 复活 | 旧 generation 的 heartbeat/effect/owner-protected 操作被 deterministic fencing 拒绝 | `test_ws008_stale_owner_reconcile_can_preserve_attributable_dirty_wip`; `test_stale_fenced_owner_reconcile_recover_fences_resurrection` |

## Gate 判定

- Failure injection 只在具体 path/provenance/HEAD/effect/identity/digest 不确定时阻塞。
- `worktree dirty` 本身不作为 liveness、claim、release、reconcile 或 recover blocker。
- 本矩阵通过后，WS008.5 的下一自然 Gate 是 WS079/WS080/WS086/AStockT_AI wrapper adoption；随后再做 release/package smoke、发布和合并。
