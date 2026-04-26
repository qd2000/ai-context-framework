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
3. `acf.py` 是无第三方依赖的辅助 CLI，已支持 `init`、`simplify` 和 `check`。
4. `acf.py check --strict` 会把非模板文件中的占位符视为错误，并忽略明确模板文件中的占位符。
5. `docs/ai/` 当前应通过 `python acf.py check docs/ai --profile minimal --strict`。
6. 当前已有测试覆盖 CLI 的生成、检查、状态校验、索引一致性和 strict 模板文件忽略场景。
7. `../Automation.md` 记录自动化边界、后续 CLI 命令和 subagent 草案路线。
8. `template/` 中的占位符是产品模板内容，不是本仓库事实。

---

## 当前关键约束

1. 框架必须保持模型无关。
2. 权威上下文必须是普通 Markdown，并且可人工审阅。
3. CLI 不应引入第三方运行依赖。
4. 自动化应优先做确定性检查和草案生成，不替代人的事实判断。
5. 涉及模板结构变更时，需要同时验证模板和 dogfooding 实例。

---

## 当前开放问题

1. `new worklog`、`new adr`、`new task`、`new source` 的最小接口如何设计。
2. `writeback draft` 应接收什么输入格式，以及如何避免越权写入事实源。

---

## 重要决策

重要决策请查看：`reference/Decisions_Index.md`

---

## 当前相关路径

- 项目根目录：`E:\Codes\Tools\ai-context-framework`
- AI 文档目录：`docs/ai/`
- 产品模板目录：`template/`
- CLI：`acf.py`
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

- 日期：2026-04-26
- 更新原因：完成 strict dogfooding 检查语义，`docs/ai` 可作为真实上下文严格检查。
