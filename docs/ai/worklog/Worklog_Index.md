本文件是工作记录索引。

请注意：

- 这里不是当前事实源。
- 当前事实请查看：`active/Context.md`
- 每日工作记录位于：`worklog/daily/`

---

## 工作记录

| 日期 | 摘要 | 关键结论 | 详情 |
|---|---|---|---|
| 2026-04-27 | 实现 acf.py new task、new source、new worklog、new adr、writeback draft，引入 uv dogfooding 环境，清理 minimal 模板残留，修复 init 根薄入口生成，写入 AI-facing CLI 长期阶段计划，并实现阶段 1 和阶段 2 第一版及 JSON schema 细化。 | 当前任务、资料索引、worklog、ADR、根薄入口生成、会话回写草案、可安装入口、上下文自动发现、status、JSON 输出、dry-run、changed files 和 JSON 基础字段契约已进入确定性 CLI 流程。 | `worklog/daily/2026-04-27.md` |
| 2026-04-26 | 初始化本仓库的 `docs/ai` dogfooding 上下文。 | 采用 minimal 实例和根薄入口，`template/` 继续作为产品模板。 | `worklog/daily/2026-04-26.md` |

---

## 使用规则

AI 使用本索引时，请注意：

1. 不要默认读取所有 daily worklog。
2. 只有在需要追溯具体日期时，才读取对应 daily 文件。
3. 需要近期历史时，先浏览本索引的“关键结论”列，再按需读取具体 daily 文件。
4. daily worklog 是历史过程记录，不等于当前事实。
5. 如果 worklog 与 `active/Context.md` 冲突，以 `active/Context.md` 为准。
