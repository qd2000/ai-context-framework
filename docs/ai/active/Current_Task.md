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

Review audit MVP candidate quality on ACF and FCC

---

## 所属大任务

P1 audit context design

---

## 子任务 ID

T004

---

## 当前执行线

无。

---

## 本次任务目标

1. 记录 ACF 自身与 FCC 的 `acf audit context` 只读 dogfooding 输出。
2. 复核当前 MVP candidates 是否有用、是否误报、是否太吵。
3. 判断 `active_section_too_long` 阈值和 message 是否需要调优。
4. 明确下一步优先级：调阈值 / 改消息 / 继续观察 / 进入第二批规则设计。

---

## 任务背景

T003 已实现 P1 audit context MVP。当前 ACF 自身 audit 输出 clean；FCC 只读 audit 输出 4 个 `active_section_too_long` candidates，集中在 FCC 的 active/workstreams/WS008.md、active/workstreams/WS009.md、active/workstreams/WS010.md，没有 stale 或 terminal merge 候选。下一步不应立即扩展高误报规则，而应先复盘候选质量。

---

## 输入材料

- `reference/Context_Audit_Design.md`
- `active/Task_Plan.md`
- `worklog/daily/2026-05-07.md`
- ACF 命令：`uv run acf audit context docs/ai --json`
- FCC 命令：`uv run acf audit context E:\Codes\fcc_workspace\docs\ai --json`

---

## 输出要求

1. 在 `reference/Context_Audit_Design.md` 记录 dogfooding review 小结。
2. 说明 ACF 自身 `candidates=[]`。
3. 说明 FCC 4 个候选均为 `active_section_too_long`。
4. 说明当前未观察到 stale / terminal merge 误报。
5. 明确下一步不是扩展 duplicate/evidence/volatile 规则，而是候选质量复核后再决定阈值或消息调优。

---

## 成功标准

1. 设计文档中有 ACF/FCC dogfooding review。
2. worklog 记录候选质量复盘结论。
3. `uv run acf check docs/ai --strict --json` 通过。
4. 本轮不修改 `acf.py` 或测试。

完成证据：

- `reference/Context_Audit_Design.md`
- `worklog/daily/2026-05-07.md`
- `uv run acf check docs/ai --strict --json`
- `uv run acf audit context docs/ai --json`

---

## 失败信号

1. 本轮开始实现新 audit 规则。
2. 本轮修改 FCC 内容。
3. 把 FCC 的 4 个候选直接当成事实错误，而不是待复核候选。
4. 提前进入 duplicate / evidence / volatile 规则实现。

---

## 约束条件

1. 不使用 WSL 检查 FCC。
2. FCC 只读，不写入。
3. 只做质量复盘，不做代码变更。

---

## 不允许做的事

- 不修改 `acf.py`。
- 不新增测试。
- 不实现新 candidate rule。
- 不修改 FCC 项目内容。

---

## 需要 AI 协助判断的问题

1. `active_section_too_long` 当前 80 行阈值对大型 Workstream 是否合理。
2. 当前 `suggested_action` 是否足以指导 AI 把过程细节移到 worklog/reference/Workstream detail。
3. 是否需要下一步 T005 专门调 message，而不是扩规则。

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 候选质量复盘结论。
2. 后续是否进入 T005：Tune audit context MVP thresholds and candidate messages。
