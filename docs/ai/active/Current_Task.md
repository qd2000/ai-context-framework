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

实现安全结构化编辑原语

---

## 本次任务目标

1. 提供 section get、section replace、section append 和 table upsert。
2. 所有编辑限制在上下文根目录内，并拒绝非 Markdown 目标和路径穿越。
3. 保持 JSON、dry-run、changed files 和 check-after 契约一致。

---

## 任务背景

AI-facing CLI 阶段 3 第一版已完成。

---

## 输入材料

- docs/Automation.md 阶段 3 计划。
- 现有 acf.py 写命令和 JSON 输出契约。

---

## 输出要求

- acf.py edit section/table 子命令已实现。
- tests/test_cli.py 已覆盖结构化编辑。
- README、System Manual、Automation 和 dogfooding 上下文已同步。

---

## 成功标准

1. section get/replace/append 可稳定操作指定标题。
2. table upsert 可按 key 更新或追加索引表行。
3. 路径穿越和非 Markdown 文件被拒绝。
4. 完整 uv 验证通过。

---

## 失败信号

1. 目标无法验证。
2. 任务范围需要重新确认。

---

## 约束条件

1. 不新增第三方运行依赖。
2. 不实现通用 Markdown 编辑器或语义判断。

---

## 不允许做的事

- 不实现 subagent 自动写入权威上下文。

---

## 需要 AI 协助判断的问题

1. 第一版 table upsert 保持简单的精确表头/首表匹配。

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 应写入 `active/Context.md` 的新增当前事实。
2. 应写入 `reference/Decisions_Index.md` 或 ADR 的重要决策。
3. 应写入 rules 的新增规则。
4. 应归档到 archive 的历史内容。
