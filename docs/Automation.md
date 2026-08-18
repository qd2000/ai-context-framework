# 自动化与 subagent 路线

本项目的核心价值是模型无关、纯 Markdown、可人工审阅的上下文治理。自动化的目标不是替代判断，而是减少结构漂移、索引遗漏和重复手工维护。

顶层产品设计见 `docs/ai/reference/ACF_Top_Level_Design.md`，通用产品路线见 `docs/ai/reference/Product_Roadmap.md`。后续真实项目反馈进入 ACF 前，必须先抽象成通用上下文治理问题，并能用 fixture 或最小上下文测试验证；FCC 只作为压力测试样本之一，不作为产品需求唯一来源。

非 PetroSim dogfooding 样本见 `docs/ai/reference/Non_PetroSim_Dogfooding_Sample.md`。当前选择 EcSOS `cracking-yield-prediction-system` 作为论文 / 数据分析 / Python 工具类真实样本；默认只读或 dry-run，写入前需确认目标项目状态。

## 当前已自动化

### Continuation dogfood 反馈闭环

并行 Scheduled Task / 外部 agent 使用 `acf continuation` 时，命令级成功/失败自动进入用户级 usage log；遇到具体、可复用、证据支持的 ACF / continuation / 调度工作流缺口时，agent 通过 `acf continuation issue` 写结构化 issue。`acf log issues --all-projects --json` 按稳定 fingerprint 聚合不同 worktree 的重复 occurrence，供后续产品改进直接复用。正常 active-lease no-op、等待外部任务和业务算法失败不得记录为产品 issue。

`acf.py` 先覆盖确定性工作：

