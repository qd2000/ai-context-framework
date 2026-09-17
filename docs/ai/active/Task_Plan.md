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

T001

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Active | 固化 Observer 依赖图与允许残留清单 | 无。 | Observer 当前依赖矩阵、历史保留边界和删除顺序 | 无。 | 运行 git grep 与模块调用关系审计，形成可审阅删除清单。 |
| T002 | Pending | 移除 Observer runtime 与公共产品合同 | T001 | 退役 stub、移除 runtime/automation contract/CLI 强依赖 | 无。 | 按最小切片移除 root runtime 和 automation contract 的 Observer 依赖。 |
| T003 | Pending | 同步测试、打包、smoke 与文档 | T002 | 删除专项实现和测试，更新 release gate、README、Automation 与两份手册 | 无。 | 使当前产品面、模板、包清单和验证脚本一致。 |
| T004 | Pending | 执行完整兼容与 release 验证 | T003 | strict/template、全量测试、smoke、upgrade matrix、release check、package evidence | 无。 | 关闭所有回归和文档漂移后形成可发布候选。 |
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
