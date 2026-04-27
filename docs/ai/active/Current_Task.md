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

实现 `acf.py new adr`

---

## 本次任务目标

1. 新增 `acf.py new adr <context>` 命令。
2. 自动选择下一个 ADR 编号，也允许显式传入 `--id ADR-000N`。
3. 生成无占位符 ADR 文件。
4. 按 `Active` 或 `Proposed` 状态更新 `reference/Decisions_Index.md`。
5. 用新命令生成 `ADR-0002`，记录 uv dogfooding Python 环境决策。

---

## 任务背景

ADR 和决策索引需要保持同步。此前新增决策需要手工创建 ADR 文件、选择编号、写索引行并确保状态一致，容易出现遗漏或状态漂移。

---

## 输入材料

- `reference/Decisions_Index.md` 的当前结构。
- 已有 `decisions/ADR-0001.md`。
- `../Automation.md` 中的自动化路线。
- 当前 `acf.py` 的 `new worklog` 实现模式。

---

## 输出要求

- `acf.py new adr` 子命令。
- 覆盖 Active、Proposed、自动编号和重复 ID 拒绝的测试。
- `decisions/ADR-0002.md`。
- 更新后的 `reference/Decisions_Index.md`。
- 更新后的 README、System_Manual、Automation 和当前上下文。

---

## 成功标准

1. `uv run python acf.py new adr docs/ai --title "..." --summary "..." --decision "..."` 能生成 ADR 文件并更新索引。
2. 自动编号跳过已存在 ADR。
3. 显式重复 ID 会失败，不覆盖已有 ADR。
4. Active 决策进入“当前有效决策”表。
5. Proposed 决策进入“待确认决策”表并保留详情链接。
6. `uv run python acf.py check docs/ai --profile minimal --strict` 通过。
7. `uv run python acf.py check template` 通过。
8. `uv run python -m unittest` 通过。
9. `uv run python -m py_compile acf.py tests\test_cli.py` 通过。

---

## 失败信号

1. ADR 文件和 `reference/Decisions_Index.md` 状态不一致。
2. 新命令覆盖已有 ADR。
3. 生成的 ADR 含占位符，导致 strict 检查失败。
4. Proposed 决策没有可追溯详情链接。

---

## 约束条件

1. 不引入第三方依赖。
2. 不实现 `new task`、`new source` 或 `writeback draft`。
3. 只支持新 ADR 的 `Active` 和 `Proposed` 状态。
4. 生成内容是可审阅草案，不替代人工语义判断。

---

## 不允许做的事

- 不静默覆盖已有 ADR 文件。
- 不把被否定方案或已替代决策自动写入新 ADR。
- 不改变通用模板的 uv 无关性。

---

## 需要 AI 协助判断的问题

本任务已完成。下一步优先判断 `new task`、`new source` 和 `writeback draft` 的最小接口。

---

## 完成后的回写要求

已写入：

1. `active/Context.md`：更新当前事实和开放问题。
2. `reference/Decisions_Index.md` 和 `decisions/ADR-0002.md`：记录 uv dogfooding 决策。
3. `worklog/Worklog_Index.md` 和 daily worklog：记录本次工作。
4. README、System_Manual、`../Automation.md`：更新 CLI 能力说明。
