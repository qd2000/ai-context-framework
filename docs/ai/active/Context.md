本文件记录项目当前阶段的有效上下文。

- 长期目标请查看：`reference/Project_Brief.md`
- 当前具体任务请查看：`active/Current_Task.md`
- 本文件只维护当前阶段目标和当前有效事实

---

## 审阅标记

- Last reviewed: 2026-05-05
- Review scope: 文件级；确认本文件仍适合作为当前阶段目标、当前事实、约束和开放问题的默认注意力入口。

---

## 当前阶段

Dogfooding MVP / 框架稳定化。

---

## 当前阶段目标

1. 验证本框架可以作为本仓库自身的 AI 上下文系统使用。
2. 用 `acf` 将模板生成、简化、完整度检查和结构化维护自动化，降低人工维护成本。
3. 规划并逐步实现下一批确定性维护命令。
4. 将 `acf` 逐步演进为可安装、可在任意目录调用、主要面向 AI 使用的上下文维护 CLI。

---

## 当前阶段范围

### 当前阶段要做

- 维护 `template/` 作为可复制的产品模板。
- 维护 `docs/ai/` 作为本仓库真实 dogfooding 上下文。
- 保持 CLI 无第三方运行依赖。
- 用检查命令发现结构漂移、断链、状态不一致和索引遗漏。

### 当前阶段不做

- 不做常驻 agent runtime。
- 不引入向量库、数据库或私有上下文存储。
- 不把 `acf` 做成通用 Markdown 编辑器。
- 不让 subagent 静默修改权威上下文。
- 不把 `template/` 的占位内容当作当前项目事实。

---

## 当前有效事实

