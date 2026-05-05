本文件是工作记录索引。

请注意：

- 这里不是当前事实源。
- 当前事实请查看：`active/Context.md`
- 每日工作记录位于：`worklog/daily/`

---

## 工作记录

| 日期 | 摘要 | 关键结论 | 详情 |
|---|---|---|---|
| 2026-05-05 | 完成阶段 6 事实与注意力治理 P0 规则层落地。; 追加：实现 acf review stale 只读机械检查命令。; 追加：补充 Context 文件级审阅标记最小规范。; 追加：增强 acf review stale JSON 输出契约。; 追加：增强 review stale clean 状态和 next_actions。 | v0.0.3.18 将默认目标收敛为维护低噪声、高权威、任务相关的默认注意力入口；P1 review stale / curate draft 仍仅为路线。; 追加：review stale 已覆盖默认注意力入口的 stale candidates 输出；curate draft 仍保持为后续路线。; 追加：review stale 已能识别 Last reviewed / 上次审阅 标记；dogfooding Context 当前不再产生缺少审阅标记候选。; 追加：review stale 现在输出 summary 和统一 stale item 字段；message 兼容字段暂保留，curate draft 仍未实现。; 追加：review stale 现在无候选时明确报告 clean，有候选时按 kind 给出机械下一步建议；仍不裁决语义、不写文件。 | `worklog/daily/2026-05-05.md` |
| 2026-05-03 | 实现 acf new worklog --append 的 AI-safe 定点补记能力，补齐稳定 JSON/error_code、dry-run preview、repo-relative POSIX 路径、结构化 warnings 和 anchor 缺失失败契约。; 追加：补充 worklog append anchor 守护测试，确保 render_worklog_daily 与模板示例保留 ## 今日完成 和 ## 有价值的结论。; 追加：完成 v0.0.3.17 第二轮有效性评测补证：本仓库基线、临时新项目主路径、worklog append 分支和 3 个真实项目只读升级/严格检查均通过；KnowledgeConnector 暴露 schema 已齐但内容状态漂移的诊断样本；当前剩余主要缺口是稳定安装入口仍停留在 v0.0.3.16。; 追加：根据用户反馈将下一轮 v0.0.3.17 验证整理为正式任务计划：覆盖稳定安装最小环境、真实项目写入闭环、worklog append/force 边界、跨项目健康/漂移样本和用户旅程摩擦点；旧 Done 计划已归档，新计划聚焦 T001。; 追加：完成 T001 稳定安装验证：全局 acf 已由 v0.0.3.16 更新到 v0.0.3.17；隔离最小标准项目验证 init/status/upgrade dry-run/check 主路径，strict 因模板占位符按预期失败；fcc_workspace、papers、register 使用稳定入口的 status、upgrade dry-run 和 strict check 均通过。; 追加：完成 T002 真实项目轻写入闭环：在 E:\Codes\TempCodes\register 使用稳定入口 acf v0.0.3.17 先 dry-run，再创建并追加 2026-05-03 daily worklog；写后 strict check 通过，目标项目只产生预期 worklog diff；当前计划焦点切到 T003。; 追加：完成 T003 worklog append/force 边界与恢复矩阵：稳定入口在隔离项目中正确返回 TARGET_EXISTS_APPEND_REQUIRED、APPEND_FORCE_CONFLICT、ANCHOR_NOT_FOUND；append 恢复成功，dry-run 和失败分支均不改文件 hash；路径、错误 JSON 和 warnings 契约复核通过；当前计划焦点切到 T004。; 追加：完成 T004 跨项目健康/漂移分类评测：fcc_workspace、papers、register 作为健康样本通过稳定入口只读主路径；KnowledgeConnector 作为 schema 已齐但内容状态漂移的诊断样本，upgrade dry-run no-op，strict check 暴露 27 个一致性错误且无 diff；.acf.lock 观察纳入 T005 摩擦点整理。; 追加：完成 T005 与本轮评测收口：审阅 T001-T004 证据后，将 v0.0.3.17 稳定安装、真实写入闭环、错误码恢复矩阵、跨项目 healthy/diagnostic 分类结论写入 Context；将最小 scenario smoke runner 产品化和 .acf.lock 运行态残留处理作为开放问题保留；大任务计划已标记 Done。; 追加：根据用户反馈补齐 T005 摩擦点决策矩阵，将 T001-T004 证据压缩为决策去向、smoke runner 候选范围和 v0.0.3.17 推荐版本结论；.acf.lock 残留单独进入 Feedback_Inbox F014 作为待分类改进候选。; 追加：根据用户收口建议归档 v0.0.3.17 稳定安装与跨项目评测：先将 F014 后续口径改为 .acf.lock 三分法复现分类，再归档 Current_Task 和 Task_Plan，使 T001-T005 从 active 工作转入 archive 证据。; 追加：完成 F014 .acf.lock 残留复现分类：正常串行读写和正常并发撞锁拒绝后不残留锁；硬中断持锁进程会留下 .acf.lock，因此归类为异常中断运行态副作用，并归档任务与计划。; 追加：实现最小 smoke runner：新增 scripts/minimal_smoke.py，用隔离临时目录和 CLI JSON 输出覆盖 init -> nested status/check、worklog create/append/error_code、Workstream minimal happy path；同步 README 与 docs/Automation，并归档任务和计划。 | append 能力限定在 daily worklog，并通过 --append 参数与 --force 替换语义区分，避免引入全局 append 语义。; 追加：worklog append 的模板 anchor 依赖已由专门测试显式守护。; 追加：T005 的价值应是把评测证据转成后续决策，而不是只写过程总结。; 追加：v0.0.3.17 评测闭环已归档；active 区域只保留 F014 作为后续待分类反馈。; 追加：F014 不需要立即开 CLI 修复任务；后续只保留可选清理提示或仓库卫生说明。; 追加：最小 smoke runner 只做发布前快速回归，不替代真实项目批量评测、漂移样本诊断或复杂 upgrade 审查。 | `worklog/daily/2026-05-03.md` |
| 2026-05-01 | 补强 usage log 反馈记录能力：确认自动 usage event 只适合记录命令元数据，新增显式 acf log feedback 用于记录实际使用反馈正文，并同步文档、版本和测试。 | 无。 | `worklog/daily/2026-05-01.md` |
| 2026-04-30 | 沉淀 Workstream 设计计划，完成 dogfooding gate、front matter 基础设施、upgrade 兼容矩阵、CLI/check 规格和 ADR 候选 | Workstream 应定位为可选并行目标线协作契约；front matter parser 独立于 Workstream；upgrade/check 必须 optional first；ADR-0005 先保持 Proposed，待 T004 实现验证后再评估 Active。 | `worklog/daily/2026-04-30.md` |
| 2026-04-29 | 实现任务规划、归档、升级、Knowledge 层增强，并完成反馈入口、回写流程、upgrade 兼容性规则和已有文件迁移修复。 | upgrade 不应只补缺失文件；对已存在但内容过期的 ACF 模板文件，需要保守 section 级迁移并用 dry-run/check-after 验证。 | worklog/daily/2026-04-29.md |
| 2026-04-27 | 实现 acf.py new task、new source、new worklog、new adr、writeback draft，引入 uv dogfooding 环境，清理 minimal 模板残留，修复 init 根薄入口生成，写入 AI-facing CLI 长期阶段计划，实现阶段 1/2/3，补充 CLI 渐进式披露入口、PATH 安装验收说明、acf edit dogfooding 规则、新增 opt-in 使用状态日志，并修复 Context 后切换到跨项目 dogfooding 评测任务。 | 当前任务、资料索引、worklog、ADR、根薄入口生成、会话回写草案、可安装入口、上下文自动发现、status、JSON 输出、dry-run、changed files、错误分类、section/table 编辑、CLI 发现提示、PATH 安装说明、docs/ai 结构化编辑规则、usage event log 和跨项目 dogfooding 评测任务已进入确定性流程。 | `worklog/daily/2026-04-27.md` |
| 2026-04-26 | 初始化本仓库的 `docs/ai` dogfooding 上下文。 | 采用 minimal 实例和根薄入口，`template/` 继续作为产品模板。 | `worklog/daily/2026-04-26.md` |

---

## 使用规则

AI 使用本索引时，请注意：

1. 不要默认读取所有 daily worklog。
2. 只有在需要追溯具体日期时，才读取对应 daily 文件。
3. 需要近期历史时，先浏览本索引的“关键结论”列，再按需读取具体 daily 文件。
4. daily worklog 是历史过程记录，不等于当前事实。
5. 如果 worklog 与 `active/Context.md` 冲突，以 `active/Context.md` 为准。