- 可安装入口：`pyproject.toml` 提供 `acf` console script；正式用户从 PyPI 使用 `uv tool install ai-context-framework`，更新使用 `uv tool upgrade ai-context-framework`；仓库开发期可用 `uv tool install -e .`，本仓库开发入口仍保留 `uv run python acf.py ...`。
- 上下文自动发现：`check`、`new ...` 和 `writeback draft` 在省略路径时，会从当前目录向上查找 `docs/ai` 或上下文根目录；显式路径仍优先。
- `status`：输出项目根、上下文目录、profile、当前任务状态和检查结果。
- AI 友好输出第一版：`status` 和 `check` 支持 `--json`；写命令支持 `--json`、`--dry-run`、`--check-after` 并输出 changed files。
- `init`：生成标准或简化上下文模板，并在推断出的项目根目录生成缺失的薄入口 AGENTS.md；已有根入口默认不覆盖，需要 `--force-root-agent` 才覆盖。
- `upgrade`：非破坏式补齐旧上下文缺失的 `active/Feedback_Inbox.md`、`active/Task_Plan.md`、标准 profile 的 human 层、archive、archive/feedback、Knowledge 结构和 active -> reference 规划依据追溯入口，不自动移动或覆盖 Active 当前任务。
- `simplify`：从已有上下文导出简化版本，保留真实 ADR 与 daily worklog，排除占位模板文件。
- `check`：检查目录、必需文件、UTF-8、乱码、空文件、内部 Markdown 引用、任务状态、决策状态、资料状态、ADR 状态一致性和 worklog 日期路径；`--strict` 会将占位符残留视为错误。
- `plan init|add-task|set-task|focus|status`、`plan reference list|add|remove` 与 `plan stage list|add|set|done`：维护当前大任务计划、轻量子任务板、`## 规划依据` 和 `## 任务阶段` 表；`plan reference` 只写 reference 路径和一句话用途，可用 `--sync-current-task` 显式同步到 Active `active/Current_Task.md`；Task Stage CLI 不创建 task object 单文件，也不自动修改 `active/Current_Task.md`。
- `task start|done|block|clear`：从任务板启动、完成、阻塞或清空当前小任务。
- `archive current-task|task-plan|list`：归档旧当前任务或旧大任务计划，并维护 `archive/Archive_Index.md`。
- `knowledge draft|apply|list|show|mark`：生成可审阅 Knowledge 草案，审阅后写入可复用经验索引，并维护状态。
- `new task`：生成或重置 `active/Current_Task.md`，默认拒绝覆盖 Active 任务，除非传入 `--force`。
- `new source`：向 `reference/Sources_Index.md` 添加或更新资料索引行，默认拒绝重复资料标题，除非传入 `--force`。
- `new worklog`：按日期生成 daily worklog，并向 `worklog/Worklog_Index.md` 添加或更新索引行。
- `new adr`：生成下一个 ADR 文件，并按 Active 或 Proposed 状态更新 `reference/Decisions_Index.md`。
- `writeback draft`：把会话结束回写建议保存到 `worklog/writeback-drafts/`，生成可审阅草案，不直接修改权威上下文文件。
- `edit section get|replace|append`：读取、替换或追加上下文根目录内 Markdown 文件的指定 section body。
- `edit table upsert`：按 key column 更新或追加上下文根目录内 Markdown 表格行。
- `doctor`：面向人和 AI 的健康诊断入口，复用 `check` 并报告跨文件生命周期漂移、终态 Workstream authority scope 残留、generated index 漂移、attention hygiene 和本地数据副本证据信号；`--fix safe` 只执行确定性低风险修复，`--report` 和 `--draft-semantic` 生成可审阅产物，`--projects` 支持多项目只读诊断。
- `workstream reserve`：在 primary branch 上通过预约锁、跨 active/archive/Git/journal 编号扫描和 reservation-path 冲突校验，创建唯一 WS 占位提交；使用 Git 的路径限定提交保留其他 agent 的 staged/unstaged/untracked 修改，只阻断 detail/index 自身或其父子路径发生碰撞；它不创建 branch/worktree，原 `workstream add` 不加载 Git 生命周期。
- `worktree create|attach|verify|list|audit|sync|merge-plan|merge|artifact-plan|artifact-migrate|close|resume`：供 AI 选择调用的可选 Git 生命周期。merge 固定使用临时 integration worktree，primary 只做 collision-aware fast-forward promotion；operation journal 记录候选、检查、artifact、等待、重规划、冲突现场和 promotion。短时锁、路径状态和 HEAD 推进有限重试；冲突或检查失败保留 integration worktree供 resume；ignored/untracked 结果通过 handoff manifest 分类和摘要验证；close 与 merge 共用 lifecycle 锁并支持文件占用退避和部分成功恢复。
- `continuation init|configure|doctor|coordination status|coordination attempt|coordination challenge|claim|assert-owner|heartbeat|progress|effect prepare|effect update|effect list|workspace status|workspace intent|workspace refresh|reconcile|recover|renew|checkpoint|release|pause|resume|prompt|issue`：为外部 AI scheduler 或人工多轮任务提供模型无关的 bounded continuation 控制面。时序参数拆分为 scheduler interval、lease TTL、renew interval、heartbeat recommendation 与 stale threshold；`long-running` profile 默认 `60/180/45/10/25` 分钟，已有 task 可用 `continuation configure --profile long-running` 原位切换。每个 runner 先登记 bounded attempt；已有 owner 时 contender 自动 open/join challenge，但 challenge 本身不授予写权限。普通可定位项目的 ACF 命令只 opportunistic 提示当前 owner generation 的 pending challenge，绝不充当 ACK；owner-protected continuation 命令只有在 `lease_id + generation + fence_token` 校验成功后才 authenticated touch，release 则解析为 `owner_released`。challenge timeout 仅是 `ownership_forfeiture_candidate`，formal preemption 仍必须消费 workspace/HEAD/effect/identity reconcile evidence，并由 generation fencing 保证最多一个 writer。ownerless recovery 如已有外部权威证明某个**既存 deterministic effect identity** 已 terminal，可在 `reconcile` receipt 中显式携带 `--effect-key/--effect-terminal-status/--effect-external-id/--effect-evidence-ref`；该路径只记录 observation，不触发外部动作，不允许新建 effect 或替换 external id，并把 receipt 绑定 observed effect digest，只有后续 `recover` 仍完全匹配时才 terminalize journal，unknown、identity mismatch、observation drift 继续 fail-closed。workspace manifest v2 使用 bounded Git path/status/digest 管理 `baseline_external / task_owned / external non-overlap / conflict`，但 worktree-level `clean/dirty` 不参与 liveness、claim、release、reconcile、recover 决策。正常 release 可保留未提交 task-owned WIP 并 handoff 到下一 generation，Git commit 只服务自然语义 checkpoint；ownerless handoff 期间 task-owned digest 漂移才产生真实 conflict。无 manifest 的 changed paths 报 `workspace_provenance_missing`，而不是笼统 `worktree_dirty`。Scheduled Task 的小时触发只是唤醒，不截断自然 Gate；`acf continuation prompt` 是唯一 generic Scheduled Task protocol 权威，项目 wrapper 每轮重新读取它，只保留固定身份和项目特有 Runtime/科学/权限/验收约束。运行态只保存在用户级 `~/.acf/projects/.../continuation/`，ACF 不保存 transcript/raw tool output、不创建定时任务、不运行常驻 agent。设计见 `docs/ai/reference/Continuation_Control_Design.md`。
- 使用状态日志：`log enable|disable|status|tail|summarize|projects|prune` 管理默认开启的用户级全局 usage event log，按项目子目录记录命令结果元数据；`log projects --scan-root <path> --json` 支撑跨项目 dogfooding 和旧项目升级盘点。
- CLI 渐进式披露入口：`acf status|next` 未显式选择 Workstream 时返回 `GlobalOnly`，只给全局文件指针和 Workstream 摘要；attention 不参与路由。显式 `--workstream`、Active Current_Task 唯一绑定或 verified worktree 只返回 pointer-only 入口，随后再调用 `acf workstream context WSNNN` 才披露专属内容。冲突或无效选择保持全局并以结构化错误 fail-closed。模板和 minimal init 产物只提示这些入口、`acf --help` 和系统手册发现路径，不在默认入口列完整命令手册。
- 最小 smoke runner：`scripts/minimal_smoke.py` 使用隔离临时目录和 CLI JSON 输出，覆盖 `init -> nested status/check`、`new worklog create/append/error_code`、Workstream 最小 happy path、archive-candidates / archive-draft / explicit archive 主路径和 Task Stage 最小 happy path；Git worktree 事务由 `tests/test_worktree_cli.py` 的临时真实仓库矩阵单独覆盖，不接触用户仓库。
- 升级兼容 runner：`scripts/upgrade_matrix.py` 使用风险驱动 fixture 验证旧上下文可被非破坏式带到当前工具可治理状态；quick 模式随单元测试运行，full 模式用于 release 前扩展检查。
- 发布验收 runner：`scripts/release_check.py` 可运行 template/strict、minimal smoke、unit、full upgrade matrix，并在隔离 uv 环境中分别安装 wheel 与 sdist，验证 `acf --version`、`acf init`、`acf check --strict` 和 `uv tool install` console script。
- 一键安装/更新脚本：`scripts/install_acf.ps1`、`scripts/update_acf.ps1` 和对应的 `sh` 入口只依赖已安装的 uv；GitHub Actions 的 CI 和 `v*` tag 发布 workflow 负责测试、构建和 PyPI 发布，Trusted Publishing 配置仍需在 GitHub/PyPI 侧完成。
- Context governance fixture matrix：`tests/fixtures/context_matrix/` 和 `tests/test_context_matrix.py` 覆盖 minimal clean、legacy reference、audit long section、complex Workstream、Workstream lifecycle/archive candidate 和 authority gate，作为 P3 audit rule expansion 前的防过拟合样本。

