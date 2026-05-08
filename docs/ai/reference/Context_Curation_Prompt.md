# ACF Context Curation Prompt

你正在整理一个使用 ACF（AI Context Framework）的项目上下文。

目标不是保存更多内容，而是维护一个低噪声、高权威、任务相关的默认注意力入口。

除非用户明确要求落盘，否则本 prompt 的默认产物是整理建议，不是文件修改。

---

## 核心原则

1. 默认上下文只保留当前目标、当前事实、当前任务和下一步。
2. 写入前必须判断唯一权威位置。
3. 能更新旧表述时，不追加重复事实。
4. worklog 记录历史过程，不作为当前事实。
5. archive 保存历史材料，默认不作为当前事实。
6. Feedback_Inbox 保存待处理信号，不作为已确认事实。
7. 不确定的内容不要升格为当前事实。
8. 不要为了整理而扩大读取范围；优先读取 active、相关索引、stale/curation signals 和必要的最近 worklog。

---

## 输入优先级

冲突时按以下顺序判断：

1. 用户当前指令
2. [active/Current_Task.md](../active/Current_Task.md)
3. [active/Task_Plan.md](../active/Task_Plan.md)
4. [active/Context.md](../active/Context.md)
5. [active/Feedback_Inbox.md](../active/Feedback_Inbox.md)，仅作为待处理信号
6. [reference/Decisions_Index.md](Decisions_Index.md)
7. `decisions/ADR-*.md`
8. [reference/Knowledge_Index.md](Knowledge_Index.md)
9. `worklog/`
10. `archive/`

---

## 推荐读取流程

先运行或读取以下结果：

```bash
acf status --json
acf check --strict --json
acf review stale --json
acf curate draft --dry-run --json
```

然后按需读取：

```text
active/Context.md
active/Current_Task.md
active/Task_Plan.md
active/Feedback_Inbox.md
reference/Decisions_Index.md
reference/Knowledge_Index.md
最近相关 worklog
```

不要默认读取：

```text
archive/
全部 worklog/
全部 ADR 正文
全部 reference 文档
```

只有在用户要求追溯历史、需要证据或存在明确冲突时，才读取这些内容。

---

## 整理任务

### 1. 当前事实整理

找出 [active/Context.md](../active/Context.md) 中：

- 仍然成立、应该保留的事实；
- 已过期、应删除或归档的事实；
- 与其他文件重复的事实；
- 表述过长、可以压缩的事实；
- 需要补充来源或审阅标记的事实。

输出时不要直接重写全文，先给出候选清单。

### 2. 任务状态整理

检查 [active/Current_Task.md](../active/Current_Task.md) 和 [active/Task_Plan.md](../active/Task_Plan.md)：

- 当前任务是否仍 Active；
- 是否缺少更新时间；
- 是否已经完成但未归档；
- Task_Plan 中是否有状态不一致；
- 是否有任务应该关闭、阻塞、完成或清空。

不要自动判定任务完成；只给出建议和需要确认的问题。

### 3. Feedback 整理

检查 [active/Feedback_Inbox.md](../active/Feedback_Inbox.md)：

- 哪些反馈仍待处理；
- 哪些已进入 Task_Plan；
- 哪些应升格为 Context 当前事实；
- 哪些应形成 Knowledge 或 ADR 候选；
- 哪些应关闭或归档；
- 哪些缺少日期、状态或证据。

Feedback_Inbox 不是当前事实源，不要把其中内容直接当成事实。

### 4. Knowledge / ADR 候选

判断是否存在：

- 可复用经验，应进入 Knowledge draft；
- 重要且长期有效的设计决策，应进入 ADR；
- 只属于历史过程的信息，应留在 worklog。

不要把普通过程记录升格为 Knowledge 或 ADR。

### 5. 重复和冲突整理

对于疑似重复或冲突内容，逐项输出：

- 文件 A / section；
- 文件 B / section；
- 冲突或重复点；
- 建议保留的唯一权威位置；
- 其他位置建议：删除、缩写为引用、归档、保留为历史；
- 需要用户确认的问题。

不要在没有证据时选择“谁是真的”。

---

## 输出格式

请按以下格式输出整理结果：

```markdown
# 上下文整理建议

## 总体判断

- 结构状态：
- 升级状态：
- stale / curation 状态：
- 当前主要风险：

## 建议保留的当前事实

| 权威位置 | 内容摘要 | 原因 | 是否需要修改 |
|---|---|---|---|

## 建议更新或替换的内容

| 文件 | section | 旧内容摘要 | 新建议 | 动作 |
|---|---|---|---|---|
```

动作只能使用：

- replace
- remove
- archive
- shorten_to_reference
- keep_as_history
- needs_human_confirmation

继续输出：

```markdown
## 建议归档或关闭的内容

| 文件 | 内容摘要 | 原因 | 建议动作 |
|---|---|---|---|

## 待确认问题

| 问题 | 为什么需要确认 | 建议确认人 |
|---|---|---|

## 建议使用的 acf 命令

先给 dry-run 命令，再给正式命令。
```

命令示例：

```bash
acf edit section replace active/Context.md --heading "## 当前有效事实" --input tmp/context-facts.md --dry-run --json
acf edit section replace active/Context.md --heading "## 当前有效事实" --input tmp/context-facts.md --check-after --json
```

最后列出“不执行的事项”，例如：

- 不自动判断事实真假；
- 不自动清空 Feedback_Inbox；
- 不自动归档 Current_Task；
- 不读取 archive；
- 不做语义级全量去重。

---

## 写入规则

如果用户要求你直接落盘：

1. 先说明将修改哪些文件。
2. 优先使用 acf 命令：
   - `edit section get / replace / append`
   - `edit table upsert`
   - `task / plan / archive / knowledge / new worklog`
3. 高风险修改先 dry-run。
4. 对 [active/Context.md](../active/Context.md) 优先 replace，不优先 append。
5. 不要把同一事实完整复制到多个文件。
6. 修改后运行：

```bash
acf check --strict --json
acf review stale --json
acf curate draft --dry-run --json
```

---

## 禁止事项

- 不要把 worklog 当作当前事实源。
- 不要把 Feedback_Inbox 当作已确认事实。
- 不要为了消除 stale signal 而伪造审阅结论。
- 不要自动判断用户意图已经改变。
- 不要自动删除不确定内容。
- 不要把 archive 加入默认读取路径。
- 不要输出大段重复原文；只输出摘要、位置和建议动作。
