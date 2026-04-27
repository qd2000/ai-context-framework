# 自动化与 subagent 路线

本项目的核心价值是模型无关、纯 Markdown、可人工审阅的上下文治理。自动化的目标不是替代判断，而是减少结构漂移、索引遗漏和重复手工维护。

## 当前已自动化

`acf.py` 先覆盖确定性工作：

- 可安装入口：`pyproject.toml` 提供 `acf` console script；本仓库开发入口仍保留 `uv run python acf.py ...`。
- 上下文自动发现：`check`、`new ...` 和 `writeback draft` 在省略路径时，会从当前目录向上查找 `docs/ai` 或上下文根目录；显式路径仍优先。
- `status`：输出项目根、上下文目录、profile、当前任务状态和检查结果。
- AI 友好输出第一版：`status` 和 `check` 支持 `--json`；写命令支持 `--json`、`--dry-run`、`--check-after` 并输出 changed files。
- `init`：生成标准或简化上下文模板，并在推断出的项目根目录生成缺失的薄入口 AGENTS.md；已有根入口默认不覆盖，需要 `--force-root-agent` 才覆盖。
- `simplify`：从已有上下文导出简化版本，保留真实 ADR 与 daily worklog，排除占位模板文件。
- `check`：检查目录、必需文件、UTF-8、乱码、空文件、内部 Markdown 引用、任务状态、决策状态、资料状态、ADR 状态一致性和 worklog 日期路径；`--strict` 会将占位符残留视为错误。
- `new task`：生成或重置 `active/Current_Task.md`，默认拒绝覆盖 Active 任务，除非传入 `--force`。
- `new source`：向 `reference/Sources_Index.md` 添加或更新资料索引行，默认拒绝重复资料标题，除非传入 `--force`。
- `new worklog`：按日期生成 daily worklog，并向 `worklog/Worklog_Index.md` 添加或更新索引行。
- `new adr`：生成下一个 ADR 文件，并按 Active 或 Proposed 状态更新 `reference/Decisions_Index.md`。
- `writeback draft`：把会话结束回写建议保存到 `worklog/writeback-drafts/`，生成可审阅草案，不直接修改权威上下文文件。

这些检查不需要模型判断，适合作为每次模板修改后的基础验证。

## 长期阶段计划：AI-facing CLI

长期方向是把 `acf` 从仓库内脚本演进为可安装、可在任意目录调用、主要面向 AI 使用的上下文维护 CLI。它的定位是上下文文件 API，而不是通用 Markdown 编辑器。

### 阶段 1：可安装命令和上下文发现

状态：已实现第一版。

目标：

- 提供可安装命令 `acf`，保留 `uv run python acf.py ...` 作为本仓库开发入口。
- 支持从任意子目录自动发现上下文根目录。
- 增加 `acf status`，输出当前项目根、上下文目录、profile、当前任务状态和最近检查结果。
- 写操作默认作用于发现到的上下文目录，也允许显式传入目标路径覆盖。

验收：

- 在项目任意子目录运行 `acf status` 能定位同一套上下文。
- 不传路径即可运行常用 `check` 和 `new` 命令。
- 无新增第三方运行依赖。

### 阶段 2：AI 友好输出和安全执行模式

状态：已实现第一版，并完成 JSON schema 基础字段、exit code 和错误分类细化。

目标：

- 全局支持 `--json`，让 AI 能稳定读取 changed files、warnings、errors 和 next actions。
- 全局支持 `--dry-run`，预览写入结果。
- 写命令输出被修改文件列表，并可选执行写后 `check`。
- 统一 exit code，区分成功、检查失败、输入错误和安全拒绝。

验收：

- AI 无需解析自然语言输出即可判断下一步。
- 所有写命令都有 dry-run 测试。
- 失败输出包含足够定位问题的信息。

已完成：

- `status --json` 和 `check --json` 输出可解析 JSON。
- JSON 输出包含 `schema_version`、`ok`、`error_code` 和 `next_actions`。
- 检查失败时 `error_code` 为 `check_failed`，AI 可以读取 `next_actions` 决定后续动作。
- 退出码已区分成功、检查失败、输入错误、安全拒绝和非预期运行时错误。
- 写命令输出 changed files，支持 `--dry-run --json` 预览。
- 写命令支持 `--check-after`。
- `check template` 会校验 `pyproject.toml` 中模板 data-files 与 `template/` 文件同步，避免打包漏文件。

### 阶段 3：安全结构化编辑

目标：

