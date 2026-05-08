# Non-PetroSim Dogfooding Sample

本文记录 ACF 在 FCC 之外的真实项目 dogfooding 样本选择和只读评估结果。

---

## 状态

Selected

---

## 样本

| 项目 | 路径 | 类型 | 当前角色 |
|---|---|---|---|
| cracking-yield-prediction-system | `E:\Codes\EcSOS\cracking-yield-prediction-system` | 论文 / 数据分析 / Python 工具项目 | P2 非 PetroSim dogfooding 样本 |

---

## 选择理由

该项目适合作为 FCC 之外的真实样本：

1. 不是 FCC / PetroSim 项目，不依赖 PetroSim runtime。
2. 项目形态不同：论文第4章实验复现、真实工厂收率预测、数据/脚本/表图/写作迁移并存。
3. 已有 `docs/ai/` 上下文，但形态落后于当前 ACF，适合验证 upgrade 兼容和低噪声 audit。
4. 当前任务是论文补充实验 E4-1，不是并行 Workstream-heavy 工程任务，可验证 ACF 对非 Workstream 项目的适用性。
5. 有真实 active/context 演化需求：数据事实源、实验口径、结果路径、论文表述边界和复现实验计划。
6. 不需要读写敏感运行态，也不需要启动训练或 ECSOS runtime 就能做只读治理评估。

---

## 只读检查结果

检查日期：2026-05-07。

本轮未修改 EcSOS 项目。

### Git 状态

`git status -sb` 显示：

```text
## master...origin/master [ahead 1]
```

含义：目标项目本地已有未推送提交或状态差异。ACF dogfooding 不应在未明确授权时写入该项目。

`git log --oneline origin/master..HEAD` 显示本地 ahead commit 为：

```text
c236a77 初始化docs/ai/
```

含义：当前 ahead 状态来自目标项目已有 `docs/ai/` 初始化提交。执行正式 upgrade 写入前，应先确认该本地提交是否保留、推送或继续在其上追加。

### ACF status / check

命令：

```bash
uv run acf status E:\Codes\EcSOS\cracking-yield-prediction-system\docs\ai --json
uv run acf check E:\Codes\EcSOS\cracking-yield-prediction-system\docs\ai --json
uv run acf check E:\Codes\EcSOS\cracking-yield-prediction-system\docs\ai --strict --json
```

结果：

1. context 可识别为 standard profile。
2. 当前任务状态为 Active。
3. check / strict check 均失败，唯一结构错误是缺少 [reference/Context_Curation_Prompt.md](Context_Curation_Prompt.md)。

### ACF upgrade dry-run

命令：

```bash
uv run acf upgrade E:\Codes\EcSOS\cracking-yield-prediction-system\docs\ai --dry-run --json
```

结果：

1. dry-run 成功。
2. 计划变更包括：
   - [reference/Context_Curation_Prompt.md](Context_Curation_Prompt.md)
   - `AGENTS.md`
   - [rules/Project_Rules.md](../rules/Project_Rules.md)
   - [reference/System_Manual.md](System_Manual.md)
3. 说明该项目适合验证非破坏式 upgrade：结构可升级，但不应自动改写当前 active 事实。

### ACF audit context

命令：

```bash
uv run acf audit context E:\Codes\EcSOS\cracking-yield-prediction-system\docs\ai --json
```

结果：

1. 输出 1 个 candidate。
2. 类型为 `stale_current_task_or_workstream_stage`。
3. path 为 [active/Current_Task.md](../active/Current_Task.md)。
4. reason 为 Active 当前任务缺少 ISO update / review date。
5. 未出现 `active_section_too_long` 或 `terminal_conclusion_not_merged` 候选。

### ACF review stale

命令：

```bash
uv run acf review stale E:\Codes\EcSOS\cracking-yield-prediction-system\docs\ai --json
```

结果：

