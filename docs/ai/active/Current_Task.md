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

P2 Test Matrix Expansion

---

## 所属大任务

P2 Test Matrix Expansion

---

## 子任务 ID

T001

---

## 当前执行线

无。

---

## 本次任务目标

1. 盘点现有 fixtures 覆盖。
2. 新增 context matrix fixtures：minimal_clean、legacy_old_context、audit_long_section、workstream_complex、authority_gate。
3. 先补测试矩阵，不新增 audit 规则。
4. 明确 P3 前需要非 PetroSim 真实项目样本。

---

## 任务背景

Product Roadmap 已明确：FCC 是压力测试样本，不是产品需求唯一来源。后续新增规则必须可抽象、可机械检测、可测试、可兼容、可降级。当前任务先补通用测试矩阵，防止 ACF 继续被单个真实项目牵着走。

---

## 输入材料

- `reference/Product_Roadmap.md`
- `tests/fixtures/upgrade_matrix/`
- `tests/test_cli.py`
- `scripts/upgrade_matrix.py`

---

## 输出要求

1. 新增 `tests/fixtures/context_matrix/`。
2. 新增 `tests/test_context_matrix.py`。
3. `audit_long_section` 验证 H1 wrapper 不误报、真实长 section 会报。
4. `workstream_complex` 验证 complex Workstream strict / sync no-op。
5. `authority_gate` 验证 direct authority claim strict fail。
6. 不修改 `acf.py`。

---

## 成功标准

1. `uv run python -m unittest tests.test_context_matrix` 通过。
2. `uv run python -m unittest` 通过。
3. `uv run acf check docs/ai --strict --json` 通过。
4. `uv run acf status docs/ai --json` 通过。
5. 本轮没有新增 audit candidate kind。

完成证据：

- `tests/fixtures/context_matrix/`
- `tests/test_context_matrix.py`
- `worklog/daily/2026-05-07.md`

---

## 失败信号

1. 用 FCC 内容作为 fixture。
2. 新增 audit rule。
3. 修改 `acf.py`。
4. 让 minimal / legacy 项目承担新默认负担。

---

## 约束条件

1. fixture 应保持最小，不复制真实项目。
2. 每个 fixture 只验证一个通用问题。
3. legacy 覆盖优先复用现有 upgrade matrix，不重复造旧上下文。

---

## 不允许做的事

- 不实现 duplicate / evidence / volatile audit rules。
- 不修改 FCC。
- 不新增运行依赖。
- 不新增常驻 runner。

---

## 需要 AI 协助判断的问题

1. context matrix 是否足以作为 P3 audit rule 前置门槛。
2. 是否需要后续把 context matrix 抽成独立 runner。
3. 非 PetroSim 样本应选择哪类项目。

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 新增 fixture 覆盖清单。
2. 验证命令和结果。
3. 后续候选：选择非 PetroSim 样本，而不是继续扩 audit rules。
