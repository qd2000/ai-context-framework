本文件记录当前正在处理的具体任务。

- 长期目标请查看：`reference/Project_Brief.md`
- 当前阶段目标请查看：`active/Context.md`
- 当前大任务计划请查看：`active/Task_Plan.md`
- 本文件只维护当前具体任务

如果用户在当前对话中提出了新的具体需求，并且该需求与本文件冲突，以用户当前消息为准。

---

## 当前任务状态

Done

---

## 任务名称

Inspect EcSOS as non-PetroSim dogfooding sample

---

## 所属大任务

P2 Non-PetroSim Dogfooding Sample

---

## 子任务 ID

T001

---

## 当前执行线

无。

---

## 本次任务目标

1. 只读查看 `E:\Codes\EcSOS\cracking-yield-prediction-system`。
2. 判断该项目是否适合作为 ACF 非 PetroSim 真实 dogfooding 样本。
3. 记录 ACF status/check/upgrade/audit/review stale 的只读信号。
4. 不修改目标项目。

---

## 任务背景

ACF 已有 ACF 自身、FCC、minimal / legacy / synthetic fixtures。为了防止后续 P3 audit rules 过拟合 FCC/PetroSim，需要增加一个非 PetroSim 真实项目样本。EcSOS 项目是论文 / 数据分析 / Python 工具项目，已有旧版 ACF context 和 Active 当前任务，适合验证非 Workstream-heavy 项目的 upgrade/audit 适用性。

---

## 输入材料

- `E:\Codes\EcSOS\cracking-yield-prediction-system\AGENTS.md`
- `E:\Codes\EcSOS\cracking-yield-prediction-system\README.md`
- `E:\Codes\EcSOS\cracking-yield-prediction-system\docs\ai`
- `reference/Product_Roadmap.md`

---

## 输出要求

1. 新增 `reference/Non_PetroSim_Dogfooding_Sample.md`。
2. 更新 `reference/Product_Roadmap.md`。
3. 更新 `../Automation.md` 和 `reference/Sources_Index.md` 的入口。
4. 记录只读检查结果和后续写入边界。
5. 不修改 EcSOS 项目。

---

## 成功标准

1. 明确 EcSOS 是否适合作为非 PetroSim 样本。
2. 记录 check/status 当前失败原因。
3. 记录 upgrade dry-run planned changes。
4. 记录 audit/review stale candidates。
5. ACF 自身 `uv run acf check docs/ai --strict --json` 通过。

完成证据：

- `reference/Non_PetroSim_Dogfooding_Sample.md`
- `reference/Product_Roadmap.md`
- `../Automation.md`
- `reference/Sources_Index.md`
- `worklog/daily/2026-05-07.md`

---

## 失败信号

1. 修改 EcSOS 项目内容。
2. 启动训练、采样或 runtime。
3. 将 EcSOS 业务规则写成 ACF 通用规则。
4. 直接进入 P3 audit rule implementation。

---

## 约束条件

1. 目标项目只读。
2. 不使用 WSL。
3. 只记录通用上下文治理信号。
4. 目标项目当前 `git status` 显示 ahead，写入前必须另行确认。

---

## 不允许做的事

- 不运行训练或实验脚本。
- 不执行 `acf upgrade` 正式写入。
- 不修改 EcSOS 文件。
- 不新增 ACF audit rule。

---

## 需要 AI 协助判断的问题

1. EcSOS 暴露的是通用 ACF 问题，还是项目业务问题。
2. 它适合覆盖哪些 ACF 能力，不适合覆盖哪些能力。
3. 后续写入前需要哪些安全边界。

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. EcSOS 作为非 PetroSim 样本的适配性结论。
2. 只读检查结果。
3. 后续是否进入 EcSOS 正式 upgrade 写入。
