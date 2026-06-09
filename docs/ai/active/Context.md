本文件记录项目当前阶段的有效上下文。

- 长期目标请查看：[reference/Project_Brief.md](../reference/Project_Brief.md)
- 当前具体任务请查看：[active/Current_Task.md](Current_Task.md)
- 本文件只维护当前阶段目标和当前有效事实

---

## 审阅标记

- Last reviewed: 2026-06-09
- Review scope: 文件级；同步 WS004 旧项目升级审计完成事实和 v0.0.3.51 稳定版版本事实。

---

## 当前阶段

Dogfooding MVP / 框架稳定化。

---

## 当前阶段目标

1. 验证本框架可以作为本仓库自身的 AI 上下文系统使用。
2. 用 `acf` 将模板生成、简化、完整度检查和结构化维护自动化，降低人工维护成本。
3. 规划并逐步实现下一批确定性维护命令。
4. 将 `acf` 逐步演进为可安装、可在任意目录调用、主要面向 AI 使用的上下文维护 CLI。

---

## 当前阶段范围

### 当前阶段要做

- 维护 `template/` 作为可复制的产品模板。
- 维护 `docs/ai/` 作为本仓库真实 dogfooding 上下文。
- 保持 CLI 无第三方运行依赖。
- 用检查命令发现结构漂移、断链、状态不一致和索引遗漏。

### 当前阶段不做

- 不做常驻 agent runtime。
- 不引入向量库、数据库或私有上下文存储。
- 不把 `acf` 做成通用 Markdown 编辑器。
- 不让 subagent 静默修改权威上下文。
- 不把 `template/` 的占位内容当作当前项目事实。

---

## 当前有效事实

### 核心事实

1. 本仓库维护模型无关、Markdown-first 的 AI 上下文管理框架；核心产品源是 `template/`，真实 dogfooding 实例是 `docs/ai/`。
2. `acf` 是主要面向 AI 的上下文维护 CLI；它负责确定性检查、生成、结构化编辑、归档、草案和审计，不替代人的事实判断，也不扩展为通用 Markdown 编辑器或常驻 runtime。
3. 当前版本事实为 `v0.0.3.51`：`acf --version`、`pyproject.toml`、`uv.lock` 和本地包元数据应保持同步。
4. 本仓库使用 uv Python 环境，Python 版本约束为 `>=3.10`；运行项目 Python 或 CLI 时优先使用 `uv run python ...` 和 `uv run acf ...`。
5. `docs/ai/` 当前应保持 `uv run acf check --strict` 通过；CLI 或模板行为变更后还应运行 `uv run acf check template`、`uv run python -m unittest`，必要时运行 upgrade matrix。

### 已落地能力摘要

1. 基础维护：`init`、`simplify`、`status`、`check`、`new task/source/reference/rule/feedback/human-note/worklog/adr`、`writeback draft`、`version show/set` 已形成可安装 CLI 主链路。
2. AI 友好契约：主要命令支持 `--json`、`--dry-run`、`--check-after`、稳定 `schema_version/ok/error_code/next_actions`、changed files 和分层退出码。
3. 安全编辑：`edit section get|replace|append` 和 `edit table upsert` 仅允许在 context root 内既有 Markdown 文件上做结构化修改。
4. 计划与历史：`plan`、`task`、`archive`、`decisions`、`knowledge`、`feedback`、`workstream` 系列命令已提供当前任务板、当前任务、旧任务/旧计划归档、Feedback 生命周期、Archive / Decisions / Knowledge index sync MVP 和可选并行 Workstream 层的第一版。
5. 观测与评测：usage event log 默认开启并写入用户级目录；`acf log projects` 可只读盘点全局 usage log 项目，`scripts/minimal_smoke.py` 和 `scripts/upgrade_matrix.py` 覆盖最小 smoke 与旧上下文升级兼容性。
6. 注意力治理：`review stale`、`audit context`、`curate draft`、`doctor` 和 [reference/Context_Curation_Prompt.md](../reference/Context_Curation_Prompt.md) 已提供机械 stale signal、active 污染候选、可审阅整理草案、跨文件健康诊断、doctor report / semantic draft 和 safe repair；CLI 不裁决事实真假。
7. 链接治理：P2-7 已实现 Markdown link check/linkify/link add 能力，并完成 README、template manual、dogfooding manual 和 gap 文档同步。
8. Workstream-first 上下文治理：WS003 已实现 Workstream-first 入口推荐、文件集型 guard 强验收、workstream next-actions / preflight、Knowledge v2 metadata 草案链路、links graph / backlinks 派生视图和 draft status。
9. 旧项目升级审计：WS004 已实现 `upgrade --plan --json` 只读升级计划、全局日志项目盘点、旧项目风险 finding/readiness 模型和完整升级测试矩阵。

### 当前进展与未完成项