1. 本仓库的核心产物是 `template/` 标准 AI 上下文模板。
2. `docs/ai/` 是本仓库真实使用中的 standard dogfooding 上下文实例。
3. `acf` 是无第三方依赖的辅助 CLI，已支持 `status`、`init`、`simplify`、`check`、`new task`、`new source`、`new worklog`、`new adr`、`writeback draft`、`edit section`、`edit table upsert` 和 `log enable|disable|status|tail|summarize|prune`。
4. `acf check --strict` 会把检查目标中的占位符残留视为错误。
5. 本仓库已使用 `pyproject.toml` 和 `uv.lock` 建立最小 uv Python 环境，Python 版本约束为 `>=3.10`。
6. 本仓库运行 Python 代码时，优先使用 `uv run python ...`。
7. `docs/ai/` 当前应通过 `uv run acf check --strict`。
8. 当前已有测试覆盖 CLI 的生成、检查、状态校验、索引一致性、strict 占位符检查、task/source/worklog/ADR 自动生成、writeback draft、上下文自动发现、status、JSON schema、错误分类、section/table 编辑、usage event log 和 console script 配置。
9. `init --profile minimal` 和 `simplify` 不再向真实 minimal 实例复制 ADR 模板文件与 daily worklog 模板文件；真实 ADR 和 worklog 应通过 `new adr`、`new worklog` 生成，`simplify` 会保留已有真实 ADR 和 daily worklog。
10. `acf init` 会在推断出的项目根目录生成缺失的薄入口 AGENTS.md；已有根入口默认不覆盖，需要 force root agent 参数才覆盖。
11. 两层 AGENTS.md 设计已由 `decisions/ADR-0003.md` 记录：根目录薄入口负责发现和转发，上下文目录内入口负责完整导航。
12. `../Automation.md` 记录自动化边界、后续 CLI 命令和 subagent 草案路线。
13. `template/` 中的占位符是产品模板内容，不是本仓库事实。
14. `template/` 是面向使用者的产品源，新增或修改前应确认是通用模板需求；本仓库 dogfooding 特例应写入根入口、`docs/ai/` 或维护文档，不写入通用模板。
15. `writeback draft` 只生成 `worklog/writeback-drafts/` 下的可审阅草案，不直接修改权威上下文文件。
16. `decisions/ADR-0004.md` 已记录长期产品方向：`acf` 应演进为可安装、任意目录可调用、主要面向 AI 的上下文维护 CLI。
17. `../Automation.md` 已记录 AI-facing CLI 的阶段路线：可安装与上下文发现、AI 友好输出、安全结构化编辑、草案/subagent 接入、跨项目 dogfooding 评测。
18. `pyproject.toml` 已提供 `acf` console script，模板文件通过 setuptools data files 随包安装；本仓库开发入口仍保留 `uv run python acf.py ...`。
19. `acf status` 已能从当前目录向上发现 `docs/ai` 或上下文根目录，并输出项目根、上下文目录、profile、当前任务状态和检查结果。
20. `acf check`、`acf new ...` 和 `acf writeback draft` 在省略上下文路径时，会使用自动发现到的上下文；显式传入路径时仍以显式路径为准。
21. `acf status --json` 和 `acf check --json` 已提供机器可读输出。
22. 写命令已支持 `--json`、`--dry-run`、`--check-after`，并输出 changed files。
23. `acf check template` 会校验 `pyproject.toml` 中模板 data-files 与 `template/` 文件同步，降低新增模板文件后打包遗漏的风险。
24. JSON 输出已包含基础稳定字段：`schema_version`、`ok`、`error_code` 和 `next_actions`；检查失败时 `error_code` 为 `check_failed`。
25. acf 退出码已区分成功、检查失败、输入错误、安全拒绝和非预期运行时错误；JSON 错误响应会包含 `message` 和 `next_actions`。
26. `acf edit section get|replace|append` 已支持读取、替换和追加上下文根目录内 Markdown section，并继承 JSON、dry-run、changed files 和 check-after 契约。
27. `acf edit table upsert` 已支持按 key column 更新或追加 Markdown 表格行，目标限制在上下文根目录内已有 `.md` 文件。
28. 模板入口、minimal init 产物和当前 dogfooding 入口已补充 CLI 渐进式披露入口：默认只提示 `acf status --json`、`acf --help` 和按需读取系统手册，不在入口列完整命令手册。
29. README 和产品手册已补充安装到 PATH 的说明：开发期可用 `uv tool install -e .` 安装可执行命令，并用 `uv tool update-shell`、`where acf` 或 `which acf` 验证。
30. 后续维护 `docs/ai/` 内上下文计划、规则、worklog 或索引时，应优先 dogfood `acf edit section` 或 `acf edit table upsert`，先用 `--dry-run --json` 预览高风险写入。
31. `acf edit` 当前安全边界是 context-root 内已有 Markdown 文件；`../Automation.md` 等 `docs/ai/` 外仓库级文档暂时仍通过常规补丁维护，项目级安全编辑能力需单独设计。
32. `acf log enable|disable|status|tail|summarize|feedback|prune` 已实现默认开启的用户级全局 usage event log，日志默认存放在 `%USERPROFILE%\.acf\projects\<project-id>\` 或 `~/.acf/projects/<project-id>/`，按项目子目录记录命令结果元数据和显式反馈事件用于 dogfooding 评测。
33. 自动 usage event 不写入项目目录或 `worklog/`，不记录正文输入、stdin 内容、Markdown diff 或完整 stdout/stderr；实际使用反馈正文只能通过显式 `acf log feedback --text/--input` 记录；测试可用 `ACF_HOME` 指定隔离的日志根目录；日志写入带用户级锁，配置和 prune 重写使用原子替换。
34. `active/Task_Plan.md` 已成为当前大任务计划和轻量子任务板，默认读取但必须保持短、准、低噪音。
35. `archive/Archive_Index.md`、`archive/tasks/` 和 `archive/plans/` 已成为旧当前任务和旧大任务计划的归档结构，archive 默认不读取。
36. `reference/Knowledge_Index.md` 和 `reference/knowledge/` 已成为可复用经验层；Knowledge 不保存当前事实、不保存一次性过程、不重复 ADR 或 rules。
37. `acf upgrade`、`acf plan ...`、`acf task ...`、`acf archive ...` 和 `acf knowledge ...` 已实现第一版，并继承 JSON、dry-run、changed files 和 check-after 契约。

38. 已完成一轮新版 CLI dogfooding 评测：本仓库 usage log 记录 33 个事件、临时新项目 usage log 记录 12 个事件，`init/status/check/upgrade/plan/task/archive/knowledge` 主路径均可跑通。
39. 本轮评测发现的优先改进方向包括：`plan status` next_task 推荐逻辑、同文件写命令并发保护、Knowledge 草案质量检查、plan complete 体验、PowerShell 长 Markdown 输入提示和中文标题 slug 策略；详情见 `worklog/daily/2026-04-29.md`。

40. `acf --version` 已支持版本输出，当前版本以最新版本事实为准。
41. P1/P2 dogfooding 改进已落地：`plan status` 推荐逻辑考虑 Active 与依赖，写命令增加 `.acf.lock` 互斥，Knowledge strict 检查拦截草案占位，新增 `plan complete`，中文标题 slug 保留安全 Unicode，文档补充 PowerShell `--input` 提示。

42. `acf upgrade` 进一步增强旧文档兼容：可补旧 standard/minimal AGENTS 读取顺序，并为旧 System Manual 补充升级流程和相关命令说明。
43. Windows 命令定位说明已修正：PowerShell 使用 `Get-Command acf`，CMD 使用 `where.exe acf`。
44. P2 剩余改进已落地：`task start` 会生成更完整的 `Current_Task.md` 并默认拦截未完成依赖；Knowledge apply/check 增加确定性相似度去重；`upgrade` 对高度自定义旧文档会追加 `ACF:UPGRADE-NOTES` marker 块并保持幂等。
45. 开发调试阶段 usage event log 已改为默认开启；日志写入增加用户级锁，配置和 prune 重写使用原子替换，`log summarize` 支持 `--days`、`--since`、`--command`、`--errors-only` 和 feedback_count 统计。
46. 新增 `active/Feedback_Inbox.md` 作为人工临时反馈、问题、需求和计划碎片入口；AI 应先整理归属，不要把其中随想直接当作已确认事实。
47. `docs/ai` 已从 minimal dogfooding 上下文补齐为 standard 上下文，包含 rules 按需规则、Architecture、Tech_Context 和 System_Manual。
48. 版本号维护规则已进入项目规则：修改 CLI 对外行为、模板结构、打包文件、命令契约、默认策略或用户可见文档时，需要判断是否更新 version number；更新时优先使用 `uv run acf version set <version>`。
49. 真实项目 strict 检查会忽略 ADR template 和 YYYY-MM-DD daily worklog 这两个示例模板文件的占位符，模板源自身仍通过 `acf check template` 暴露占位符 warning。

50. 会话结束回写协议已改为落盘优先：可确定内容应优先写入对应文件或生成可审阅草案，最终回复只报告实际变更、草案路径、验证结果和仍需人工判断的风险。
51. Feedback_Inbox 生命周期已明确：Open/Triaged/Planned/Done/Rejected 各有处理规则，Done/Rejected 需要证据位置或拒绝原因，长期已处理反馈归档到 `archive/feedback/`。
52. `acf init` 和 `acf upgrade` 已补齐 `archive/feedback/` 目录；旧上下文升级会非破坏式补齐反馈归档结构。
53. T002-T005 已完成验证：`uv run acf check template`、`uv run acf check docs/ai --strict --json`、`uv run acf upgrade docs/ai --dry-run --json`、`uv run acf version show --json` 和 `uv run python -m unittest` 均通过。
54. `acf --version` 当前版本记为 `v0.0.3.25`，`pyproject.toml`、`uv.lock` 和本地包元数据同步为 `0.0.3.25`。
55. 修改 `template/`、默认上下文结构、打包清单或 `acf upgrade` 行为时，必须评估旧版本上下文升级兼容性；新增结构应同步到 init 文件清单、upgrade 补齐清单、data-files、文档、init/upgrade 测试和 upgrade compatibility runner。
56. `acf upgrade --help` 已明确当前 schema 会补齐 Feedback_Inbox、Task_Plan、archive、archive/feedback 和 Knowledge；旧上下文升级演练已验证 dry-run、正式 upgrade --check-after 和 check 均可通过。
57. `acf upgrade` 已支持对已存在但内容过期的 ACF 模板文件做保守 section 级迁移：AGENTS、Feedback_Inbox、Project_Rules 和 System_Manual 会在识别到旧段落时更新；无法识别的自定义文档仍通过 marker notes 非破坏式提示。
58. Workstream 可选层的 T002 读取规则已通过 dogfooding 明确：`init`/`upgrade` 默认不启用 Workstream；仅当存在 Active、Blocked 或 ReadyToMerge workstream，或需要整理并行协作时，才按需读取 Workstreams 索引。
59. 已完成最小 Workstream dogfooding gate：`Workstreams.md` 和 `workstreams/WS001.md` 记录 WS001 从 Open 到 Done 的试运行、ReadyToMerge 合并请求和 evidence；当前 Workstream 索引状态为 Inactive。
60. `decisions/ADR-0005.md` 已作为 Proposed ADR 记录可选 Workstream 层的稳定取舍；T004 实现并验证后再评估是否改为 Active。
61. T004 第一刀已完成：`acf workstream init/status/list/show` 可用；实现范围限定为 Workstream 数据模型、front matter schema 校验、scope normalize、initialized 判断和最小查询/初始化命令。
62. T004 第二刀已完成：`acf workstream add/set/block/cancel` 可用；`add` 需要显式 `--id`，会生成详情文件并同步索引；`set` 只允许基础状态转换；`block` 和 `cancel` 必须提供 reason 并写入详情文件。
63. T004 第三刀已完成：`acf workstream merge-request/ready/done` 可用；`merge-request` 只覆盖详情文件的合并请求 section，不改权威上下文；`ready` 要求 Active 状态且合并请求含 target 和候选摘要；`done` 要求 ReadyToMerge 状态、evidence 和 `merge_resolution`，并把证据写入详情文件。
64. T004 第四刀已完成：`acf workstream claim/note` 可用；`claim` 追加 read_scope/write_scope，typed write_scope 做命令内有限冲突检查，draft 缺 WS ID 只给 warning；`note` 只允许追加到白名单详情 section，缺失 section 自动创建；尚未实现 archive 或全局 Workstream check。
65. T004 第五刀已完成并闭环：`acf check` 已接入 optional Workstream 检查；没有 `active/Workstreams.md` 时不检查、不 warning；存在索引时检查详情目录、索引链接、front matter schema、状态必填内容、索引/详情一致性、authority/assigned 冲突和 draft 文件名 warning/strict error。
66. `decisions/ADR-0005.md` 已从 Proposed 升为 Active；可选 Workstream 层第一版实现、模板读取规则、CLI、check 和验证均已落地。
67. `acf new worklog --append` 已提供 AI-safe 的同日 daily worklog 定点补记能力：仅追加到稳定 anchor，JSON 使用稳定 error_code、repo-relative POSIX 路径、结构化 warnings、dry-run preview 和 1-based `insert_after_line`；`writeback draft --append` 暂缓。

68. `v0.0.3.17` 已完成稳定安装与跨项目评测主链路：全局 `acf v0.0.3.17`、最小标准项目 `init/status/upgrade dry-run/check`、3 个健康真实项目 `status/upgrade dry-run/check --strict` 均通过；新 init 项目 strict 因模板占位符失败属于预期的内容未填充状态。
69. 稳定入口已在真实项目 `E:\Codes\TempCodes\register` 完成 worklog create + append 轻写入闭环，写后 strict check 通过，diff 限定在 daily worklog 与 Worklog_Index。
70. `new worklog --append/--force` 错误码恢复矩阵已验证：`TARGET_EXISTS_APPEND_REQUIRED` 可按 `next_actions` 加 `--append` 恢复；`APPEND_FORCE_CONFLICT` 和 `ANCHOR_NOT_FOUND` 会安全拒绝且不写入；dry-run 不改变文件 hash；JSON 路径和 `warnings` 契约满足 AI 解析需求。
71. 跨项目评测已区分 healthy 与 diagnostic 样本：`fcc_workspace`、`papers`、`register` 为健康样本；`KnowledgeConnector` 属于 schema 已齐但内容状态漂移的诊断样本，`upgrade --dry-run` no-op，strict check 暴露 27 个一致性错误。

72. 已新增本地最小 smoke runner `scripts/minimal_smoke.py`：使用隔离临时目录和 CLI JSON 输出，覆盖 `init -> nested status/check`、`new worklog create/append/error_code` 和 Workstream 最小 happy path；不覆盖真实项目批量评测、漂移样本诊断或复杂 upgrade 审查。

73. 阶段 6「事实与注意力治理」P0 已进入产品化：模板、dogfooding 入口、Always_Active、System Manual、README、Automation 和 `writeback draft` 草案结构均强调默认注意力入口、唯一权威位置、replace 优先、历史默认不可见和 curation draft 不进入默认读取路径；P1 的 `review stale` 和 `curate draft` 最小版已实现。

74. `acf review stale` 已实现只读机械检查：覆盖 `active/Current_Task.md`、`active/Task_Plan.md`、`active/Feedback_Inbox.md`、`active/Context.md`、`reference/Knowledge_Index.md` 和 `worklog/knowledge-drafts/`，输出 `stale_items` 和 `warnings`，不做语义裁决、不写文件、不读取 archive 或全量 worklog。

75. Context 文件级审阅标记最小规范已落地：模板和 dogfooding `active/Context.md` 使用 `## 审阅标记` + `Last reviewed: YYYY-MM-DD`，`acf review stale` 可据此消除缺少审阅标记的机械候选；该规范不要求条目级事实 ID。

