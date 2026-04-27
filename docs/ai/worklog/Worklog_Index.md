本文件是工作记录索引。

请注意：

- 这里不是当前事实源。
- 当前事实请查看：`active/Context.md`
- 每日工作记录位于：`worklog/daily/`

---

## 工作记录

| 日期 | 摘要 | 关键结论 | 详情 |
|---|---|---|---|
| 2026-04-27 | 设计讨论：AGENTS.md 两层结构的合理性与实现缺陷。 | 两层 AGENTS.md（根薄入口 + docs/ai 完整入口）设计符合渐进式暴露原则，问题在于 acf.py init 实现不完整。 | `worklog/daily/2026-04-27.md` |
| 2026-04-27 | 实现 acf.py new task、new worklog、new adr，引入 uv dogfooding 环境，并清理 minimal 实例模板残留。 | 当前任务、worklog 和 ADR 的创建已进入确定性 CLI 流程；Python 验证入口统一为 uv run python；minimal 真实实例不再保留 ADR/worklog 占位模板文件。 | `worklog/daily/2026-04-27.md` |
| 2026-04-26 | 初始化本仓库的 `docs/ai` dogfooding 上下文。 | 采用 minimal 实例和根薄入口，`template/` 继续作为产品模板。 | `worklog/daily/2026-04-26.md` |

---

## 使用规则

AI 使用本索引时，请注意：

1. 不要默认读取所有 daily worklog。
2. 只有在需要追溯具体日期时，才读取对应 daily 文件。
3. 需要近期历史时，先浏览本索引的“关键结论”列，再按需读取具体 daily 文件。
4. daily worklog 是历史过程记录，不等于当前事实。
5. 如果 worklog 与 `active/Context.md` 冲突，以 `active/Context.md` 为准。
