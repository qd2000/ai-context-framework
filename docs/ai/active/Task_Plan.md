本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、状态、证据入口和下一步，不记录长过程、完整日志或详细推理

---

## 大任务状态

Done

---

## 大任务名称

P2 Non-PetroSim Dogfooding Sample

---

## 大任务目标

1. 在 ACF 自身、FCC、minimal / legacy / synthetic fixtures 之外，选择一个非 PetroSim 真实项目样本。
2. 只读评估该样本是否能验证 ACF 在不同项目形态下的适用性。
3. 记录选择理由、当前 ACF check/audit/upgrade 信号和后续写入边界。
4. 本轮不修改目标项目，不新增 audit 规则。

---

## 成功标准

1. 选择一个非 PetroSim 真实项目样本。
2. 样本类型不同于 FCC：论文 / 数据分析 / Python 工具项目。
3. 完成只读 `status`、`check`、`upgrade --dry-run`、`audit context`、`review stale` 评估。
4. `reference/Non_PetroSim_Dogfooding_Sample.md` 记录选择理由和检查结果。
5. `reference/Product_Roadmap.md` 与 `../Automation.md` 指向该样本。
6. 不修改目标项目内容。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | Inspect EcSOS as non-PetroSim candidate | Product Roadmap; context matrix | 样本适配性判断、只读检查结果、后续写入边界 | `reference/Non_PetroSim_Dogfooding_Sample.md`; `reference/Product_Roadmap.md`; `worklog/daily/2026-05-07.md`; verification: `uv run acf check docs/ai --strict --json`, `uv run acf status docs/ai --json` | 若后续需要写入 EcSOS，先确认目标项目 ahead 状态并从 `acf upgrade --dry-run` 开始。 |

---

## 任务阶段

| ID | 状态 | 父任务 | 名称 | 归属 Workstream | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |  |  |

---

## 非目标

本阶段不做：

1. 不修改 EcSOS 项目内容。
2. 不启动 EcSOS runtime、训练或采样任务。
3. 不新增 audit candidate rule。
4. 不把 EcSOS 的论文业务规则写入 ACF。
5. 不把启发式 audit 接入 `check --strict`。

---

## 后续候选

1. 经用户明确授权后，对 EcSOS 执行 `acf upgrade --dry-run` 计划变更的正式写入。
2. 写入后复跑 EcSOS `acf check`、`acf audit context`、`acf review stale`。
3. 在 ACF 中记录非 PetroSim 样本写入前/后的差异，再决定是否进入 P3 audit rule expansion。

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
