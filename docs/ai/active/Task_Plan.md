本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Active

---

## 大任务名称

并行 Workstream 任务与信息管理方案

---

## 大任务目标

1. 为多个 agents 在同一项目中并行处理不同目标定义可选的目标线治理协议。
2. 明确 Workstream 与 Task、Feedback、权威上下文和草案的关系。
3. 规划后续模板、检查规则和 CLI 支持，同时保持旧项目兼容。

---

## 成功标准

1. F007 已编号并映射到本计划。
2. Workstream 设计原则、状态机、合并契约、写入类型和 optional 兼容规则已落入 docs/ai。
3. 后续实现任务有明确拆分，且不把 ACF 扩展为 agent runtime。

---

## 当前焦点

T002

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | 沉淀 Workstream 设计方案 | F007 用户反馈。 | reference/Workstream_Design.md | reference/Workstream_Design.md 已沉淀设计原则、状态机、合并契约、写入类型、front matter 判断和落地顺序；Feedback_Inbox F007 已映射到本计划。 | 无。 |
| T002 | Pending | 设计可选模板与读取规则 | T001 | template 与 docs/ai 的可选 Workstreams 结构变更方案 | 无。 | 决定是否新增 active/Workstreams.md 与 active/workstreams/，并更新 AGENTS 默认读取规则。 |
| T003 | Pending | 规划 acf workstream 命令与检查规则 | T001,T002 | acf workstream init/add/list/show/set/ready/done 与 check 规则设计 | 无。 | 先做结构维护和一致性检查，不做语义判断或调度。 |
| T004 | Pending | 实现与验证 Workstream 可选层 | T002,T003 | 模板、CLI、测试、文档和版本更新 | 无。 | 实现时同步 README、System Manual、Automation、data-files、init/upgrade/check 测试和版本号。 |

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 已失效的大任务计划应归档到 `archive/plans/`。
4. 不要把历史过程、完整日志或详细推理写入本文件。