这些检查不需要模型判断，适合作为每次模板修改后的基础验证。

## 长期阶段计划：AI-facing CLI

长期方向是把 `acf` 从仓库内脚本演进为可安装、可在任意目录调用、主要面向 AI 使用的上下文维护 CLI。它的定位是上下文文件 API，而不是通用 Markdown 编辑器。

### 阶段 1：可安装命令和上下文发现

状态：已实现第一版；PyPI 发布、安装、更新和发布前验收闭环已加入仓库，正式启用还需配置 PyPI 项目和 Trusted Publishing。

目标：

- 提供可安装命令 `acf`，保留 `uv run python acf.py ...` 作为本仓库开发入口。
- 支持从任意子目录自动发现上下文根目录。
- 增加 `acf status`，输出当前项目根、上下文目录、profile、当前任务状态和最近检查结果；默认不选择 Workstream，显式 `--workstream` 才返回专属 pointer。
- 写操作默认作用于发现到的上下文目录，也允许显式传入目标路径覆盖。

验收：

- 在项目任意子目录运行 `acf status` 能定位同一套上下文。
- 不传路径即可运行常用 `check` 和 `new` 命令。
- 无新增第三方运行依赖。

### 阶段 2：AI 友好输出和安全执行模式

状态：已实现第一版，并完成 JSON schema 基础字段、exit code 和错误分类细化。

