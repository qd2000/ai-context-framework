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

补充 CLI 渐进式披露入口

---

## 本次任务目标

1. 让模板和 init 产物在默认入口中提示 AI 可用 acf 管理上下文。
2. 保持默认入口轻量，只提供工具发现路径，不写完整命令手册。
3. 通用模板不绑定本仓库 uv dogfooding 运行方式。

---

## 任务背景

模板入口、minimal init 产物和当前 dogfooding 入口的 CLI 渐进式披露已完成。

---

## 输入材料

- template AGENTS 入口。
- minimal AGENTS 生成字符串。
- template Project Rules 和 System Manual。

---

## 输出要求

- 模板和 minimal init 产物包含 CLI 辅助维护提示。
- 测试覆盖 minimal 和 standard init 的 AGENTS CLI 发现提示。
- dogfooding 上下文和 worklog 已同步。

---

## 成功标准

1. 默认入口提示 acf status --json、acf --help 和按需读取系统手册。
2. System Manual 首选 acf 命令，python acf.py 只作为未安装兼容方式。
3. 完整 uv 验证通过。

---

## 失败信号

1. 目标无法验证。
2. 任务范围需要重新确认。

---

## 约束条件

1. 不新增 CLI 行为。
2. 不在根薄入口加入完整 CLI 说明。
3. 不把 uv 写入通用模板。

---

## 不允许做的事

- 不实现阶段 4 subagent 接入。

---

## 需要 AI 协助判断的问题

1. 无。

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 应写入 `active/Context.md` 的新增当前事实。
2. 应写入 `reference/Decisions_Index.md` 或 ADR 的重要决策。
3. 应写入 rules 的新增规则。
4. 应归档到 archive 的历史内容。