76. `acf review stale --json` 输出契约已增强：顶层包含 `summary.total`、`summary.by_kind` 和 `summary.by_path`；每个 stale item 统一包含 `kind`、`signal`、`path`、`reason`、`age_days`、`status` 和 `suggested_action`，并暂时保留 `message` 兼容字段。

77. `acf review stale` 已精炼 clean 状态与 `next_actions`：无 stale candidate 时明确报告 clean，有候选时按 `kind` 给出低风险机械下一步建议；这些建议仍不做事实真假判断、不触发写入。

78. `acf curate draft` 最小版已实现为 `review stale` 的机械下游：只消费 stale signal，生成 curation-drafts 目录下的日期命名可审阅注意力治理草案；无 stale candidate 时不创建空草案，同名草案已存在时安全拒绝，不读取 archive、不判断事实真假、不修改权威上下文。

79. 阶段 6 P1.5 已新增 upgrade compatibility runner：`scripts/upgrade_matrix.py` 使用 `tests/fixtures/upgrade_matrix/` 中的风险驱动最小旧形态 fixture，验证旧项目可被非破坏式带到当前工具可治理状态；quick 模式随单元测试运行，full 模式用于 release 前扩展检查。该 runner 同时暴露并修复了旧 AGENTS 与旧 System Manual 需要二次 upgrade 才完成 marker notes / 手册提示补齐的幂等性问题。

