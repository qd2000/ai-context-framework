本文件记录当前正在处理的具体任务。

- 长期目标请查看：`reference/Project_Brief.md`
- 当前阶段目标请查看：`active/Context.md`
- 本文件只维护当前具体任务

如果用户在当前对话中提出了新的具体需求，并且该需求与本文件冲突，以用户当前消息为准。

---

## 当前任务状态

Done

说明：

- Active：当前任务正在进行
- Paused：当前任务暂停
- Done：当前任务已完成
- Empty：暂无需要写入文件的当前任务

---

## 任务名称

实现 acf.py new task

---

## 本次任务目标

1. 新增确定性命令生成 active/Current_Task.md。
2. 默认保护 Active 任务，覆盖时要求 --force。
3. 同步 README、System_Manual、Automation 和 dogfooding 上下文。

---

## 任务背景

该任务由当前维护流程创建，需要写入当前任务文件以便协作过程可追踪。

---

## 输入材料

- 用户当前请求。
- `active/Context.md`。

---

## 输出要求

- acf.py 新增 new task 子命令。
- tests/test_cli.py 覆盖生成、状态校验和 Active 覆盖保护。
- README、System_Manual、Automation 和 docs/ai 上下文已同步。

---

## 成功标准

1. new task 能生成无占位符且状态有效的 Current_Task 文件。
2. Active 任务未传 --force 时不会被静默覆盖。
3. 约定的 uv 验证命令通过。

---

## 失败信号

1. 目标无法验证。
2. 任务范围需要重新确认。

---

## 约束条件

1. 不引入第三方依赖。
2. 保持 template 的通用性。

---

## 不允许做的事

- 本轮不实现 new source。
- 本轮不实现 writeback draft。

---

## 需要 AI 协助判断的问题

1. new source 和 writeback draft 的最小接口后续如何设计。

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 应写入 `active/Context.md` 的新增当前事实。
2. 应写入 `reference/Decisions_Index.md` 或 ADR 的重要决策。
3. 应写入 rules 的新增规则。
4. 应归档到 archive 的历史内容。
