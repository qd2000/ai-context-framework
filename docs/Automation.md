# 自动化与 subagent 路线

本项目的核心价值是模型无关、纯 Markdown、可人工审阅的上下文治理。自动化的目标不是替代判断，而是减少结构漂移、索引遗漏和重复手工维护。

## 当前已自动化

`acf.py` 先覆盖确定性工作：

- `init`：生成标准或简化上下文模板。
- `simplify`：从已有上下文导出简化版本。
- `check`：检查目录、必需文件、UTF-8、乱码、空文件、内部 Markdown 引用、任务状态、决策状态、资料状态、ADR 状态一致性和 worklog 日期路径；`--strict` 会将非模板文件中的占位符视为错误。
- `new worklog`：按日期生成 daily worklog，并向 `worklog/Worklog_Index.md` 添加或更新索引行。
- `new adr`：生成下一个 ADR 文件，并按 Active 或 Proposed 状态更新 `reference/Decisions_Index.md`。

这些检查不需要模型判断，适合作为每次模板修改后的基础验证。

## 适合继续程序化的工作

优先做可验证、低歧义、可回退的命令：

1. `new task`：按模板生成或重置 `active/Current_Task.md`。
2. `new source`：向 `reference/Sources_Index.md` 添加资料条目。
3. `writeback draft`：读取会话结束回写建议，拆成 Context、Task、Decision、Worklog、Archive 草案，但不自动落盘。

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
- 让 subagent 自动修改 `active/Context.md`、`reference/Decisions_Index.md` 或 ADR 并静默提交。
- 用复杂编排替代当前的 Markdown 事实源。

原因是这些功能会削弱“模型无关、人工可审阅、文件即事实源”的设计边界，并提高调试和迁移成本。

## Dogfooding 规则

修改本项目时，应把本仓库当成第一个使用者：

1. Python 代码优先通过项目 uv 环境运行：`uv run python ...`。
2. 模板结构变化后运行 `uv run python acf.py check template`。
3. CLI 行为变化后运行 `uv run python acf.py check docs/ai --profile minimal --strict` 和 `uv run python -m unittest`。
4. 如果发现跨文件同步问题，优先考虑补充 `acf.py check` 规则，而不是只补文档说明。
5. 如果某项维护动作重复出现两次以上，评估是否应新增 CLI 子命令或 subagent 草案流程。
