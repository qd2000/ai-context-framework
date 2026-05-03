本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Active

---

## 大任务名称

v0.0.3.17 稳定安装与跨项目评测

---

## 大任务目标

1. 验证稳定安装入口升级到 v0.0.3.17 后，在最小环境和真实项目中的安装、升级、配置与恢复路径。
2. 验证真实项目写入闭环、多次状态流转、worklog append/force 边界与跨项目复杂性。

---

## 成功标准

1. 稳定安装 acf v0.0.3.17 可在最小标准项目和至少一个真实项目完成 status、upgrade dry-run、strict check。
2. 至少一个真实项目完成轻写入闭环，并记录是否需要跳出 CLI 手工修复。
3. new worklog --append/--force 的关键边界和错误码可由 AI 根据 JSON 输出恢复。
4. 跨项目样本区分健康项目和 schema 当前但内容漂移项目，并形成后续产品化建议。

---

## 当前焦点

T001

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Pending | 稳定安装 v0.0.3.17 最小环境验证 | 无 | 稳定安装版本、最小标准项目 status/upgrade/check 证据 | 无。 | 更新或隔离安装 acf v0.0.3.17，并在最小标准项目运行 status/upgrade dry-run/check |
| T002 | Pending | 真实项目轻写入闭环验证 | T001 | 一个健康真实项目的 new worklog 或 plan/task 写入闭环记录 | 无。 | 选择健康真实项目，先 dry-run，再执行最小写入并 strict check |
| T003 | Pending | worklog append/force 边界与恢复验证 | T001 | append、force、重复创建、冲突、异常输入和 AI next_actions 评测摘要 | 无。 | 在隔离项目中组合验证 create/append/force/error_code 分支，记录恢复路径 |
| T004 | Pending | 跨项目健康与漂移样本评测 | T001 | 健康项目与内容漂移项目的分类评测记录 | 无。 | 扩展真实项目 status/upgrade dry-run/check 样本，单独标注 KnowledgeConnector 类漂移诊断样本 |
| T005 | Pending | 用户旅程摩擦点整理 | T002,T003,T004 | AI 友好性、错误恢复和不常见场景摩擦清单 | 无。 | 从真实操作记录和 usage log 中整理重复摩擦点，判断是否进入 smoke runner 或新命令设计 |

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 已失效的大任务计划应归档到 `archive/plans/`。
4. 不要把历史过程、完整日志或详细推理写入本文件。
