本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

最小 smoke runner 设计与实现

---

## 大任务目标

1. 固化 v0.0.3.17 已验证主路径为本地最小 smoke runner，用于发布前快速回归。
2. 第一版只覆盖 init/status/check、worklog create/append/error_code 和 workstream minimal happy path。
3. 不纳入真实项目批量评测、漂移样本诊断或复杂 upgrade 审查。

---

## 成功标准

1. runner 使用隔离临时目录，只调用 CLI 入口，输出结构化 JSON 摘要，任一场景失败返回非零，不修改本仓库 docs/ai。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | 实现最小 smoke runner | 无。 | 短、透明、少封装的本地 smoke runner 脚本与验证记录 | 已实现 scripts/minimal_smoke.py，使用 subprocess 参数列表调用 CLI，不使用 shell 字符串；覆盖 init -> nested status/check、worklog create/append/TARGET_EXISTS_APPEND_REQUIRED/APPEND_FORCE_CONFLICT、Workstream init/add/merge-request/set Active/ready/done/check；验证 uv run python scripts/minimal_smoke.py --acf uv run acf 通过。 | 无。 |

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 已失效的大任务计划应归档到 `archive/plans/`。
4. 不要把历史过程、完整日志或详细推理写入本文件。
