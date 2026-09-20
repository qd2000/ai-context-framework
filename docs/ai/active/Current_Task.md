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

v0.0.3.97 版本收敛、全量门禁与收口

---

## 所属大任务

WS017 Runtime 缺陷与欠账修复

---

## 子任务 ID

T005

---

## 所属 Workstream

无。

---

## 当前执行线

无。

---

## 本次任务目标

1. 取得发布授权后执行
2. 产出并验证输出物：版本文件、CHANGELOG、发布与已安装验证、WS017 收口归档

---

## 任务背景

该任务来自 `active/Task_Plan.md` 中的子任务 T005，所属大任务为“WS017 Runtime 缺陷与欠账修复”。依赖记录：T004

---

## 输入材料

当前任务应列出必要 active 文件和相关 reference 规划依据；不要只写 `active/Context.md`。

- `active/Task_Plan.md`。
- `active/Context.md`。
- [reference/Top_Level_Implementation_Gap.md](../reference/Top_Level_Implementation_Gap.md)：六域真实差距与下一批候选。
- [reference/ACF_Top_Level_Design.md](../reference/ACF_Top_Level_Design.md)：模块边界与 CLI 分层上位约束。
- [reference/System_Manual.md](../reference/System_Manual.md)：用户可见命令合同，新增命令需同步。
- 依赖 T004 证据：用 code-explorer 逐条取证后校准六域矩阵：第 4 域「test / smoke 运行态隔离」由 缺陷 改为 已实现（v0.0.3.93 落地，WS017 补齐 worktree_release_smoke 同类实例），并把 release_check 仓库门禁段作为观测项保留而非本轮修复；「跨项目 issue 生命周期」与第 6 域「跨项目 open issue 收口」的 open 计数由 4 更正为 3（curated handoff 以 git:17024d2 + pypi:0.0.3.95 resolve）；第 5 域 CI 由 部分 改为 已实现（checkout 固定 3d3c42e5aac5…、setup-uv 08807647e706…、tests/package 双 job os 矩阵含 windows-latest、release 以 verify: uses ci.yml + needs verify 为必需门禁）；「版本收敛与发布闭合」更新为 v0.0.3.96 事实并在发布闭合后改写为 缺口 无；「发布链」缺口同步；第 3 域命令树快照路径数 210 -> 212；头部状态与 Next Code PR Decision 候选清单同步到 WS017。check docs/ai --strict 与 guard 文件集强验收全绿。

---

## 输出要求

- 版本文件、CHANGELOG、发布与已安装验证、WS017 收口归档

---

## 成功标准

1. 输出物已完成：版本文件、CHANGELOG、发布与已安装验证、WS017 收口归档
2. 子任务 T005 的完成证据已写回任务板。
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