1. 输出 2 个 stale items。
2. [active/Current_Task.md](../active/Current_Task.md)：Active 当前任务缺少 dated status note。
3. [active/Context.md](../active/Context.md)：缺少 `Last reviewed` / `上次审阅` marker。

---

## 初步判断

EcSOS 适合作为 P2/P3 之间的非 PetroSim 真实样本。

它能验证的通用问题：

1. 旧版 ACF context 的非破坏式 upgrade。
2. 非 Workstream-heavy 项目中的 active task stale signal。
3. 论文 / 数据分析项目中的当前事实、实验口径、结果路径和写作边界治理。
4. minimal / synthetic fixture 之外的真实 active context 低噪声 audit。
5. ACF 是否能在没有 FCC Workstream 复杂度的项目中保持有用而不过度报错。

暂不作为以下能力的主要样本：

1. Workstream authority gate。
2. Workstream stage focus。
3. Workstream index sync。
4. 多 agent 并行目标线治理。

这些能力仍主要由 FCC 和 synthetic fixtures 覆盖。

---

## 推荐下一步

第一步仍应保持只读或 dry-run：

1. 将 EcSOS 记录为非 PetroSim dogfooding 样本。
2. 如需写入，先在用户明确授权后执行 `acf upgrade --dry-run` 的计划变更。
3. 写入前确认目标项目本地 `ahead 1` 状态是否可接受。
4. 写入后只验证：
   - `acf check docs/ai --json`
   - `acf audit context docs/ai --json`
   - `acf review stale docs/ai --json`
5. 不在 EcSOS 项目中测试 FCC/PetroSim 专属规则。

---

## Upgrade Rehearsal Plan

目标：在用户明确授权前，只准备演练计划，不写 EcSOS。

### 授权前检查

1. 确认目标项目路径仍为 `E:\Codes\EcSOS\cracking-yield-prediction-system`。
2. 复跑 `git status -sb`，确认是否仍为 `ahead 1` 且无其他 dirty files。
3. 复跑 `git log --oneline origin/master..HEAD`，确认 ahead commit 是否仍为 `c236a77 初始化docs/ai/`。
4. 复跑 `acf upgrade --dry-run --json`，确认 planned changes 仍限于结构升级文件。
5. 不运行训练、采样、论文生成或任何 runtime 命令。

### 写入步骤

仅在用户明确授权后执行：

```bash
uv run acf upgrade E:\Codes\EcSOS\cracking-yield-prediction-system\docs\ai --json
```

写入范围预期只包括：

1. [reference/Context_Curation_Prompt.md](Context_Curation_Prompt.md)
2. `AGENTS.md`
3. [rules/Project_Rules.md](../rules/Project_Rules.md)
4. [reference/System_Manual.md](System_Manual.md)

若 dry-run 输出发生变化，应停止并重新评估。

### 写后验证

只验证 context 结构和 audit 信号，不改论文事实：

```bash
uv run acf check E:\Codes\EcSOS\cracking-yield-prediction-system\docs\ai --json
uv run acf audit context E:\Codes\EcSOS\cracking-yield-prediction-system\docs\ai --json
uv run acf review stale E:\Codes\EcSOS\cracking-yield-prediction-system\docs\ai --json
git -C E:\Codes\EcSOS\cracking-yield-prediction-system status -sb
git -C E:\Codes\EcSOS\cracking-yield-prediction-system diff -- docs/ai
```

### 写入后不自动处理

以下候选只记录，不自动修：

1. Active Current_Task 缺 dated status note。
2. Context 缺 review marker。
3. 论文实验事实、数据事实源、口径决策或表图迁移问题。

这些内容属于目标项目语义治理，需要用户或主代理另行确认。

---

## 非目标

1. 不启动训练、采样或 ECSOS runtime。
2. 不修改 EcSOS 项目内容，除非用户明确要求。
3. 不把 EcSOS 的论文业务规则写入 ACF。
4. 不因为 EcSOS 的单一现象直接新增 ACF audit / strict 规则。
5. 不把该项目替代 FCC；它是验证矩阵中的另一类样本。
