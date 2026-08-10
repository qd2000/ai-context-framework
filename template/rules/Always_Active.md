这些规则每次 AI 协作都必须遵守。

1. 不要编造缺失事实。
2. 区分事实、推测、建议，明确标注不确定性。
3. 如果上下文不足，说明缺少什么，不要自行猜测。
4. 默认上下文只保留当前目标、当前事实、当前任务和下一步。
5. 写入前必须判断唯一权威位置；能更新旧表述时，不追加重复事实。
6. worklog 记录历史过程，archive 保存历史材料，Feedback_Inbox 保存待处理信号；它们默认不作为当前事实。
7. 不要默认读取 archive、完整 worklog、原始日志或 curation draft。
8. 未显式选择 Workstream 时，只读取全局上下文和 Workstreams 摘要；不得读取任何 WS detail、read_scope、reference、output 或专属 worklog。
9. `attention` 只用于管理看板，不构成 Workstream 加载授权；多个活动 Workstream 是正常状态，不得自动选择。
10. 只有显式选择、Active Current_Task 唯一绑定或 verified worktree 才能进入单一 Workstream；冲突或无效选择必须保持全局并 fail-closed。
11. 能引用权威位置时，不复制完整表述。
12. 不要重复推进已标记为 Rejected 的方案，除非用户明确要求。
13. 如果用户当前消息与项目文件冲突，指出冲突并说明以哪个为准。
14. 可以建议更新项目文件，但最终写入由用户决定。
12. Workstream 与 Git worktree 相互独立：创建 Workstream 不隐式创建 branch/worktree；AI 只有在任务需要隔离环境时才调用 `acf worktree create`，未使用 worktree 的原任务逻辑不得受影响。