目标：

- 全局支持 `--json`，让 AI 能稳定读取 changed files、warnings、errors 和 next actions。
- 全局支持 `--dry-run`，预览写入结果。
- 写命令输出被修改文件列表，并可选执行写后 `check`。
- 统一 exit code，区分成功、检查失败、输入错误和安全拒绝。

验收：

- AI 无需解析自然语言输出即可判断下一步。
- 所有写命令都有 dry-run 测试。
- 失败输出包含足够定位问题的信息。

已完成：

- `status --json` 和 `check --json` 输出可解析 JSON。
- JSON 输出包含 `schema_version`、`ok`、`error_code` 和 `next_actions`。
- 检查失败时 `error_code` 为 `check_failed`，AI 可以读取 `next_actions` 决定后续动作。
- 退出码已区分成功、检查失败、输入错误、安全拒绝和非预期运行时错误。
- 写命令输出 changed files，支持 `--dry-run --json` 预览。
- 写命令支持 `--check-after`。
- `check template` 会校验 `pyproject.toml` 中模板 data-files 与 `template/` 文件同步，避免打包漏文件。

### 阶段 3：安全结构化编辑

状态：已实现第一版。

目标：

- 提供面向 AI 的结构化 Markdown 编辑原语，而不是自由文本编辑器。
- 支持 section get、section replace、section append。
- 支持 table upsert，用于维护索引类文件。
- 所有编辑必须限制在上下文根目录内，拒绝路径穿越。

验收：

- 常见上下文维护任务可以通过 CLI 完成，不需要 AI 手工拼接整文件。
- 写入后 `check --strict` 能稳定发现结构漂移。
- CLI 不理解语义，只做确定性文件编辑和校验。

已完成：

- section get 支持读取精确 Markdown heading 下的正文，并可输出 JSON。
- section replace 和 section append 支持 `--text`、`--input`、stdin、`--json`、`--dry-run` 和 `--check-after`。
- table upsert 支持精确表头或首表匹配，按 key column 更新或追加行。
- edit 写操作只允许目标为上下文根目录内已有 `.md` 文件，并拒绝路径穿越和非 Markdown 目标。

### 阶段 4：草案和 subagent 接入

目标：

- 保持权威上下文由人或主代理审阅后写入。
- 让 subagent 产出分类草案或建议 patch，而不是静默修改权威文件。
- 优先完善 `writeback-curator`、`decision-curator`、`history-distiller` 和 `source-curator`。

验收：

- subagent 输出可以直接转成 `writeback draft` 或 dry-run patch。
- 权威文件写入仍有明确审阅点。
- 不引入常驻 runtime、数据库或私有存储。

### 阶段 5：跨项目 dogfooding 评测

目标：

- 在其他真实项目中验证初始化、发现、检查、写入和回写流程。
- 默认启用用户级全局 usage event log，按项目子目录记录命令成功率、错误类型、dry-run 使用和 changed files 规模。
- 记录 AI 使用 CLI 与直接手改 Markdown 的错误率差异。
- 只把重复出现的人工动作产品化成新命令。

验收：

- 任意目录调用的成功率和错误信息可评估。
- 常见维护动作中，大多数可以由 CLI 完成。
- 新能力没有破坏“纯 Markdown、模型无关、人工可审阅”的边界。
- usage event log 只记录状态元数据，不记录正文输入，不进入 `worklog/`。

### 阶段 6：事实与注意力治理

状态：P0 governance hardening 已以 `v0.0.3.26` 作为稳定基线收口；P1 `audit context` MVP 已实现为只读 candidates 命令，不生成 patch，不接入默认 strict。既有 `review stale`、`curate draft` 最小版、upgrade compatibility runner 和 Context Curation Prompt Template 继续保留。

目标不是保存更多上下文，而是持续维护一个低噪声、高权威、任务相关的默认注意力入口。

原则：

- `active/` 只保留当前目标、当前事实、当前任务和下一步。
- 写入前必须判断唯一权威位置；能更新旧表述时，不追加重复事实。
- worklog 记录历史过程，archive 保存历史材料，Feedback_Inbox 和 human 保存待处理或未整理信号；它们默认不作为当前事实。
- 整理事实时优先读取 changed files、`active/`、相关索引和最近 worklog。
- 不为 curation 默认读取 archive 或全部历史日志；writeback draft 和 curation draft 不进入默认读取路径。
- CLI 只做机械发现和草案生成，不裁决语义事实。

