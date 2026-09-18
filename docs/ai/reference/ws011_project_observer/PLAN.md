# WS011 Project Observer 实施计划

> Historical / Inactive since 2026-09-18. The Project Observer product was retired in `v0.0.3.92`; this plan is historical implementation evidence for WS011 and is not a current roadmap.

## 1. 任务定位

WS011 实现 ACF Project Observer：一个项目一个 Global Observer，统一观察同一项目内所有相关 worktree，将机器执行状态转换为详细、易懂、可追溯的人类语义进展，并以用户级结构化状态和自包含静态 HTML 持久化。

完整架构事实源：`docs/ai/reference/ws011_project_observer/DESIGN.md`。

本计划只定义实施顺序、验收、dogfood 和发布门槛。

---

## 2. 固定执行身份

- Workstream：`WS011`
- Branch：`codex/ws011-project-observer-autonomous-observability`
- Worktree：由 `acf worktree verify --workstream WS011` 的本地 registry 绑定为权威；当前开发实例位于 `D:\PROJECT\Tools\ai-context-framework_worktrees\ws011-project-observer-autonomous-observability`
- Continuation task-id：`WS011`
- 稳定控制面：当前机器已安装稳定 `acf`
- Observer 产品-under-test：worktree 内 `uv run acf observer ...`

稳定 continuation 与开发态 Observer 必须分离：开发态 Observer 可以读取并展示 ACF 自身状态，但未发布候选不得替换稳定 continuation canonical state。

---

## 3. 成功标准

### 3.1 架构

1. Observer Core 不硬编码 MCP、电脑、盘符、特定项目或特定 VM 名称。
2. 项目访问工具由外部 wrapper / adapter 注入。
3. Observer 广泛读取，但运行态只写用户级 `.acf/.../observer/`。
4. Observer 不参与 Writer ownership/recovery/effect/control。
5. 当前不引入 HTTP server、daemon、数据库、向量库或第三方运行依赖。

### 3.2 数据

1. current / timeline / observations / alerts / runs / workstream semantic state 均有稳定 schema。
2. history 默认永久保留；只允许无损 rotation，不自动删除 meaningful history。
3. current/HTML 等覆盖文件原子写入。
4. Observer 自身有 lock、self-health、data age、snapshot consistency。
5. sensitive value 不进入 Observer state/HTML。

### 3.3 语义

1. Dashboard 主视图不只显示内部编号或英文 technical stage。
2. 每个 Workstream 至少解释：当前问题、为什么现在做、最近证明/排除什么、意味着什么、下一步及原因。
3. canonical identity 永久保留并可检索。
4. glossary、confidence、provenance、interpretation history 可审计。
5. 不制造没有明确分母的假进度百分比。

### 3.4 展示

1. 生成可直接 `file://` 打开的自包含 HTML。
2. 红/黄/绿/蓝/灰颜色具有固定语义，同时有文字/图标，不以颜色作为唯一信息载体。
3. 不使用夸张 Hero 字号，适合持续阅读。
4. 支持项目总览、alerts、Workstream 详情、语义 timeline、技术详情展开和基本筛选/搜索。

### 3.5 Dogfood / 发布

1. ACF 项目是第一个 dogfood 项目。
2. 第一版命令可运行后，每个实质阶段必须使用 `uv run acf observer ...` 真实观察本项目。
3. 发现可复用 ACF/Observer 缺陷立即通过稳定控制面记录 issue。
4. Observer 相关 high/critical issue 在发布前必须收口或有明确不发布决定。
5. 多轮 ACF 自 dogfood 稳定后才允许 merge/release/PyPI/global install。

---

## 4. 实施阶段

### WS011.1 设计冻结与 CLI / schema 骨架

目标：把完整设计转成可测试的产品合同，而不是先写 renderer 再补生命周期。

工作：

- 固化 CLI 命令族，例如：
  - `acf observer snapshot`
  - `acf observer update`
  - `acf observer status`
  - `acf observer render`
  - 后续按实际实现合并或调整，但保持 read/normalize/render 职责清晰；
- 定义 project observer directory discovery；
- 定义 current/event/run/alert/semantic/self-health schema；
- 定义 canonical identity / semantic / confidence / provenance 字段；
- 定义 observer lock 和 atomic-write contract；
- 先写 schema/CLI failure-mode tests。

验收：

- parser / JSON envelope 稳定；
- `--json`、`error_code`、`next_actions` 可机器解析；
- observer 目录只位于用户级 ACF state；
- 未扫描项目时不会写项目文件。

### WS011.2 Project / Worktree / ACF 只读 Snapshot

目标：建立真正不参与控制面的项目观察事实层。

工作：

- project identity / context discovery；
- worktree registry / Git status / HEAD；
- Workstream summary/detail pointer；
- continuation state 的 Observer-safe 读取；
- 识别 current execution/progress/health 原始信号；
- start/end fingerprint 与一次稳定重读；
- `snapshot_consistency` 输出；
- 明确测试普通观察不 ACK challenge、不改 lease、不改 workspace owner、不改 effect。

验收：

- 对 ACF 自己的多个 worktree 生成稳定 snapshot；
- project Git 工作区除预先存在状态外零新增修改；
- 控制面文件 digest 在观察前后不因 Observer 改变。

### WS011.3 历史、事件与自健康

目标：完整保留有信息价值的进展，同时避免重复全量 snapshot 膨胀。

工作：