- 提供面向 AI 的结构化 Markdown 编辑原语，而不是自由文本编辑器。
- 支持 section get、section replace、section append。
- 支持 table upsert，用于维护索引类文件。
- 所有编辑必须限制在上下文根目录内，拒绝路径穿越。

验收：

- 常见上下文维护任务可以通过 CLI 完成，不需要 AI 手工拼接整文件。
- 写入后 `check --strict` 能稳定发现结构漂移。
- CLI 不理解语义，只做确定性文件编辑和校验。

### 阶段 4：草案和 subagent 接入

目标：

- 保持权威上下文由人或主代理审阅后写入。
- 让 subagent 产出分类草案或建议 patch，而不是静默修改权威文件。
- 优先完善 `writeback-curator`、`decision-curator`、`history-distiller` 和 `source-curator`。

验收：

- subagent 输出可以直接转成 `writeback draft` 或 dry-run patch。
- 权威文件写入仍有明确审阅点。
- 不引入常驻 runtime、数据库或私有存储。

### 阶段 5：跨项目 dogfooding 评测

目标：

- 在其他真实项目中验证初始化、发现、检查、写入和回写流程。
- 记录 AI 使用 CLI 与直接手改 Markdown 的错误率差异。
- 只把重复出现的人工动作产品化成新命令。

验收：

- 任意目录调用的成功率和错误信息可评估。
- 常见维护动作中，大多数可以由 CLI 完成。
- 新能力没有破坏“纯 Markdown、模型无关、人工可审阅”的边界。

## 适合继续程序化的工作

优先做可验证、低歧义、可回退的命令：

1. 根薄入口自定义字段：允许用户在生成时追加少量仓库级规则，但仍不把完整上下文写入根入口。
2. 安全结构化编辑原语：section get/replace/append 和 table upsert。
3. `writeback-curator` 接入：由 subagent 生成更高质量的回写分类草案，但仍只输出草案。

这些命令应默认只生成草案或骨架。真正写入权威上下文前，仍应由用户或主代理确认。

## 适合 subagent 的工作

subagent 适合处理需要语义判断、但不应静默修改权威文件的任务：

1. `readset-planner`：根据用户任务建议应读取哪些上下文文件，避免过读或漏读。
2. `writeback-curator`：把会话结果分类到 Context、Current_Task、Decision、Worklog、Archive。
3. `decision-curator`：判断某个结论是否应升格为 ADR，并草拟决策内容。
4. `history-distiller`：从 daily worklog 提炼关键结论，标记应同步到 Context 或 Decisions_Index 的候选内容。
5. `source-curator`：整理外部资料摘要、可信度和后续动作。

这些 subagent 的输出应是草案、评审意见或建议 patch，不应默认直接应用。

## 暂不建议自动化

以下内容现在不适合进入 MVP：

- 常驻 daemon 或 chat runtime。
- 向量库、数据库或私有格式存储。
- 通用 Markdown 编辑器。
- 让 CLI 进行语义判断或事实裁决。
- 让 subagent 自动修改 `active/Context.md`、`reference/Decisions_Index.md` 或 ADR 并静默提交。
- 用复杂编排替代当前的 Markdown 事实源。

原因是这些功能会削弱“模型无关、人工可审阅、文件即事实源”的设计边界，并提高调试和迁移成本。

## Dogfooding 规则

修改本项目时，应把本仓库当成第一个使用者：

1. Python 代码优先通过项目 uv 环境运行：`uv run python ...`。
2. acf CLI 优先通过项目 uv 入口运行：`uv run acf ...`；需要调试脚本入口时再使用 `uv run python acf.py ...`。
3. 模板结构变化后运行 `uv run acf check template`。
4. CLI 行为变化后运行 `uv run acf check --strict`、`uv run python -m unittest` 和 `uv run python -m py_compile acf.py tests\test_cli.py`。
5. minimal 实例不保留 ADR 和 worklog 的占位模板文件，真实条目通过 `new adr` 和 `new worklog` 生成。
6. 新增或重置当前任务时优先使用 `new task`，新增资料索引时优先使用 `new source`，重要设计决策优先使用 `new adr`，当天工作记录优先使用 `new worklog`。
7. 会话结束回写建议需要暂存时，优先使用 `writeback draft`，再由人或主代理审阅后决定是否写入权威上下文。
8. 修改 `template/` 前先确认该变更属于通用产品模板需求，而不是本仓库 dogfooding 特例。
9. 如果发现跨文件同步问题，优先考虑补充 `acf.py check` 规则，而不是只补文档说明。
10. 如果某项维护动作重复出现两次以上，评估是否应新增 CLI 子命令或 subagent 草案流程。
