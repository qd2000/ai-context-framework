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

Tune active_section_too_long wrapper handling and messages

---

## 所属大任务

P1 audit context design

---

## 子任务 ID

T005

---

## 当前执行线

无。

---

## 本次任务目标

1. 用 FCC 的 WS008 / WS009 / WS010 long-section candidates 只读复核 `active_section_too_long` 的质量。
2. 判断当前 80 行阈值是否需要调整，或是否存在计数口径问题。
3. 改进 `active_section_too_long` 的 candidate message，使后续 AI 更容易采取低风险整理动作。
4. 不新增新的 audit candidate rule。

---

## 任务背景

T004 复盘确认 ACF 自身 audit clean；FCC 只读 audit 输出 4 个 `active_section_too_long` candidates，集中在 WS008 / WS009 / WS010。进一步复核发现 3 个候选来自 Workstream H1 文档标题包含全部子 section 的 wrapper 计数，属于重复信号；真正仍超过阈值的是 WS009 的 `分析层级` section。

---

## 输入材料

- `acf.py`
- `tests/test_cli.py`
- `reference/Context_Audit_Design.md`
- ACF 命令：`uv run acf audit context docs/ai --json`
- FCC 命令：`uv run acf audit context E:\Codes\fcc_workspace\docs\ai --json`

---

## 输出要求

1. `active_section_too_long` 跳过带子标题的 H1 文档 wrapper。
2. 真实长 H2/H3 section 仍继续产生 candidate。
3. `suggested_action` 和 `next_actions` 表述为“缩短当前事实、拆分窄 section、移动历史到 worklog/reference”，不暗示 Workstream detail 自身一定是目标。
4. 新增回归测试锁定 H1 wrapper 不误报。
5. 更新设计文档和 worklog。

---

## 成功标准

1. targeted audit tests 通过。
2. ACF 自身 `acf audit context docs/ai --json` 仍为 `candidates=[]`。
3. FCC 只读 audit 从 4 个 long-section candidates 降为 1 个真实长 section candidate。
4. `uv run acf check docs/ai --strict --json` 通过。
5. 不修改 FCC 内容。

完成证据：

- `acf.py`
- `tests/test_cli.py`
- `reference/Context_Audit_Design.md`
- `worklog/daily/2026-05-07.md`
- `uv run python -m unittest tests.test_cli.CliTests.test_audit_context_reports_long_active_section tests.test_cli.CliTests.test_audit_context_ignores_h1_wrapper_with_child_sections`
- `uv run acf audit context docs/ai --json`
- `uv run acf audit context E:\Codes\fcc_workspace\docs\ai --json`

---

## 失败信号

1. 提高阈值掩盖所有 FCC 信号。
2. 新增 duplicate / evidence / volatile 规则。
3. 修改 FCC 内容。
4. 把 audit candidates 接入 `check --strict`。

---

## 约束条件

1. FCC 只读，不写入。
2. 不使用 WSL 检查 FCC。
3. 只调现有 low-risk rule 的计数口径和消息。

---

## 不允许做的事

- 不新增 audit candidate kind。
- 不生成 patch/fix/curation draft。
- 不自动拆分或移动 FCC Workstream 内容。

---

## 需要 AI 协助判断的问题

1. H1 wrapper 是否应被视为文档容器而不是真实内容 section。
2. 80 行阈值在跳过 H1 wrapper 后是否仍合理。
3. message 是否足以指导后续人工或 AI 做低风险整理。

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. FCC 样本从 4 个候选降为 1 个候选的结论。
2. `active_section_too_long` 的后续策略：先观察真实长 section，再决定是否调阈值。
