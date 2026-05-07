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

Draft EcSOS upgrade rehearsal plan

---

## 所属大任务

EcSOS upgrade rehearsal plan

---

## 子任务 ID

T001

---

## 当前执行线

无。

---

## 本次任务目标

1. 为 EcSOS 非 PetroSim 样本写 upgrade rehearsal plan。
2. 明确授权前检查、写入步骤、写后验证和不自动处理项。
3. 记录 EcSOS 当前 `ahead 1` 的具体 commit。
4. 本轮不修改 EcSOS。

---

## 任务背景

EcSOS 已选为 ACF 非 PetroSim 真实样本。只读评估显示它是旧版 ACF context，缺少 `reference/Context_Curation_Prompt.md`；`acf upgrade --dry-run` 可非破坏式补结构。同时目标项目当前 `git status` 为 `ahead 1`，本地 ahead commit 是 `c236a77 初始化docs/ai/`。正式写入前需要明确授权和安全边界。

---

## 输入材料

- `reference/Non_PetroSim_Dogfooding_Sample.md`
- EcSOS 只读命令结果：
  - `git status -sb`
  - `git log --oneline origin/master..HEAD`
  - `acf upgrade --dry-run --json`
  - `acf audit context --json`
  - `acf review stale --json`

---

## 输出要求

1. 在 `reference/Non_PetroSim_Dogfooding_Sample.md` 增加 Upgrade Rehearsal Plan。
2. 写清授权前检查。
3. 写清预期写入文件。
4. 写清写后验证命令。
5. 写清 stale / 论文事实不自动修。

---

## 成功标准

1. rehearsal plan 可直接指导后续授权执行。
2. 明确：没有用户授权不写 EcSOS。
3. 明确：upgrade 只做结构升级，不改论文事实。
4. `uv run acf check docs/ai --strict --json` 通过。
5. `uv run acf status docs/ai --json` 通过。

完成证据：

- `reference/Non_PetroSim_Dogfooding_Sample.md`
- `active/Task_Plan.md`
- `active/Current_Task.md`
- `worklog/daily/2026-05-07.md`

---

## 失败信号

1. 本轮执行 EcSOS `acf upgrade` 正式写入。
2. 修改 EcSOS 当前任务或论文事实。
3. 自动修 stale candidates。
4. 新增 audit rule。

---

## 约束条件

1. EcSOS 只读。
2. 不使用 WSL。
3. 不运行训练、采样或 runtime。
4. 不新增 ACF 代码。

---

## 不允许做的事

- 不修改 EcSOS 文件。
- 不运行 `acf upgrade` 非 dry-run。
- 不提交 EcSOS。
- 不把 EcSOS 业务问题写入 ACF 产品规则。

---

## 需要 AI 协助判断的问题

1. 写入前哪些条件必须重新确认。
2. 写入后哪些验证足以证明结构升级安全。
3. 哪些 stale / audit 候选必须保留为人工审阅。

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. rehearsal plan 已写入。
2. 后续需要用户明确授权才能写 EcSOS。