P1 命令：

- 已实现：`acf review stale` 机械检查默认注意力入口是否可能过期，例如 Active 当前任务长期未更新、Feedback 长期未处理、Context 缺少审阅信号、Knowledge 草案长期未推进；命令只读，只输出 stale candidates，不判断内容真假。
- 已实现：Context 文件级审阅标记最小规范，推荐 `Last reviewed: YYYY-MM-DD` / `上次审阅：YYYY-MM-DD`，不要求条目级事实 ID。
- 已实现：`acf review stale --json` 输出契约增强，提供稳定 `kind`、`reason`、`age_days`、`status`、`suggested_action` 字段和 `summary.by_kind` / `summary.by_path` 汇总。
- 已实现：`acf review stale` 的 clean 状态和 `next_actions` 精炼；无 stale candidate 时明确报告 clean，有候选时按 `kind` 给出低风险机械下一步建议。
- 已实现：`acf curate draft` 最小版只消费 `review stale` 的结构化 stale signals，生成 `worklog/curation-drafts/` 下的可审阅注意力治理草案；无候选时不创建空草案，同名草案已存在时安全拒绝。
- 已实现：`acf audit context` MVP，只读输出 active 层上下文治理 candidates；第一版仅覆盖 `active_section_too_long`、`stale_current_task_or_workstream_stage` 和 `terminal_conclusion_not_merged`（ReadyToMerge 待合并或 Done 缺合并结果），不判断事实真假、不写文件、不接入 strict。
- 已实现：`acf doctor`，设计文档为 `docs/ai/reference/Doctor_Reconcile_Design.md`；命令默认只读，报告 Task / Current_Task 生命周期漂移、终态 Workstream authority scope 残留、Workstreams / Archive generated index 漂移、Workstream 协议 drift、Decisions / Sources / data evidence 和 attention hygiene findings；`--fix safe` 只做可回退的确定性修复，数据 hash 证据只读取项目根内相对路径，`--report` / `--draft-semantic` 生成人工可审阅产物，`--projects` 用于多项目只读巡检。
- 已实现：upgrade compatibility runner，以 `tests/fixtures/upgrade_matrix/` 的最小旧形态 fixture 验证旧项目可以升级到当前工具可治理状态，而不是自动变干净；runner 先执行 `upgrade --plan --json` 验证只读评估和 no-write/no-log，再执行 dry-run/apply/idempotency 检查；quick 模式随单元测试运行，full 模式作为 release 前扩展检查。
- 已实现：`reference/Context_Curation_Prompt.md` 作为按需读取的上下文整理 prompt 模板，帮助 AI 输出整理建议；它不是默认 active 规则，也不是 CLI 自动语义清理能力。
- 后续增强：`acf curate draft` 可再考虑基于 changed files、`active/`、索引文件和最近 N 天 worklog 生成更丰富整理草案，列出疑似重复事实、疑似陈旧 active 内容、已完成但未归档任务、已处理但仍留在 inbox 的内容，以及可能应升格到 Context / Knowledge / ADR 的近期结论。

暂缓：

- 全量事实 ID 化。
- 每条事实 `Last reviewed`。
- 语义级自动去重。
- CLI 自动判断哪个事实是真的。
- curation draft 默认进入读取路径。

### P0 governance hardening baseline

状态：已完成，基线版本为 `v0.0.3.26`。

**P0 governance hardening**：先把 FCC 暴露的阶段注册、Workstream 内部阶段焦点、权威写入、合并结果、active 滞留做成 `acf check --strict` 的确定性门禁；generated index 只在 Workstream 上先检测后 sync；content audit 独立后置，不进入默认 strict。

实施顺序：

