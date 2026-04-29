本文件记录本仓库 AI context framework 的维护手册摘要。

完整产品手册以仓库模板目录中的 System_Manual 为源；本文件只记录 dogfooding 实例中的项目内维护要点。

---

## 当前上下文层级

1. `active/Context.md`：当前阶段事实。
2. `active/Feedback_Inbox.md`：人工临时反馈、问题、需求和计划碎片。
3. `active/Task_Plan.md`：当前大任务计划和子任务板。
4. `active/Current_Task.md`：当前具体任务。
5. `rules/`：默认和按需规则。
6. `reference/`：长期背景、架构、技术环境、决策和 Knowledge 索引。
7. `worklog/`：历史工作记录。
8. `archive/`：旧任务和旧计划归档。

---

## 常用维护命令

- `uv run acf status --json`
- `uv run acf upgrade docs/ai --dry-run --json`
- 通用升级形式：`acf upgrade [target]`
- `uv run acf check --strict`
- `uv run acf plan status docs/ai --json`
- `uv run acf log summarize --days 7 --json`
- `uv run acf version show --json`
- `uv run acf version set v0.0.3.2 --dry-run --json`

PowerShell 中反引号是转义字符。写入包含 Markdown 反引号或多行正文时，优先使用 `--input <file>`。

---

## 人工反馈处理

1. 人工可直接写入 `active/Feedback_Inbox.md`。
2. AI 处理 Open 条目时，先判断归属。
3. 可执行事项进入 `active/Task_Plan.md`。
4. 当前事实进入 `active/Context.md`。
5. 重要决策进入 ADR。
6. 历史过程进入 worklog。
7. 可复用经验进入 Knowledge 草案流程。
8. Done/Rejected 条目必须保留证据位置或拒绝原因；超过 10 条，或完成超过 30 天且不再支撑当前计划时，整理到 `archive/feedback/`。

## 会话结束回写

1. 不再默认打印完整“无需更新”清单。
2. 可确定的计划、任务、Context、worklog、Knowledge、archive 或 ADR/rules 变化，优先用 `acf` 命令或结构化编辑落盘。
3. 不能安全落盘但需要保留的判断，生成 `writeback draft` 草案。
4. 最终回复只报告实际修改、草案路径、验证结果和仍需人工判断的风险。

---

## Strict 检查策略

真实项目 strict 检查不应被标准模板中的示例文件阻塞。ADR template 和 YYYY-MM-DD daily worklog 是模板示例，不是项目事实；模板源自身仍应通过 `acf check template` 暴露占位符 warning。

---

## Upgrade 兼容性维护

开发修改 `template/`、默认上下文结构、打包清单或 `acf upgrade` 行为时，必须同时评估旧版本上下文的升级路径：

1. 新增目录或文件时，同步更新 init 文件清单、upgrade 补齐清单和 `pyproject.toml` data-files。
2. 修改入口、手册或默认读取顺序时，检查 `acf upgrade` 是否能非破坏式更新旧 AGENTS/System Manual，不能安全重排时应追加 marker notes。
3. 补充或更新 init/upgrade 单元测试，覆盖新项目生成和旧项目 dry-run/正式 upgrade。
4. 验证 `uv run acf check template`、`uv run acf upgrade docs/ai --dry-run --json`、`uv run acf check docs/ai --strict --json` 和 `uv run python -m unittest`。
