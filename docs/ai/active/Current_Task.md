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

Review audit MVP command contract

---

## 所属大任务

P1 audit context design

---

## 子任务 ID

T002

---

## 当前执行线

无。

---

## 本次任务目标

1. 复核 `reference/Context_Audit_Design.md`，把 P1 audit 从设计草案收敛为可实现的 MVP 命令契约。
2. 冻结 `acf audit context [path] --json` 的只读边界、JSON 顶层字段和 candidate 字段。
3. 收窄第一版规则，只保留低误报候选；暂缓更容易误报的语义类规则。

---

## 任务背景

T001 已完成 P1 audit context 设计草案。下一步不是写代码，而是先确认 MVP 契约是否足够窄、字段是否稳定、首批规则是否低误报，并继续保持 audit 不进入默认 strict、不自动修改事实。

---

## 输入材料

- `active/Task_Plan.md`
- `reference/Context_Audit_Design.md`
- `../Automation.md`

---

## 输出要求

1. 在 `reference/Context_Audit_Design.md` 新增或收敛 `MVP Command Contract`。
2. 固定命令形态：

```bash
acf audit context [path] --json
```

3. 固定 JSON 顶层字段：`schema_version`、`ok`、`command`、`context`、`candidates`、`summary`、`next_actions`。
4. 固定 candidate 字段：`kind`、`severity`、`path`、`section`、`reason`、`suggested_action`。
5. 第一版 MVP rules 只保留：
   - `active_section_too_long`
   - `stale_current_task_or_workstream_stage`
   - `terminal_conclusion_not_merged`
6. 暂缓：
   - `duplicate_active_fact_candidate`
   - `strong_claim_without_evidence`
   - `volatile_fact_in_wrong_authority_location`

---

## 成功标准

1. MVP 命令契约足够明确，可直接转化为后续测试用例。
2. 设计仍然声明只读、不生成 patch、不修改文件、不创建 curation draft。
3. 设计仍然声明不进入默认 `acf check --strict`。
4. 默认读取范围仍限定为 active 入口和 Workstream 当前状态，不读取 archive、全量 worklog 或历史 curation draft。
5. `acf check docs/ai --strict --json` 通过。

完成证据：

- `reference/Context_Audit_Design.md`
- `worklog/daily/2026-05-07.md`
- `uv run acf check docs/ai --strict --json`
- `uv run acf status docs/ai --json`

---

## 失败信号

1. 本轮开始实现 `acf audit context`。
2. 把全部 candidate rules 都列为第一版 MVP。
3. 设计允许自动删除、合并或改写权威上下文。
4. 默认读取范围扩大到 archive 或全量 worklog。

---

## 约束条件

1. 本阶段只做设计复核，不做代码。
2. 不修改 `acf.py`、测试或 CLI 行为。
3. 保持 T001 的非目标继续成立。

---

## 不允许做的事

- 不实现 `acf audit context`。
- 不新增测试。
- 不把 audit 接入 strict。
- 不生成自动修复或 patch 设计。

---

## 需要 AI 协助判断的问题

1. MVP 首批 3 条规则是否都能靠机械信号实现。
2. JSON schema 是否足够稳定，能支撑后续 MVP 测试。

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 应写入 worklog 的设计复核和验证摘要。
2. 后续是否进入 `acf audit context` 只读 MVP 实现。
