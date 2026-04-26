本文件记录当前正在处理的具体任务。

- 长期目标请查看：`reference/Project_Brief.md`
- 当前阶段目标请查看：`active/Context.md`
- 本文件只维护当前具体任务

如果用户在当前对话中提出了新的具体需求，并且该需求与本文件冲突，以用户当前消息为准。

---

## 当前任务状态

Done

说明：

- Active：当前任务正在进行
- Paused：当前任务暂停
- Done：当前任务已完成
- Empty：暂无需要写入文件的当前任务

---

## 任务名称

初始化 `docs/ai` dogfooding 上下文

---

## 本次任务目标

1. 使用 `acf.py init docs/ai --profile minimal` 初始化真实上下文实例。
2. 填充当前项目的最小真实事实，避免保留纯占位上下文。
3. 将根目录 `AGENTS.md` 调整为薄入口，并转发到 `AGENTS.md`。
4. 记录 dogfooding 决策和工作日志。
5. 运行检查与测试，确认初始化结果可用。

---

## 任务背景

本仓库此前主要维护 `template/` 产品模板和轻量 CLI，还没有一个真实使用中的上下文实例。为了验证框架自身的使用体验，需要在 `docs/ai/` 下创建 dogfooding 实例，并让后续协作优先读取它。

---

## 输入材料

- 已批准的初始化计划。
- `acf.py` 的 `init`、`simplify`、`check` 命令。
- `template/` 下的 minimal 模板文件。
- `../Automation.md` 中的自动化路线。

---

## 输出要求

- `docs/ai/` minimal 上下文实例。
- 已填充的 `active/Context.md`、`active/Current_Task.md`、`reference/Project_Brief.md`、`reference/Decisions_Index.md` 和 worklog。
- 一个实际 ADR：`decisions/ADR-0001.md`。
- 根目录 `AGENTS.md` 薄入口转发。
- 验证结果。

---

## 成功标准

1. `docs/ai/` 存在并包含 minimal 上下文结构。
2. 核心事实文件不再是纯空模板。
3. `reference/Decisions_Index.md` 只登记真实决策，不登记模板示例。
4. `worklog/Worklog_Index.md` 的日期和 daily 文件路径一致。
5. `python acf.py check docs/ai --profile minimal` 通过。
6. `python acf.py check template` 和 `python -m unittest` 通过。

---

## 失败信号

1. `docs/ai` 仍然主要由未替换占位符构成。
2. 根 `AGENTS.md` 和 `docs/ai` 重复维护完整事实。
3. 决策索引登记了模板示例或断开的 ADR 链接。
4. worklog 索引引用不存在的 daily 文件。

---

## 约束条件

1. 本轮不修改 CLI 行为来支持 strict dogfooding。
2. 本轮不引入新依赖。
3. 本轮不删除 generated `decisions/ADR-0001-template.md`，因为它仍是当前 minimal 模板输出的一部分。
4. 自动化路线只记录为计划，不在本任务中实现新命令。

---

## 不允许做的事

- 不实现 agent runtime。
- 不引入向量库或数据库。
- 不让 subagent 自动写入权威上下文。
- 不把 `template/` 的占位内容当作本仓库事实。

---

## 需要 AI 协助判断的问题

本任务已完成。后续需要判断的问题请查看 `active/Context.md` 的“当前开放问题”。

---

## 完成后的回写要求

已写入：

1. `active/Context.md`：当前阶段事实。
2. `reference/Decisions_Index.md` 和 `decisions/ADR-0001.md`：dogfooding 决策。
3. `worklog/Worklog_Index.md` 和 `worklog/daily/2026-04-26.md`：工作记录。
