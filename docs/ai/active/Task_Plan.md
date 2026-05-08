本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

P2-6 Human Layer and Template Modernization

---

## 大任务目标

1. Implement standard-profile human notes, Obsidian boundary docs, unified template placeholders, canonical ACF markers, upgrade compatibility, tests, version bump, and release commit.

---

## 成功标准

1. Standard init and upgrade create human layer while minimal does not.
2. Templates use canonical placeholders and marker docs use canonical ACF marker format.
3. Legacy placeholders and markers remain compatible with future warnings.
4. Verification suite passes and v0.0.3.34 is committed and pushed.

---

## 规划依据

列出当前大任务必须对齐的 reference 设计、路线或差距文档；只放路径和一句话用途，不复制详细规划。

- `reference/ACF_Top_Level_Design.md`：上位架构、边界和非目标。
- `reference/Product_Roadmap.md`：阶段路线、近期优先级和 P2-6 定位。
- `reference/Top_Level_Implementation_Gap.md`：实现差距矩阵、P2-6 状态和后续切片依据。
- `reference/System_Manual.md`：dogfooding 维护命令、人机协作和上下文治理规则。
- `reference/Upgrade_Migration_Plan.md`：upgrade 非破坏式补齐、marker notes 和旧项目兼容边界。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | Update templates and CLI | 无。 | Standard human layer, canonical placeholders, canonical markers and compatibility helpers implemented | acf.py template/ docs/ai upgrade and targeted CLI tests cover human layer, placeholders, markers, and compatibility helpers. | 无。 |
| T002 | Done | Update docs and dogfood upgrade | T001 | README, manuals, roadmap, gap docs and docs/ai human layer updated through upgrade | README, template and docs/ai manuals, roadmap, gap docs, AGENTS, and docs/ai human layer updated via upgrade dry-run/apply; docs/ai strict check passed. | 无。 |
| T003 | Done | Verify behavior and version | T002 | Checks, unittest, smoke, upgrade matrix, diff check and v0.0.3.34 completed | version show v0.0.3.34 aligned; py_compile passed; check template ok with placeholder warnings; docs/ai strict ok; audit context ok with 2 advisory candidates; unittest 202 tests ok; minimal_smoke ok; upgrade_matrix quick ok; git diff --check ok. | 无。 |
| T004 | Done | Commit and push release | T003 | Lore commit and pushed branch | Lore commit prepared after full verification; final response will report pushed commit hash. | 无。 |

---

## 任务阶段

| ID | 状态 | 父任务 | 名称 | 归属 Workstream | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |  |  |

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 当前大任务依赖 reference 规划时，必须在 `## 规划依据` 列出路径和一句话用途。
4. 已失效的大任务计划应归档到 `archive/plans/`。
5. 不要把历史过程、完整日志或详细推理写入本文件。