80. 阶段 6 P1.6 已新增 `reference/Context_Curation_Prompt.md`：该文件是按需读取的 AI 上下文整理 prompt 模板，默认产物是整理建议，不是文件修改；`init` 和 `upgrade` 会补齐该 reference 文件，但不自动运行 stale/curation、也不让 CLI 裁决事实真假。

---

## 当前关键约束

1. 框架必须保持模型无关。
2. 权威上下文必须是普通 Markdown，并且可人工审阅。
3. CLI 不应引入第三方运行依赖。
4. Python 命令应优先使用项目 uv 环境运行。
5. 自动化应优先做确定性检查和草案生成，不替代人的事实判断。
6. 涉及模板结构变更时，需要同时验证模板和 dogfooding 实例。
7. 新增或重置当前任务优先使用 `acf new task`；新增资料索引优先使用 `acf new source`；重要设计决策优先使用 `acf new adr`；当天工作记录优先使用 `acf new worklog`。
8. 会话结束回写建议需要暂存时优先使用 `acf writeback draft`，再审阅是否写入权威上下文。
9. 修改 `template/` 时，应同步检查 README、上下文入口说明和 System Manual 是否仍一致。
10. 任意目录 CLI 的设计应优先服务 AI 的确定性上下文维护，不扩展为自由文本编辑器或常驻运行时。

