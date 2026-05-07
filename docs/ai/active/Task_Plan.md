本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、状态、证据入口和下一步，不记录长过程、完整日志或详细推理

---

## 大任务状态

Done

---

## 大任务名称

P1 audit context design

---

## 大任务目标

1. 在 P0 governance hardening baseline 之后，定义并实现只读的 `audit context` MVP。
2. 第一版只输出 candidates，不进入默认 strict，不自动修改事实。
3. MVP 只实现低误报规则：长 active section、陈旧当前任务 / Workstream 阶段、ReadyToMerge / Done 结论未合并候选。

---

## 成功标准

1. `reference/Context_Audit_Design.md` 记录 P1 audit 的目标、输入范围、候选规则、JSON 输出契约和非目标。
2. `acf audit context [path] --json` 只读输出稳定 candidates、summary 和 next_actions。
3. `../Automation.md`、README 和 System Manual 说明 audit 不是 strict、不是 patch/fix、不是事实裁决。
4. 单元测试、template check、docs/ai strict check 通过。
5. 完成 MVP candidate quality dogfooding review，先评估候选质量，再决定是否调阈值或扩规则。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | P1 audit context design draft | P0 governance hardening baseline `v0.0.3.26` | `reference/Context_Audit_Design.md`; `../Automation.md`; `active/Current_Task.md` | `worklog/daily/2026-05-07.md`; verification: `uv run acf check docs/ai --strict --json`, `uv run acf status docs/ai --json` | 无。 |
| T002 | Done | Review audit MVP command contract | T001 | `acf audit context [path] --json` 只读输出契约、candidate 字段、首批 MVP rules | `worklog/daily/2026-05-07.md`; verification: `uv run acf check docs/ai --strict --json`, `uv run acf status docs/ai --json` | 无。 |
| T003 | Done | Implement audit context MVP | T002 | `acf audit context [path] --json`、三条 MVP candidate rules、read-only 测试 | `worklog/daily/2026-05-07.md`; verification: targeted audit tests, `uv run python -m py_compile acf.py`, `uv run python -m unittest`, `uv run acf check template`, `uv run acf check docs/ai --strict --json`, `uv run acf status docs/ai --json`, `uv run acf audit context docs/ai --json` | 无。 |
| T004 | Done | Review audit MVP candidate quality on ACF and FCC | T003 | dogfooding review 结论、候选质量判断、下一步建议 | `reference/Context_Audit_Design.md`; `worklog/daily/2026-05-07.md`; verification: `uv run acf check docs/ai --strict --json`, `uv run acf audit context docs/ai --json` | 无。 |

---

## 任务阶段

| ID | 状态 | 父任务 | 名称 | 归属 Workstream | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |  |  |

---

## 非目标

本阶段不做：

1. 不把 content audit 接入默认 strict。
2. 不自动修改 `active/Context.md` 或其他权威上下文。
3. 不做自动事实裁决。
4. 不做自动语义去重。
5. 不读取 archive 或全量 worklog 作为默认 audit 输入。
6. 不实现 patch / fix / curation draft 生成。
7. 不实现 duplicate fact、strong claim without evidence、volatile fact wrong location。

---

## 基线验证

本实现任务至少运行：

```bash
uv run python -m unittest tests.test_cli.CliTests.test_audit_context_clean_json_reports_no_candidates tests.test_cli.CliTests.test_audit_context_reports_long_active_section tests.test_cli.CliTests.test_audit_context_reports_stale_current_task_and_workstream_stage tests.test_cli.CliTests.test_audit_context_reports_terminal_conclusion_not_merged tests.test_cli.CliTests.test_audit_context_is_read_only
uv run python -m unittest
uv run acf check template
uv run acf check docs/ai --strict --json
uv run acf status docs/ai --json
```

进入实现前再评估是否需要补充：

```bash
uv run python -m unittest
uv run acf check template
```

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 已失效的大任务计划应归档到 `archive/plans/`。
4. 不要把历史过程、完整日志或详细推理写入本文件。