1. Task Stage registry：在 `active/Task_Plan.md` 增加 `## 任务阶段` 表，检查 `T001.4` 这类阶段编号的注册、父任务和 Workstream 绑定。
2. Workstream Stage Focus：在 Workstream 详情中支持 optional `current_stage` 和 `## 阶段` 表，检查 `WS004.2` 这类内部阶段注册、归属、唯一 Active 阶段和终态 Workstream 阶段状态；第一版不实现 stage CLI，也不实现全局 `active/Current_Task.md` 阶段对齐。
3. Authority write gate + `merge_targets`：禁止 Workstream 通过 `owned` / `assigned` 直接 claim 内置 authority path；需要影响权威文件时使用 `merge_targets` 和合并请求；本阶段不做 `merge_resolution`。
4. Merge resolution + active retention gate：Done Workstream 必须有 evidence 和 `merge_resolution`；Done / Cancelled 留 active 必须有 `keep_active_reason` 和 `keep_active_until`。
5. Workstream index consistency check, then sync：PR 4a 先检测 `active/Workstreams.md` 与详情 front matter 是否一致；PR 4b 引入 `acf workstream sync --dry-run --json`，只更新 `active/Workstreams.md`，不删除缺详情的旧索引行。
6. 后续独立 `audit context`：只输出 candidates，不进入默认 `check --strict`。

非目标：

1. 不新增 task object 单文件。
2. 不引入可配置 authority map。
3. 不让 generated index 覆盖 Knowledge / ADR / Archive。
4. 不把 content audit 接入默认 strict。
5. 不做自动事实裁决、自动语义去重或自动合并权威上下文。
6. PR 1b 不实现完整 `acf workstream stage` / `focus` 命令。

基线验证：

```bash
uv run acf check template
uv run acf check docs/ai --strict --json
uv run acf upgrade docs/ai --dry-run --json
uv run python -m unittest
uv run python scripts/minimal_smoke.py --acf uv run acf
uv run python scripts/upgrade_matrix.py --mode quick
```

### P1 audit context MVP

状态：MVP 已实现。设计文档为 `docs/ai/reference/Context_Audit_Design.md`。

目标：

1. 定义只读 `acf audit context docs/ai --json` 的输出契约。
2. 只输出 candidates、summary 和 next_actions。
3. 不进入默认 `acf check --strict`。
4. 不自动修改 `active/Context.md` 或其他权威上下文。
5. 不做事实真假裁决、自动语义去重或自动合并。

第一版已实现候选规则限定为：

1. active section too long。
2. stale current task / stale workstream stage。
3. ReadyToMerge conclusion not merged / Done missing merge resolution。

暂缓：

1. duplicate active facts candidate。
2. volatile fact in wrong authority location。
3. strong claim without evidence。

默认读取范围只覆盖当前注意力入口和 Workstream 当前状态：

- `active/Context.md`
- `active/Current_Task.md`
- `active/Task_Plan.md`
- `active/Workstreams.md`
- `active/workstreams/*.md`

非目标：

1. 不做自动事实裁决。
2. 不做自动语义去重。
3. 不默认修改 `Context.md`。
4. 不进入 `check --strict`。
5. 不读取 archive 或全量 worklog。
6. 不生成 patch 或自动修复。

MVP JSON 形态保持极小：

```json
{
  "candidates": [],
  "summary": {},
  "next_actions": []
}
```

## 适合继续程序化的工作

优先做可验证、低歧义、可回退的命令：

1. 根薄入口自定义字段：允许用户在生成时追加少量仓库级规则，但仍不把完整上下文写入根入口。
2. `doctor` 后续增强：把更多真实项目中重复出现的机械漂移纳入 findings；新增自动修复前必须先有只读 finding、fixture 和 dry-run 测试。
3. `audit context` 后续增强：只在 MVP 稳定后评估 duplicate / evidence / volatile location 候选，仍保持只读 candidates，不接入 strict。
4. `curate draft` 后续增强：在当前 signal -> draft 边界内补充 changed-files / duplicate 机械信号。
5. `writeback-curator` 接入：由 subagent 生成更高质量的回写分类草案，但仍只输出草案。
6. 跨项目 dogfooding 评测脚本：记录常见命令是否能在真实项目子目录稳定运行。
7. 安全项目级编辑能力：评估是否需要让 CLI 在明确授权下维护 `docs/ai/` 外的仓库级文档；当前不放宽 `acf edit` 的 context-root 限制。

这些命令应默认只生成草案或骨架。真正写入权威上下文前，仍应由用户或主代理确认。

## 适合 subagent 的工作

subagent 适合处理需要语义判断、但不应静默修改权威文件的任务：

