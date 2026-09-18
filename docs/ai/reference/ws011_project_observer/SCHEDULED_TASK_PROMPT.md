# WS011 Scheduled Task Prompt

> Historical / Inactive since 2026-09-18. The WS011 Scheduled Task was deleted when the Project Observer product was retired in `v0.0.3.92`. This file is retained as historical evidence only and must not be re-registered as a live wrapper.

以下为 WS011 开发阶段 Scheduled Task wrapper。它只保留固定身份、项目访问工具和 ACF 自 dogfood 特有边界；generic continuation 协议由每轮安装态稳定 `acf continuation prompt` 动态生成。

---

@DevSpace Local

持续推进 ACF 项目 WS011「Project Observer 与自治可观测性」。

固定身份：

- Project：`D:\PROJECT\Tools\ai-context-framework`
- Worktree：`D:\PROJECT\Tools\ai-context-framework_worktrees\ws011-project-observer-autonomous-observability`
- Branch：`codex/ws011-project-observer-autonomous-observability`
- Workstream：`WS011`
- Continuation task-id：`WS011`
- Plan：`docs/ai/reference/ws011_project_observer/PLAN.md`
- Design：`docs/ai/reference/ws011_project_observer/DESIGN.md`

每次 Scheduled Task 都是独立无人值守 activation；本地 Git、Workstream、PLAN/DESIGN、continuation state、tests/evidence、Observer 输出和本轮工具结果是事实源，不依赖网页聊天历史恢复状态。

## Activation 强制规则

1. 第一有效动作必须调用当前 ACF 项目配置的 @DevSpace Local。
2. 必须打开且只使用上述固定 worktree，并执行至少一次本地命令获取本轮真实证据。
3. 未获得本轮工具输出前，不得输出当前进度、完成判断、下一步或假设性汇报。
4. DevSpace 连接失败时按合理方式重连；持续不可用才按 generated protocol 处理，禁止无工具编造进展。

进入 worktree 后读取根 `AGENTS.md`、`docs/ai/AGENTS.md`、`acf workstream context WS011`、当前 PLAN/DESIGN 和必要的最小上下文；验证 path、branch、registry/common-dir 后再写入。

每轮必须运行：

`acf continuation prompt "D:\PROJECT\Tools\ai-context-framework_worktrees\ws011-project-observer-autonomous-observability" --task-id WS011 --json`

将返回的 `prompt` 与 `execution_policy` 作为本轮唯一 generic continuation / contention / ownership / recovery / workspace / effect / checkpoint / release 协议。wrapper 不复制第二套 generic 状态机。

## 双控制面 dogfood 规则

- 已安装稳定 `acf` 是 WS011 continuation canonical control plane。
- Worktree 内 `uv run acf observer ...` 是 Observer 产品-under-test。
- 未发布候选 Observer 不得替换或直接重写稳定 continuation canonical state。
- 从第一个 `uv run acf observer` 命令可运行开始，每个实质阶段都必须真实观察 ACF 项目自身，检查用户级 observer state/history 和自包含 HTML。
- Observer Core 不得硬编码 `@DevSpace Local`、其他 MCP 名称、电脑名、盘符或项目实例；本 wrapper 中出现具体工具名只是当前项目访问合同。

## Project Observer 核心边界

- 一个项目一个 Global Observer；同一项目多个 worktree 统一观察。
- read broad / write narrow / control none：可以按需读取项目和所有相关 worktree，但 Observer 运行态只写用户级 `.acf/.../observer/`，不修改 Writer 项目文件或 continuation/workstream/effect 控制状态。
- 当前只实现自包含静态 HTML，不实现 HTTP 服务、daemon 或跨项目聚合。
- meaningful progress/history 默认永久保存，只允许无损 rotation，不自动删除。
- 主视图必须输出详细中文语义：当前问题、为什么现在做、最近证明/排除什么、意味着什么、下一步为什么这样走；不能只搬运内部编号或英文缩写。
- canonical 原始名称必须保留且可搜索/展开；翻译带 provenance/confidence/version，低置信度明确标注暂译。
- execution/progress/health 分离；没有明确分母时禁止生成假百分比。
- 颜色用于语义引导：红 critical、黄 warning、绿 healthy/verified、蓝 active/info、灰 technical/history；同时必须有文字/图标，且不使用夸张字号。
- 不把 API key、token、password、license、private key、fence token 或 credential 值复制到 Observer state/HTML。

按 PLAN 自主选择当前最有价值的实现范围和验证深度。subtask、test、commit、checkpoint 或 Gate 完成都不是停止理由；仍有安全、非重复、有价值工作就继续推进。

每个实质实现阶段后运行 development-state Observer dogfood，检查真实 ACF Dashboard/semantic timeline，并把发现的具体、可复用 ACF/Observer 缺陷用稳定控制面记录：

`acf continuation issue "D:\PROJECT\Tools\ai-context-framework_worktrees\ws011-project-observer-autonomous-observability" --task-id WS011 --category observer --severity high --text "concise reusable defect" --evidence-ref "durable evidence reference" --json`

实际记录时根据缺陷类型和严重程度替换 `--category`、`--severity`、`--text` 与 `--evidence-ref` 的值；示例中的 `observer/high` 不是固定分类。

只修改 WS011 scope 内文件；显式暂存已验证文件，禁止 `git add .`，禁止 stash/reset/clean/rebase/force 清除未知状态。CLI 修改按项目规则运行 focused tests、WS011 file-scoped guard、`git diff --check`、`uv run acf check template`、`uv run acf check --strict` 和适用 regression；release 前再运行 full/release gates。

发布硬门槛：Observer 功能完成、ACF 自 dogfood 连续多轮稳定、Observer 相关 high/critical issue 收口、文档/模板/测试同步并通过 release gate 之前，不得发布 PyPI、不得升级全局稳定 ACF。达到门槛后再执行 ACF-managed merge、release、PyPI publish、全局安装和安装态二次 dogfood。

最终汇报只基于本轮真实工具结果，说明当前阶段、实际完成内容、dogfood 结果、issues、验证、commit/checkpoint、continuation 状态和明确 next_action。
