本文件记录当前正在处理的具体任务。

- 长期目标请查看：`reference/Project_Brief.md`
- 当前阶段目标请查看：`active/Context.md`
- 本文件只维护当前具体任务

如果用户在当前对话中提出了新的具体需求，并且该需求与本文件冲突，以用户当前消息为准。

---

## 当前任务状态

Active

说明：

- Active：当前任务正在进行
- Paused：当前任务暂停
- Done：当前任务已完成
- Empty：暂无需要写入文件的当前任务

---

## 任务名称

版本 bump、发布闭环与全局安装验证

---

## 所属大任务

WS015 发布链收口与 worktree 退役窄路径

---

## 子任务 ID

T006

---

## 所属 Workstream

WS015

---

## 当前执行线

WS015 / T006 版本 bump、发布闭环与全局安装验证

---

## 本次任务目标

1. 等待用户侧两项：确认 v0.0.3.93 Actions run 结论；授权 commit + tag v0.0.3.94 + push 触发 PyPI 发布，随后用 scripts/update_acf.ps1 更新全局安装并验证 acf --version。
2. 产出并验证输出物：目标版本、门禁全绿、PyPI 版本与 installed-state

---

## 任务背景

该任务来自 `active/Task_Plan.md` 中的子任务 T006，所属大任务为“WS015 发布链收口与 worktree 退役窄路径”。依赖记录：T004,T005,T002

---

## 输入材料

当前任务应列出必要 active 文件和相关 reference 规划依据；不要只写 `active/Context.md`。

- `active/Task_Plan.md`。
- `active/Context.md`。
- [reference/Top_Level_Implementation_Gap.md](../reference/Top_Level_Implementation_Gap.md)：六域真实差距与下一批代码决策的入口。
- [reference/Product_Roadmap.md](../reference/Product_Roadmap.md)：阶段路线与准入门槛，确认本轮属稳定化而非新能力阶段。
- [reference/ACF_Top_Level_Design.md](../reference/ACF_Top_Level_Design.md)：CLI 分层与 worktree 边界，作为 retire 命令分层的上位约束。
- [reference/System_Manual.md](../reference/System_Manual.md)：用户可见命令合同，retire 说明需与此保持一致。
- 依赖 T004 证据：新增 tests/test_worktree_retire.py 共 11 项：可退役（worktree/registry 清理且分支保留）、apply 幂等 already_retired、缺/空 evidence-ref、未知 disposition、已合并分支拒绝并提示 close、dirty 拒绝、未登记拒绝、deny 授权拒绝、journal 记录 disposition/evidence/快照、close 行为不变；与 package_skeleton 合并 19 项通过。
- 依赖 T005 证据：docs/Worktree_Lifecycle.md 新增退役章节与拒绝条件表；docs/Automation.md、项目与模板 System_Manual.md、README.md 同步 retire；Top_Level_Implementation_Gap 第 2 域改为已实现并更新 Next Code PR Decision 与第 4/5/6 域；Product_Roadmap 当前阶段改为 WS015；CHANGELOG 新增 v0.0.3.94；同步修正 ai_context_framework/runtime_parts/upgrade.py 手册压缩字面量与模板逐字一致（含既有 force 漂移）。
- 依赖 T002 证据：发布链诊断完成：tag 已推送且不可变、PyPI 仍无 .93、本地制品复现可发布、Actions 结论待用户确认；判定以新的不可变版本发布。

---

## 输出要求

- 目标版本、门禁全绿、PyPI 版本与 installed-state

---

## 成功标准

1. 输出物已完成：目标版本、门禁全绿、PyPI 版本与 installed-state
2. 子任务 T006 的完成证据已写回任务板。
3. `acf plan status` 能显示任务板可继续推进。

---

## 失败信号

1. 依赖任务未完成或证据不足。
2. 输出物无法通过检查或人工复核验证。
3. 执行中发现用户当前需求与任务板记录冲突。

---

## 约束条件

1. 遵守当前项目规则和默认读取顺序。
2. 保持 `active/Task_Plan.md` 与 `active/Current_Task.md` 状态同步。
3. 不要把一次性过程或当前事实直接写入 Knowledge。

---

## 不允许做的事

- 无。

---

## 需要 AI 协助判断的问题

1. 执行过程中是否发现应回写 Context、ADR、rules、Knowledge 或 archive 的内容？

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 应写入 `active/Context.md` 的新增当前事实。
2. 应写入 `reference/Decisions_Index.md` 或 ADR 的重要决策。
3. 应写入 rules 的新增规则。
4. 应写入 `reference/Knowledge_Index.md` 或 Knowledge 条目的可复用经验。
5. 应归档到 archive 的历史内容。
