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

实现 acf.py new source

---

## 本次任务目标

1. 统一 Sources_Index 为可由 CLI 维护的表格格式。
2. 新增 new source 命令，向 reference/Sources_Index.md 添加或更新资料条目。
3. 扩展 check_sources，校验表格资料状态。

---

## 任务背景

该任务由当前维护流程创建，需要写入当前任务文件以便协作过程可追踪。

---

## 输入材料

- 用户当前请求。
- `active/Context.md`。

---

## 输出要求

- acf.py 已新增 new source 子命令、source 索引更新逻辑和表格状态检查。
- tests/test_cli.py 已覆盖 source 生成、重复保护、force 更新和状态校验。
- README、System_Manual、Automation、template 与 docs/ai 上下文已同步。

---

## 成功标准

1. new source 能写入 Sources_Index 表格并通过 check。
2. 无效资料状态会被 check 检出。
3. 约定的 uv 验证命令通过。

---

## 失败信号

1. 目标无法验证。
2. 任务范围需要重新确认。

---

## 约束条件

1. Python 命令使用 uv run python。
2. 不引入第三方依赖。
3. template 保持通用产品模板语义。

---

## 不允许做的事

- 本轮不实现 writeback draft。
- 本轮不实现资料笔记全文生成。

---

## 需要 AI 协助判断的问题

1. 后续是否需要 source-curator 生成资料摘要草案。

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 应写入 `active/Context.md` 的新增当前事实。
2. 应写入 `reference/Decisions_Index.md` 或 ADR 的重要决策。
3. 应写入 rules 的新增规则。
4. 应归档到 archive 的历史内容。
