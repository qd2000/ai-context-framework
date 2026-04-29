本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

反馈入口与回写流程 dogfooding 改进

---

## 大任务目标

1. 将 Feedback_Inbox 作为人工反馈入口纳入可持续维护流程。
2. 让会话结束回写从“重复打印建议”改为“优先落盘或生成明确草案，并只报告实际变更”。
3. 建立已处理反馈的归档、隐藏或清理规则，避免 active 上下文长期膨胀。
4. 用当前 docs/ai dogfooding 上下文验证新流程是否可执行、可检查、可升级。

---

## 成功标准

1. F005/F006 均有明确任务映射、处理状态和证据位置。
2. AI Update Protocol 明确会话结束时哪些内容应落盘、哪些只能生成草案、哪些不应重复输出。
3. Feedback_Inbox 生命周期明确 Done/Rejected/Planned 条目的保留、归档和清理策略。
4. 如新增或调整 CLI 行为，`--help`、文档和单元测试同步覆盖。
5. 完成后 `uv run acf check docs/ai --strict --json` 与 `uv run acf upgrade docs/ai --dry-run --json` 通过。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | 规范化 Feedback_Inbox 新增人工反馈 | 无。 | F005/F006 条目编号、状态和后续处理明确 | active/Feedback_Inbox.md: F005/F006 已编号、标为 Planned，并映射到本计划。 | 无。 |
| T002 | Done | 定义会话结束回写落盘协议 | T001 | 明确哪些会话结束内容应直接落盘、哪些生成草案、最终报告只包含实际变更和验证结果 | docs/ai/AGENTS.md: 会话结束回写建议已改为落盘优先协议，覆盖计划、Feedback、Context、worklog、Knowledge、Archive、ADR/rules 和最终回复规则。 | 无。 |
| T003 | Done | 定义 Feedback_Inbox 生命周期与归档策略 | T001 | 明确 Open/Triaged/Planned/Done/Rejected 的处理规则、保留阈值、归档位置和 AI 清理责任 | active/Feedback_Inbox.md: 已定义 Open/Triaged/Planned/Done/Rejected 生命周期、Done/Rejected 保留阈值、archive/feedback/YYYY-MM.md 归档位置和 AI 清理责任；F001-F006 已更新为 Done。 | 无。 |
| T004 | Done | 实现文档与 CLI 支持 | T002, T003 | 模板、docs/ai、System Manual、必要 CLI/help/check 流程与测试同步更新 | template/AGENTS.md、template/active/Feedback_Inbox.md、template/reference/System_Manual.md、docs/ai/reference/System_Manual.md、README.md 已同步 T002/T003 协议；acf init/upgrade 文件清单补齐 archive/feedback；测试覆盖 init/upgrade；版本同步到 v0.0.3.3；验证：acf check template、acf check docs/ai --strict、acf upgrade docs/ai --dry-run、python -m unittest 均通过。 | 无。 |
| T005 | Done | 验证反馈驱动流程并记录 dogfooding 结果 | T004 | strict 检查、upgrade dry-run、相关单元测试和 worklog/Context 更新完成 | worklog/daily/2026-04-29.md 与 worklog/Worklog_Index.md 已记录反馈入口与回写流程 dogfooding 结果；active/Context.md 已同步回写协议、Feedback 生命周期、archive/feedback、v0.0.3.3 和验证事实；验证：acf check docs/ai --strict、acf upgrade docs/ai --dry-run、python -m unittest 均通过。 | 无。 |
| T006 | Done | 补充升级兼容性开发要求 | T004 | 明确开发修改 template 或本系统时必须评估 acf upgrade 对旧版本上下文的兼容度，并保证旧版本可良好升级 | docs/ai/rules/Project_Rules.md、template/rules/Project_Rules.md、docs/ai/reference/System_Manual.md、template/reference/System_Manual.md 和 README.md 已补充 upgrade 兼容性开发要求；tests/test_cli.py 增加模板规则保护测试；版本同步到 v0.0.3.4；验证：acf check docs/ai --strict、acf upgrade docs/ai --dry-run、acf version show、python -m unittest 均通过。 | 无。 |

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 已失效的大任务计划应归档到 `archive/plans/`。
4. 不要把历史过程、完整日志或详细推理写入本文件。
