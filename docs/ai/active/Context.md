本文件记录项目当前阶段的有效上下文。

- 长期目标请查看：`reference/Project_Brief.md`
- 当前具体任务请查看：`active/Current_Task.md`
- 本文件只维护当前阶段目标和当前有效事实

---

## 当前阶段

Dogfooding MVP / 框架稳定化。

---

## 当前阶段目标

1. 验证本框架可以作为本仓库自身的 AI 上下文系统使用。
2. 用 `acf.py` 将模板生成、简化和完整度检查自动化，降低人工维护成本。
3. 规划并逐步实现下一批确定性维护命令。

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
- 不让 subagent 静默修改权威上下文。
- 不把 `template/` 的占位内容当作当前项目事实。

---

## 当前有效事实

1. 本仓库的核心产物是 `template/` 标准 AI 上下文模板。
2. `docs/ai/` 是本仓库真实使用中的 dogfooding 上下文实例。
3. `acf.py` 是无第三方依赖的辅助 CLI，已支持 `init`、`simplify`、`check`、`new task`、`new worklog` 和 `new adr`。
4. `acf.py check --strict` 会把检查目标中的占位符残留视为错误。
5. 本仓库已使用 `pyproject.toml` 和 `uv.lock` 建立最小 uv Python 环境，Python 版本约束为 `>=3.10`。
6. 本仓库运行 Python 代码时，优先使用 `uv run python ...`。
7. `docs/ai/` 当前应通过 `uv run python acf.py check docs/ai --profile minimal --strict`。
8. 当前已有测试覆盖 CLI 的生成、检查、状态校验、索引一致性、strict 占位符检查、task 自动生成、worklog 自动生成和 ADR 自动生成场景。
9. `init --profile minimal` 和 `simplify` 不再向真实 minimal 实例复制 ADR 模板文件与 daily worklog 模板文件；真实 ADR 和 worklog 应通过 `new adr`、`new worklog` 生成，`simplify` 会保留已有真实 ADR 和 daily worklog。
10. `../Automation.md` 记录自动化边界、后续 CLI 命令和 subagent 草案路线。
11. `template/` 中的占位符是产品模板内容，不是本仓库事实。

---

## 当前关键约束

1. 框架必须保持模型无关。
2. 权威上下文必须是普通 Markdown，并且可人工审阅。
3. CLI 不应引入第三方运行依赖。
4. Python 命令应优先使用项目 uv 环境运行。
5. 自动化应优先做确定性检查和草案生成，不替代人的事实判断。
6. 涉及模板结构变更时，需要同时验证模板和 dogfooding 实例。

---

## 当前开放问题

1. `new source` 的最小接口如何设计。
2. `writeback draft` 应接收什么输入格式，以及如何避免越权写入事实源。
3. **新发现：根目录 AGENTS.md 的生成与设计** - 见下方详述。

---

## 设计问题：AGENTS.md 的两层结构

### 问题描述

当前设计理念是"渐进式暴露"，但 `acf.py init` 的实现不完整：

- **设计理念**：根目录 AGENTS.md（薄入口） + docs/ai/AGENTS.md（完整入口）
- **README 说法**：第 46 行推荐"在项目根目录放置 AGENTS.md"
- **实际情况**：`acf.py init docs/ai` 只生成 docs/ai/AGENTS.md，不生成根目录版本
- **结果**：新项目初始化后，根目录没有入口文件，用户困惑

### 设计意图确认

经过讨论，当前设计（两个 AGENTS.md）是**符合渐进式暴露原则的**：

1. **根目录 AGENTS.md**（薄入口）
   - 角色：最轻量级的仓库级配置
   - 内容：简要说明 + "详见 docs/ai/AGENTS.md" 转发
   - 维护者：仓库框架维护者
   - 频率：很少改动

2. **docs/ai/AGENTS.md**（完整入口）
   - 角色：项目当前上下文的完整导航
   - 内容：默认读取顺序 + 按需读取指引 + 事实源优先级
   - 维护者：项目团队 + AI 协作
   - 频率：按项目阶段更新

### 后续改进方向

**优先级 1（MVP 后立即改进）**：
- 修改 `acf.py init` 逻辑，在 target 根目录生成薄入口 AGENTS.md
- 更新 README 第 43-48 行的"使用方法"部分，明确说明这个两层设计

**优先级 2（文档完善）**：
- 在 decisions/ 中创建 ADR-0002，正式记录"渐进式暴露的两层 AGENTS.md 设计"
- 在 template/AGENTS.md 顶部添加注释，说明它是"上下文内的完整入口，不是根目录版本"

**优先级 3（验证）**：
- 用 KnowledgeConnector 项目验证改进后的初始化流程

---

## 重要决策

重要决策请查看：`reference/Decisions_Index.md`

---

## 当前相关路径

- 项目根目录：`E:\Codes\Tools\ai-context-framework`
- AI 文档目录：`docs/ai/`
- 产品模板目录：`template/`
- CLI：`acf.py`
- Python 项目配置：`pyproject.toml`
- uv 锁文件：`uv.lock`
- 自动化路线：`../Automation.md`
- 资料索引：`reference/Sources_Index.md`
- 工作记录索引：`worklog/Worklog_Index.md`

---

## 容易误解的地方

1. `template/` 是产品模板，不是本仓库当前事实源。
2. `docs/ai/` 是真实 dogfooding 实例，优先级高于模板占位内容。
3. worklog 是历史过程记录，不等于当前事实。
4. subagent 适合产出草案和审阅意见，不应默认静默落盘到权威上下文。

---

## 上次更新

- 日期：2026-04-27
- 更新原因：实现 `acf.py new task`，将当前任务文件维护纳入确定性 CLI 流程。
