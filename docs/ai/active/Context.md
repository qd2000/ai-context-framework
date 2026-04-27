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

1. 本仓库的核心产物是 `template/` 标准 AI 上下文模板。
2. `docs/ai/` 是本仓库真实使用中的 dogfooding 上下文实例。
3. `acf.py` 是无第三方依赖的辅助 CLI，已支持 `init`、`simplify`、`check`、`new task`、`new source`、`new worklog`、`new adr` 和 `writeback draft`。
4. `acf.py check --strict` 会把检查目标中的占位符残留视为错误。
5. 本仓库已使用 `pyproject.toml` 和 `uv.lock` 建立最小 uv Python 环境，Python 版本约束为 `>=3.10`。
6. 本仓库运行 Python 代码时，优先使用 `uv run python ...`。
7. `docs/ai/` 当前应通过 `uv run python acf.py check docs/ai --profile minimal --strict`。
8. 当前已有测试覆盖 CLI 的生成、检查、状态校验、索引一致性、strict 占位符检查、task 自动生成、source 自动生成、worklog 自动生成、ADR 自动生成和 writeback draft 场景。
9. `init --profile minimal` 和 `simplify` 不再向真实 minimal 实例复制 ADR 模板文件与 daily worklog 模板文件；真实 ADR 和 worklog 应通过 `new adr`、`new worklog` 生成，`simplify` 会保留已有真实 ADR 和 daily worklog。
10. `acf.py init` 会在推断出的项目根目录生成缺失的薄入口 AGENTS.md；已有根入口默认不覆盖，需要 force root agent 参数才覆盖。
11. 两层 AGENTS.md 设计已由 `decisions/ADR-0003.md` 记录：根目录薄入口负责发现和转发，上下文目录内入口负责完整导航。
12. `../Automation.md` 记录自动化边界、后续 CLI 命令和 subagent 草案路线。
13. `template/` 中的占位符是产品模板内容，不是本仓库事实。
14. `template/` 是面向使用者的产品源，新增或修改前应确认是通用模板需求；本仓库 dogfooding 特例应写入根入口、`docs/ai/` 或维护文档，不写入通用模板。
15. `writeback draft` 只生成 `worklog/writeback-drafts/` 下的可审阅草案，不直接修改权威上下文文件。
16. `decisions/ADR-0004.md` 已记录长期产品方向：`acf` 应演进为可安装、任意目录可调用、主要面向 AI 的上下文维护 CLI。
17. `../Automation.md` 已记录 AI-facing CLI 的阶段路线：可安装与上下文发现、AI 友好输出、安全结构化编辑、草案/subagent 接入、跨项目 dogfooding 评测。

---

## 当前关键约束

1. 框架必须保持模型无关。
2. 权威上下文必须是普通 Markdown，并且可人工审阅。
3. CLI 不应引入第三方运行依赖。
4. Python 命令应优先使用项目 uv 环境运行。
5. 自动化应优先做确定性检查和草案生成，不替代人的事实判断。
6. 涉及模板结构变更时，需要同时验证模板和 dogfooding 实例。
7. 新增或重置当前任务优先使用 `acf.py new task`；新增资料索引优先使用 `acf.py new source`；重要设计决策优先使用 `acf.py new adr`；当天工作记录优先使用 `acf.py new worklog`。
8. 会话结束回写建议需要暂存时优先使用 `acf.py writeback draft`，再审阅是否写入权威上下文。
9. 修改 `template/` 时，应同步检查 README、上下文入口说明和 System Manual 是否仍一致。
10. 任意目录 CLI 的设计应优先服务 AI 的确定性上下文维护，不扩展为自由文本编辑器或常驻运行时。

---

## 当前开放问题

1. 第一阶段是否先实现可安装命令、上下文自动发现和 `acf status`。
2. `--json`、`--dry-run` 和写后检查应如何作为全局能力接入现有子命令。
3. 安全结构化编辑的第一批原语是否限定为 section get/replace/append 和 table upsert。
4. 根薄入口生成是否需要支持少量用户自定义仓库规则字段。
5. 是否需要 `writeback-curator` subagent 生成更高质量的回写分类草案。

---

## 长期阶段计划：AI-facing CLI

定位：`acf` 是上下文文件 API，主要供 AI 在项目中稳定维护上下文；它不替代人的判断，也不作为通用 Markdown 编辑器。

1. 可安装命令和上下文发现：支持在任意子目录调用 `acf`，自动找到上下文根目录，并提供 `acf status`。
2. AI 友好输出和安全执行模式：支持 `--json`、`--dry-run`、统一 exit code、changed files 输出和写后检查。
3. 安全结构化编辑：提供 section 和 table 级别的确定性编辑，限制写入范围在上下文根目录内。
4. 草案和 subagent 接入：让 subagent 产出可审阅草案或建议 patch，不静默改写权威上下文。
5. 跨项目 dogfooding 评测：在真实项目中验证任意目录调用、检查、写入和回写流程。

详细路线和验收标准见：`../Automation.md`

---

## 已解决设计问题：AGENTS.md 的两层结构

### 已解决的问题

此前设计理念是"渐进式暴露"，但 `acf.py init` 的实现不完整：

- **设计理念**：根目录 AGENTS.md（薄入口） + docs/ai/AGENTS.md（完整入口）
- **README 说法**：第 46 行推荐"在项目根目录放置 AGENTS.md"
- **旧实现**：`acf.py init docs/ai` 只生成上下文目录内入口，不生成根目录版本
- **修复结果**：`acf.py init` 现在生成缺失的根薄入口，并保护已有根入口不被静默覆盖

### 设计意图确认

当前设计（两个 AGENTS.md）符合渐进式暴露原则：

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

**已完成**：
- 修改 `acf.py init` 逻辑，在推断出的项目根目录生成薄入口 AGENTS.md。
- 更新 README 和 template 入口说明，明确两层入口设计。
- 新增 `decisions/ADR-0003.md`，正式记录"渐进式暴露的两层 AGENTS.md 设计"。

**后续可选**：
- 根薄入口生成支持少量用户自定义仓库规则字段。
- 用其他真实项目验证改进后的初始化流程。

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
- 更新原因：写入 AI-facing CLI 长期阶段计划，并新增 `ADR-0004` 记录产品方向。
