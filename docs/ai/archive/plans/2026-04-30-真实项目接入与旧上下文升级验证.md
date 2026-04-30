本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

真实项目接入与旧上下文升级验证

---

## 大任务目标

1. 验证 ACF v0.0.3.12 在真实项目中的旁路接入和旧 ACF 上下文非破坏式升级路径。
2. 确认默认不启用 Workstream、旧文件不批量添加 front matter、旧项目 check 不被新结构打扰。
3. 沉淀可复用的真实项目升级验收表和推广前判断标准。

---

## 成功标准

1. 至少完成一个低风险真实项目的 dry-run 接入或升级审查记录。
2. 试点流程包含 status/check/upgrade dry-run、planned_changes 审查、正式升级或暂缓结论、strict check 和 git diff 人工审查要求。
3. Workstream/front matter 保持 optional，没有被默认启用或批量迁移。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | 确定试点项目与验收表 | 无。 | 试点选择标准、风险边界和 ACF v0.0.3.12 Upgrade Acceptance 模板 | reference/Real_Project_Upgrade_Playbook.md 与 worklog/daily/2026-04-30.md 已记录试点项目、验收表和三类真实项目验证结果。 | 无。 |
| T002 | Done | 验证无 ACF 项目的旁路接入 | T001 | 新建 docs/ai 旁路接入 dry-run/正式 init/check 记录 | papers：无 ACF 上下文，执行 standard init 并补齐最小 docs/ai 事实后 strict check 通过；未启用 Workstream，未修改论文、脚本或数据文件；详见 worklog/daily/2026-04-30.md。 | 无。 |
| T003 | Done | 验证旧 ACF 上下文升级路径 | T001 | 旧上下文 status/check/upgrade dry-run/planned_changes 审查和正式升级或暂缓结论 | knowledgeConnector：旧 ACF upgrade 正式执行并通过 strict check；register：upgrade dry-run changed_files 为空且 strict check 通过；详见 worklog/daily/2026-04-30.md。 | 无。 |
| T004 | Done | 记录试点验收与推广判断 | T002,T003 | worklog 中的 Upgrade Acceptance 记录、推广/暂缓结论和后续候选清单 | worklog/daily/2026-04-30.md 已记录三类试点：knowledgeConnector 旧上下文升级、register no-op upgrade、papers 新项目 init；均验证 Workstream/front matter optional 边界。 | 无。 |

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 已失效的大任务计划应归档到 `archive/plans/`。
4. 不要把历史过程、完整日志或详细推理写入本文件。
