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

跨项目 dogfooding 评测

---

## 本次任务目标

1. 在临时或真实小项目中验证 acf init/status/check/new/edit/writeback/log 的完整使用路径。
2. 启用 usage event log，记录命令成功率、失败类型、dry-run 使用和 changed files 规模。
3. 根据评测结果形成后续功能排序建议。

---

## 任务背景

AI-facing CLI 阶段 1/2/3 已实现第一版，usage event log 已可记录命令结果元数据；下一步需要用真实项目流程验证哪些能力足够、哪些仍需产品化。

---

## 输入材料

- 当前 dogfooding 上下文：docs/ai/。
- 自动化路线：docs/Automation.md。
- usage event log：acf log enable/status/tail/summarize/prune。

---

## 输出要求

- 一份跨项目 dogfooding 评测记录。
- 后续功能排序建议，重点评估 project-root scoped edit、文件创建命令和 writeback-curator。

---

## 成功标准

1. 至少完成一轮 init/status/check/new/edit/writeback/log 路径验证。
2. 记录成功命令、失败命令、失败原因和 AI 使用痛点。
3. 给出下一步优先级建议。

---

## 失败信号

1. 无法在临时或真实项目中复现完整流程。
2. usage event log 无法提供足够评估信息。

---

## 约束条件

1. 不引入第三方运行依赖。
2. 不把 usage event log 当作权威上下文或 worklog。
3. 不因 docs/ai 是 minimal profile 而补齐 standard profile 文件。

---

## 不允许做的事

- 本任务不实现新的 CLI 子命令。
- 本任务不发布 PyPI。

---

## 需要 AI 协助判断的问题

1. 评测后是否需要优先实现 project-root scoped edit。
2. 评测后是否需要优先实现 acf new rule/reference 等文件创建命令。
3. 评测后是否需要 writeback-curator subagent。

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 应写入 `active/Context.md` 的新增当前事实。
2. 应写入 `reference/Decisions_Index.md` 或 ADR 的重要决策。
3. 应写入 rules 的新增规则。
4. 应归档到 archive 的历史内容。
