本文件记录当前正在处理的具体任务。

- 长期目标请查看：`reference/Project_Brief.md`
- 当前阶段目标请查看：`active/Context.md`
- 本文件只维护当前具体任务

如果用户在当前对话中提出了新的具体需求，并且该需求与本文件冲突，以用户当前消息为准。

---

## 当前任务状态

Active

说明：

- Active：当前任务正在进行
- Paused：当前任务暂停
- Done：当前任务已完成
- Empty：暂无需要写入文件的当前任务

---

## 任务名称

发布并全局安装 v0.0.3.92

---

## 所属大任务

WS013 Observer Retirement and v0.0.3.92

---

## 子任务 ID

T005

---

## 所属 Workstream

- `WS013`

---

## 当前执行线

无。

---

## 本次任务目标

1. 在 T004 验证通过的候选上完成 `.92` 版本更新、CHANGELOG 与 README/PKG-INFO 同步，并重跑完整 release gate。
2. 合并 master、创建 immutable `v0.0.3.92` tag、push 触发 PyPI 发布，并用 `scripts/update_acf.ps1` 完成全局安装与 installed-state 验证。

---

## 任务背景

该任务来自 `active/Task_Plan.md` 中的子任务 T005，所属大任务为“WS013 Observer Retirement and v0.0.3.92”。依赖记录：T004 已 Done（check template/strict、unittest 646 tests OK、minimal smoke、upgrade matrix full、release check 与 P5 七项断言全部通过）。

---

## 输入材料

当前任务应列出必要 active 文件和相关 reference 规划依据；不要只写 `active/Context.md`。

- `active/Task_Plan.md`。
- `active/Context.md`。
- [reference/ws013_observer_retirement_ws012_closeout/PLAN.md](../reference/ws013_observer_retirement_ws012_closeout/PLAN.md)：WS013 Observer 退役、WS012 收尾、验证矩阵与 v0.0.3.92 发布路线。
- 依赖 T004 证据：check template/strict pass；unittest 646 tests OK（skipped 3）；minimal smoke ok；upgrade matrix full 28 fixtures ok；release_check full ok 且 wheel+sdist 隔离安装 smoke 通过；P5 七项专项断言通过（contract 无 Observer 键、observer_retired、隔离 ACF_HOME 无副作用、产物仅含 stub、无新增依赖）。
- 发布入口：`ai_context_framework/version.py`、`pyproject.toml`、`uv.lock`、`CHANGELOG.md`、`README.md`、`ai_context_framework.egg-info/PKG-INFO`、`.github/workflows/release.yml`、`scripts/update_acf.ps1`。

---

## 输出要求

- `.92` 版本更新与 CHANGELOG/README/PKG-INFO 同步。
- 完整 release gate 重跑证据、master merge、immutable `v0.0.3.92` tag、PyPI publish。
- 全局安装与 installed-state evidence（version/status/check/workstream/continuation/observer 墓碑）。

---

## 成功标准

1. `acf version show --json` 显示 `.92`，且 version.py / pyproject / uv.lock / PKG-INFO 一致，完整 release gate 通过。
2. `.92` 完成 master 合并、immutable tag、PyPI publish、`scripts/update_acf.ps1` 全局安装和 installed-state 验证。
3. 子任务 T005 的完成证据已写回任务板，T006 可以继续。

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
