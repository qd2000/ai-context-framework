本文件记录本仓库当前架构。

---

## 架构概览

本仓库由三层组成：

1. 产品模板层：`template/`，提供可复制的 AI context framework 标准结构。
2. CLI 自动化层：`acf.py`，提供初始化、检查、结构化写入、归档、Knowledge 和日志能力。
3. Dogfooding 实例层：`docs/ai/`，记录本仓库真实使用中的上下文。

---

## 模块划分

### 模板模块

职责：

- 维护标准和简化上下文文件。
- 提供 AGENTS、active、rules、reference、decisions、worklog、archive 等结构。

输入：

- 框架设计决策。
- dogfooding 发现的问题。

输出：

- 可被 `acf init` 复制的模板文件。

### CLI 模块

职责：

- 复制模板、发现上下文、检查结构。
- 提供确定性 Markdown 写入原语。
- 管理任务计划、归档、Knowledge、usage log 和版本号。

输入：

- 命令行参数。
- 当前上下文 Markdown 文件。

输出：

- 更新后的 Markdown 文件。
- JSON 或文本命令结果。

### Dogfooding 模块

职责：

- 记录本仓库当前事实、规则、任务、决策和工作记录。
- 验证框架是否能支撑真实迭代。

输入：

- 用户反馈。
- CLI 实际使用结果。

输出：

- 改进计划、当前任务、worklog 和 ADR。

---

## 关键边界

1. CLI 只做确定性落盘和检查，不替代人或 AI 的事实判断。
2. Knowledge 是可复用经验层，不是当前事实源。
3. usage event log 是运行态元数据，不进入项目 worklog。
4. archive 默认不读取，只在追溯历史时使用。

---

## 已知架构风险

1. 单文件 `acf.py` 会随着命令增加而变大，后续可能需要模块化。
2. Markdown 表格编辑能力适合确定性维护，但不适合复杂语义迁移。
3. Knowledge 相似度检查是规则化近似检测，不是语义理解。
