本文件是会话结束回写草案，不是当前事实源。

请人工审阅后，再决定是否使用 CLI 或手工方式写入权威上下文。

---

## 草案名称

2026-06-09-fcc-workspace-monitor-acf-improvements

---

## 原始回写建议

```text
# fcc_workspace monitor surfaced ACF improvement candidates

来源：2026-06-09 fcc_workspace docs/ai context monitor。

## 现象

1. 在 `/mnt/e/Codes/fcc_workspace` 中，裸 `uv run acf ...` 和项目规则推荐的 `wuv run acf ...` 都调用到 `/home/qiudong/.local/bin/acf`，并在导入 `/mnt/e/Codes/Tools/ai-context-framework/acf.py` 时失败：`ModuleNotFoundError: No module named 'ai_context_framework'`。通过 `PYTHONPATH=/mnt/e/Codes/Tools/ai-context-framework wuv run python /mnt/e/Codes/Tools/ai-context-framework/acf.py ...` 可绕过并执行检查。
2. `acf check docs/ai --strict --json` 报 fcc_workspace 的 `active/workstreams/WS030 dot md` 中 `blocking_depends_on` / `consumer_context` front matter 字段不被 schema 允许，同时拒绝 `WS030.1b`、`WS030.2a`、`WS030.2b` 这类字母后缀 stage id，并认为 `current_stage: WS030.1b` 无效。实际项目用这些字段和 stage id 表达跨 workstream 阻塞依赖、下游消费语境和细分阶段，属于自然的复杂 workstream 命名/元数据需求；需要决定是扩展 schema，还是在文档/错误提示中明确允许字段和推荐替代写法。

## 建议

- 将 CLI 可安装/任意目录调用问题纳入后续 P2/P3 维护：确认用户级 `acf` shim、editable/source checkout、uv/wuv 环境组合下的 import 路径，避免跨项目 dogfooding 时需要手动 `PYTHONPATH`。
- 评估 workstream schema：若接受字母后缀，补测试覆盖 `WS030.1b` / `WS030.2a` / `WS030.2b`；若不接受，改 validator message 和 manual，提示使用 `WS030.2.1` 或纯数字阶段。
- 评估 `blocking_depends_on` / `consumer_context` 这类扩展 front matter 是否应进入正式 schema；如果不进入，提供推荐承载位置，例如正文 `Context Packet` 或 `depends_on` 的结构化扩展。
- 这两项还不是当前事实；建议进入 Feedback_Inbox 或下一轮 Task_Plan，而非直接写入 Context。
```

---

## 当前事实变更候选

- 目标文件：
- 旧表述：
- 新表述：
- 建议动作：replace / append / remove / archive
- 原因：

---

## 唯一权威位置判断

- 信息类型：
- 权威位置：
- 其他位置是否已有重复：
- 建议处理：

---

## 应只保留为历史的信息

- 内容摘要：
- 建议位置：worklog / archive
- 不进入 active 的原因：

---

## 待确认信号

- 内容：
- 建议位置：Feedback_Inbox / writeback draft
- 需要谁确认：

---

## 可升格候选

- ADR 候选：
- Knowledge 候选：
- rules 候选：
- source 候选：

---

## 建议命令

- 当前任务或计划：优先使用 `acf task ...` 或 `acf plan ...`。
- 当前事实：优先使用 `acf edit section get|replace ...`，能 replace 时不 append。
- 历史过程：优先使用 `acf new worklog ...`。
- 可复用经验：优先使用 `acf knowledge draft ...`。
- 重要决策：优先使用 `acf new adr ...`。

---

## 审阅清单

- [ ] 已确认唯一权威位置。
- [ ] 已确认当前事实是 replace、append、remove 还是 archive。
- [ ] 已确认低优先级文件是否应改为引用而不是复制全文。
- [ ] 已确认哪些内容只保留为历史过程。
- [ ] 已确认哪些内容仍需人工判断。
