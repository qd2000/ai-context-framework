本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：[active/Context.md](../../active/Context.md)
- 当前正在执行的小任务请查看：[active/Current_Task.md](../../active/Current_Task.md)
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

P2-7 Markdown Link Traceability

---

## 大任务目标

1. Implement clickable Markdown link maintenance for Obsidian-friendly human navigation without depending on Obsidian双链.

---

## 成功标准

1. 大任务目标已完成并通过必要验证。

---

## 规划依据

列出当前大任务必须对齐的 reference 设计、路线或差距文档；只放路径和一句话用途，不复制详细规划。

- [reference/Product_Roadmap.md](../../reference/Product_Roadmap.md)：阶段路线和近期优先级。
- [reference/ACF_Top_Level_Design.md](../../reference/ACF_Top_Level_Design.md)：上位架构、Markdown-first 边界和非 Obsidian 绑定约束。
- [reference/Top_Level_Implementation_Gap.md](../../reference/Top_Level_Implementation_Gap.md)：实现差距矩阵和 P2-7 状态。
- [reference/System_Manual.md](../../reference/System_Manual.md)：Markdown 链接、人工导航和 CLI 维护规则。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | Implement Markdown link parser/checker | 无。 | check 校验本地 Markdown link、图片和 heading anchor | acf.py check/link helpers and targeted tests passed | 无。 |
| T002 | Done | Implement linkify and link add | T001 | linkify 和 link add CLI、JSON、dry-run 和测试 | linkify/link add CLI implemented; targeted CLI tests passed | 无。 |
| T003 | Done | Document and dogfood clickable links | T002 | README、template manual、docs-acf manual、gap 和当前上下文更新 | v0.0.3.35 set；check template/docs-acf strict/audit/unittest/upgrade_matrix quick/git diff --check completed；commit and push will be reported in final response | 无。 |
| T004 | Done | Verify release and push | T003 | 验证结果、v0.0.3.35、Lore commit 和 push | v0.0.3.35 set；check template ok with expected placeholder warnings；docs/ai strict ok；audit context ok with 2 advisory candidates；unittest 208 tests ok；upgrade_matrix quick ok；git diff --check ok | 提交并汇报 |

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
