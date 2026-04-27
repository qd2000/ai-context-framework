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

写入 AI-facing CLI 长期阶段计划

---

## 本次任务目标

1. 把任意目录可用、主要给 AI 使用的 acf 长期路线写入 dogfooding 上下文。
2. 明确近期阶段、边界和评测标准。
3. 记录该产品方向的长期决策。

---

## 任务背景

该规划已写入 dogfooding 上下文和 ADR。

---

## 输入材料

- 用户关于任意目录 CLI 和 AI 使用场景的需求。
- docs/Automation.md。
- active/Context.md。

---

## 输出要求

- docs/Automation.md 增加 AI-facing CLI 阶段路线。
- active/Context.md 增加长期阶段计划和当前开放问题。
- 新增 ADR-0004 记录产品方向。

---

## 成功标准

1. dogfooding strict check 通过。
2. 计划不把 CLI 扩展成通用 Markdown 编辑器或常驻 runtime。

---

## 失败信号

1. 目标无法验证。
2. 任务范围需要重新确认。

---

## 约束条件

1. 不改 CLI 代码。
2. Python 命令使用 uv run python。
3. 仍保持无第三方运行依赖。

---

## 不允许做的事

- 本轮不实现可安装 CLI。
- 本轮不实现结构化编辑命令。

---

## 需要 AI 协助判断的问题

1. 无。

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 应写入 `active/Context.md` 的新增当前事实。
2. 应写入 `reference/Decisions_Index.md` 或 ADR 的重要决策。
3. 应写入 rules 的新增规则。
4. 应归档到 archive 的历史内容。
