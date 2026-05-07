本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、状态、证据入口和下一步，不记录长过程、完整日志或详细推理

---

## 大任务状态

Done

---

## 大任务名称

P2 Test Matrix Expansion

---

## 大任务目标

1. 在继续新增 audit 规则前，先补通用测试样本矩阵。
2. 用 fixtures 覆盖 minimal、legacy、audit long section、complex Workstream 和 authority gate。
3. 每个样本只验证一个通用上下文治理问题，不绑定 FCC 业务。
4. 明确 P3 高误报 audit rules 之前需要非 PetroSim 真实项目样本。

---

## 成功标准

1. 现有 fixture 覆盖已盘点：`upgrade_matrix` 已覆盖 legacy / upgrade 兼容。
2. 新增 `tests/fixtures/context_matrix/`，包含 `minimal_clean`、`legacy_old_context`、`audit_long_section`、`workstream_complex`、`authority_gate`。
3. 新增 `tests/test_context_matrix.py`，验证 context matrix inventory 和四个可执行通用场景。
4. `audit_long_section` 验证 H1 wrapper 不误报、真实长 H2 section 会报。
5. `workstream_complex` 验证 current_stage、terminal retention、merge_resolution 和 sync no-op。
6. `authority_gate` 验证 direct authority claim 在 strict 下失败。
7. 不新增 audit candidate rule。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | Inventory existing fixture coverage | Product Roadmap | 现有 fixtures 覆盖盘点 | `tests/fixtures/upgrade_matrix/`; `reference/Product_Roadmap.md` | 无。 |
| T002 | Done | Add audit_long_section fixture | T001 | long section fixture metadata 和测试 | `tests/fixtures/context_matrix/audit_long_section/metadata.json`; `tests/test_context_matrix.py` | 无。 |
| T003 | Done | Add workstream_complex fixture | T001 | complex Workstream fixture metadata 和测试 | `tests/fixtures/context_matrix/workstream_complex/metadata.json`; `tests/test_context_matrix.py` | 无。 |
| T004 | Done | Add authority_gate fixture | T001 | authority gate fixture metadata 和测试 | `tests/fixtures/context_matrix/authority_gate/metadata.json`; `tests/test_context_matrix.py` | 无。 |
| T005 | Done | Decide whether non-PetroSim real sample is needed | T001-T004 | 决策：P3 前需要至少一个非 PetroSim 真实项目样本；本轮不选择具体项目 | `reference/Product_Roadmap.md`; `worklog/daily/2026-05-07.md` | 后续单独开任务选择样本。 |

---

## 任务阶段

| ID | 状态 | 父任务 | 名称 | 归属 Workstream | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |  |  |

---

## 非目标

本阶段不做：

1. 不新增 duplicate / evidence / volatile audit rules。
2. 不修改 FCC 内容。
3. 不新增 CLI 命令。
4. 不把启发式 audit 接入 `check --strict`。
5. 不要求 context matrix fixture 复制整套真实项目。

---

## 后续候选

1. 选择一个非 PetroSim 真实项目样本，验证 P0/P1/P2 矩阵是否能解释非 FCC 项目。
2. 评估是否需要把 context matrix 做成独立 runner；当前先保留为 unittest fixture matrix。
3. 在多项目样本稳定后，再评估 P3 audit rule expansion。

---

## 基线验证

本任务至少运行：

```bash
uv run python -m unittest tests.test_context_matrix
uv run acf check docs/ai --strict --json
uv run acf status docs/ai --json
```

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 已失效的大任务计划应归档到 `archive/plans/`。
4. 不要把历史过程、完整日志或详细推理写入本文件。
