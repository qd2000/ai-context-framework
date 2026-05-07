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

P1 audit context design draft

---

## 所属大任务

P1 audit context design

---

## 子任务 ID

T001

---

## 当前执行线

无。

---

## 本次任务目标

1. 新增 `reference/Context_Audit_Design.md`，记录 P1 audit context 的只读 candidates 设计。
2. 更新 `../Automation.md`，把 P0 baseline 后的下一阶段收敛为设计先行。
3. 保持本轮只写设计，不实现 CLI、不修改检查规则。

---

## 任务背景

P0 governance hardening 已以 `v0.0.3.26` 作为稳定基线收口，并通过 ACF 自身与 FCC dogfooding 验证。下一阶段应先定义 P1 audit context 的边界，避免在 P0 后立即引入启发式检查、自动事实裁决或自动写回。

---

## 输入材料

- `active/Task_Plan.md`
- `../Automation.md`
- `reference/Context_Curation_Prompt.md`
- P0 baseline：`v0.0.3.26`

---

## 输出要求

1. 设计文档明确 `acf audit context docs/ai --json` 的只读输出草案。
2. 候选规则限定为：
   - duplicate active facts candidate
   - volatile fact in wrong authority location
   - strong claim without evidence
   - Done/ReadyToMerge conclusion not merged
   - active section too long
   - stale current task / stale workstream stage
3. 非目标明确写入：不自动事实裁决、不自动语义去重、不默认修改 Context、不进入 strict、不读取 archive / 全量 worklog。

---

## 成功标准

1. `reference/Context_Audit_Design.md` 存在且边界清楚。
2. `../Automation.md` 指向该设计，不把 P1 audit 写成已实现能力。
3. `acf check docs/ai --strict --json` 通过。
4. 本轮没有修改 `acf.py`、测试或 CLI 行为。

完成证据：

- `reference/Context_Audit_Design.md`
- `../Automation.md`
- `worklog/daily/2026-05-07.md`
- `uv run acf check docs/ai --strict --json`
- `uv run acf status docs/ai --json`

---

## 失败信号

1. 本轮开始实现 `acf audit context`。
2. 把 audit candidates 接入默认 `acf check --strict`。
3. 设计暗示 CLI 可以自动删除、合并或改写权威上下文。
4. 默认读取 archive 或全量 worklog。

---

## 约束条件

1. 本阶段只做设计，不做代码。
2. 保持 P0 deterministic gates 与 P1 advisory audit 的边界。
3. 保持旧项目兼容；未来实现也不得要求项目先迁移为固定 schema。

---

## 不允许做的事

- 不修改 `acf.py`。
- 不新增测试。
- 不实现 `acf audit context`。
- 不新增依赖。
- 不修改 FCC 项目内容。

---

## 需要 AI 协助判断的问题

1. 哪些 audit rule 足够机械、低误报，未来可能单独升格为 strict rule？
2. 第一版 JSON 输出是否足够稳定，能支撑后续 curation draft 或人工审阅？

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 应写入 `active/Context.md` 的新增当前事实。
2. 应写入 worklog 的设计和验证摘要。
3. 后续是否进入 T002：MVP command contract review。

