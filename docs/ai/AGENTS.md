本文件告诉 AI 助手如何进入、理解和协助本项目。

本目录是简化版 AI 上下文根目录。默认只读取当前有效上下文和核心规则，其他资料按需读取。

---

## 默认读取顺序

1. `active/Context.md`
2. `rules/Always_Active.md`
3. `active/Current_Task.md`（仅当任务状态为 Active 时）

如果用户在当前消息中已给出明确任务，以用户当前消息为准。

---

## 目录结构

```text
active/      当前阶段上下文和当前任务
rules/       核心规则
reference/   长期背景、资料索引和决策索引
decisions/   重要决策详情
worklog/     整理后的工作记录
```

---

## 按需读取指引

| 场景 | 读取文件 |
|---|---|
| 需要理解长期背景 | `reference/Project_Brief.md` |
| 需要追溯重要决策 | `reference/Decisions_Index.md` -> `decisions/ADR-*.md` |
| 涉及项目通用约束 | `rules/Project_Rules.md` |
| 需要了解近期进展 | `worklog/Worklog_Index.md` |
| 涉及外部资料来源 | `reference/Sources_Index.md` |

---

## 事实源优先级

1. 用户当前消息
2. `active/Current_Task.md`
3. `active/Context.md`
4. `reference/Decisions_Index.md`
5. ADR 文件
6. `worklog/`

worklog 是历史过程记录，不等于当前事实。

---

## 会话结束回写建议

重要协作结束时，请给出以下建议，由用户决定是否写入：

- `active/Context.md` 是否需要更新
- `active/Current_Task.md` 状态是否需要变化
- 是否需要新增 ADR 或更新 `reference/Decisions_Index.md`
- 是否需要新增 worklog 条目