11. 维护 `docs/ai/` 内已有 section 或 table 时，优先使用 `acf edit` 的结构化写入能力；CLI 只负责确定性落盘，不裁决事实内容。
12. 不为 dogfooding 临时放宽 `acf edit` 的 context-root 限制；若需要编辑仓库级文档，应先设计安全的项目级编辑边界。

13. usage event log 是用户级运行态观测数据，不是权威上下文；日志写入失败不应影响原命令退出码。
14. Task_Plan 只保存当前大任务拆分、子任务状态、证据和下一步；详细过程进入 worklog，失效计划进入 archive。
15. Knowledge 只能通过草案流程沉淀可迁移判断；当前事实仍以 `active/Context.md`、`active/Task_Plan.md` 和 `active/Current_Task.md` 为准。

---

## 当前开放问题

1. 根薄入口生成是否需要支持少量用户自定义仓库规则字段。
2. 是否需要 writeback-curator subagent 生成更高质量的回写分类草案。
3. 是否需要为 `docs/ai/` 外的仓库级维护文档设计安全的 project-root scoped edit 能力，还是继续保持常规补丁维护。
4. 是否需要新增 `acf new rule`、`acf new reference` 等文件创建命令，让 AI 能安全创建新的上下文文档。
5. 异常硬中断持锁进程会留下 `.acf.lock`；正常串行读写和正常并发撞锁拒绝后未复现残留。后续仅需判断是否补充清理提示、`.gitignore` 或仓库卫生说明。

