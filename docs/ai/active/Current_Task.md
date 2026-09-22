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

WS019 Ownerless dirty WIP agent-first takeover 收口：文档同步、版本条目与全量门禁

---

## 所属大任务

WS019 Ownerless dirty WIP agent-first takeover

---

## 子任务 ID

T003

---

## 所属 Workstream

WS019

---

## 当前执行线

文档同步与发布闭合（T003）

---

## 本次任务目标

1. 同步 WS019 的 Workstream 索引、设计文档、两份 System Manual、Automation.md、README 与 CHANGELOG。
2. 版本号收敛到 v0.0.3.99（version.py / pyproject.toml / uv.lock / PKG-INFO）。
3. 重建命令树快照并跑全量门禁（check template、check docs/ai --strict、unittest、upgrade_matrix、隔离安装）。

---

## 任务背景

ownerless handoff 漂移后，Agent 此前只能通过 commit / stash / revert / 删除现场才能继续，等于用工作区动作偿还控制面缺口。WS019 新增 `acf continuation workspace review-handoff` 审查包与 `claim --handoff-review-file` 原子接管，让同一个 Agent 保留现场、批量审查、一次性接管后继续处理；ACF 始终只验证确定性事实，不判断代码语义。

---

## 输入材料

当前任务应列出必要 active 文件和相关 reference 规划依据；不要只写 `active/Context.md`。

- `active/Workstreams.md` 与 `active/workstreams/WS019.md`：WS019 的 active 事实源。
- `active/Task_Plan.md`：子任务板与规划依据。
- `reference/Continuation_Control_Design.md`：continuation 命令面与 handoff 语义上位约束。
- `reference/System_Manual.md`：用户可见命令合同，新增命令需同步。
- `CHANGELOG.md`：版本条目事实。

---

## 输出要求

- `docs/ai/reference/Continuation_Control_Design.md`、`docs/ai/reference/System_Manual.md`、`template/reference/System_Manual.md`、`docs/Automation.md`、`README.md`、`CHANGELOG.md` 与 WS019 实现一致。
- `ai_context_framework/version.py` 等四处版本一致为 v0.0.3.99。
- `tests/fixtures/cli_surface.json` 重建且其余命令零漂移。

---

## 成功标准

1. check template、check docs/ai --strict、unittest、upgrade_matrix 与隔离安装门禁全绿。
2. 文档中所有新增命令与错误码与实现一致，无过期描述。
3. 版本四处一致且 CHANGELOG 有 v0.0.3.99 条目。

---

## 失败信号

1. 任一门禁失败或命令树快照出现预期外漂移。
2. 文档仍描述"只能先清理现场才能继续"的旧语义。

---

## 约束条件

1. 遵守当前项目规则。
2. 只改 WS019 write_scope 内声明的文件；authority 文件仅通过 merge request 说明同步。

---

## 不允许做的事

- 不新增宽泛 `--force` 或放宽未知漂移的默认阻塞。
- 不在 review/接管过程中修改、提交、stash 或删除工作区文件。

---

## 需要 AI 协助判断的问题

1. 无。

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 应写入 `active/Context.md` 的新增当前事实。
2. 应写入 `reference/Decisions_Index.md` 或 ADR 的重要决策。
3. 应写入 rules 的新增规则。
4. 应写入 `reference/Knowledge_Index.md` 或 Knowledge 条目的可复用经验。
5. 应归档到 archive 的历史内容。
