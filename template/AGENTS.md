本文件告诉 AI 助手如何进入、理解和协助本项目。

**设计说明**：这是上下文目录内的完整入口文件，应该放在 docs/ai/AGENTS.md（项目初始化时自动复制）。
项目根目录应该有一个薄入口 `AGENTS.md` 文件，指向本文件的位置；`acf.py init` 会在缺失时生成该薄入口，且默认不覆盖已有根入口。
详见 README 中关于"两层 AGENTS.md 的设计"部分。

本项目采用分层上下文结构。不要默认扫描整个项目或读取所有文件。先读取当前有效上下文，再根据任务按需读取。

---

## 路径约定

本文件所在目录是 AI 上下文根目录。以下所有路径均相对于本文件所在目录。

---

## 核心原则

1. 不是所有保存的信息都应第一时间暴露给 AI。
2. AI 默认只读取当前有效、高信号、低噪音的上下文。
3. 历史记录、归档资料、原始日志默认不进入当前上下文。
4. 不同类型的信息有不同事实源，避免重复维护。
5. 如果不同文件之间出现冲突，应按事实源优先级判断。
6. 核心行为规则请遵守 `rules/Always_Active.md`。

---

## 目录结构

```text
active/      当前有效上下文，AI 默认优先读取
rules/       规则系统，按 always / requested / manual 分层
reference/   支持性资料、索引、摘要，按需读取
decisions/   重要决策详情，通常通过 Decisions_Index.md 进入
worklog/     整理后的工作记录，不是原始运行日志
archive/     历史归档，默认不读取
```

---

## 默认读取顺序

进入本项目后，请默认只读取以下文件：

1. `active/Context.md`
2. `rules/Always_Active.md`
3. `active/Current_Task.md`（仅当该文件存在且任务状态为 Active 时）

如果用户在当前消息中已给出明确任务，以用户当前消息为准，以上文件作为背景上下文。

---

## 按需读取指引

| 场景 | 读取文件 |
|------|----------|
| 需要理解项目长期背景 | `reference/Project_Brief.md` |
| 需要追溯重要决策 | `reference/Decisions_Index.md` → `decisions/ADR-*.md` |
| 涉及架构设计 | `reference/Architecture.md` |
| 涉及技术实现、运行环境 | `reference/Tech_Context.md` |
| 涉及外部资料来源 | `reference/Sources_Index.md` |
| 需要了解近期进展 | `worklog/Worklog_Index.md` → 最近 N 条 daily |
| 涉及项目通用约束 | `rules/Project_Rules.md` |
| 涉及代码实现 | `rules/Coding_Rules.md` |
| 涉及写作输出 | `rules/Writing_Rules.md` |
| 涉及方案评审 | `rules/Review_Rules.md` |
| 需要了解系统详细用法 | `reference/System_Manual.md` |

除上述场景外，不要默认读取 archive、完整 worklog、原始日志或所有 reference 文件。

---

## 事实源优先级

如果不同文件之间存在冲突，按以下优先级判断：

1. 用户当前消息
2. `active/Current_Task.md`
3. `active/Context.md`
4. `reference/Decisions_Index.md`
5. `decisions/` 中的 ADR 文件
6. `worklog/`
7. `archive/`

worklog 是历史过程记录，archive 是归档材料，均不等于当前事实。

---

## 目标信息来源

不同层级的目标由不同文件维护：

- 长期目标 / 项目愿景：`reference/Project_Brief.md`
- 当前阶段目标：`active/Context.md`
- 当前具体任务：`active/Current_Task.md`
- 当前用户临时需求：用户当前消息

---

## 输出格式要求

给出重要建议时，优先使用以下结构：

1. 结论
2. 理由
3. 风险
4. 可选方案
5. 建议下一步
6. 需要用户确认的事项

评审任务额外指出：最可能失败的地方、需验证的假设、信息不足之处。
设计任务额外区分：当前 MVP、后续扩展、不建议现在做的部分。

---

## 会话结束回写要求

每次重要协作结束时，AI 必须输出标准化的回写建议：

```markdown
## 会话结束回写建议

### Context.md 更新
- [具体变更内容，或"无需更新"]

### Current_Task.md 更新
- 状态变更：[Active → Done / 无变化]

### 新增决策
- [决策内容 + 建议 ADR 编号，或"无"]

### 今日 Worklog 条目
- [完成了什么 + 关键结论，或"无"]

### 需要归档的内容
- [或"无"]
```

最终是否写入，由用户决定。

---

## 详细使用手册

各目录的详细使用规则、资料处理、日志处理、不确定信息处理等，请参阅：

→ `reference/System_Manual.md`