1. 当前阶段处在 P2 收尾和阶段 6「事实与注意力治理」深化之间；WS002 模块化拆分、WS003 Workstream-first 上下文治理和 WS004 旧项目升级审计均已完成并归档，`v0.0.3.51` 是当前推荐正式使用稳定版本。
2. 当前无活跃计划；[active/Task_Plan.md](Task_Plan.md) 为 Empty。
3. 当前无活跃任务；[active/Current_Task.md](Current_Task.md) 为 Empty。
4. Knowledge / ADR / Archive sync 的 generated marker 设计已落地 [reference/Generated_Marker_Sync_Design.md](../reference/Generated_Marker_Sync_Design.md)；通用 marker helper、`acf knowledge sync` MVP、`acf decisions sync` MVP 和 `acf archive sync` MVP 已实现。
5. `acf archive current-task/task-plan` 已修复移动 Markdown 文件后相对链接断裂问题：归档写入前会按新文件位置重写已有本地 Markdown 链接，并追加 `ACF:ARCHIVE:RECORD` marker 供后续 sync 恢复归档原因。
6. 新反馈 F016 要求 Context 采用渐进式披露；本文件已改为核心事实 + 索引结构，细节不再线性堆放在默认注意力入口。
7. 新反馈 F017 要求“上次修改/上次更新”精确到分钟并工具化；已 triage，尚未设计统一格式或 CLI 生成能力。

### 默认索引

1. 产品目标和阶段路线：[reference/Project_Brief.md](../reference/Project_Brief.md)、[reference/Product_Roadmap.md](../reference/Product_Roadmap.md)。
2. 架构与边界：[reference/ACF_Top_Level_Design.md](../reference/ACF_Top_Level_Design.md)、[../Automation.md](../../Automation.md)、[reference/System_Manual.md](../reference/System_Manual.md)。
3. 实现差距与下一步：[reference/Top_Level_Implementation_Gap.md](../reference/Top_Level_Implementation_Gap.md)、[reference/Generated_Marker_Sync_Design.md](../reference/Generated_Marker_Sync_Design.md)、[reference/Doctor_Reconcile_Design.md](../reference/Doctor_Reconcile_Design.md)、[active/Task_Plan.md](Task_Plan.md)、[active/Feedback_Inbox.md](Feedback_Inbox.md)。
4. 决策与规则：[reference/Decisions_Index.md](../reference/Decisions_Index.md)、[rules/Project_Rules.md](../rules/Project_Rules.md)、[decisions/ADR-0003.md](../decisions/ADR-0003.md)、[decisions/ADR-0004.md](../decisions/ADR-0004.md)、[decisions/ADR-0005.md](../decisions/ADR-0005.md)。
5. 可复用经验与历史证据：[reference/Knowledge_Index.md](../reference/Knowledge_Index.md)、[worklog/Worklog_Index.md](../worklog/Worklog_Index.md)、[archive/Archive_Index.md](../archive/Archive_Index.md)；archive 默认不读，只有追溯历史时按需进入。

---

## 当前关键约束

1. 框架必须保持模型无关。
2. 权威上下文必须是普通 Markdown，并且可人工审阅。
3. CLI 不应引入第三方运行依赖。
4. Python 命令应优先使用项目 uv 环境运行。
5. 自动化应优先做确定性检查和草案生成，不替代人的事实判断。
6. 涉及模板结构变更时，需要同时验证模板和 dogfooding 实例。
7. 新增或重置当前任务优先使用 `acf new task`；新增资料索引优先使用 `acf new source`；重要设计决策优先使用 `acf new adr`；当天工作记录优先使用 `acf new worklog`。
8. 会话结束回写建议需要暂存时优先使用 `acf writeback draft`，再审阅是否写入权威上下文。
9. 修改 `template/` 时，应同步检查 README、上下文入口说明和 System Manual 是否仍一致。
10. 任意目录 CLI 的设计应优先服务 AI 的确定性上下文维护，不扩展为自由文本编辑器或常驻运行时。

11. 维护 `docs/ai/` 内已有 section 或 table 时，优先使用 `acf edit` 的结构化写入能力；CLI 只负责确定性落盘，不裁决事实内容。
12. 不为 dogfooding 临时放宽 `acf edit` 的 context-root 限制；若需要编辑仓库级文档，应先设计安全的项目级编辑边界。

13. usage event log 是用户级运行态观测数据，不是权威上下文；日志写入失败不应影响原命令退出码。
14. Task_Plan 只保存当前大任务拆分、子任务状态、证据和下一步；详细过程进入 worklog，失效计划进入 archive。
15. Knowledge 只能通过草案流程沉淀可迁移判断；当前事实仍以 [active/Context.md](Context.md)、[active/Task_Plan.md](Task_Plan.md) 和 [active/Current_Task.md](Current_Task.md) 为准。

---

## 当前开放问题

