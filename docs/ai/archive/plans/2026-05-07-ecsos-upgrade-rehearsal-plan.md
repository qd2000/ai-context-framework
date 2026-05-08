本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、状态、证据入口和下一步，不记录长过程、完整日志或详细推理

---

## 大任务状态

Done

---

## 大任务名称

EcSOS upgrade rehearsal plan

---

## 大任务目标

1. 为 EcSOS 非 PetroSim dogfooding 样本准备 upgrade dry-run -> apply 的授权前检查计划。
2. 明确写入前必须确认目标项目 `ahead 1` 状态。
3. 固定只读 / dry-run / 写入 / 写后验证顺序。
4. 明确 upgrade 只验证 context 结构，不自动改论文事实、不修 stale 当前任务。
5. 本轮只写 ACF 计划文档，不写 EcSOS。

---

## 成功标准

1. `reference/Non_PetroSim_Dogfooding_Sample.md` 增加 Upgrade Rehearsal Plan。
2. 记录 EcSOS `ahead 1` 的具体 commit：`c236a77 初始化docs/ai/`。
3. 写入范围预期限定为 upgrade dry-run 输出的结构文件。
4. 写后验证命令明确为 check / audit / review stale / git status / git diff。
5. 明确 stale current task、Context review marker 和论文事实不自动修。
6. 本轮不修改 EcSOS 项目内容。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | Draft EcSOS upgrade rehearsal plan | Non-PetroSim sample selection | 授权前检查、写入步骤、写后验证、不自动处理清单 | `reference/Non_PetroSim_Dogfooding_Sample.md`; `worklog/daily/2026-05-07.md`; verification: `uv run acf check docs/ai --strict --json`, `uv run acf status docs/ai --json` | 等用户明确授权后，才进入 EcSOS upgrade apply。 |

---

## 任务阶段

| ID | 状态 | 父任务 | 名称 | 归属 Workstream | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |  |  |

---

## 非目标

本阶段不做：

1. 不执行 EcSOS `acf upgrade` 正式写入。
2. 不修改 EcSOS active/Context.md、Current_Task.md 或 Task_Plan.md。
3. 不修 stale candidates。
4. 不运行训练、采样、论文生成或 runtime 命令。
5. 不新增 ACF audit rules。

---

## 后续候选

1. 用户明确授权后，按 rehearsal plan 执行 EcSOS upgrade apply。
2. 写后只验证 context 结构和 audit/stale 信号。
3. 将写入前/后差异写回 ACF worklog，再决定是否进入 P3 audit rule expansion。

---

## 基线验证

本任务至少运行：

```bash
uv run acf check docs/ai --strict --json
uv run acf status docs/ai --json
```

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 已失效的大任务计划应归档到 `archive/plans/`。
4. 不要把历史过程、完整日志或详细推理写入本文件。
