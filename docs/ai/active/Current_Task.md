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

修复 AGENTS.md 生成并同步 template 设计约束

---

## 本次任务目标

1. 让 acf.py init 生成根目录薄入口 AGENTS.md，并保护已有入口不被静默覆盖。
2. 用正确 ADR 编号记录两层 AGENTS.md 设计。
3. 将 template 设计理念和后续维护要求同步到 dogfooding 上下文。

---

## 任务背景

该任务由当前维护流程创建，需要写入当前任务文件以便协作过程可追踪。

---

## 输入材料

- 用户当前请求。
- `active/Context.md`。

---

## 输出要求

- acf.py 已新增根薄入口生成逻辑和 --force-root-agent 参数。
- tests/test_cli.py 已覆盖根薄入口生成、默认不覆盖和显式覆盖。
- ADR-0003、Context、Project_Rules、Project_Brief、Automation、README、System_Manual 和 worklog 已同步。

---

## 成功标准

1. init docs/ai 会生成根薄入口和 docs/ai 完整入口。
2. 已有根 AGENTS.md 默认不会被覆盖，显式参数才覆盖。
3. docs/ai --strict、template check、unittest 和 py_compile 均通过。

---

## 失败信号

1. 目标无法验证。
2. 任务范围需要重新确认。

---

## 约束条件

1. Python 命令使用 uv run python。
2. 不引入第三方依赖。
3. template 保持模型无关和通用性。

---

## 不允许做的事

- 本轮不实现 new source。
- 本轮不实现 writeback draft。

---

## 需要 AI 协助判断的问题

1. 根薄入口生成是否还需要后续支持自定义项目规则字段。

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 应写入 `active/Context.md` 的新增当前事实。
2. 应写入 `reference/Decisions_Index.md` 或 ADR 的重要决策。
3. 应写入 rules 的新增规则。
4. 应归档到 archive 的历史内容。
