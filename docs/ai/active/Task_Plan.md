本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Active

---

## 大任务名称

WS013 Observer Retirement and v0.0.3.92

---

## 大任务目标

1. 完整吸收并终止 WS012，保持历史可追溯且清除本地运行态残留。
2. 从 ACF 核心移除 Observer runtime、Dashboard、Target Registry 和 presentation lifecycle，只保留无副作用退役提示。
3. 同步代码、测试、打包、smoke、README、Automation、项目/模板手册并完成完整兼容验证。
4. 全部 Gate 通过后发布并全局安装 v0.0.3.92，再归档 WS013。

---

## 成功标准

1. WS012 无 branch/worktree/registry/continuation/temp 残留，且完整血缘由 WS013 保留。
2. 发布包不含 Observer 实现；continuation prompt 不含 Observer contract；retired stub 不读写状态。
3. strict/template check、全量 unittest、minimal smoke、full upgrade matrix、release check 和 package smoke 全部通过。
4. v0.0.3.92 完成 immutable tag、PyPI publish、全局安装和 installed-state 验证。

---

## 规划依据

列出当前大任务必须对齐的 reference 设计、路线或差距文档；只放路径和一句话用途，不复制详细规划。

- [reference/ws013_observer_retirement_ws012_closeout/PLAN.md](../reference/ws013_observer_retirement_ws012_closeout/PLAN.md)：WS013 Observer 退役、WS012 收尾、验证矩阵与 v0.0.3.92 发布路线。

---

## 当前焦点

T005

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | 固化 Observer 依赖图与允许残留清单 | 无。 | Observer 当前依赖矩阵、历史保留边界和删除顺序 | reference/ws013_observer_retirement_ws012_closeout/PLAN.md 第9节：Observer 依赖矩阵、安全删除顺序、历史保留边界与退役 stub 设计约束 | 无。 |
| T002 | Done | 移除 Observer runtime 与公共产品合同 | T001 | 退役 stub、移除 runtime/automation contract/CLI 强依赖 | commands/observer.py 改造为无副作用 observer_retired 墓碑；删除 8 个 observer 实现模块与 commands/observer_presentation；automation_contracts.py 仅拆 Observer 子树保留 Writer 契约；契约测试与墓碑回归通过，check --strict 通过 | 无。 |
| T003 | Done | 同步测试、打包、smoke 与文档 | T002 | 删除专项实现和测试，更新 release gate、README、Automation 与两份手册 | 删除 4 个 Observer 专项测试套件与 output/observer 产物；minimal_smoke 改为 human report 场景；release_check 移除 Dashboard 前置；egg-info 重新生成仅保留 stub；新增 2 个墓碑无副作用回归；README/Automation/两份 System Manual/Context 同步退役说明；296+135 tests OK | 无。 |
| T004 | Done | 执行完整兼容与 release 验证 | T003 | strict/template、全量测试、smoke、upgrade matrix、release check、package evidence | check template/strict pass；unittest 646 tests OK（skipped 3，2803s）；minimal smoke ok；upgrade matrix full 28 fixtures ok；release_check full ok 且 wheel+sdist 隔离安装 smoke 通过；P5 七项断言通过（continuation contract 无 Observer 键、observer_retired、隔离 ACF_HOME 无副作用、产物仅含 stub、无新增依赖） | 无。 |
| T005 | Pending | 发布并全局安装 v0.0.3.92 | T004 | 版本更新、CHANGELOG、merge/tag/publish/global install/installed-state evidence | 无。 | 全部 Gate 通过后才 bump 版本并发布。 |
| T006 | Pending | 归档 WS013 并清理开发运行态 | T005 | WS013 Done/archive，worktree/branch/continuation 清理，global-only 状态 | 无。 | 发布闭环后执行最终 closeout。 |

---

## 任务阶段

| ID | 状态 | 父任务 | 名称 | 归属 Workstream | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |  |  |

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 当前大任务依赖 reference 规划时，必须在 `## 规划依据` 列出路径和一句话用途。
4. 已失效的大任务计划应归档到 `archive/plans/`。
5. 不要把历史过程、完整日志或详细推理写入本文件。
