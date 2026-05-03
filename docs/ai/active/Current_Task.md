本文件记录当前正在处理的具体任务。

- 长期目标请查看：`reference/Project_Brief.md`
- 当前阶段目标请查看：`active/Context.md`
- 本文件只维护当前具体任务

如果用户在当前对话中提出了新的具体需求，并且该需求与本文件冲突，以用户当前消息为准。

---

## 当前任务状态

Done

---

## 任务名称

用户旅程摩擦点整理

---

## 所属大任务

v0.0.3.17 稳定安装与跨项目评测

---

## 子任务 ID

T005

---

## 本次任务目标

1. 整理 T001-T004 使用旅程摩擦点，包括并发读写撞锁后疑似 .acf.lock 运行态残留的观察；判断是否需要自动清理、gitignore 或文档提示，并评估是否进入最小 smoke runner。
2. 产出并验证输出物：AI 友好性、错误恢复和不常见场景摩擦清单

---

## 任务背景

该任务来自 `active/Task_Plan.md` 中的子任务 T005，所属大任务为“v0.0.3.17 稳定安装与跨项目评测”。依赖记录：T002,T003,T004

---

## 输入材料

- `active/Task_Plan.md`。
- `active/Context.md`。
- 依赖 T002 证据：使用稳定入口 acf v0.0.3.17 在健康真实项目 E:\Codes\TempCodes\register 完成 worklog create + append 轻写入闭环；写入前 dry-run 可解释，写后 acf check docs/ai --strict --json 通过；目标项目仅出现预期 docs/ai/worklog/Worklog_Index.md 修改和 docs/ai/worklog/daily/2026-05-03.md 新文件。
- 依赖 T003 证据：使用稳定入口 acf v0.0.3.17 在隔离临时项目完成 worklog append/force 错误码恢复矩阵：已有当天 worklog 未传 append/force 返回 TARGET_EXISTS_APPEND_REQUIRED 且 hash 不变；按 next_actions 加 --append 可成功恢复 action=append；--append --force 返回 APPEND_FORCE_CONFLICT 且 hash 不变；append dry-run 返回 would_change=true、1-based insert_after_line 且 hash 不变；复制临时项目删除 anchor 后 append 返回 ANCHOR_NOT_FOUND 且不写入。target/changed_files 为 repo-relative POSIX slash，失败 JSON 含 ok=false/error_code/message/target，成功 JSON 含 warnings: []。
- 依赖 T004 证据：使用稳定入口 acf v0.0.3.17 完成跨项目只读分类评测：fcc_workspace、papers、register 作为 healthy 样本，status、upgrade docs/ai --dry-run、check docs/ai --strict 均通过，upgrade planned_changes=0，读操作前后 git status 不变；KnowledgeConnector 作为 schema 已齐但内容状态漂移的 diagnostic 样本，status/check 返回 check_failed 并识别 docs/ai 上下文，upgrade dry-run 通过且 planned_changes=0，strict check 暴露 27 个可行动一致性错误，读操作前后 git status 不变。

---

## 输出要求

- AI 友好性、错误恢复和不常见场景摩擦清单

---

## 成功标准

1. 输出物已完成：AI 友好性、错误恢复和不常见场景摩擦清单
2. 子任务 T005 的完成证据已写回任务板。
3. `acf plan status` 能显示任务板可继续推进。

---

## 失败信号

1. 依赖任务未完成或证据不足。
2. 输出物无法通过检查或人工复核验证。
3. 执行中发现用户当前需求与任务板记录冲突。

---

## 约束条件

1. 遵守当前项目规则和默认读取顺序。
2. 保持 `active/Task_Plan.md` 与 `active/Current_Task.md` 状态同步。
3. 不要把一次性过程或当前事实直接写入 Knowledge。

---

## 不允许做的事

- 无。

---

## 需要 AI 协助判断的问题

1. 执行过程中是否发现应回写 Context、ADR、rules、Knowledge 或 archive 的内容？

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 应写入 `active/Context.md` 的新增当前事实。
2. 应写入 `reference/Decisions_Index.md` 或 ADR 的重要决策。
3. 应写入 rules 的新增规则。
4. 应写入 `reference/Knowledge_Index.md` 或 Knowledge 条目的可复用经验。
5. 应归档到 archive 的历史内容。
