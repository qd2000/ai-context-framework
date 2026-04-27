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

细化 acf JSON schema：schema_version、error_code 和 next_actions

---

## 本次任务目标

1. 为 JSON 输出增加稳定 schema_version 字段。
2. 为 check/status/write 输出增加统一 error_code 语义。
3. 为 AI 增加 next_actions 字段，减少解析自然语言输出。

---

## 任务背景

该任务已完成，承接 AI-facing CLI 阶段 2 第一版继续细化 JSON schema 和字段契约。

---

## 输入材料

- docs/Automation.md 的适合继续程序化工作。
- 现有 acf.py JSON 输出实现。

---

## 输出要求

- acf.py JSON payload 包含 schema_version、error_code 和 next_actions。
- tests/test_cli.py 覆盖成功、check 失败和 dry-run JSON 字段。
- README、System Manual、Automation 和 dogfooding 上下文同步。

---

## 成功标准

1. status/check/write JSON 输出字段稳定且测试可解析。
2. check 失败时 JSON 返回 error_code 和 next_actions。
3. 完整 uv 验证通过。

---

## 失败信号

1. 目标无法验证。
2. 任务范围需要重新确认。

---

## 约束条件

1. 不新增第三方运行依赖。
2. 不实现结构化 Markdown 编辑。
3. 不改变非 JSON 人类输出语义。

---

## 不允许做的事

- 本轮不实现 section/table 编辑原语。
- 本轮不引入 subagent。

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
