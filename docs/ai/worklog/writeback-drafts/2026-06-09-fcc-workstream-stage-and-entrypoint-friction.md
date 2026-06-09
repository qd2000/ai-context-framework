本文件是会话结束回写草案，不是当前事实源。

请人工审阅后，再决定是否使用 CLI 或手工方式写入权威上下文。

---

## 草案名称

2026-06-09-fcc-workstream-stage-and-entrypoint-friction

---

## 原始回写建议

```text
来自 fcc_workspace context monitor 的跨项目 dogfooding 观察：1) 在 fcc_workspace 直接运行全局 acf 入口失败，报 ModuleNotFoundError: No module named ai_context_framework；使用 PYTHONPATH=/mnt/e/Codes/Tools/ai-context-framework acf ... 可以运行，说明当前环境中的入口安装/路径提示仍可能让真实项目自动化误判 acf 不可用。2) fcc_workspace 的 WS030 使用 current_stage=WS030.2a，acf check 将其判为 invalid workstream stage id；这符合现有 WS001.1 数字阶段规则，但真实项目会自然使用 2a 这类子阶段命名。建议后续评估：是否扩展 Workstream stage ID grammar 支持字母子阶段，或至少在 check/status 的 next_actions 中给出可执行修复建议（例如改为 WS030.2.1 或补文档约束）。可并入 F019 Workstream UX / 多 agent 编排设计反馈，或作为独立安装入口/阶段号 UX 改进项。
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
