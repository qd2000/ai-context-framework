本文件记录当前正在处理的具体任务。

- 长期目标请查看：`reference/Project_Brief.md`
- 当前阶段目标请查看：`active/Context.md`
- 当前大任务计划请查看：`active/Task_Plan.md`
- 本文件只维护当前具体任务

如果用户在当前对话中提出了新的具体需求，并且该需求与本文件冲突，以用户当前消息为准。

---

## 当前任务状态

Done

---

## 任务名称

Implement audit context MVP

---

## 所属大任务

P1 audit context design

---

## 子任务 ID

T003

---

## 当前执行线

无。

---

## 本次任务目标

1. 实现只读命令 `acf audit context [path] --json`。
2. 只实现三条低误报规则：
   - `active_section_too_long`
   - `stale_current_task_or_workstream_stage`
   - `terminal_conclusion_not_merged`
3. 固定 JSON 输出：`schema_version`、`ok`、`command`、`context`、`candidates`、`summary`、`next_actions`。
4. 保持命令不写文件、不生成 patch、不创建 curation draft、不接入 `check --strict`。

---

## 任务背景

T001 已完成 P1 audit context 设计草案，T002 已冻结 MVP 命令契约。当前任务是在该契约内实现只读 MVP，先获得结构化 candidates 输出，为后续真实项目 dogfooding 提供机械审计入口。

---

## 输入材料

- `active/Task_Plan.md`
- `reference/Context_Audit_Design.md`
- `../Automation.md`
- `acf.py`
- `tests/test_cli.py`

---

## 输出要求

1. `acf audit context docs/ai --json` 可运行。
2. clean context 输出空 `candidates`、稳定 `summary` 和 `next_actions`。
3. 长 active section 产生 `active_section_too_long` candidate。
4. Active Current_Task 或 Workstream current_stage 超过阈值未更新时产生 `stale_current_task_or_workstream_stage` candidate。
5. ReadyToMerge / Done 有未合并信号时产生 `terminal_conclusion_not_merged` candidate。
6. audit 命令不写文件。

---

## 成功标准

1. 新增 audit MVP 单元测试通过。
2. `uv run python -m unittest` 通过。
3. `uv run acf check template` 通过。
4. `uv run acf check docs/ai --strict --json` 通过。
5. README、template System Manual、dogfooding System Manual、Automation 和设计文档同步。

完成证据：

- `acf.py`
- `tests/test_cli.py`
- `../../README.md`
- `../../template/reference/System_Manual.md`
- `reference/System_Manual.md`
- `reference/Context_Audit_Design.md`
- `../Automation.md`
- `worklog/daily/2026-05-07.md`
- targeted audit tests
- `uv run python -m py_compile acf.py`
- `uv run python -m unittest`
- `uv run acf check template`
- `uv run acf check docs/ai --strict --json`
- `uv run acf status docs/ai --json`
- `uv run acf audit context docs/ai --json`

---

## 失败信号

1. 本轮实现 duplicate fact、strong claim without evidence 或 volatile fact wrong location。
2. audit 接入默认 `acf check --strict`。
3. 新增 patch、fix、write 或 curation draft 行为。
4. 默认读取 archive 或全量 worklog。

---

## 约束条件

1. 保持无第三方运行依赖。
2. 保持旧项目兼容；没有 Workstream 时 audit 仍可运行。
3. candidate 只表示候选，不表示事实错误。

---

## 不允许做的事

- 不实现自动修复。
- 不修改 FCC 项目内容。
- 不做语义事实裁决。
- 不改变 `review stale` / `curate draft` 既有行为。

---

## 需要 AI 协助判断的问题

1. MVP 阈值是否需要后续通过 dogfooding 调整。
2. 后续是否需要为 rejected / archived 等已解决但未合并状态提供单独的低优先级审计候选。

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 应写入 worklog 的实现和验证摘要。
2. 是否进入 FCC 只读 dogfooding。
