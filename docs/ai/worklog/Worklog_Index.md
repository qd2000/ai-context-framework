本文件是工作记录索引。

请注意：

- 这里不是当前事实源。
- 当前事实请查看：`active/Context.md`
- 每日工作记录位于：`worklog/daily/`

---

## 工作记录

| 日期 | 摘要 | 关键结论 | 详情 |
|---|---|---|---|
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
