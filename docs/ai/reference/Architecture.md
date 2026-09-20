本文件记录本仓库当前架构。

---

## 架构概览

本仓库由三层组成：

1. 产品模板层：`template/`，提供可复制的 AI context framework 标准结构。
2. CLI 自动化层：`ai_context_framework/` 包，提供初始化、检查、结构化写入、归档、Knowledge 和日志能力；顶层 `acf.py` 只是兼容 shim，转发到包的 runtime。
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

## runtime 组合契约

CLI 自动化层不接受隐式全局注入，组合方式固定如下（决策依据见 [ADR-0007](../decisions/ADR-0007.md)）：

- `ai_context_framework/runtime.py` 是组合入口：`build_parser()` 只调用各命令组的 `register_*_parser()` 完成命令树组合，`main()` 负责参数解析、执行与 usage log；它不再内联定义任何命令组。
- `ai_context_framework/runtime_parts/*` 提供领域实现，并用模块级 `__acf_exports__` 显式声明向 runtime 提供的名字；安装期对「未声明导出、声明缺失、同名不同对象」一律 fail-closed。
- `ai_context_framework/commands/*` 提供命令 handler 与命令组注册。命令模块可以 import `runtime_parts`，`runtime` 可以 import `commands`，但 `commands` 不得 import `runtime`。
- 共享的 argparse helper 与常量放在叶子模块 `ai_context_framework/cli_arguments.py` 与 `ai_context_framework/constants.py`，避免命令模块为取得 helper 而反向依赖 runtime。
- 命令组归属规则：解析器注册与其命令模块同置；当命令模块接近 2000 行可审阅门禁时，改用独立的 `*_parsers` 模块（例如 `commands/workstream_parsers.py`、`commands/continuation_group_parsers.py`）。
- `register_*_parser()` 必须显式接收 handler：CLI 绑定的是 `runtime_parts` 的 deps 适配器，而不是命令模块里的同名函数，二者不可互换。
- `runtime.set_root(root)` 是唯一受支持的 ROOT 重绑定入口；顶层 `acf.py` 只在自身 `ROOT` 与 `runtime.ROOT` 实际不同时调用它，不写 runtime 私有全局。

契约由两道自动护栏锁定：`tests/test_cli_surface_snapshot.py` 用 210 条路径快照锁定命令树形状（子命令、参数名、dest、nargs、default、choices、handler 限定名）；`scripts/runtime_export_audit.py` 断言导出表、消费者注入与动态访问无缺口。

---

## 关键边界

1. CLI 只做确定性落盘和检查，不替代人或 AI 的事实判断。
2. Knowledge 是可复用经验层，不是当前事实源。
3. usage event log 是运行态元数据，不进入项目 worklog。
4. archive 默认不读取，只在追溯历史时使用。

---

## 已知架构风险

1. 命令组分散到多个模块后，定位「某命令在哪里注册」依赖命名规则（命令模块或独立 `*_parsers` 模块），规则失效时会增加检索成本。
2. Markdown 表格编辑能力适合确定性维护，但不适合复杂语义迁移。
3. Knowledge 相似度检查是规则化近似检测，不是语义理解。