1. 根薄入口生成是否需要支持少量用户自定义仓库规则字段。
2. 是否需要 writeback-curator subagent 生成更高质量的回写分类草案。
3. 是否需要为 `docs/ai/` 外的仓库级维护文档设计安全的 project-root scoped edit 能力，还是继续保持常规补丁维护。
4. 是否需要继续新增 weekly/report 创建命令，或保持 human layer 只通过 `new human-note` 写 Inbox。
5. 异常硬中断持锁进程会留下 `.acf.lock`；正常串行读写和正常并发撞锁拒绝后未复现残留。后续仅需判断是否补充清理提示、`.gitignore` 或仓库卫生说明。
6. 是否需要为 Context 审阅标记、“上次更新”和其他时间字段提供分钟级统一格式及 CLI 生成能力。

---

## 长期阶段计划：AI-facing CLI

定位：`acf` 是上下文文件 API，主要供 AI 在项目中稳定维护上下文；它不替代人的判断，也不作为通用 Markdown 编辑器。

1. 可安装命令和上下文发现：支持在任意子目录调用 `acf`，自动找到上下文根目录，并提供 `acf status`。（已实现第一版）
2. AI 友好输出和安全执行模式：支持 `--json`、`--dry-run`、统一 exit code、changed files 输出和写后检查。（已实现第一版）
3. 安全结构化编辑：提供 section 和 table 级别的确定性编辑，限制写入范围在上下文根目录内。（已实现第一版）
4. 草案和 subagent 接入：让 subagent 产出可审阅草案或建议 patch，不静默改写权威上下文。
5. 跨项目 dogfooding 评测：在真实项目中验证任意目录调用、检查、写入和回写流程。

详细路线和验收标准见：[../Automation.md](../../Automation.md)

---

## 已解决设计问题：AGENTS.md 的两层结构

### 已解决的问题

此前设计理念是"渐进式暴露"，但 `acf.py init` 的实现不完整：

- **设计理念**：根目录 AGENTS.md（薄入口） + [docs/ai/AGENTS.md](../AGENTS.md)（完整入口）
- **README 说法**：第 46 行推荐"在项目根目录放置 AGENTS.md"
- **旧实现**：`acf.py init docs/ai` 只生成上下文目录内入口，不生成根目录版本
- **修复结果**：`acf.py init` 现在生成缺失的根薄入口，并保护已有根入口不被静默覆盖

### 设计意图确认

当前设计（两个 AGENTS.md）符合渐进式暴露原则：

1. **根目录 AGENTS.md**（薄入口）
   - 角色：最轻量级的仓库级配置
   - 内容：简要说明 + "详见 [docs/ai/AGENTS.md](../AGENTS.md)" 转发
   - 维护者：仓库框架维护者
   - 频率：很少改动

2. **[docs/ai/AGENTS.md](../AGENTS.md)**（完整入口）
   - 角色：项目当前上下文的完整导航
   - 内容：默认读取顺序 + 按需读取指引 + 事实源优先级
   - 维护者：项目团队 + AI 协作
   - 频率：按项目阶段更新

### 后续改进方向

**已完成**：
- 修改 `acf.py init` 逻辑，在推断出的项目根目录生成薄入口 AGENTS.md。
- 更新 README 和 template 入口说明，明确两层入口设计。
- 新增 [decisions/ADR-0003.md](../decisions/ADR-0003.md)，正式记录"渐进式暴露的两层 AGENTS.md 设计"。

**后续可选**：
- 根薄入口生成支持少量用户自定义仓库规则字段。
- 用其他真实项目验证改进后的初始化流程。

---

## 重要决策

重要决策请查看：[reference/Decisions_Index.md](../reference/Decisions_Index.md)

---

## 当前相关路径

- 项目根目录：`E:\Codes\Tools\ai-context-framework`
- AI 文档目录：`docs/ai/`
- 产品模板目录：`template/`
- CLI：`acf.py`
- 当前大任务计划：[active/Task_Plan.md](Task_Plan.md)
- Python 项目配置：`pyproject.toml`
- uv 锁文件：`uv.lock`
- 包清单：`MANIFEST.in`
- 自动化路线：[../Automation.md](../../Automation.md)
- 资料索引：[reference/Sources_Index.md](../reference/Sources_Index.md)
- 工作记录索引：[worklog/Worklog_Index.md](../worklog/Worklog_Index.md)

---

## 容易误解的地方

1. `template/` 是产品模板，不是本仓库当前事实源。
2. `docs/ai/` 是真实 dogfooding 实例，优先级高于模板占位内容。
3. worklog 是历史过程记录，不等于当前事实。
4. subagent 适合产出草案和审阅意见，不应默认静默落盘到权威上下文。

---

## 上次更新

- 日期：2026-06-09
- 更新原因：同步 WS004 旧项目升级审计完成事实和 `v0.0.3.51` 当前稳定版本事实。