- `runs.jsonl` liveness；
- meaningful timeline event detection；
- unchanged milestone observation；
- alerts lifecycle；
- monthly / lifecycle rotation without deletion；
- archive 语义；
- observer_status / data age；
- overlap lock；
- interrupted write recovery。

验收：

- 同状态连续观察不复制全量历史；
- meaningful event 永久可追溯；
- 分片后能重建完整 timeline；
- render 失败保留上一有效页面。

### WS011.4 Semantic Observation Layer

目标：从“状态监控”升级为“项目进展解释器”。

工作：

- 渐进式读取 Workstream + continuation + PLAN + 当前阶段 evidence；
- canonical term → human title / explanation；
- current focus / why-now / recent-proof / implication / next-step；
- meaningful progress event 聚合；
- glossary；
- confidence；
- provenance；
- interpretation version/history；
- 防止旧 semantic cache 覆盖当前项目事实；
- 为开放研究任务禁止假百分比。

验收：

- ACF WS011 自己的进展可以被解释成中文完整逻辑，而不只是 `WS011.4 / running`；
- 原始 technical term 可一键对应；
- 低置信度解释明确标记“暂译/当前理解”；
- 语义解释变化产生可审计事件。

### WS011.5 静态 HTML Renderer

目标：把 Observer state 转成可长期阅读的自包含项目 Dashboard。

工作：

- 项目总览 / self-health / data age；
- current alerts；
- Workstream semantic cards；
- execution / progress / health 分离；
- semantic timeline；
- canonical technical detail；
- 搜索 / 筛选 / 折叠；
- 内嵌数据；
- 颜色语义；
- 无障碍颜色冗余表达；
- 克制字体层级；
- secret-safe rendering。

验收：

- `file://` 可直接打开；
- 不需要 HTTP；
- 页面在较窄宽度仍可读；
- 不使用夸张字号；
- 重要异常通过颜色+文字+图标明显呈现。

### WS011.6 ACF 开发态自 dogfood

目标：在发布之前让 Observer 长时间真实观察自己的开发项目和自己的 Workstream。

每轮 Scheduled Task：

1. 用稳定安装态 `acf continuation prompt` 获取 WS011 continuation 协议；
2. 继续开发当前未完成能力；
3. 一旦 `uv run acf observer` 可运行，就在同轮用开发态 Observer 观察 ACF 项目；
4. 打开/解析生成的 current/timeline/HTML，确认语义、历史、一致性和视觉结果；
5. 将可复用问题通过稳定 `acf continuation issue` 记录；
6. 继续修复，而不是因为一次 Gate/commit/checkpoint 就结束。

重点 dogfood：

- Observer 是否能发现当前 WS011 与其他 registry worktree；
- 是否错误影响 writer/control plane；
- 一致性重读是否在真实并发下有效；
- 历史是否去重但不丢 meaningful progress；
- 中文语义是否真正易懂；
- technical identity 是否可追溯；
- Dashboard 颜色是否能快速引导注意；
- 长历史是否仍能快速加载/更新；
- sensitive content 是否被过滤。

### WS011.7 多轮稳定性与异常场景

目标：在真实长任务边界下证明 Observer 不会变成新的阻塞源。

覆盖：

- Observer activation overlap；
- Writer 在扫描中改变 HEAD/state；
- stale/expired/active lease；
- unresolved effect；
- Workstream complete/archive；
- 无 workstream 项目；
- 多 worktree；
- 语义来源缺失；
- 低置信度翻译；
- 大 timeline 分片；
- render interruption；
- observer state schema migration。

### WS011.8 产品文档、模板和回归

同步：

- `README.md`；
- `docs/Automation.md`；
- dogfooding `System_Manual.md`；
- template `System_Manual.md`；
- CLI help；
- minimal smoke；
- unit tests；
- 必要 upgrade matrix。

要求 Observer Core 的文档示例使用抽象“项目访问工具”，不得把某个 MCP 名称写成通用产品前提。

### WS011.9 发布与安装态二次 dogfood

只有前述 Gate 全部满足后：

1. full/release check；
2. ACF-managed merge；
3. version/release；
4. PyPI publish；
5. 全局稳定 ACF 更新；
6. 使用全局稳定 `acf observer` 再观察 ACF 项目；
7. 与开发态最终 golden output 对比；
8. 无新增高严重度回归后完成 WS011 archive/closeout。

---

## 5. 实施原则

1. 完整设计，分阶段实现；不得为了“先能跑”删除已经确认的生命周期要求。
2. 先稳定数据层和安全边界，再做语义和 HTML，不让 renderer 成为事实源。
3. 不添加第三方运行依赖。
4. 不把 ACF 变成 daemon、常驻 agent runtime、数据库或私有 scheduler。
5. 每个阶段形成自然 semantic checkpoint，但 checkpoint/commit/Gate 均不是 activation 停止信号。
6. 新发现的可复用 ACF/Observer 缺陷使用稳定 `acf continuation issue` 记录稳定 fingerprint。
7. 不修与 Observer 无关的历史 issue，除非它直接阻塞 WS011 dogfood；通用 issue backlog 在 WS011 之外继续单独整理。

---

## 6. 当前 next_action

完成 WS011 continuation 初始化和 Scheduled Task 接入，然后进入 WS011.1：先实现 CLI/schema/observer-directory/atomic-write/lock 的基础合同与测试；一旦首个 development-state observer 命令可运行，立即开始 ACF 自 dogfood，不等待完整 HTML 完成。