1. `readset-planner`：根据用户任务建议应读取哪些上下文文件，避免过读或漏读。
2. `writeback-curator`：把会话结果分类到 Context、Current_Task、Decision、Worklog、Archive。
3. `decision-curator`：判断某个结论是否应升格为 ADR，并草拟决策内容。
4. `history-distiller`：从 daily worklog 提炼关键结论，标记应同步到 Context 或 Decisions_Index 的候选内容。
5. `source-curator`：整理外部资料摘要、可信度和后续动作。

这些 subagent 的输出应是草案、评审意见或建议 patch，不应默认直接应用。

## 暂不建议自动化

以下内容现在不适合进入 MVP：

- 常驻 daemon 或 chat runtime。
- 向量库、数据库或私有格式存储。
- 通用 Markdown 编辑器。
- 让 CLI 进行语义判断或事实裁决。
- 让 subagent 自动修改 `active/Context.md`、`reference/Decisions_Index.md` 或 ADR 并静默提交。
- 用复杂编排替代当前的 Markdown 事实源。

原因是这些功能会削弱“模型无关、人工可审阅、文件即事实源”的设计边界，并提高调试和迁移成本。

## Dogfooding 规则

修改本项目时，应把本仓库当成第一个使用者：

1. Python 代码优先通过项目 uv 环境运行：`uv run python ...`。
2. acf CLI 优先通过项目 uv 入口运行：`uv run acf ...`；需要调试脚本入口时再使用 `uv run python acf.py ...`。
3. 发布前快速回归可运行 `uv run python scripts/minimal_smoke.py --acf uv run acf`；该脚本只验证少量最小主路径，不替代真实项目评测矩阵。
4. 模板结构变化后运行 `uv run acf check template`。
5. CLI 行为变化后运行 `uv run acf check --strict`、`uv run python -m unittest` 和 `uv run python -m py_compile acf.py tests\test_cli.py tests\test_upgrade_matrix.py scripts\minimal_smoke.py scripts\upgrade_matrix.py`。
6. 修改 `upgrade`、模板结构或注意力治理入口时，发布前运行 `uv run python scripts/upgrade_matrix.py --mode full --acf uv run acf`。
7. 发布前完整验收运行 `uv run python scripts/release_check.py --mode full`；只验证 wheel/sdist 安装链路时运行 `uv run python scripts/release_check.py --mode package`。
8. minimal 实例不保留 ADR 和 worklog 的占位模板文件，真实条目通过 `new adr` 和 `new worklog` 生成。
9. standard 实例包含 `human/Human_Notes.md`、`human/weekly/` 和 `human/reports/`，用于人工异步笔记、周记录和汇报材料；minimal 实例不补 human 层。
10. Obsidian `[[双链]]` 只服务人工导航，ACF 不解析、不校验、不依赖双链；结构化引用仍使用普通 Markdown 路径。
11. 模板占位符统一使用 `【ACF:KEY|提示】`，表格单元格内使用 `【ACF:KEY】`；机器维护块统一使用 `<!-- ACF:<DOMAIN>:<PURPOSE>:START --> ... END -->`。
12. 新增或重置当前任务时优先使用 `new task`，维护大任务 reference 规划依据时优先使用 `plan reference`，新增资料索引时优先使用 `new source`，重要设计决策优先使用 `new adr`，当天工作记录优先使用 `new worklog`。
13. 会话结束回写建议需要暂存时，优先使用 `writeback draft`，再由人或主代理审阅后决定是否写入权威上下文。
10. 维护 `docs/ai/` 内已有 section 或 table 时，优先使用 `edit section` 或 `edit table upsert`，高风险写入先用 `--dry-run --json`。
11. 修改 `docs/Automation.md` 等 `docs/ai/` 外仓库级文档时，当前仍使用常规补丁；是否提供项目级安全编辑能力应作为独立设计处理。
12. 需要评估 CLI 实际使用效果时，可用默认开启的 usage event log；日志是运行态元数据，不是 worklog。如需关闭某项目日志，运行 `acf log disable`。
12. 修改 `template/` 前先确认该变更属于通用产品模板需求，而不是本仓库 dogfooding 特例。
13. 如果发现跨文件同步问题，优先考虑补充 `acf.py check` 规则，而不是只补文档说明。
14. 如果某项维护动作重复出现两次以上，评估是否应新增 CLI 子命令或 subagent 草案流程。