---

## 长期阶段计划：AI-facing CLI

定位：`acf` 是上下文文件 API，主要供 AI 在项目中稳定维护上下文；它不替代人的判断，也不作为通用 Markdown 编辑器。

1. 可安装命令和上下文发现：支持在任意子目录调用 `acf`，自动找到上下文根目录，并提供 `acf status`。（已实现第一版）
2. AI 友好输出和安全执行模式：支持 `--json`、`--dry-run`、统一 exit code、changed files 输出和写后检查。（已实现第一版）
3. 安全结构化编辑：提供 section 和 table 级别的确定性编辑，限制写入范围在上下文根目录内。（已实现第一版）
4. 草案和 subagent 接入：让 subagent 产出可审阅草案或建议 patch，不静默改写权威上下文。
5. 跨项目 dogfooding 评测：在真实项目中验证任意目录调用、检查、写入和回写流程。

详细路线和验收标准见：`../Automation.md`

---

## 已解决设计问题：AGENTS.md 的两层结构

### 已解决的问题

此前设计理念是"渐进式暴露"，但 `acf.py init` 的实现不完整：

- **设计理念**：根目录 AGENTS.md（薄入口） + docs/ai/AGENTS.md（完整入口）
- **README 说法**：第 46 行推荐"在项目根目录放置 AGENTS.md"
- **旧实现**：`acf.py init docs/ai` 只生成上下文目录内入口，不生成根目录版本
- **修复结果**：`acf.py init` 现在生成缺失的根薄入口，并保护已有根入口不被静默覆盖

### 设计意图确认

当前设计（两个 AGENTS.md）符合渐进式暴露原则：

1. **根目录 AGENTS.md**（薄入口）
   - 角色：最轻量级的仓库级配置
   - 内容：简要说明 + "详见 docs/ai/AGENTS.md" 转发
   - 维护者：仓库框架维护者
   - 频率：很少改动

2. **docs/ai/AGENTS.md**（完整入口）
   - 角色：项目当前上下文的完整导航
   - 内容：默认读取顺序 + 按需读取指引 + 事实源优先级
   - 维护者：项目团队 + AI 协作
   - 频率：按项目阶段更新

### 后续改进方向

**已完成**：
- 修改 `acf.py init` 逻辑，在推断出的项目根目录生成薄入口 AGENTS.md。
- 更新 README 和 template 入口说明，明确两层入口设计。
- 新增 `decisions/ADR-0003.md`，正式记录"渐进式暴露的两层 AGENTS.md 设计"。

**后续可选**：
- 根薄入口生成支持少量用户自定义仓库规则字段。
- 用其他真实项目验证改进后的初始化流程。

---

## 重要决策

重要决策请查看：`reference/Decisions_Index.md`

---

## 当前相关路径

- 项目根目录：`E:\Codes\Tools\ai-context-framework`
- AI 文档目录：`docs/ai/`
- 产品模板目录：`template/`
- CLI：`acf.py`
- 当前大任务计划：`active/Task_Plan.md`
- Python 项目配置：`pyproject.toml`
- uv 锁文件：`uv.lock`
- 包清单：`MANIFEST.in`
- 自动化路线：`../Automation.md`
- 资料索引：`reference/Sources_Index.md`
- 工作记录索引：`worklog/Worklog_Index.md`

---

## 容易误解的地方

1. `template/` 是产品模板，不是本仓库当前事实源。
2. `docs/ai/` 是真实 dogfooding 实例，优先级高于模板占位内容。
3. worklog 是历史过程记录，不等于当前事实。
4. subagent 适合产出草案和审阅意见，不应默认静默落盘到权威上下文。

---

## 上次更新

- 日期：2026-04-29
- 更新原因：完成反馈入口与回写流程 dogfooding 改进的协议、模板/CLI 支持和验证记录，同步当前事实与版本号。
