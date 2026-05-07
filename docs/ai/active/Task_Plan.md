本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、状态、证据入口和下一步，不记录长过程、完整日志或详细推理

---

## 大任务状态

Active

---

## 大任务名称

P1 audit context design

---

## 大任务目标

1. 在 P0 governance hardening baseline 之后，定义只读的 `audit context` 设计边界。
2. 第一阶段只写设计，不实现 `acf audit context` 命令。
3. 明确 P1 audit 只输出 candidates，不进入默认 strict，不自动修改事实。

---

## 成功标准

1. `reference/Context_Audit_Design.md` 记录 P1 audit 的目标、输入范围、候选规则、JSON 输出草案和非目标。
2. `../Automation.md` 从 P0 收口转向 P1 设计路线，避免把 audit 提前写成默认 strict 或自动修复能力。
3. `active/Current_Task.md` 明确当前任务只是设计草案，不改 CLI。
4. `acf check docs/ai --strict --json` 通过。

---

## 当前焦点

T001

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | P1 audit context design draft | P0 governance hardening baseline `v0.0.3.26` | `reference/Context_Audit_Design.md`; `../Automation.md`; `active/Current_Task.md` | `worklog/daily/2026-05-07.md`; verification: `uv run acf check docs/ai --strict --json`, `uv run acf status docs/ai --json` | 无。 |
| T002 | Pending | Review audit MVP command contract | T001 | `acf audit context docs/ai --json` 只读输出契约 | 待 T001 完成 | 设计复核后再决定是否进入实现。 |

---

## 任务阶段

| ID | 状态 | 父任务 | 名称 | 归属 Workstream | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |  |  |

---

## 非目标

本阶段不做：

1. 不实现 `acf audit context`。
2. 不把 content audit 接入默认 strict。
3. 不自动修改 `active/Context.md` 或其他权威上下文。
4. 不做自动事实裁决。
5. 不做自动语义去重。
6. 不读取 archive 或全量 worklog 作为默认 audit 输入。

---

## 基线验证

本设计任务至少运行：

```bash
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

