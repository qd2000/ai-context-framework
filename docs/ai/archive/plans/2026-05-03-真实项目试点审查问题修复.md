本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

真实项目试点审查问题修复

---

## 大任务目标

1. 修复三项目审查中发现的上下文语义问题。
2. 补强真实项目审查包和 playbook。
3. 对齐 upgrade JSON 输出契约与实际实现。

---

## 成功标准

1. knowledgeConnector 的重复回写协议已移除。
2. papers 的文件命名规则与中文原始资料现实一致。
3. Real_Project_Upgrade_Playbook 已说明 committed diff、untracked init 文件和 UTF-8 输出要求。
4. upgrade --dry-run --json 的字段契约已实现或文档已修正。
5. ACF 仓库 strict check、template check 和相关测试通过。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | 修复 knowledgeConnector 旧回写协议残留 | F008 | knowledgeConnector docs/ai/AGENTS.md 小修 | knowledgeConnector 分支 test/acf-v0.0.3.12 已提交 9018be9 Remove stale ACF writeback checklist；strict check 通过，upgrade dry-run 无变更。 | 无。 |
| T002 | Done | 修复 papers 命名规则冲突 | F009 | papers AGENTS.md、Project_Rules.md 与 Context 小修 | papers 分支 test/acf-v0.0.3.12-init 已修正 AGENTS.md、docs/ai/rules/Project_Rules.md 和 active/Context.md；strict check 通过，upgrade dry-run 无变更。 | 无。 |
| T003 | Done | 更新真实项目审查包 playbook | F010,F012 | Real_Project_Upgrade_Playbook.md | reference/Real_Project_Upgrade_Playbook.md 已补充 committed diff、untracked/staged diff 和 PowerShell UTF-8 输出要求；strict check 通过。 | 无。 |
| T004 | Done | 对齐 upgrade JSON 契约 | F011 | CLI 或文档修正 | acf upgrade --dry-run --json 已新增 detected_features、planned_changes、skipped_changes；README 和 template System_Manual 已同步；版本升至 v0.0.3.13；相关 upgrade 单元测试通过。 | 无。 |

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 已失效的大任务计划应归档到 `archive/plans/`。
4. 不要把历史过程、完整日志或详细推理写入本文件。
