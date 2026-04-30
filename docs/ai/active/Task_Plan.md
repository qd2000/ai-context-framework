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

T004

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | 沉淀 Workstream 设计方案 | F007 用户反馈。 | reference/Workstream_Design.md | reference/Workstream_Design.md 已沉淀设计原则、状态机、合并契约、写入类型、front matter 判断和落地顺序；Feedback_Inbox F007 已映射到本计划。 | 无。 |
| T002 | Done | 设计可选模板与读取规则 | T001 | template 与 docs/ai 的可选 Workstreams 结构变更方案 | docs/ai/AGENTS.md、template/AGENTS.md、docs/ai/reference/System_Manual.md、template/reference/System_Manual.md 已明确 Workstream 可选读取规则；reference/Workstream_Design.md 已记录 T002 决议：init/upgrade 默认不启用，按需读取。 | 无。 |
| T003 | Done | 规划 acf workstream 命令与检查规则 | T001,T002 | acf workstream 命令接口、JSON 输出、状态转换、scope claim 和 check/error code 规则 | reference/Workstream_Design.md 已补齐 T003 CLI/check 实现规格：命令范围、通用写命令契约、每个命令的参数/改动文件/dry-run/check-after/error_code、机器可执行状态转换表、scope claim 规则、check severity 和命令测试计划；未实现 CLI 代码。 | 无。 |
| T004 | Active | 实现与验证 Workstream 可选层 | T002,T003,T005,T006,T007 | 模板、CLI、测试、文档和版本更新 | 第一刀已完成：acf.py 新增 Workstream 数据模型、schema、scope normalize、initialized 判断和 `acf workstream init/status/list/show`；tests/test_cli.py 覆盖未 init 可选行为、init 幂等、list/show front matter 解析和 schema 错误；版本已升至 v0.0.3.8。 | 下一刀进入创建与状态转换命令：add/set/block/cancel/ready/done，并保持 upgrade 默认不启用 Workstream。 |
| T005 | Done | 规划 front matter metadata 支持 | T001,T002 | reference/Front_Matter_Metadata_Plan.md 中的极小 YAML 子集、解析器接口、schema 校验和迁移工具计划 | acf.py 已新增无依赖 front matter 基础能力：parse_front_matter、format_front_matter、validate_front_matter、FrontMatterSchema 和诊断码；tests/test_cli.py 新增 5 个单元测试覆盖合法/非法语法、稳定 format、required/enum/list、typed write_scope 和路径诊断；验证：acf check template、acf check docs/ai --strict、python -m unittest、py_compile 均通过。 | 无。 |
| T006 | Done | 规划 upgrade 迁移与兼容性矩阵 | T002,T005 | reference/Upgrade_Migration_Plan.md | reference/Upgrade_Migration_Plan.md 已钉死 upgrade 默认不启用 Workstream、显式 workstream init 启用路径、front matter 检查触发条件、upgrade JSON 字段语义和测试矩阵；保持旧 ADR/worklog/Knowledge 无 front matter 不报错。 | 无。 |
| T007 | Done | 执行 Workstream dogfooding gate | T002,T003,T005,T006 | docs/ai 最小 Workstream 试运行记录与验收结论 | active/Workstreams.md 与 active/workstreams/WS001.md 已完成最小 Workstream dogfooding；WS001 记录 Open -> Active -> ReadyToMerge -> Done、合并请求、evidence 和 Inactive 索引状态；docs/ai strict check 通过。 | 无。 |
| T008 | Done | 生成 Workstream 设计 ADR 候选 | T001,T002 | decisions/ADR-0005.md 或对应 ADR 草案 | decisions/ADR-0005.md 已生成 Proposed ADR，reference/Decisions_Index.md 已列入待确认决策；ADR 只记录稳定取舍，不复制 Workstream_Design 细节。 | T004 实现并验证后再评估是否将 ADR-0005 改为 Active。 |

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 已失效的大任务计划应归档到 `archive/plans/`。
4. 不要把历史过程、完整日志或详细推理写入本文件。
