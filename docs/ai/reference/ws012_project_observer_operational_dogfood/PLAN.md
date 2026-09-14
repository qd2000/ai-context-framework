# WS012 — Project Observer Operational Dogfood & Maintenance

## 1. Mission

WS012 承接已经完成并归档的 WS011 之后的 **production operational dogfood**，不是重新开发 Project Observer。

目标：

- 让正式 `ACF Project Observer` Scheduled Task 长期以稳定安装态 ACF 运行；
- 让独立 Maintenance Writer 持续监督 watchdog 是否真的按期刷新，而不是自己替 watchdog 刷新；
- 验证 Dashboard freshness、北京时间展示、跨 worktree authority/source consistency、Writer 并行、异常检测和版本升级后的稳定性；
- 让 Observer 从“最近状态页”演进为可持续阅读的项目地图：展示总体目标、架构关系、逻辑 milestone 链、当前位置和关键历史证据，而不是只展示最近完成内容；
- 为 continuation 增加正式的动态用户需求注入渠道，使运行中的 Scheduled Task 能安全接收 requirement / priority / constraint / plan change，并在 authority refresh 后调整计划；
- 让 WS012 消费跨项目 `continuation issue` 聚合池，完成 current-stable triage、严重问题立即修复和普通问题的计划化批处理；
- 发现具体、可复用的 Observer/ACF 缺陷时，用正式 issue → fix → tests → release → installed-state dogfood 闭环处理；
- 不复活 WS011，不把 WS012 变成常驻 agent runtime、数据库或私有 scheduler。

WS011 保持历史事实：核心 Project Observer 产品已经完成、发布并归档。

---


## Current authority — Observer Agent-first / control-plane safety

本节由当前 durable user directives 同步而来；**与后续历史章节冲突时，以本节为准**。历史版本号、旧 acceptance 计数、旧页面模板、旧 renderer contract 与旧 scheduler minute 只保留 provenance，不再作为永久执行约束。

### 2026-09-14 post-migration authority refresh

三个现有 Production Observer 已完成 Agent-first 提示原位迁移，并已有迁移后的自然独立运行证据。因此，任何“等待用户迁移 ACF / FCC / AStockT_AI Observer 提示”的旧表述只保留为历史，不再是 blocker、当前阶段或 next action。

当前阶段为 `post-migration-agent-first-production-dogfood`。下一步只读取三个 Production Observer 的自然运行与真实稳定入口、notes/history/freshness/evidence，检查 Agent-first 行为、项目语义页面自主性、证据真实性、last-good/history/freshness 与 anti-masking。发现项先分类为 prompt-specific、project-specific 或 reusable ACF/Observer product defect；只有可复现的 reusable product defect 才进入 WS012 issue → fix → test → candidate 流。在新的 Production dogfood 形成自然 release boundary 前，不因既有 release-readiness 提前选择、tag 或 publish 后继版本。

本轮首批 post-migration 质量复核结论：ACF、FCC、AStockT_AI 均已形成真实 Agent-authored 页面而非固定 renderer 套壳；FCC 对 WS079/080/086 的科学路线与纠错最具项目语义，AStockT_AI 在 legacy helper 仍为 `.88` 时也能独立维护 WS192/Gate B/盈利证据页面，证明 helper 不是页面前置。ACF 页面自身仍把已经迁移的 FCC / AStockT_AI 写成 pending，暂归类为 ACF Observer 的跨项目证据范围/内容刷新问题，不把它直接升级为通用产品 bug。可复现的通用 S3 缺口是 FCC 稳定 `index.html` 实际包含 159 个 U+FFFD replacement characters，而 ACF / AStockT_AI 当前 Agent-owned 页面均为 strict UTF-8 且 U+FFFD=0；现有 Agent-first contract 只有 last-good/update-failure 保护，没有文本完整性要求。generation 207 因此只补 strict UTF-8 回读、U+FFFD 禁止、稳定入口晋升前验证及既有 last-good 失败语义，并保持 FCC Production 页面由其自然 Observer 自行刷新，Maintenance 不手工改写。

Generation 208 已在 g207 lease 正常到期后，基于 `physical_execution=absent`、HEAD=`57e0de7` 未漂移、workspace 全量分类且 effect journal `197 completed / 31 historical failed / 0 unresolved` 的 fresh reconcile receipt 正式 recover，并继承上述 text-integrity WIP。当前 directive revision 58 已将 post-migration durable plan-change 正式 `adopt`，`PLAN.md` 与 active `WS012.md` 已同步，不再保留“等待 prompt migration”为当前事实。针对本 slice 的 `tests.test_automation_contracts + tests.test_continuation_cli + tests.test_observer_cli` 共 176 项 terminal PASS；`uv run acf check --strict` PASS（仅保留既有 WS012 267/260 行 context-budget warning），13 文件 file-scoped Workstream guard PASS，`git diff --check` PASS。该结果仍是 successor candidate evidence；在 checkpoint/immutable release/global install 与后续自然 Production proof 之前，不得宣称 installed `.89` 已获得文本完整性修复。

Generation 210 已在 generation 209 的 authenticated coordination challenge `c947a126-f69e-41ec-ab88-2278fb20ae8a` 明确 timeout 后，使用 fresh `physical_execution=absent`、HEAD=`721aac8d432959cf4b2fe2119a903290010f8e56` 未漂移、workspace 无 conflict/unclassified、effect journal `198 completed / 31 historical failed / 0 unresolved` 完成 reconcile/recover；reconcile receipt=`972fd165-75e0-44c0-8a61-d15261732ed1`，recovery=`bb0e41d7-3b5f-431d-a26c-3c48dc688193`。本次 recovery 使用 stable `.89` 正式 file-based owner credential transport，并已通过 `assert-owner` 验证 generation 210 的 fenced ownership；不把 raw credential 写入仓库或 evidence。

同一轮 post-migration dogfood 又取得三条新的**自然 Scheduled Production activation**证据：FCC 约 2026-09-15 03:45 +08、ACF 约 03:51 +08、AStockT_AI 约 03:58 +08。FCC Agent-owned 稳定 `index.html` 在 03:42 +08 仍可 strict UTF-8 解码且 U+FFFD=0，且 rev332/rev333 的自然 Observer notes/history 已连续记录 strict UTF-8 / no-U+FFFD；ACF primary 的 Agent-owned `output/observer/candidate/index.html` 在 03:50 +08 亦为 strict UTF-8 / U+FFFD=0。AStockT_AI 的自然 activation 仍健康，其 user-level helper `dashboard.html` 在 03:57 +08 为 strict UTF-8 / U+FFFD=0，而 Agent-owned `production_observer.html` 保持 01:59 +08 last-good、同样 strict UTF-8 / U+FFFD=0，本次没有新的 stable-entry promotion；在没有证据证明其 prompt/last-good/freshness contract 被违反前，这只作为 Observe evidence，不升级为新产品 issue。

因此，本轮没有观察到新的 text-integrity regression，但这**不能**关闭 issue `83063f341ef586d70017`：当前 Production 页面能够自我重建并保持干净，只证明症状当前消失；`721aac8` 的 validate-before-promote contract 仍是 candidate-only。当前 clean release integration lane 仍为 `cee21f94ba3aacb7e0ce06ce6cbdaa9cfb60d08d`，它与 `721aac8` 的 merge-base 仍是 `57e0de769a82cee9b0c7453c7009241165d72a74`，尚不存在同时包含 text-integrity 与 credential-hardening 的统一 successor HEAD；因此继续禁止提前宣称 `.90` 已选择、tag、publish 或 global install。issue `83063f...` 只有在该 contract 进入 immutable successor、global install，并由新的自然 installed-state Production evidence 证明损坏 stable entry 会被拒绝晋升后才能 resolve。

Generation 211 又取得了 g210 之后的自然 Production 证据，而没有由 Maintenance 刷新 canonical Observer runtime：FCC Production Observer 在约 04:33 +08 形成 stable rev338，Agent-owned `index.html` 于约 04:39 更新、`observer_notes.md` 于约 04:40 更新；当前 stable entry 以 UTF-8 读取时 U+FFFD=0。ACF Production Observer 随后在约 04:48 +08 形成 installed `.89` stable revision 776，primary Agent-owned `output/observer/candidate/index.html` 于约 04:49 更新、notes 于约 04:50 更新；该页面 strict UTF-8 回读成功且 U+FFFD=0。FCC 本轮新增的是项目科学/路线事实（例如 E213 bounded ExternalStream qualification 与 WS080 exact-binding 纠偏），未暴露新的通用 ACF/Observer 缺陷；ACF 仍 fail-visible 保留 `.89` 的 source-divergent / stale legacy-helper 状态。AStockT_AI 本轮没有取得比 g210 已记录的 03:58 +08 更晚、可独立定位的 Agent-owned stable-entry evidence，因此不把缺少新样本冒充 regression 或成功。结论仍是：text-integrity 当前未复发，`83063f...` 保持 open candidate-only，继续等待统一 successor + global install + installed-state natural proof。

Generation 212 继续取得 g211 之后的新自然 Production 样本，且仍未由 Maintenance 调用 `snapshot / interpret / narrative / render`。FCC installed `.89` Production Observer 在 05:33:57 +08 形成 stable rev340，self-health `errors=[]`、11 个 worktree 扫描完成；Agent-owned `index.html` / notes / history 随后于约 05:40–05:41 自然刷新，stable `index.html` 重新 strict UTF-8 回读成功且 U+FFFD=0。该轮新增内容仍属于 FCC 项目科学/路线事实（例如 WS080 Final-CRC 纠偏后 Case_01 为 7/54 exact、WS086 ready0 staging transport blocker 收窄、WS079 E213 之后无新科学 crossing），没有暴露新的 reusable ACF/Observer product defect。ACF installed `.89` Production Observer 随后在 05:44:40 +08 启动并于 05:44:48 +08 成功结束，fresh/stable、Dashboard render success、`worktrees_scanned=4`；primary Agent-owned page / notes 于约 05:45–05:46 自然更新，页面 strict UTF-8 / U+FFFD=0。ACF 页面仍 truthful fail-visible 保留 `.89` 的 `WS012:source-divergent`、Project Narrative / legacy semantic stale 等既有 candidate-only 缺口，没有新的 root-cause cluster。AStockT_AI 在当前固定 DevSpace Local 可访问面没有定位到比 g210 03:58 +08 更晚、可独立证明的 Agent-owned stable-entry 样本，因此继续保持 Observe，不用“缺少新样本”推断回归或成功。Fresh Git worktree 核验还确认 WS012=`cc2f118`、credential-hardening=`79ad2cd`、release integration=`cee21f9` 均未发生新的统一后继汇合；因此 `.90` 仍未选择/tag/publish/global-install，issue `83063f341ef586d70017` 继续保持 open，等待 text-integrity contract 真正进入 immutable successor 后的 installed-state natural proof。

Generation 213 又取得 g212 之后的自然 Production 证据，Maintenance 仍未调用 `snapshot / interpret / narrative / render`。FCC installed `.89` Production Observer 在 06:37 +08 成功形成 stable rev343、`errors=[]`、`worktrees_scanned=11`；Agent-owned `index.html` 于 06:41 +08 更新并经独立 strict UTF-8 回读确认 U+FFFD=0。该轮项目事实继续前进到 WS079 E214 terminal-positive 与 E215 首次 bounded Column Run（`CurrentIteration=0`、`CfsConverged=false`），属于 FCC 项目科学路线，不是 ACF 产品缺陷。ACF installed `.89` Production Observer 在 06:48:24 +08 启动、06:48:30 +08 成功结束，fresh/stable、Dashboard render success、`worktrees_scanned=4`；primary checkout 的 Agent-owned `output/observer/candidate/index.html` / notes 于约 06:49 +08 自然更新，页面 strict UTF-8 / U+FFFD=0。AStockT_AI 仍没有比 g210 03:58 +08 更新、且能从当前固定 DevSpace Local 独立定位的 Agent-owned stable-entry 样本，因此继续保持 Observe。

本轮还把 stable-entry 与辅助 notes/history 的完整性分开核验：ACF primary notes、FCC notes、FCC stable index 和 FCC `agent_history.jsonl` 都能 strict UTF-8 解码且 U+FFFD=0；但 FCC `observer_notes.md` 的最新 rev343 段落实际包含 6 个字面量 `` `r`n `` 分隔符，而 stable `index.html` 与 `agent_history.jsonl` 均为 0。该现象当前仅发生在 FCC Agent-authored notes 的写入格式，稳定入口未受影响，也没有证据指向 ACF 通用存储/renderer，因此先归类为 prompt/project-specific output-format defect，不新建全局 continuation issue；后续自然运行若跨项目或重复复现，再升级 reusable root-cause。当前 WS012 HEAD=`ded91b3c81ba71e76169d7dac9d6699a91246970`，credential-hardening=`79ad2cd`、release integration=`cee21f9`，最新 immutable tag 仍为 `v0.0.3.89`；仍无统一 successor HEAD 或 `.90` release 事实，issue `83063f341ef586d70017` 继续保持 open candidate-only。

### Observer Agent-first v2.0 — current unique route

2026-09-11 priority-100 durable `plan_change` directive `dir-153b33e6d0cb4bccbb67` 已正式 supersede `dir-41b8581a296544399208` 的 Task-Semantic Visualization v1.2 固定 renderer 后续路线。当前产品判断是：**Project Observer 是自主理解和展示项目的 Agent，不是 ACF 渲染前端；ACF 降为可选上下文导航、部分数据、维护工具和参考材料，不得成为唯一信息源、事实裁判、页面结构或 HTML 生成前置。**

同日 priority-100 durable `plan_change` directive `dir-e8d265cd219943b3b702` 进一步细化发布/验收顺序，但**不 supersede** Agent-first 主 directive：minimum S2 解耦安全并验证后先发布 early Beta，当前预期版本仅在 identity 空闲时为 `v0.0.3.89`；Beta/global install 后由用户手工更新现有三个 Production Observer Scheduled Task 提示并开展真实 dogfood；随后 WS012 继续 S2/S3/S4/S5，再发布下一 successor stable（当前预期仅在 identity 空闲时为 `v0.0.3.90`），并再次由用户手工更新/复核三个 Observer。Beta 不等待穷尽 legacy、完整 S3、全项目 dogfood、长期 Production acceptance 或当前原型人工视觉 PASS，也不等于最终完成。Scheduled Task prompt mutation 是人工平台 handoff，仓库 Agent 只负责在 Beta 前准备 copy-paste-ready 提示包与 checklist，禁止假定自己能修改 scheduler。

当前唯一详细执行计划仍使用既有正式路径，但内容已经切换为 Agent-first successor：

`docs/ai/reference/ws012_project_observer_operational_dogfood/OBSERVER_HTML_VISUALIZATION_PLAN.md`

原始用户交接材料为 `D:/PROJECT/Tools/ai-context-framework/.omx/user_inbox/observer-agent-first-20260911/OBSERVER_AGENT_FIRST_REDESIGN_PLAN.md`，SHA256=`84199c1a3fccf0b68b84a3ed71afd23b8f78a22772765bc9b5cddfcff0b8920d`。正式仓库 authority 以本 PLAN 与上述详细计划为准；外部 inbox 只保留来源凭证。

当前路线按 **S0–S5 + 两阶段 release dogfood loop** 连续推进：S0 authority/route 切换 → S1 首份真实 Agent-authored candidate 页面 → minimum S2 解耦/验证 → early Beta/global install → 用户手工迁移三个 Production Observer + 独立 real dogfood → 继续 S2/S3/S4/S5 → successor stable/global install → 用户再次手工更新/复核与 dogfood。阶段不是新状态机，也不是固定 work quota。

Agent 可直接使用被授权的一手文件、Git、源码、测试、日志、业务/实验结果与 ACF 等多源材料，并在自己的 Observer 输出空间维护 HTML/CSS/SVG/JS、资源、数据提取脚本和历史。Target Registry、`primary_visualization.kind/spec`、Map Review/presentation lifecycle、fixed renderer、deterministic re-render、统一 shell/卡片/单一主图等旧机制均不再是页面生成前置；已有兼容数据可读，但停止继续扩旧强制路径。`acf observer snapshot` 会写旧 Observer runtime/dashboard，Maintenance 不得把它当纯只读取数入口，也不得靠例行 refresh 掩盖 Production Observer failure。

真实性与体验要求继续保持：中文优先、北京时间、实际进展、每次有记录运行可查、历史可选/可比、指标口径真实、未知/失败 fail-visible、路线/架构/物理流程/数据流不混义、用户人工视觉验收可推翻 machine-only PASS。等待人工 review 不再阻塞可逆的 Agent-first 解耦和其他有价值工作。

权限边界保持不变：本计划不授权修改未授权业务/科学代码，不授权 submit/retry/kill、共享 Runtime 控制、凭据访问或数据外发，也不改变其他 Writer ownership、scheduler 频率/启停。Writer continuation/effect/fencing/Git 安全合同继续以每轮 stable `acf continuation prompt + execution_policy` 为唯一 generic authority。

当前阶段：**`v0.0.3.89` Agent-first Beta immutable release / publish / global install 已完成，主线进入平台提示迁移 handoff + installed-state Production dogfood**。minimum S2 checkpoint 仍为 `ae3a53bc521c0595bafdd90b86079814c4e67670`；release-prep checkpoint 为 `8363fa49aa5dd550b09eeaef7fd83d9e1bf44a30`；Beta 已 merge 到 `master` commit `cd87d23950f543df1f6f8c07f04d56395aaa85b7`，`origin/master` 与本地一致，immutable tag `v0.0.3.89`、GitHub trusted-publishing workflow 和 distributions 均已形成，canonical Windows global `acf` 已安装为 `v0.0.3.89`。generation 183 又关闭了 generation 182 两条 Windows CMD smoke `exit=2` 留下的歧义：`where.exe acf`、`acf --version`、显式 `acf workstream context WS012`、`acf continuation doctor --task-id WS012` 与 `acf observer status` 均经 canonical `acf.cmd` terminal/exit 0；失败点可复现为 merge 后 `WS012` registry=`merged`、共享 Workstream=`Merging` 导致裸 `acf status --json` 返回 `selection_invalid / registry_not_active`。这属于 long-lived Maintenance 的 post-release lifecycle reactivation 缺口现场，不是 `.89` CMD launcher 失败；generation 183 已按既有 reattach contract 将 Workstream 恢复为 `Active` 并对同一 existing checkout 执行幂等 `worktree attach --apply`，registry 回到 `active` 后 canonical CMD `acf status --json` terminal/exit 0、verified-worktree selection 恢复。generation 184 又由独立 Production Observer revision 679 暴露出一个相邻的可复用 truthfulness 缺口：`.89` 会把“Beta 已 merge 到 primary、同一 long-lived registered branch 随后从 pre-merge tip 合法继续维护”的拓扑误报为 critical `source-divergent`，即使 primary 自 common base 后没有独立修改该 Workstream authority path。该问题已登记为 issue `551b9be5530cc2ce2462`；candidate 现在仅在 active registered Workstream、primary authority 文件 working-tree clean，且 primary 对该 authority path 自 common base 无独立改动时，把这种 post-merge continuation 识别为 ordered source lineage；真正独立修改同一 authority path 仍保持 divergent/fail-visible。generation 185 在 generation 184 stale 后，经 authenticated challenge timeout + fresh physical/HEAD/workspace/effect reconciliation 正式 recover，完成 `observer_workstream_sources.py` helper extraction 并对最新形态重新验证：三场景 lineage regression 3/3 PASS、完整 `tests.test_observer_cli` 45/45 PASS；package-skeleton 首次明确暴露新模块未进入 `SOURCES.txt`，补齐 metadata 后 8/8 PASS；strict context check PASS（仅保留既有 WS012 context-budget warnings）。最新只读 candidate capture 再次针对当前真实 ACF/WS012 得到 `source_consistency=consistent / active_registered_worktree_post_merge_continuation`。该结果仍只是 candidate 修复证据；Maintenance 不得刷新 canonical Production snapshot 来伪造 `.89` 告警已消失，issue 也必须等 successor immutable stable/global install 后的独立 Production Observer 证明再 resolve。

独立 Production Observer 现已有真正的 `.89` post-install activation：revision 677 / run `7952ac80-6aa4-49a8-9d37-352cbe2c1ee7` 成功，`self_health.acf_version=v0.0.3.89`、Dashboard render success、snapshot consistency stable、lock idle、data fresh。该证据只证明新 stable binary 已被 Production Observer 实际消费；**现有 ACF / FCC / AStockT_AI 三个 Production Observer Scheduled Task 的 Agent-first 提示仍须由用户按详细计划 §11.1 手工原位迁移**，因此当前不得把这次 `.89` activation 冒充“Agent-first prompt production acceptance”。copy-paste-ready 共用主提示与三任务 migration checklist 已在详细计划落盘；下一主线是平台迁移后观察三个任务自然独立运行并收集 Agent-first Production evidence，同时 WS012 继续 S2/S3/S4/S5 与 successor stable。人工视觉 review pending 不阻塞 Beta，但用户未认可前仍不得宣称最终视觉 PASS；不得先设计新的通用 renderer/API/schema/plugin platform。

两条 priority-70 context/template 简化 requirement `dir-0b707f4b16b24550b627` 与 `dir-d54a9978f1964a33926e` 已分别在 directive revision 53/54 以 evidence-backed lifecycle 正式 `resolve`。其确认项已经由 active-history compaction、Workstream-index scope compaction、fresh non-ACF/customized regeneration、default worktree guidance simplification 与 Global-first Context routing 的 reusable-source 修复及验证覆盖；候选的 submit/review/status/re-review 现象也已按 Git/authority 证据判定为 scheduler/supervisor 选择而非仍待修的 ACF template defect。该 resolve 只关闭 bounded priority-70 follow-on，不关闭 WS012 长期 mission，也不改变 Agent-first 主线；后续不得把“继续清 priority-70 backlog”作为默认 next action，只有出现新的可复现 recurring symptom 才重新登记并按证据处理。

Generation 194 已把独立、可复现的 S3 stable-entry/update-failure 缺口正式 checkpoint 到 `0fccdabacd844816f6fe28165c496762ccc5ee58`：`agent_first_output.update_failure_policy` 机器化要求“failed update 不替换稳定入口 / last-good 仍可读 / partial-source failure fail-visible / 失败后 freshness 仍真实”，focused `automation_contracts + continuation prompt + observer status` regression 10/10 PASS，随后 strict check、WS012 file-scoped guard 与 `git diff --check` 也通过。generation 195 在该 HEAD 上运行完整 successor release-readiness gate，durable effect `g195-successor-release-readiness-full-gate` 已 terminal `process_exit_0`；当前 effect journal 为 182 completed / 30 historical failed / 0 unresolved。generation 196 又在 generation 195 stale 后，经 authenticated challenge timeout 与 fresh `physical execution absent + HEAD unchanged + classified workspace + unresolved effects=0` 证据完成正式 reconcile/recover；没有重放已终态 gate。

当前 release-readiness 诊断进一步确认：`v0.0.3.89..HEAD` 有 11 个 post-Beta commits，但最高本地 immutable tag 仍是 `v0.0.3.89`，`pyproject.toml` 与 `ai_context_framework/version.py` 也仍是 `0.0.3.89`。因此 generation 195 的 full-gate PASS 只证明当前 successor candidate 的产品/仓库 Gate 就绪，不等于已经选择 successor identity、tag、publish 或 global install。详细计划 §12/§16 仍要求先完成 §11.1 的三任务用户手工原位 prompt migration，并取得独立 Production dogfood 反馈，再据真实 S2/S3/S4/S5 缺口决定自然 successor release boundary；不得仅因 Gate PASS 就机械发布 `.90`。独立 Production Observer revision 708 仍在 installed `v0.0.3.89` 上 fresh/stable，并继续 fail-visible 报告 `WS012:source-divergent`；Maintenance 没有刷新 canonical runtime 掩盖该告警。

Generation 198 在等待 §11.1 平台迁移期间按“主动寻找安全、非重复替代工作”的长期自治合同复核全局 continuation issue：先用 immutable installed `v0.0.3.89` 的隔离实测关闭了两个已被 `42fc9eb` 解决但仍遗留 open 的 baseline-external recovery issue，并依据 `8081983` 已进入 `.88/.89`、`.88` installed-state physical-liveness regression 2/2 PASS 的既有权威关闭对应 stale physical-execution issue。随后确认仍 open 的 `083e6d6ec1e44e812476` 是真实高优先级 recovery 缺口：eligible reconcile receipt 会因后续 scheduler wake 仅追加 contender attempt、改变整个 coordination digest 而被误判 stale。candidate 修复把 recovery freshness 缩窄到“当前 owner generation 的非终态 challenge 安全字段”，明确忽略 append-only attempt / contender-id / coordination `updated_at` bookkeeping；owner ACK/release/challenge outcome 仍会改变 recovery digest 并继续使旧 receipt stale。回归同时保留“owner ACK 后 recovery 必须拒绝”的既有安全测试，并新增“reconcile 后仅新增 contender attempt 仍可消费原 eligible receipt”的复现链。该修复仍是 successor candidate，issue 在 immutable stable/global install 前不得提前 resolve。

Generation 199 在同一 external-handoff 阶段继续按长期自治合同寻找新的 S2/S3/S5 evidence，并由独立 installed `.89` Production Observer revision 721 发现新的 S3 历史连续性缺口：`ws012-writer` 的 append-only semantic-review journal 中仅有一条旧 review 因 `problem.node_ref=maintenance` 不属于该 review 自身 route nodes 而不再满足当前严格 validator，但 stable `.89` 会因此把整个 `review_history` 清空，导致其余大量有效归档路线也全部不可见。该缺口已登记 issue `c432f0b2bdbc872f5edc`。candidate 修复保持新写入/显式 strict reader 的严格验证不变，只把 human-facing Dashboard projection 改成逐 event 局部降级：有效 archive 继续返回，坏 event 被跳过并在 `review_history_error` fail-visible 记录首个诊断/额外数量；Dashboard 有有效 archive 时同时显示“部分历史路线不可读”警告和其余可读版本，不用今天的事实重绘过去。定向 regression 2/2 PASS，`tests.test_observer_presentation + tests.test_observer_cli` 合计 90/90 PASS；更重要的是，candidate `uv run acf observer presentation-status` 对真实 ACF 项目的只读投影已经恢复大批有效历史，同时仍精确报告 line 90 的 `maintenance` dangling-node diagnostic。该验证没有执行 Production snapshot/interpret/narrative/render，不计入 Production acceptance，也不改变 §11.1 三任务用户侧 prompt migration 仍是当前外部主边界；本修复在 semantic checkpoint、successor immutable install 与 installed-state proof 之前保持 candidate-only。

Generation 204 又由独立 installed `.89` Production Observer revision 743 暴露一个相邻的 S3 truthful-freshness 缺口：Workstream semantic 已更新到 generation 203 的 graceful handoff，但 Project Narrative v86 仍明确描述 generation 201 fresh owner，却被 `.89` 判为 `status=current`。根因是 Project Narrative 的 deterministic source projection 只覆盖 continuation 的 stage/status/objective/next_action/unresolved-effect count，没有覆盖 narrative 可引用的最新 round、lease identity/liveness、state update 与 terminal effect totals。该问题已登记 issue `5b49fa7e4de69ba5ae29`。generation 204 candidate 将这些**语义相关** continuation facts 纳入 Project Narrative source fingerprint，同时刻意排除 heartbeat/renew 时间戳等纯 liveness-churn 字段，避免每次正常 heartbeat 都把 narrative 置 stale；新的 regression 证明 generation、terminal effect totals、lease liveness 改变会使 fingerprint 改变，而仅 heartbeat timestamp 变化不会。最终验证为 package-skeleton 8/8 PASS、Project Narrative focused/E2E 2/2 PASS、`tests.test_observer_cli + tests.test_observer_presentation` 91/91 PASS；candidate `observer narrative` 对真实 ACF 项目仅只读计算后已把旧 v86 正确判为 `stale`，没有写 canonical Production Observer runtime。该修复同样保持 candidate-only；§11.1 三个现有 Production Observer 的用户侧 Agent-first 原位迁移仍是外部主边界，不能因本次修复或测试通过提前选择/tag/publish successor。

`.88` release / global install / continuation closeout 仍是历史完成事实，禁止 replay。任何 candidate 页面、测试、commit、release、单次 Production activation 或 directive adopt 都不等于 WS012 长期 mission 完成。

### Historical — Task-Semantic Visualization v1.2（superseded implementation route）

2026-09-08 用户通过 durable `plan_change` directive `dir-4dd0233543ac4a3b9202` 明确确认了 Q1–Q6，并用审阅修订后的 **Observer HTML Visualization v1.1** supersede 旧 Human-First visualization directive `dir-5272efd83a0e434298e1`。2026-09-10 人工复核明确 H1 FAIL 后，priority-100 durable directive `dir-41b8581a296544399208` 又 supersede `dir-de45c52233d04c97af5d` 的后续纠偏路线，并将 H1 目标升级为 **Task-Semantic Visualization v1.2**。人工 FAIL、Q1–Q6 及 v1.1 中 expected-target、run/history、archive/concurrency、anti-masking 等有效要求继续保留；与 generic roadmap/narrative 作为 H1 终点的历史表述冲突时，以 v1.2 successor 为准。本节仅保存 sequencing/status pointer；本阶段的**唯一详细执行计划**仍是：

`docs/ai/reference/ws012_project_observer_operational_dogfood/OBSERVER_HTML_VISUALIZATION_PLAN.md`

该文件最初从 v1.1 用户 inbox 交接到 WS012 worktree；当前 v1.2 successor 的 source handoff=`D:/PROJECT/Tools/ai-context-framework/.omx/user_inbox/observer-task-semantic-visualization-v1.2-20260910/TASK_SEMANTIC_VISUALIZATION_PLAN.md`，SHA256=`611872fd8c7f03ffc8aea20fbcbab8a4f1bb379af3ba81f386d1ee97e1a5c76c`，已在详细计划 `0.0` 节正式落盘。后续若本 PLAN、旧 directive、历史 P1–P4 描述与该详细计划冲突，以该详细计划及更新后的正式 successor authority 为准；历史内容只保留 provenance。

v1.2 不再把所有 target 的 generic roadmap/narrative/card 页面视为 H1 终点。Production Observer 必须从 fresh authority 先判断 target 的 `primary_progress_question`，由 Agent 选择一个 dominant primary visualization；ACF 只验证与确定性渲染，禁止按 project/target 名称硬编码。首批通用 archetype 为 `metric_trend`、`status_matrix`、`process_flow` 和 compact `roadmap`，generic narrative 仅作为证据不足时的 fallback。真实 dogfood 预期但不硬编码：WS086→objective trend、WS079→component matrix、WS080→真实 FCC/建模 process flow、WS012→compact roadmap。主图中文优先；run/provenance/raw IDs 降级但仍可追溯；指标必须 finite/comparable/evidence-bound；历史 kind 改变不得伪装成连续同图。H1 必须重新生成 fresh real ACF + FCC candidate dashboards 并取得新的人工 PASS 后才能关闭。

`.88` release / global install / continuation closeout 已完成，禁止 replay 或重新打开 continuation P0。当前阶段按 v1.1 的 H0–H5 执行：**H0 authority handoff 已完成，当前处于 H1 map-first minimum useful visual Gate**。H1 candidate 已具备真实 inline-SVG relationship diagrams、显式 current/next node binding、problem-to-route 校验、中文优先 first-screen 摘要与最近真实 Agent run 投影；2026-09-09 generation 119 对 generation 118 的 focused-suite failure 做了定向诊断，确认是两处中文化后的旧英文测试断言漂移，修正后 Observer CLI / presentation / target-projection / targets 四个 focused 模块合计 111 tests PASS，file-scoped WS012 guard 与 `git diff --check` 通过。generation 121 又取得 isolated candidate render 的 terminal/no-orphan browser evidence（1366×768 与 1920×1080 页面 artifact），但当前 DevSpace surface 无法直接完成人工视觉检查，因此 H1 visual acceptance 仍 fail-visible 保持 open。generation 122 在不冒充 H1 closure 的前提下推进相容的 expected-target hardening：同一 `target_id` 若实际注册绑定与显式 expected-target contract 在 automation/workstream/continuation/route 等字段上不一致，registry health 现在明确返回 `conflict`，恢复入口不会覆盖现有绑定并要求 authority 统一；21 个 target registry tests、44 个 Observer CLI tests、file-scoped guard 与 `git diff --check` 通过。generation 127–129 在 H1 人工视觉验收仍受当前 surface 限制时，按 active-alternative contract 只推进**不改变 formal route 的 H2-adjacent 可逆增量**：逐次 run history 不再因默认 12 条展示窗口丢失、更早 run 仍可展开；旧 semantic review 作为独立归档路线版本保存且历史 journal 损坏只局部降级历史区；generation 128 加入单历史版本选择器；generation 129 在此基础上加入双历史版本 A/B 选择与并排查看，当前路线仍保持在上方，比较只改变浏览方式、不改写当前路线，也不自动推断节点等价关系，禁用脚本时仍完整展示全部归档版本。generation 129 新增 focused compare regression 1/1 PASS，完整 `tests.test_observer_presentation` 39/39 PASS，file-scoped WS012 guard 与 `git diff --check` PASS。上述增量均不构成 H1 PASS，也不把 formal stage 提前推进到 H2。H1 不以完整历史、指标体系或跨项目迁移为前置条件；expected-target recovery 与上述 H2-adjacent work 均不能反向阻塞 H1。

generation 129 随后还完成了基于稳定 node id 与显式 relationship 的历史版本差异摘要：新增/缺失节点、状态变化、关系变化只按已持久化身份比较，不按标题猜测等价；`g129-h2-history-diff-summary-focused` 与 `g129-h2-observer-presentation-suite-diff-summary` 均已由 durable physical-execution evidence 证明 exit=0。generation 131 在 authenticated challenge 超时后，以 fresh doctor 证明旧 g130 physical execution absent、HEAD 未变化、workspace 全分类且 unresolved effects=0，完成正式 reconcile/recover；随后对 H1 first-screen 与逐次 run history 增加 run 来源 provenance：区分 `Writer continuation round` 与显式自动任务 `run marker`，并在可用时显示 generation/runner，降低把不同来源运行混为同一 Agent run 的风险。逐次历史 focused 首次验证暴露一个 helper rename 后的旧私有符号引用并 terminal exit=1；修正引用后使用新 deterministic key 重验 1/1 PASS，完整 `tests.test_observer_presentation` 39/39 PASS。generation 132 又补齐 automation contract 已要求但展示链仍缺失的 `route_link`：continuation round 使用已注册 target `route_ref` 作为稳定路线关联，显式 run marker 优先保留本次 marker 自身 route_ref、缺失时再退回 target route_ref；first-screen 最近 run 与逐次 run history 均显式展示该路线关联，不从标题或当前状态猜测具体节点。修正两次 focused test 输入问题后，新的 focused 4/4 PASS，Observer CLI / presentation / target-projection / targets 四模块合计 119 tests PASS。generation 133 继续补齐 run-result 的证据覆盖表达：first-screen 最近 run 明确显示关联 evidence 数量或“证据覆盖不足”，逐次 run history 在有 evidence_ref 时提供可展开的完整引用，无可归属 evidence 时 fail-visible 显示缺口而不把命令成功冒充结果证据；修正一次仅由 unittest class 路径写错造成的 terminal 验证失败后，定向回归 1/1 PASS，完整 `tests.test_observer_presentation` 39/39 PASS，随后 Observer CLI / presentation / target-projection / targets 四模块合计 119 tests PASS，strict check、file-scoped WS012 guard 与 `git diff --check` 均通过。generation 134 在 generation 133 stale 且 authenticated challenge deadline 到期后，以 fresh doctor 重新确认 physical execution absent、HEAD 未变化、workspace 全分类、unresolved effects=0，完成正式 reconcile/recover；随后在独立临时 `ACF_HOME` 中、仅通过 `ACF_OBSERVER_CONTINUATION_READ_HOME` 只读 canonical continuation，连续两次完成 candidate snapshot/render，均 terminal exit=0。第二次 snapshot 还补齐同一 `ws012-writer` 的 expected-target contract，registry health=`healthy`、expected=1/registered=1、missing/conflict=0，semantic review 保持 current，Dashboard digest=`d70c34ccc325278d03a85610392a1ae65f0635701a3f28017a21e745b68eb742`。这组 repeated isolated terminal evidence 只增强 H1 的 reproducible/no-orphan dogfood 证据，不构成人工视觉 PASS，也不改变 H1 formal status。generation 135 随后的独立 Production activation（revision 509）暴露一个新的可复用 Observer truthfulness 缺陷：continuation 已通过 `released_to_running_handoff` 明确进入合法 ownerless running handoff、lease 按合同应当 absent，但 stable `.88` 仍把它归类为 `continuation_running_without_fresh_lease` 并产生 owner-liveness warning。该缺陷已登记为 issue `4112e9212faa24ef52ce`；candidate 现在只有在 `status=running + phase=released + milestone=released_to_running_handoff + lease absent` 四项同时成立时把它识别为健康 ownerless handoff，普通 running-without-lease、stale 或 expired lease 仍保持 fail-visible。新增定向回归 1/1 PASS，Observer CLI / presentation / target-projection / targets 四模块在最终 refactor 后再次合计 119 tests PASS；`observer.py` 保持 2000 行。额外 package-skeleton 诊断先暴露了两个早于本 slice 的 H1 WIP release-readiness 缺口：新 `observer_dashboard.py` 未进入 egg-info `SOURCES.txt`、`observer_storage.py=2303` 行超过 2000-line gate。generation 135 已按正式 `scope-add` 扩展 `observer_runtime_storage.py`，把 user-level path/history/runtime-storage primitives 从 `observer_storage.py` 拆到 540 行专用模块，同时把 `observer_storage.py` 收回 1989 行，并补齐 `observer_dashboard.py` / `observer_runtime_storage.py` 的 source metadata；package-skeleton 现为 8/8 PASS。该 refactor 保持历史 public import surface 由 `observer_storage` re-export，119 个 Observer focused tests 继续 PASS。H1 仍 open；这些 candidate 修复不构成人工视觉 PASS，issue `4112e9212faa24ef52ce` 也必须等待未来 immutable stable/global install 后的独立 Production Observer 证明再 resolve。

generation 137 在 generation 136 stale 且 authenticated challenge `61534c75-370a-4dd0-9789-4bad1ceef483` 的 persisted deadline 正式超时后，继续按 stable `.88` generated protocol 取得 fresh physical-execution / HEAD / workspace / effect evidence：旧 owner physical execution absent、HEAD 仍为 `d6cd1c0afea22bf58b9906149fdfbfaa36fcf945`、workspace 无 conflict/unclassified/unexpected-nonoverlap、effects unresolved=0；随后以 reconcile receipt `afe62e72-272d-4f56-a26f-fa3f8334acb6` 正式 recover 为 generation 137。接管后重新执行 Observer CLI / presentation / target-projection / targets 四模块，**119/119 PASS**。继续对 H1 中文优先 first-screen 做低副作用静态审查时发现：已知 `future` route/milestone status 仍可能以英文直接出现在主图状态文字；candidate 已把该状态统一呈现为“后续阶段”，并补齐 relation-diagram 对 `fresh/stale/not_reviewed/unconfigured` 的中文状态映射，避免主展示重新泄漏已知英文 machine state。对应 `tests.test_observer_presentation + tests.test_package_skeleton` 合计 **47/47 PASS**，且 package-skeleton 继续覆盖当前拆分模块。该改动只收紧 H1 human-first 文案，不改变任何 authority semantics、route identity 或 formal H1 状态；真实视觉 rubric 仍保持 open。

generation 138 在 generation 137 stale 后，通过 authenticated challenge `22e577be-6b8f-478f-a1b2-8fa7cde577e4` 的 tool-backed wait 跨过 persisted deadline，并以 fresh doctor 再次确认旧 owner physical execution absent、HEAD 未变化、workspace 全分类且 effects unresolved=0；receipt `17cb71a8-3c1d-43b9-b234-2b597549a972` 随后正式 recover ownership。H1 相邻静态审查又发现人类可见层仍会泄漏 machine value：SVG 节点 tooltip 仍显示 raw status，问题卡片仍直接显示 `agent_self / blocks_current_step / route_change / working` 等枚举，当前真实路线/架构常用的 `next / observed_by` 也会直接画在关系边上。candidate 现在对 tooltip 使用与节点正文一致的中文状态，把问题的处理者、阻塞影响、计划影响与 lifecycle 状态映射为中文并显式展示“阻塞影响”，同时仅对已知 machine relation enum 使用中文箭头标签（如“下一步”“由其观察”）；未知值仍 fail-visible 保留原值，不猜测自由文本语义。最新 relation regression 1/1、`tests.test_observer_presentation + tests.test_package_skeleton` **47/47 PASS**；此前同一 generation 的 Observer CLI / presentation / target-projection / targets 四模块 **119/119 PASS**，`observer_storage.py` 仍保持 2000-line gate 内（1996 行）。该 slice 只增强 Human-First 可读性，**H1 仍需真实视觉 rubric 才能关闭**。

2026-09-10 用户完成 ACF + FCC Dashboard 人工截图复核并明确给出 **H1 MANUAL VISUAL REVIEW = FAIL**（directive `dir-de45c52233d04c97af5d`）。该人工结论高于此前 machine-only / render-only evidence；H1 在新的人工 PASS 前保持 open。最新优先级不再是继续扩底层字段，而是重构视觉信息架构：主区必须真正 map-first，将完整路线压缩成一眼可理解的阶段/分支/当前路径图；首屏突出已完成、当前、下一步、剩余阶段与最近实质进展；路线图与架构图分开切换；主区中文优先，FCC 英文技术长段落降到折叠详情；当前位置/why-now/下一步/执行范围等语义去重；每次 Agent run 仍完整可查但默认降级为紧凑时间线/表格；stale/not-reviewed target 只显示紧凑 fail-visible 提示并在有历史有效图时提供归档入口；当前节点/问题/下一步/最近进展的视觉层级高于 provenance/ID/schema/raw evidence；计划节点、历史、运行与技术详情通过分层/折叠/切换控制纵向长度，目标是在常见桌面首屏或一屏半内理解目标、路线、当前位置、最近进展、问题与下一步。修复后必须生成新的 ACF + FCC 实际 Dashboard 供再次人工视觉复核；不得因本反馈另起 Workstream、修改 scheduler 或重开 continuation P0。上述 10 项详细验收已同步到唯一详细 authority `OBSERVER_HTML_VISUALIZATION_PLAN.md#50-2026-09-10-人工视觉复核-failh1-信息架构纠偏`。

H1 之后依次推进 H2（分层进度、逐次 run history、历史归档/查看/比较、灵活指标）、H3（expected-target 完整性/恢复/兼容）、H4（ACF + FCC 真实项目验收；AStockT_AI 在合法可访问时纳入）、H5（新的 immutable release/global install 与独立 Production acceptance）。任何 machine test、commit、checkpoint、单次 render 或 release 都不单独关闭视觉 Gate；若当前执行环境无法完成真实视觉检查，必须 fail-visible 保持 human acceptance open，并提供真实生成 artifact 供人工打开检查。

当前 next action：保持 H1 open，执行 `dir-41b8581a296544399208` 的 Task-Semantic Visualization v1.2：先把现有 generic renderer 固定为 fallback 并建立最小 `primary_visualization` contract，再按 fresh authority/evidence 实现和 dogfood `metric_trend / status_matrix / process_flow / compact roadmap`，确保每个 target 只有一个回答核心进展问题的 dominant primary visualization，随后生成新的真实 ACF + FCC candidate Dashboards 供用户再次人工复核。当前大规模 classified WIP 在最早安全语义边界先形成 validated Git checkpoint；新的人工 PASS 前不得关闭 H1，也不得推进 formal H2。每个有意义的语义/展示变化后 refresh authority，不为固定 work quota 重复无增量采样。

### Post-H1 bounded context-friction maintenance backlog

durable requirement `dir-0b707f4b16b24550b627`（priority 70）作为 **H1 之后的 bounded follow-on maintenance** 纳入 WS012；它不得打断 priority-90 Observer HTML v1.1、不得重新打开已关闭的 continuation P0、不得新增 H1 前置 Gate、不得修改 scheduler。允许与 H1 完全相容的小修在自然 checkpoint 一并处理，但更广泛的简化必须等 Human-First 视觉交付取得当前阶段所需 evidence 后再进入。

后续维护范围保持窄且 evidence-driven：① 消除 `active/Context.md` 与 Global-first/Always_Active 的 routing 文案漂移，使行为 authority 唯一且 template/upgrade 不复活旧规则；② 压缩 `active/Workstreams.md` 默认摘要中的长 write-scope 展开，同时保留完整 machine scope、selected detail、sync/context/guard 与 parser 兼容；③ 把 `template/AGENTS.md` 入口中的低频 integration-worktree merge/promotion/retry/artifact 细节降为 task-triggered detail，保留必要安全边界；④ 缓解 WS012 active-history/context-budget 压力，把已关闭阶段和长 Activity Log 细节迁入现有 history/archive，并保留当前 mission/stage/evidence/next-action 与有效恢复证据的稳定指针；⑤ 对 Codex 线程中 submit/review/status/re-review、Runtime scope detour、简化时误删有效约束等现象分别区分 scheduler/supervisor 选择与 ACF 产品缺陷，只删除已有证据证明的重复 bookkeeping，不把机械 check PASS 当作语义完整性证明。

该 follow-on 的验收原则：不丢上下文或有效规则，不削弱 live-writer/fencing/effect/provenance/write-scope/Git/Observer safety，不引入模型特定时间预算、daemon/database/额外 scheduler/telemetry platform；用少量代表性 standard/minimal/custom/older-context 路径比较无关读取和重复维护变化。文档改动运行适用的 strict/template/link/scope 检查；若触及 generator/CLI，再补 focused deterministic、幂等 regeneration、full-scope discovery 和 semantic-preservation regressions。只有已确认项完成验证、候选项被修复或有 evidence-backed 结论证明不是 ACF 缺陷后，才 resolve 该 directive；仅写入 backlog/adopt 不等于完成。

clarification `dir-d54a9978f1964a33926e` 进一步冻结 **product/template-level** 边界：上述 recurring symptoms 必须追到可复用来源（`template/` 入口/规则、standard/minimal initialization、shared context/Workstream summary generation，以及受影响的 simplify/upgrade path）并只修责任层；ACF 自身 docs/WS012 只能作为 reproduction/acceptance example，instance-only cleanup 不能关闭该 requirement。验收必须额外覆盖一个使用受影响模板/生成器的 isolated fresh **non-ACF** project，以及受影响的 existing/customized context upgrade 或 re-generation path；证明 stale routing text、verbose default scope expansion 和 redundant default instructions 不会被重新生成，完整 selected scope 仍可发现，unrelated user text/有效 constraints 不丢失，重复 generation 幂等，minimal profile 仍保持 genuinely minimal。不得 hardcode WS012/FCC/project path 或模型假设，不做静默批量语义迁移；语义不确定时保留人工决策。每个原始 symptom 最终都应有一条简短的 symptom → reusable source/fix → validation evidence 映射。

Generation 188–190 已完成其中 **shared Workstream summary 的 verbose default scope expansion** 产品级修复与要求的跨项目 regeneration acceptance。索引生成器只在 `write_scope <= 3` 时内联完整值，超过 3 项统一压缩为 `详情(N 项)`；解析端遇到该摘要后从 detail front matter 恢复完整 typed scope，因此 `acf workstream context`、guard/parser、旧 inline 格式和重复 sync 幂等保持兼容。generation 188 的 focused regression、完整 CLI suite、template check、strict check、WS012 file-scoped guard 与 diff check 均 terminal/exit 0，并形成产品 checkpoint `35648e0`；generation 189 继续在 fresh non-ACF-shaped `sample-project/docs/ai` context 上验证同一 generator，并加入 project-specific detail note，证明 sync/regeneration 不会覆盖无关用户自定义内容，定向 effect `g189-workstream-index-nonacf-customized-regeneration` 与完整 CLI suite `g189-workstream-index-cli-suite-post-nonacf` 均 terminal/exit 0。generation 190 随后通过 persisted challenge timeout + fresh physical/HEAD/workspace/effect reconciliation 正式 recover stale generation 189，复用上述已终态证据而不机械重跑，补做当前 test-only diff 的 file-scoped guard / `git diff --check` 后，将该跨项目回归 checkpoint 为 `82fbc5b`。因此“global Workstreams index 被长 scope dump 膨胀”及其 fresh non-ACF/customized regeneration 验收已闭环；该证据随后成为 `dir-0b707f4b16b24550b627` / `dir-d54a9978f1964a33926e` 在 revision 53/54 正式 resolve 的组成部分，不再保留一个虚构的 residual priority-70 cleanup lane。

Generation 190–192 又完成了 **默认入口重复 worktree 指令 + generated Context stale routing** 的 reusable source-level 收敛：`template/AGENTS.md` 不再默认复制完整 integration-worktree merge 状态机，只保留在任务实际涉及 merge / close / recovery / artifact handoff 时按需读取 `acf worktree --help` 与 `System_Manual` 的窄入口，同时继续显式保留 no-stash/reset/clean/rebase/force 与不静默解冲突的安全边界；`template/rules/Always_Active.md` 删除与 AGENTS 重复的 worktree 默认规则；`template/active/Context.md` 不再默认把 `active/Current_Task.md` 声明成唯一当前执行入口，而是对齐 Global-first：未选 Workstream 保持全局上下文，显式选择后先 `acf workstream context WSxxx` 再按 scope 渐进读取，`Current_Task` 只在它本身为当前全局任务时作为任务事实源；`upgrade.py` 只迁移已知 legacy exact rule，并保留 unrelated project-specific AGENTS / Always-Active / Context 文本。generation 190 的完整 CLI suite `g190-context-default-simplification-cli-suite` terminal/exit 0；generation 191 的 `g191-context-global-first-focused`、template check、upgrade audit 与完整 CLI suite 均 terminal/exit 0。generation 192 在 generation 191 stale 且 authenticated challenge deadline 到期后，用 fresh physical-execution absent、HEAD=`5ae8923` 未变化、workspace/effect/provenance 与 unresolved-effects=0 证据正式 reconcile/recover，依据已落盘的 WS012 scope-add 将继承的 `template/active/Context.md` WIP reclassify 为 task-owned；未重放已终态代码测试，只对恢复后的最新文档形态重新取得 warning-free status、strict check、file-scoped guard 与 diff check。上述两项 symptom 均已闭环，并与前述 history/scope/regeneration evidence 一起支撑两条 priority-70 directives 在 revision 53/54 正式 resolve；不得再为“清 backlog”制造无证据 busywork。project instance authority path 仍不得靠普通 Workstream `assigned:` scope 直接覆盖。Generation 193 在 generation 192 stale、physical execution absent、HEAD=`7ca603a`、unresolved effects=0 且 workspace 全分类后，通过 persisted challenge timeout + reconcile/recover 接管，并以最新 directive journal 确认该 bounded lane 已关闭；当前 Writer 路线回到 post-Beta Agent-first 主线与 successor 准备。

### Long-running autonomy / active alternative search

directive revision 50 的 `dir-dd3b3c0fc01b452d9b3b` 将 WS012 的长期执行默认值从“等待 fresh opportunity”纠正为**主动寻找安全增量工作**：只要 WS012 长期 mission 仍 open，当前合法 Writer 就应围绕总体 mission 与当前 PLAN 大阶段持续选择 safe、useful、non-repetitive 的下一步，而不是把某一条 lane 暂时 blocked 解释为整个 activation 应 no-op/waiting。

- anti-busywork 只禁止在**输入、环境、证据与策略均未变化**时机械重复同一已证明无增量的失败动作；新的 root-cause 诊断、相邻缺口实现、补验证/证据、可复用 contract 加固、可访问 target dogfood、release preparation、或能够降低不确定性的低副作用实验都属于合法替代工作；
- 某一路径暂时 blocked 时，优先切换到不冲突的替代 lane；在没有新的安全增量工作之前，不要求通过 claim/控制面 lifecycle 人为制造进度，但也不得把 persisted `waiting for fresh opportunity` 当作默认退出理由；
- 以 WS012 总体 mission 和 PLAN 大阶段为主要 work unit；单个 bug、实验、测试、checkpoint、release Gate 或局部验证默认留在当前 Maintenance scope 连续推进，不为调度便利拆成新的 Workstream/独立任务；
- test、commit、checkpoint、Gate、release preparation 都只是 persistence/validation 证据，不是 stop signal；自然 checkpoint 后立即 refresh authority，并在仍有安全增量工作时继续；
- 在没有四项 task-level hard stop（总体目标完成、用户明确暂停、需要不可替代人工授权/凭据/决策、DevSpace 经合理重试仍不可用）时，如果要结束当前 activation，必须先显式审计当前可执行替代项，并证明 blocker 诊断、相邻实现、验证、contract hardening、可访问 target dogfood、release preparation 与低副作用诊断均暂时没有增量价值。

该原则属于 P1.5 Prompt Execution Contract 的 durable Writer contract：static wrapper 继续只保存高显著 bootstrap/project-specific extension，不固化 volatile owner/stage；每轮 stable `acf continuation prompt + execution_policy` 必须机器可读地表达 active alternative search、blocked-lane switching、anti-busywork 的窄拒绝范围、checkpoint 后继续与 no-useful-work alternative audit。所有既有 owner/fencing/write-scope/effect/Git/Production Observer anti-masking 边界保持不变。

### Scheduled Writer overconstraint reduction / graceful handoff

最新 durable authority `dir-d98bf9b8628244cabe68` + `dir-fb0de0b1b4fc4536b97a` 冻结 continuation physical-execution/self-stale P0 的实现范围到 checkpoint `8081983f23cee184f32c8028caa6185d521d5b30`，并将当前实现主线切换为 **Scheduled Writer overconstraint reduction**。P0 不再为了流程顺序单独发布一个 patch；其 installed-state terminal proof 与本阶段改动合并进入下一次正常 stable release/global install/dogfood。P0 issue 只有在 installed-state physical-execution proof 完成后才能 terminal resolve，但这不再阻塞本阶段实现。

本阶段的目标不是“放松安全”，而是让控制面成本与真实风险成比例，让 long-lived Scheduled Writer 在不存在 verified-live 冲突 Writer、未知/未决 non-idempotent effect、真实 fencing conflict 或无法解释的 workspace/provenance drift 时，尽快回到安全有价值的项目工作：

- elapsed wall-clock、当前平台/模型的可见运行时长、challenge delay、stale threshold、duty cycle 等只允许作为诊断 telemetry；禁止把任何当前观察值固化成 semantic execution budget / work quota / stop signal。lease/heartbeat/stale/renew 仍是可配置的 liveness mechanics；
- active lease、历史异常 generation、task-owned dirty、scheduler wake、checkpoint/test/commit/Gate 完成或单个 lane blocked 都不能单独成为 session-end 理由；真正结束 activation 仍需满足 hard stop，或在安全控制点证明当前没有 safe/useful incremental alternative；
- verified-live previous physical execution 必须安全 yield，禁止 duplicate submit/run；unknown effect、真实 provenance ambiguity 继续 fail-closed；除此之外优先选择最便宜、确定、可审计的安全 continuation 路径，避免在证据未变化时重复 doctor/status/challenge/recovery bookkeeping；
- current owner 在 genuine safe session end 必须先持久化准确 stage/next_action/evidence，再执行 **graceful running handoff**：释放当前 owner/round，但保持 long-lived continuation `status=running`，为下一 activation 留下 ownerless、可直接 claim 的 handoff-safe 状态。不得为了等待下一 scheduler wake 故意留下将来会 stale 的 running owner；graceful handoff 也不是 checkpoint/test/commit 后提前退出的借口；
- continuation prompt/JSON 必须提供机器可读 execution observability，至少区分 `bootstrap_control_plane / project_work / physical_execution / graceful_handoff / abnormal_incomplete_termination / recovery_overhead`。这些字段用于解释实际执行与控制面成本，不得被解释成固定 timing target；
- deterministic/fake timing regression 优先验证 policy，不依赖当前 ChatGPT/Scheduled Task 的偶然墙钟行为。

2026-09-07 的真实 dogfood 又暴露出本阶段尚未闭合的两个 generic continuation 缺口，因此它们必须在下一次 stable baseline **之前**与 overconstraint reduction 一起完成，而不是先发布一版、再单独追加：

- **ownerless handoff provenance deadlock**：gen78 已通过 `release --handoff` 明确释放 owner，但 handoff 时记录的 task-owned `ai_context_framework.egg-info/SOURCES.txt` 只因末尾缺一个 LF 而 dirty；后续已审阅 release closeout 把它恢复为 semantic-clean 后，`observe_handoff()` 正确发现 `task_owned_handoff_drift`，但旧 CLI 形成 `claim` 被 conflict 阻塞、`workspace reclassify/refresh` 又要求 active owner 的闭环死锁。修复必须保留默认 fail-closed，并提供窄、evidence-backed 的 ownerless cleanup reconciliation：只接受 explicit graceful handoff、lease absent、无 unresolved effect、generation 对齐、原 task-owned + retained intent、当前 semantic-clean、且 cleanup path 精确解释全部 handoff conflict；HEAD 若同时推进还必须显式 exact accept。该路径只修 workspace provenance 并保留审计 receipt，不自行授予 ownership/recover。当前真实 WS012 已用该设计 dogfood：receipt `26e17f8b-aa46-4731-a164-e38ce519933e` 后 `doctor.can_claim=true / blocked_reasons=[]`，随后正常 claim generation 79；未知 dirty 改写仍必须继续阻塞。
- **same-activation stale-owner takeover latency**：不得假设 ChatGPT Scheduled Task 模型能够纯 idle 等待一个 challenge window。历史 WS012 已证明同一 runner 可以跨 10+ 分钟 challenge window 后完成 recovery，但没有证据证明“无工具活动空等”本身受平台保证。因此 continuation 要提供 tool-backed blocking coordination `wait/await`：单个确定性工具调用读取**已持久化 challenge 的 deadline**并等待 `owner_active / owner_released / timeout` 之一，不硬编码 10 分钟语义预算、不授予 ownership、不自动判死/recover；timeout 后若当前 activation 仍存在，立即刷新 physical execution / HEAD / workspace / effect / provenance，按现有 formal reconcile/recover 取得新 generation，并在**同一 activation**继续安全有价值的项目工作。verified-live 长任务必须 yield，graceful ownerless handoff 则直接 claim、不进 challenge。
- `v0.0.3.87` 已成为 immutable failed release identity：GitHub master/tag 已形成，但正式 release workflow 在 publish 前因跨平台 CI regressions 失败，PyPI 无 `.87`。已确认的修复项包括 POSIX continuation execution command-tail parsing、Python 3.10 Observer f-string compatibility 与 Windows CI path/timing/environment assumptions。不得重推或复用 `.87` identity；这些 release regressions 与上述两个 continuation 缺口应在**同一当前阶段**收敛。

因此当前发布顺序更新为：`P0 frozen checkpoint 8081983 + Scheduled Writer overconstraint/graceful-handoff closure（含 .87 cross-platform CI fixes + ownerless handoff reconcile + tool-backed stale-owner wait/await） → one combined successor stable release/global install → installed-state physical-liveness + graceful-handoff + ownerless-direct-claim + stale-owner-wait/recover dogfood → Human-First Visualization Gate + expected-target Registry recovery Gate → P4 real-project dogfood → latest-authority Production acceptance → ongoing maintenance`。这里**不**先发 successor 再实现 blocking wait；它属于当前 continuation 阶段的补完，必须进入同一次 stable baseline 和 installed-state proof。该顺序 supersede 本文件中要求“P0 必须先单独 release/installed proof 才能开始下一实现”以及任何“先 successor release，再补 blocking wait”的临时表述；安全 proof 本身没有取消，只是合并到同一稳定 baseline。

### v0.0.3.88 installed-state closeout fact

截至 2026-09-08 14:27 +08:00，上述 combined continuation stage 已完成并退出当前执行主线：`v0.0.3.88` 已绑定 immutable tag，GitHub release workflow `34191533373` 成功，PyPI 已发布 wheel/sdist，并通过 `scripts/update_acf.ps1` 安装为 Windows 全局稳定版；`Get-Command acf` 解析为 canonical `acf.cmd`，同目录 `acf.exe` 不存在，uv-tool Python 从 `site-packages` 导入 `ai_context_framework`。安装态 focused continuation regressions 6/6、physical-liveness regressions 2/2 通过；真实 canonical WS012 又由安装态 `.88` 的 `coordination wait` 持续 589.647 秒跨过 persisted challenge deadline，明确返回 `ownership_granted=false`，随后基于 fresh Git/workspace/effect/GitHub/PyPI evidence 正式 reconcile/recover 到 generation 93。release/overconstraint/physical-liveness directives `dir-476ee3ab6bbc446fb167`、`dir-f1ce142b6f5f46479b09`、`dir-d98bf9b8628244cabe68`、`dir-fb0de0b1b4fc4536b97a` 已 evidence-backed resolve；对应 release CI、graceful-handoff compatibility、ownerless cleanup、physical-liveness 与 Windows source-isolation issues 也已收口。后续不得重放 `.88` publish/release effect，也不得继续把 continuation P0 当作当前 feature lane；当前唯一高优先级 durable route 是紧邻的 Human-First Visualization / expected-target Registry recovery Gate。

### Human-First Visualization / Registry Recovery Gate

durable directive `dir-5272efd83a0e434298e1` 将 Observer V2 的下一条强制路线调整为：**先安全关闭并发布当前 priority-100 continuation-liveness P0；随后必须完成 Human-First Visualization 与 expected-target Registry recovery 两个 Gate，才允许进入广泛 P4 或重启最终 Production acceptance。** 既有 P3 只代表 machine/runtime checkpoint，不再等同人类可读结果验收。

- Dashboard 主视图必须中文优先、面向项目决策阅读，而不是 developer/debug state dump。英文 ID、fingerprint、schema、raw provenance 等保留但降级到次要/折叠层；任何 mojibake 都直接判定 Gate fail。
- 每个 target 第一屏必须能直接回答：最终目标、完整路线、当前位置、为什么现在做这一步、最近证明/排除/改变了什么、问题及其 plan/route impact、下一步及理由、执行健康/是否需人工介入，以及最近 Agent run 的 start/end/duration/result/major outcome。
- architecture / roadmap / dependency / branch / multi-lane 等关系必须根据最新 authority 选择真实图形语义，并在现有 self-contained、single-file、`file://` safe 边界内用确定性 HTML/CSS + inline SVG 或等价静态实现展示 meaningful edges、current path 与 problem binding；“卡片 + 文本箭头”不算关系图验收通过。
- Human-First Visualization Gate 必须采用迭代视觉验收：每次有意义的 semantic/presentation 变化后生成真实 dogfood Dashboard，按显式 human-first rubric 与当前 authority/facts 检查实际 render，记录 pass/fail evidence，再继续改进直到 Gate 通过。unit tests、`check --strict`、schema、commit/checkpoint、测试数量或 HTML 成功生成都只是必要 machine evidence，不能单独关闭该 Gate；用户截图/视觉反馈属于一等 acceptance evidence，并可推翻此前 machine-only PASS。若当前执行环境不能真实检查 render，必须 fail-visible 保持 human acceptance open。
- FCC 必须恢复用户明确授权的 WS079、WS080、WS086 scheduled-automation targets：从 fresh current authority 读取各自真实 continuation identity，幂等恢复，禁止猜测历史 task-id。重新评估 FCC Project Overview，并保存中文、evidence-backed 的 enable/disable 理由。
- 新增 durable expected-target recovery/check contract：Observer user-level state 丢失后，要么从明确配置恢复 expected targets，要么明确报告 `unconfigured/incomplete/degraded` 与 alert；意外空 Registry 或缺少明确 expected target 绝不能得到绿色 Overall Health。该 contract 不得自动把任意 Workstream 提升为 target，也不得引入 daemon、数据库或额外 runtime dependency。
- real-project acceptance 至少覆盖 ACF 与 FCC；AStockT_AI 在当前执行环境可合法访问时纳入。必须覆盖 target recovery、plan/strategy change、unexpected blocker、route-impacting issue、map/presentation change、stale/incomplete run 与 Project Overview change。Production Observer 的 `read broad / write narrow / control none`、anti-masking、Markdown authority、禁止直接编辑 `dashboard.html` 等边界保持不变。

因此当前 durable 路线以紧邻的 **Scheduled Writer overconstraint reduction / graceful handoff** 小节为最新 sequencing authority：P0 checkpoint 与 overconstraint change 合并进入下一稳定 baseline，完成 installed-state physical-liveness + graceful-handoff dogfood 后，再进入 Human-First Visualization / Registry Recovery Gate。一次视觉迭代成功、一个 P4 slice、一次 release 或一个 acceptance window都不结束 WS012 长期 mission。

### Release terminal fact

`v0.0.3.84` 的 merge、`origin/master` 与 annotated tag 已形成历史 identity，但 exact GitHub Actions run `32984611066` 已取得终态 `completed/cancelled`，且 PyPI `ai-context-framework==0.0.3.84` 未发布。因此 `.84` publishing effect 只允许按同一 external identity reconcile 为 failed/cancelled；禁止 re-merge、re-push、再次 retrigger 或把新代码塞入 `.84`。`.84` 不是可 global-install 的 stable baseline，后续能力进入新的稳定候选，版本号由当时 release authority 决定。

### P0 — control-plane reliability first

P0 必须先形成独立 checkpoint，不与大型 Observer UI 重构混在一起。

1. **Fenced credential transport**：支持 `ACF_CONTINUATION_FENCE_TOKEN_FILE=<caller-controlled-temp-file>`。claim/recover 必须在提交 generation/lease 前完成 token delivery；启用 file transport 后 JSON 不回显 raw token；后续 assert-owner/heartbeat/renew/workspace/progress/effect/checkpoint/release 省略 `--fence-token` 时从同一 handle 读取；raw 参数保持兼容；非法/缺失/不可读写/空/异常尺寸 fail-closed；canonical state 只保存 hash；临时明文不进项目 Git/`~/.acf` canonical state；installed-state dogfood 必须证明 recover 后跨 execution-context 仍可继续 authenticated control-plane writes。
2. **Canonical Windows `acf.cmd`**：Windows 正式入口改为 CMD shim，通过 uv-tool environment 的 Python/module 进入 ACF，不复制业务逻辑。install/update scripts 必须创建/刷新/验证 `acf.cmd`，并机械保证同目录 `acf.exe` 不因 PATHEXT 优先级赢过 CMD；`Get-Command acf` installed-state regression 必须解析为 `acf.cmd`，并通过 CMD 验证 version/status/continuation/observer。不要新增 binary signing/certificate subsystem；文档只声明避免直接执行 ACF 自身 unsigned launcher，不声称绕过所有企业脚本/Python policy。
3. **Closeout authorization resolver**：durable scoped auto-close policy 与 explicit per-Workstream approval evidence 必须分离。记录至少可表达 project、WS id/type/class、action、authority/evidence source、revision/fingerprint、validity、supersession/revocation、optional expiry。narrower/newer explicit authority 优先；WS-specific manual gate 可覆盖项目默认；approval 不跨 WS/action 转移；material authority change 后 stale approval 必须重新评估；agent 不能靠裸 `--human-approved` 自行满足 Gate。Ready/merge/done/archive 及低层等价 closeout path 必须消费同一 resolver，AI-facing JSON 稳定给出 `auto_authorized | human_approved | approval_required | denied` 及 evidence/next-actions。必须覆盖 long-lived auto policy、manual override、non-transfer、revoked/superseded policy、stale approval、migration 与旁路回归。

### Observer V2 product authority

Observer V2 的目标是：**只展示用户实际注册并由外部自动化推进的目标，以中文 human-first 方式解释最终目标、完整路线、当前位置、问题、最近 Agent 执行、证据和下一步。**

#### Target Registry / display scope

新增显式 user-level Observer Target Registry，概念位置 `~/.acf/projects/<project-id>/observer/targets.json`（允许等价可审阅 runtime 文件）。它不写项目 Git、不成为事实源、不依赖数据库/ChatGPT 私有格式，也不要求 ACF 猜 Web Scheduled Task。Worktree/Workstream 存在不等于应该显示；只有显式注册的 scheduled-automation target 进入 Dashboard 主展示。第一阶段至少支持 fixed Workstream target 与 project-level dynamic automation target。每个 target 有独立 tab/page、timeline、problems、run chain、narrative/map。

Project Overview 是条件能力：只有认真读取当前 authority 后确实存在可解释统一目标/路线/架构时才 enable；异构项目可 evidence-backed disable，只显示 target pages；不得以偷懒为理由关闭。

#### Target Narrative / adaptive map / mandatory Map Review Gate

新增独立于 Project Narrative 的 target/workstream narrative，拥有 target-local sources、fingerprint/staleness、当前位置、problems/evidence；单个 target 变化不能让所有 target 一起 stale。derived semantic state 永不替代 Markdown authority。

可视化必须保持 single-file/self-contained/file:// safe HTML/CSS/inline SVG，不引入 React/Mermaid runtime/Graphviz runtime/CDN/daemon。Agent 根据真实语义选择 linear/branching/architecture/dependency/roadmap/state-machine/timeline/multi-lane/tree/text/hybrid，不固定模板。

每次 scheduled semantic refresh 强制执行 auditable **Map Review Gate**，至少记录 `decision=unchanged|patch|rebuild|presentation_change|project_overview_enable|project_overview_disable`、reason、evidence、authority_fingerprint。Review 必须检查 PLAN/Task Plan/Workstream/Current Task/planning references/ADR/user directives/current stage/key evidence、执行偏离、新问题、失效节点、新并行路径及当前图形是否仍真实。Fingerprint 只做 cheap triage；任何 map-relevant signal 变化都要重读必要 authority 并显式决定。重复 unchanged 也需审计，防止浅层复用；历史 map/route version 保留 provenance。

#### Problems / run observability

问题是 route/map 一等元素，并尽量绑定受影响 node/route。至少按正交维度表达：
`expectedness=expected|unexpected|unknown`；
`handler=agent_self|human_approval|human_action|external_system|other_project`；
`scope_relation=in_scope|cross_cutting|out_of_scope|tooling_dependency|external_dependency`；
`blocking_impact=non_blocking|degrading|blocks_current_step|blocks_task`；
`plan_impact=none|local_adjustment|route_change|major_replan`；
以及 detected/investigating/working/waiting/transferred/deferred/resolved 等 lifecycle。
route-impacting problem 必须触发真实 map review/update；跨项目问题只展示 dependency/impact/transfer linkage，不越权修改 foreign project。

每个 scheduled activation 尽量展示 start/end/duration/result/major outcome/route link。优先 continuation round 时间；无 continuation 时使用窄范围 user-level Observer start/finish marker。异常或不完整 run 禁止伪造 end time，只展示 last activity 与 lower-bound/approximate duration。主 timeline 只保留 Agent start/end、milestone/stage、plan/strategy change、problem、human action、route change、release、key validation；heartbeat/generation/fence/fingerprint 等噪声折叠技术详情。

#### Chinese human-first Dashboard V2

主视图必须直接给出足够细节：最终目标、完整计划/路线、当前位置/focus、为什么做当前步骤、最近证明/排除/改变了什么、当前问题及其 plan impact、下一步及理由、执行健康、是否需要人工介入、最近 Agent run 时间/时长/结果/主要产出。HEAD/generation/lease/fence/effects/schema/fingerprint/raw provenance 折叠技术详情，但有意义的 reasoning/progress 不得全部藏起来。人类可见时间按当前 authority（目前 UTC+08:00）展示，structured state 保持 canonical time semantics。

### P1 / P1.5 / P2–P4 implementation / dogfood

- **P1**：Target Registry、target-local scope/tabs、run timing/history、conditional Project Overview decision state。已在 `200c75f989319ae708acdf3ce8e4f8b4dfe1c1bc` 形成独立 checkpoint；验证包括 58 个 focused Observer tests、615 个 full unit tests、file-scoped WS012 guard、`git diff --check`、strict docs 与 template check。
- **P1.5 — Automation / Prompt Execution Contract**：在 P1 之后、P2 之前建立可审阅的自动化提示词执行合同。正确模型固定为“两类 Scheduled Task wrapper + 一个 Writer runtime-generated continuation prompt”，但不引入第二套 generic state machine：
  - **Writer Scheduled Task wrapper common core** 必须是 sufficient high-salience first-read bootstrap，而不是为了省 token 人为削薄。固定包含稳定 project/task/worktree/branch/Workstream identity、existing-worktree 的精确 project-access/DevSpace 打开语义、stable ACF upgrade/adaptation、authority refresh、每轮强制消费 `acf continuation prompt + execution_policy`、live-vs-stale owner 用户可见处理、安全/write-scope/exit 边界、checkpoint/commit/Gate 不等于 stop，以及缺失后会显著增加误执行风险的首读规则。volatile owner/generation/stage/next_action 不写死；项目/任务专属 scientific/Runtime/resource/permission/security/validation/issue-reporting 通过显式 extension slot/overlay 保留。
  - **Production Observer Scheduled Task wrapper common core** 同样是完整首读合同，至少固定 `read broad / write narrow / control none`、existing-checkout、Target Registry display scope、anti-masking、semantic review、Map Review Gate、human-first-but-detailed information policy、truthful run history、cross-project non-interference 与 local authority/source rules；项目/target 专属规则进入命名 extension slot。Observer wrapper 不复制 Writer ownership/recovery/fencing state machine。
  - **Writer runtime-generated prompt** 继续由 stable `acf continuation prompt + execution_policy` 唯一动态提供 owner/claim/recover/fencing/directive/current-plan/progress/checkpoint/release/exit generic authority；不得重复静态项目约束，也不得承载 Observer semantic state machine。
  - separation 必须成为 reviewable machine/docs/template/tests contract，而不只停留在 CLI help。已有 `scheduler_wrapper_contract` 的 sufficient-bootstrap 语义作为兼容基础，P1.5 在此基础上补齐 wrapper-family/role/static-vs-runtime/extension/evidence contracts，不回退到历史 thin-wrapper 设计。
  - **Observer anti-laziness 是硬 prompt contract**：每次 scheduled semantic refresh 必须显式审查 narrative/map/presentation/Project Overview 是否仍真实，并审计记录 `unchanged|patch|rebuild|presentation_change|project_overview_enable|project_overview_disable`、reason、evidence、authority fingerprint。fingerprint 只做 cheap triage；PLAN/Task Plan/Workstream/current task/planning refs/ADR/user directives/current stage/key evidence、执行偏离、架构、问题、依赖、并行路径或策略发生 map-relevant 变化时，必须重读必要 authority 后再决策。`unchanged` 也必须有 reason/evidence，连续 unchanged 仍可审计。
  - presentation type 必须从真实语义选择 flow/branch/architecture/dependency/roadmap/state-machine/timeline/multi-lane/tree/text/hybrid；Project Overview 只有 evidence-backed 证明不存在可信统一路线时才可 disable，并随 authority 变化重新评估。human-first 只折叠 control-plane 噪声，不得隐藏最终目标、路线、当前位置/why-now、已证明/排除/改变、问题及 plan impact、下一步及理由、health/人工介入与最新 run outcome。
  - Writer execution evidence 要能被 Observer 使用：stage/milestone、major outcome、proven/excluded result、blocker/problem + plan/route impact、next logic；heartbeat/generation/fence 噪声不足以替代语义 evidence。run observability 必须保持 start/end/duration/result 真值与顺序；无 continuation 的 target 使用 user-level marker；crash/incomplete run 禁止伪造 end time。
  - **Interactive presentation-maintenance contract** 分三种生命周期：① immediate transient presentation-only patch；② 下一次 Production Map Review 消费的 transient one-shot semantic/presentation review request；③ 明确 durable 的 presentation rule。Agent 必须先理解当前 derived semantic/presentation state，把用户意图转换为 reviewed intent/scope/rationale/evidence，ACF 只做确定性记录/并发校验，不自动解释自然语言。任何 immediate patch 只能通过窄范围 user-level derived presentation interface + deterministic re-render，禁止直接编辑 `dashboard.html`；可能改变/误导 route order、node relationship、dependency、stage/completion、architecture、mainline/branch 等语义时必须升级为 Map Review + authority reread。
  - interactive presentation write 不取得 Writer ownership，仍遵守 `read broad / write narrow / control none` 与 foreign-project non-interference；以 current presentation revision/fingerprint 做轻量 optimistic concurrency，冲突 fail-closed 并要求 reread/re-evaluate，不新增 lease/fence state machine。one-shot 成功应用/复核后必须退出 active context，仅保留审计历史；durable rule 仅在明确长期有效时进入 active contract，并支持 supersede/withdraw，防止 resolved transient guidance 被后续 Production Observer 复活。
  - P1.5 的**结构/进入 P2 Gate**必须同步 PLAN/Workstream、README/Automation/System Manual/template、相关 CLI/machine contracts 与 regression tests，并对 ACF、FCC WS079/WS080/WS086、AStockT_AI 的 Writer/Observer Scheduled Task families 完成真实 prompt-level audit、per-family migration delta 与可执行的 acceptance matrix：证明 shared common core、各项目唯一 extension、existing-wrapper migration safety 与 stable generated continuation authority 的职责边界已经冻结。若当前 scheduled execution context 对 sibling task 只有 inventory/read-back、没有 mutation authority，则该真实 platform boundary 必须 fail-visible 保留，但**不得把一个当前上下文无法执行的外部 mutation Gate 串行阻塞 P2/P3 内部产品实现**。
  - P1.5 三种 interactive presentation-maintenance lifecycle 的**完整 runtime acceptance 是跨阶段 Gate，不是 P2 的前置自相矛盾条件**：P2 实现 semantic review、one-shot review request、durable rule state/consume/supersede/withdraw 与 Map Review 语义；P3 实现 immediate transient derived-presentation patch、optimistic concurrency 与 deterministic re-render。`transient_patch / one_shot_semantic_review / durable_rule` 的 integrated acceptance（包括 cleanup、anti-resurrection、独立 Production render 交互）必须在进入 P4 / release Gate 前全部通过。未实现 runtime 前只能验证 contract/readiness，禁止伪造 runtime acceptance pass。
- **P2**：target narrative、independent fingerprint/staleness、Map Review Gate、adaptive map、problem model、route binding、cross-project transfer，并实现 P1.5 已冻结的 semantic review / presentation-maintenance runtime 语义。
- **P3**：基于 P1/P1.5/P2 重建 Chinese human-first self-contained Dashboard V2，并实现 narrow derived presentation maintenance surface。
- **P4**：真实项目 dogfood：ACF 只显示注册的 WS012 target；FCC 注册的 WS079/WS080/WS086 各自独立 tab，并认真判断是否应有 Project Overview；AStockT_AI 注册自动推进 target，若 authority 支持统一 project route 才启用 overview。必须真实覆盖 plan/strategy change、unexpected blocker、route-impacting issue、external/tooling transfer、abnormal run、map presentation change、overview enable/disable、Windows CMD、fenced credential installed-state 与 anti-masking。

最终 Production acceptance 只能从包含 P0 + P1 + P1.5 + P2–P4、正式 release + global install 的稳定安装态开始；旧 `.83`/过渡 activation 只作历史 evidence，不拼接。具体连续次数与 reset 条件读取当时最新 acceptance authority。Maintenance snapshot/narrative refresh 永远不冒充 Production activation；acceptance pass 也不结束 WS012 long-lived mission。

### Directive lifecycle / execution order

本节 durable authority 同步完成后，相关 current directives 应以本 PLAN/Workstream evidence `adopt`；对应能力真正完成后再 `resolve`。当前顺序：P0 credential → P0 Windows CMD → P0 closeout authorization → P1 → **P1.5 Automation / Prompt Execution + interactive presentation-maintenance contract** → P2 → P3 → P4 → full release/global install/installed-state dogfood → latest-authority Production acceptance → ongoing maintenance。

---

## 2. Historical scheduler topology（已被 Current authority 动态 cadence 规则 supersede）

当前 ACF dogfood 固定采用两个职责完全不同的 Scheduled Task：

### Production Observer

- 名称：`ACF Project Observer`
- cadence：每小时 `:34`
- project：`D:\PROJECT\Tools\ai-context-framework`
- workspace：primary checkout / existing-checkout
- control boundary：`read broad / write narrow / control none`
- 只允许稳定安装态 `acf observer` 写 `~/.acf/projects/<project-id>/observer/`
- 不 claim/challenge/recover/release Writer，不修改 Git/Workstream/project files，不升级 ACF
- v0.0.3.77 起，Dashboard 所有人类可见时间统一显示北京时间 `UTC+08:00`；canonical state/history 继续保存 UTC

### Maintenance Writer

- Workstream：WS012
- 标准 worktree：由 `acf worktree verify/list` 与 local registry 决定，不在共享 Markdown 固化机器绝对路径
- scheduler cadence：每小时 `:04`
- continuation task-id：`WS012`
- 负责诊断、修复、测试、release 和 installed-state verification
- 普通 wake **不得代替 Production Observer 例行执行 `observer snapshot` / render**

`:04 → :34` 保持约 30 分钟间隔，使 Writer 的真实变化先发生，Observer 再独立观察。

---

## 3. Anti-masking contract

这是 WS012 最重要的 dogfood 规则。

正式 Observer 已上线后，Maintenance Writer 每轮首先读取：

- `observer_status.json`
- `state/runs.jsonl`
- `state/current.json`
- `semantic/interpretations.jsonl`
- `dashboard.html` mtime / 可见 freshness

并判断最近一次 **Production Observer** 是否按期成功。

普通 Maintenance wake 禁止为了“让 Dashboard 看起来新鲜”而例行运行：

```text
acf observer snapshot
acf observer interpret
```

否则会掩盖：

- scheduler 没触发；
- watchdog 自身失败；
- lock/overlap 问题；
- data age stale；
- semantic 长期 stale。

只有以下场景允许 Maintenance 主动运行 Observer 写操作：

1. 修复后 focused verification；
2. 明确诊断实验，且已先保存故障前的 durable evidence；
3. release smoke / installed-state dogfood；
4. migration 或用户明确要求的人工刷新。

这类主动运行必须在 continuation effect/evidence 中注明用途，不能被当成 Production Observer 的 scheduler 成功证据。

---

## 4. Initial operational defect（历史已解决）

首个已确认问题：

- issue fingerprint：`e469e99755604428cd08`
- evidence：Observer revision 88
- 现象：primary master 已将 WS011 归档为 Done，但另一个仍注册的旧 worktree 保留历史 `WS011=Active` detail；Observer 将该旧副本重新投影成当前 Active Workstream，并产生 `registry-lifecycle-mismatch` warning 与 stale semantic。

这说明 Project Observer 当前的 Workstream source authority 仍可能把“同项目其他 worktree 中的历史副本”误当作当前 project authority。

### 期望 authority 规则

优先验证并实现以下原则，而不是简单忽略 warning：

1. primary checkout 的 active/archive lifecycle 是 project-level Workstream 当前/终态 authority；
2. 某 Workstream 自己的 bound worktree 只有在 registry/lifecycle 允许时，才能作为该 Workstream 的当前专属 source；
3. 任意其他 registered worktree 中顺带存在的旧 Active Workstream detail，不能单独复活一个在 primary 已归档/终态的 Workstream；
4. 这类历史副本可以作为 provenance / divergence / stale-source evidence 被观察，但不能覆盖 canonical current lifecycle；
5. 若 primary 与该 Workstream 自己的 active bound worktree 真正冲突，应 fail-visible（warning/critical + source consistency），不能静默选一个版本。

### Required regression

至少覆盖：

- primary archived Done + unrelated registered worktree stale Active → canonical 不复活；
- primary Active + bound worktree Active → 正常聚合；
- primary Active + bound worktree lifecycle divergence → 明确 Alert；
- unrelated worktree 的历史 WS detail 不参与 canonical current selection；
- history/provenance 仍可保留旧 source，不丢证据。

该问题已在 v0.0.3.78 完成修复、发布和 installed-state dogfood；后续 WS012 不再把本节视为当前默认执行计划。本节保留为最初 operational dogfood 的历史设计证据。

---

## 5. Operational dogfood gates

### WS012.1 — Bootstrap and separation

完成条件：

- 正式 `ACF Project Observer` task 启用且 cadence=`:34`；
- WS012 Writer cadence=`:04`；
- Dashboard shortcut 唯一维护在 `C:\Users\lenovo\Documents\ACF Project Observer.lnk`，只更新原快捷方式 target，不创建版本/时间戳副本；
- production / maintenance 权限边界和 anti-masking 文档化；
- WS012 continuation 初始化并使用稳定 ACF control plane。

### WS012.2 — Source authority hardening

完成条件：

- issue `e469e99755604428cd08` 有 deterministic regression；
- 修复后 focused Observer tests、strict/template checks、file-scoped guard 和 `git diff --check` 通过；
- 真正的 installed-state Observer 不再把已归档 WS011 ghost-resurrect 为 Active；
- 修复不删除历史 evidence，不把 arbitrary worktree 变成新的 authority。

**Implementation evidence（2026-08-24）**：已新增 primary archive authority 与 active-registry source gate。两个新回归先在旧实现上分别失败：primary 归档后 WS123 被 stale worktree 复活；registry 已 merged 时 stale bound Active 覆盖 primary Done。修复后这两个回归与既有 registry-scoped source 测试均通过，完整 `tests.test_observer_cli` 37/37 通过。真实 ACF candidate `observer snapshot --dry-run` 保留 production runtime 不写入，结果 `snapshot_consistency=stable`、current workstreams 仅 `WS012:Active`、alerts 为空、7 个 worktree diagnostics 仍保留；issue `e469e99755604428cd08` 的 ghost WS011 现场被产品层 source-authority 修复而不是靠清理旧 worktree 绕过。

### WS012.3 — Dynamic user directives / live steering

这是 2026-08-25 用户需求变化直接暴露出的 continuation 产品缺口：一个 Scheduled Task 即使已经进入 `waiting_external` 或已有 persisted `next_action`，用户仍可能在运行过程中新增需求、调整优先级、增加约束或改变计划；当前没有一等、可审计、低摩擦的输入渠道。

目标不是新增第二套 Task Plan，而是新增一个 **user-authority inbox**。第一版设计：

```text
acf continuation directive add
acf continuation directive list
acf continuation directive show
acf continuation directive adopt
acf continuation directive resolve
acf continuation directive supersede
```

要求：

- durable event 存在用户级 continuation namespace，不写项目私有数据库；
- CLI 只做确定性记录、状态迁移、边界校验、排序和 prompt 暴露，不自动判断自然语言需求真伪；
- 第一版 directive kind 固定为 `requirement | priority_change | constraint | plan_change`；
- directive 保留 `id / created_at / kind / priority / text / status / supersedes / evidence_refs` 等可审计字段，正文和集合继续受 bounded/secret-safe 约束；
- pending directive 是**新的用户 authority signal**，其优先级高于旧 persisted `next_action`，但不会静默成为项目事实；
- Agent 必须 authority refresh 后判断：临时运行要求可直接执行；持久需求/计划/约束应同步进入正确 Markdown authority（PLAN / Workstream / Rules 等），然后把 directive 标记 adopted；
- `continuation prompt --json` 稳定暴露 `directive_context`，至少包含 pending count、latest directive、digest/revision 和是否需要 authority refresh；
- generated prompt 在存在 pending directive 时高显著展示，并明确 old `next_action` 可被新用户 authority supersede；
- heartbeat / renew 至少返回 pending directive count 与 digest/revision 变化，使长 session 不必等下一个 scheduler wake 才发现用户 steering；
- directive lifecycle 保留 append-only/auditable 事件历史；resolve/supersede 不篡改原始用户输入；
- 不把普通产品 issue、自动推断、聊天 transcript 或模型内部想法写成 directive。

第一轮 dogfood 必须用该能力本身录入并消费至少两个真实 directive：

1. Observer Project Narrative / Project Map；
2. Global continuation issue intake / triage / batch maintenance。

#### WS012.3A — Directive lifecycle hardening（2026-08-26 final authority）

在继续 passive Production Observer acceptance 之前，先完成 continuation directive lifecycle 的正式加固。目标是让长时、多 Agent 项目中的 user live steering 可审计、可恢复、可长期运行，同时保持 directive 只是 **user-authority inbox**，不演化成第二套 Task Plan。

本阶段以 directive `dir-30af839cd72e4feca7de` 为最新用户 authority；它已正式 supersede 早先 provisional lifecycle directive `dir-302f383282b34c8185ff`。实现和 dogfood 必须遵守以下顺序：**P0 lifecycle semantics → P1 hygiene → P2 rollover/archive → release/global install → installed-state dogfood → restart Production Observer acceptance**。

##### P0 — Lifecycle semantics / owner separation

Directive schema/CLI 至少支持：

- lifetime：`transient | durable | unspecified`（或语义完全等价、可确定验证的 metadata）；
- projected status：`pending | adopted | resolved | superseded | withdrawn`；
- `resolve` = 工作/要求已完成；
- `withdraw` = 用户或更高 authority 明确取消，不等价于完成；
- `supersede` = 同一 active requirement 的新版本替换旧版本，并保留完整 lineage；
- 独立新增需求继续使用 `add`；已 resolved 的历史 directive 不允许被“重新打开”。

状态约束：

- transient one-shot 可 `pending -> resolved`，不要求为了形式先 adopt；
- 需要跨 round 执行的 transient directive 只有在 durable execution state 已建立后才允许 adopt；
- durable requirement / constraint / priority_change / plan_change 在 adopt 前必须完成 authority refresh，并把持久语义同步到正确 Markdown authority（PLAN / Workstream / Rules / Task 等），同时清理或 supersede 与新 authority 冲突的旧表述；
- durable adopt 必须携带可审计 evidence；**禁止仅因为 Agent“读到了文本”就 adopt**；
- 当前 session 实际消费过的 directive 在控制点必须有明确 disposition：`resolve / adopt / supersede / withdraw / keep pending with reason`，不得静默遗留；
- pending user authority 持续高于 stale persisted `next_action`。

Owner separation 是硬边界：

- 非当前 Writer owner 的 Agent 可以代表新的用户 authority 执行 `directive add/supersede`，不需要获取 Writer lease / generation / fence / workspace write authority；
- 当前 Writer 通过 `continuation prompt`、`heartbeat` 或 `renew` 暴露的 revision/digest 变化，在下一 safe control point 发现并处理；
- 外部 directive 注入本身不得偷偷获得项目文件写权限或 continuation owner 权限。

安全边界继续保留：credential-like value refusal、bounded text/evidence refs、schema migration compatibility，以及 CLI 只做机械校验/状态迁移、不自动判定自然语言事实真伪或任务是否语义完成。

##### P1 — Directive hygiene / doctor observability

`acf continuation doctor --json` 增加机械、非语义裁决式 hygiene findings，至少覆盖：

- stale adopted directive；
- stale high-priority pending directive；
- durable adopt 缺少 adoption evidence；
- active directive count pressure；
- journal event/byte rollover pressure；
- active directives 自身接近/达到 capacity 的 fail-closed 风险。

Doctor 只能报告机械事实和风险，不允许：

- 按年龄自动 resolve；
- 推断某条自然语言 requirement 已完成；
- 自动 withdraw/supersede；
- 把 hygiene warning 当作写 authority。

Generated continuation guidance 必须在有 consumed/pending directive 时高显著提示 disposition 义务，并且 heartbeat/renew 至少稳定暴露 pending/active 摘要、revision/digest 变化和 hygiene pressure，使长 session 不需要等下一个 scheduler wake。

##### P2 — Crash-safe terminal rollover / archive

当前 directive journal 不能依赖“达到 hard event/byte limit 后直接失败”作为长期运行策略。新增 terminal rollover/archive：

- 只允许归档 **完整 event chain 已终态** 的 directive：`resolved / superseded / withdrawn`；
- `pending / adopted` 及其链条绝不能归档；
- rollover 必须在 hard event/byte limits 之前由 deterministic pressure threshold 触发；
- active directives 自身已经占满 capacity 时继续 fail-closed，不通过丢 active authority 腾空间；
- current history 维持 bounded，archive history 继续可通过 CLI 查询；
- current + archive 必须保留 digest/audit 可验证性，能够证明 event chain 未丢失、未重排、未篡改；
- rollover 写入必须 crash-safe：新 archive 与 current journal 的切换不能产生半归档、双计数或丢链；
- schema migration / upgrade 必须保留 archived lineage 与 current projection compatibility。

CLI 需提供足够的 list/show/history 或等价查询能力，使 archived terminal directive 仍可被按 id/lineage 审计，而不是“归档后不可见”。

##### Required dogfood acceptance before next stable release

必须在真实 WS012 continuation 与隔离 `ACF_HOME` stress 中至少完成：

1. final lifecycle plan_change：PLAN/Workstream authority 同步后，以 evidence-backed adopt 消费；
2. transient one-shot：`pending -> resolved`；
3. durable directive：先 authority sync/evidence-backed `adopt`，再在完成后 `resolve`；
4. same-requirement edit：`supersede`，验证 old/new lineage；
5. explicit user cancellation：`withdraw`，验证与 resolve 语义不同；
6. fresh-owner external injection：另一个非 owner context 注入 directive，当前 owner 通过 revision/digest 在 safe control point 发现；
7. isolated `ACF_HOME` rollover stress：跨 event/byte pressure 执行 terminal rollover，验证 pending/adopted 不归档、terminal chain 完整、archive 可查询、digest 可审计、crash-safe；
8. credential-like refusal 与旧 schema migration regression 继续通过。

实现完成后同步 CLI help / JSON contracts / README / `docs/Automation.md` / dogfooding System Manual / template System Manual / tests / changelog/version/package metadata，并按风险运行 focused、full unit、strict/template、upgrade/package、完整 release gate。稳定 release + global install + installed-state dogfood 完成后，**此前 v0.0.3.83 的 `6/24` acceptance 只保留为历史证据；新的 directive lifecycle stable baseline 从 0 重新开始 24 次连续 Production Observer acceptance，不与旧窗口拼接。**

### WS012.4 — Observer Project Narrative / Project Map

当前 Dashboard 已能展示 overall health、Workstream 当前解释和 meaningful timeline，但页面仍偏“最近发生了什么”。新增项目级长期叙事层，第一屏还要回答：

1. 项目最终想做成什么；
2. 整体架构由哪些模块构成、如何关联；
3. 项目沿什么逻辑路线演进到现在；
4. 哪些 milestone 已完成、当前位于哪里、下一阶段是什么；
5. 每个逻辑节点由什么证据支撑。

计划新增 derived semantic state：

```text
Project Narrative
├─ overall_goal
├─ architecture
│  ├─ nodes
│  └─ edges
├─ milestones
│  ├─ id / title / status
│  ├─ depends_on / next
│  ├─ summary / implication
│  └─ evidence / provenance
└─ current_position
```

边界：

- 项目目标/架构/里程碑必须绑定明确 provenance，不由 Observer Core 自由猜测；
- model/agent 可根据权威 Markdown 生成语义解释，CLI 只验证、保存、版本化、stale 检测和渲染；
- 不默认扫描全部仓库，继续从项目入口、active authority、plan refs 和 observation profile 渐进读取；
- Project Narrative 是 derived semantic state，不替代 `Context.md`、Task Plan、Workstream、ADR 等事实源；
- source fingerprint 变化后旧 narrative 必须 fail-visible stale，不能继续装作 current。

Dashboard 新增：

- Overall Goal 区；
- Architecture Map；
- Logical Milestone Flow / Project Evolution；
- Current Position；
- milestone evidence/provenance 展开；
- 当前 Workstream 卡片和 Timeline 保留，作为“现在”和“最近变化”层，而不是被新图取代。

可视化要求：

- 继续生成单文件、`file://` 可打开、自包含 HTML；
- 不引入 React/Mermaid/Graphviz runtime/CDN/HTTP daemon；
- 流程和架构优先使用确定性 HTML/CSS + inline SVG；
- 丰富颜色，但颜色必须有稳定语义并配合文字/符号，不能只靠颜色传递状态；
- 建议视觉语义：Goal=indigo，architecture category=blue/cyan/violet，Completed=emerald，Active=blue，Maintenance=purple，Waiting=amber，Warning=orange，Critical=red，Future=slate。

### WS012.5 — Global continuation issue intake / triage / batch maintenance

每次 `:04` Maintenance wake 在不破坏 anti-masking 的前提下，轻量读取：

```text
acf log issues --all-projects --open-only --json
```

不能直接把原始 open count 当作真实 backlog。当前全局历史中存在大量旧版本同根因 fingerprint，因此必须先做 current-stable triage：

- 当前稳定 ACF 是否仍可复现；
- 是否已被后续 release 修复但漏写 resolution event；
- 是否与其他 fingerprint 属于同一 root-cause cluster；
- 是否真的是 ACF/continuation/automation 通用问题，而不是一次性业务失败；
- 是否已经有 deterministic regression / 修复方案 / affected files / validation plan。

逻辑队列：

```text
Immediate
Ready Batch
Observe
```

`Immediate` 不等待积累，满足任一条件即可抢占 passive acceptance：

- critical；
- 可能导致数据损坏、重复 non-idempotent side effect、ghost owner / half-committed generation；
- 阻断 continuation claim/recover/release 或 Scheduled Task 持续运行；
- 新稳定版本严重 regression；
- 同一 root cause 已影响多个真实 Workstream，且当前稳定版仍可复现。

普通 high/medium 问题先进入 triage/repair planning，不为了单个小 bug 高频发版。达到下列任一条件时启动 Maintenance Batch：

- `Ready Batch` 中至少 3 个**已验证、彼此独立的 root-cause cluster**；
- 同一 root cause 在当前稳定版影响至少 2 个真实 Workstream；
- 用户明确要求立即启动一轮 batch。

Batch 一旦启动，本轮目标是把当时已经进入 `Ready Batch`、安全且相互兼容的问题**全部执行完**：deterministic regression → fix → focused/full gates → 一次稳定 release → global install → installed-state dogfood → resolution events。证据不足的 `Observe` 项不为了凑数量强行实现。

一个 issue 完成 triage/repair plan 后，后续 wake 只检查 occurrence/reproduction/severity 是否变化，不重复从零规划，避免 maintenance busywork。

**2026-08-27 current-stable Immediate triage：** 全局 issue intake 在稳定安装态 `v0.0.3.83` 上确认了同一 fenced-owner credential transport 根因，至少已影响 WS079 与 WS080。代表 fingerprint 包括 `2571acfc1377ae41f0ce`、`590e29d4596887eacaa6`、`517bb8cb2f78705383de` 与 `a315b38f1c4bf13b429e`：`claim/recover` 返回 plaintext `fence_token`，而真实 project-access / scheduler command safety 会拒绝后续携带高熵 token 的 `assert-owner / heartbeat / workspace / checkpoint / release` 命令，导致已经完成 authenticated recovery 的 fresh owner 仍无法继续 fenced control-plane writes。该缺陷同时满足“阻断 Scheduled Task 持续运行”和“同一 current-stable root cause 影响多个真实 Workstream”，因此升级为 `Immediate`，不等待普通 Ready Batch 门槛。

本轮 repair contract 是 backward-compatible 的本地 credential handle：当调用方预先设置 `ACF_CONTINUATION_FENCE_TOKEN_FILE` 时，`claim/recover` 必须在提交新 generation/lease 前把新 token 写入调用方控制的临时文件，JSON 不再返回明文；同一环境变量随后允许所有 fenced owner command 在省略 `--fence-token` 时读取该 credential。raw `--fence-token` 继续兼容；token file 缺失、非法或不可读写必须 fail-closed；canonical continuation state 继续只持久化 hash，临时明文文件不进入 `~/.acf` 或项目 Git，并由调用方在 release/session closeout 后删除。修复必须覆盖 claim 与 challenge-backed recover 两条 credential issuance 路径，以及 assert-owner/heartbeat/workspace/checkpoint/release 的 installed-state dogfood。

该 Immediate 在 `v0.0.3.84` 已完成 merge/tag、但 trusted-publishing workflow 尚处于既有 queued identity 时被发现。**不得为此重写、重推或再次 retrigger `v0.0.3.84` tag，也不得把新代码塞入已经签定的 `.84` release identity。** 修复作为 `.84` 之后的下一稳定候选进入独立 release；在 `.84` 外部发布状态未终态前，只允许继续验证/提交本修复和只读查询现有 publish authority，禁止制造第二个 `.84` side effect。

### WS012.6 — 24-hour production watchdog window

原 24 小时 acceptance window 保留，但因为 WS012.3/4/5 将改变 continuation 和 Observer 产品，应在这些能力完成 release + global install 后**重新从新的稳定基线开始计数**。

2026-08-26 的 final directive lifecycle hardening（WS012.3A）再次改变 continuation 产品与稳定安装态，因此 `v0.0.3.83` 已取得的 `6/24` 只作为历史 dogfood evidence 保存。2026-08-27 又确认 fenced-owner credential transport 属于 current-stable Immediate，并将继续改变 continuation 产品；因此真正的新 acceptance baseline 必须是**包含该 Immediate 修复的最新稳定 global install**。即使 `v0.0.3.84` 先完成 publish/install，在 credential-transport 修复尚未进入后续稳定版前产生的 production activation 也只能作为 pre-baseline diagnostic evidence，不得计入最终连续 `24/24`。待该修复 stable release + global install + installed-state fenced-owner dogfood 完成后，从其后的第 1 次独立 Production Observer activation 重新计为 `1/24`，不得拼接 `.83` 或过渡 `.84` 样本。

至少观察 24 个连续 hourly Production Observer activation，期间 Maintenance 不做例行 snapshot。

Production Observer 的 Project Narrative 刷新属于正式 `:34` activation 自身，而不是 Maintenance 补写。每个 production activation 在初始 snapshot 后必须检查 `project_narrative.status`：

- `current`：保持当前 narrative，不制造重复版本；
- `stale | not_interpreted`：使用安装态 `acf observer narrative-source` 对**显式** authority source paths 读取精确 projection/fingerprint，由当前 Observer Agent 基于该 projection 与最小必要 authority 生成 derived narrative JSON，再用同一 fingerprint/source-path 集合执行 `acf observer narrative-apply`，最后重新 snapshot/render；
- 生成 narrative payload 所需 scratch 只能放 OS 临时目录，不得写项目文件、continuation/workstream/effect control state 或新增第二份 canonical Dashboard；完成后删除 scratch；
- source fingerprint 在 source→apply 之间变化、证据不足或 credential-like 内容触发拒绝时 fail-visible，保留 stale 并记录该 production activation 未通过 narrative freshness gate，禁止 Maintenance 事后刷新冒充 production 成功；
- 只有最终 production snapshot 中 narrative 已 `current`（或初始即 `current`）的 activation 才能计入连续 24 次 acceptance。

验收至少包括：

- scheduler run cadence 正常；
- `dashboard.html` freshness 持续更新；
- visible timestamps 始终为北京时间，canonical JSON 始终 UTC；
- Project Narrative / architecture / logical milestone map 在无 authority 变化时稳定，不产生无意义重复历史；
- project authority 变化后 narrative 正确 stale → refresh，不保留错误 current 状态；
- snapshot consistency / self-health / source consistency 可审计；
- 至少覆盖一次 Writer active/HEAD 变化后由后半小时 Observer 独立观察；
- unchanged period 不制造重复 meaningful history；
- semantic stale/current 行为不由 Maintenance 刷新所掩盖；
- 没有重复 Observer task、重复 Dashboard 或重复 shortcut。

不为了测试“miss”主动破坏 production task；scheduler miss/failure 用 deterministic test 覆盖，若真实发生则作为额外 dogfood evidence。

### WS012.7 — Longitudinal maintenance

24h gate 通过不自动把 WS012 Done。

后续 hourly Writer wake：

- 先处理 pending user directives；
- 再检查 Immediate global issues；
- 再判断 Ready Batch 是否达到启动条件；
- 再做 Production Observer passive acceptance / longitudinal evidence；
- 没有当前安全、有价值工作 → 不 claim、不制造 control-plane busywork，结束本次重复 wake；
- mission 保持为长期 Maintenance，除非用户明确关闭或另行迁移。

---

## 6. Release discipline

Observer 修复进入稳定版前必须：

1. focused tests；
2. `acf workstream guard WS012 --files ... --json`；
3. `git diff --check`；
4. `uv run acf check template --json`；
5. `uv run acf check docs/ai --strict --json`；
6. 与风险匹配的 full unit / upgrade matrix / `scripts/release_check.py --mode full`；
7. merge/tag/publish side effect 使用 continuation effect identity；
8. PyPI/remote authority 证明确认后才 terminalize effect；
9. 全局稳定安装后再跑 installed-state Observer dogfood。

普通 checkpoint、commit、测试通过或一次 hourly observation 都不是 mission 结束条件。

---

## 7. Immediate next action

截至 2026-09-01 generation 98，P0 credential transport、canonical Windows `acf.cmd`、closeout authorization、Observer V2 P1/P1.5/P2/P3 均已有独立 checkpoint；P3 product/runtime Gate 已由 `0e2137f9af74a9dda38553814e168f17745ea5f3`、650 full-unit tests、93 P3 focused tests、8 package-skeleton tests 与 28 个 integrated presentation lifecycle tests 收口。directive revision 36 已关闭 sibling-task prompt migration/read-back Gate，implementation stage 进入 **P4 real-project candidate dogfood**。但真实 FCC dogfood 随后暴露了新的 P0 可靠性缺陷：target-local `observer presentation-status` / `semantic-review-apply` 仍通过 full `build_observer_snapshot` 做校验，导致所有 worktree 的 Git/path facts 被重复采样；一次 FCC status 实测约 90 秒，并在 DevSpace 中返回仍在运行的 session handle。directive `dir-80ce80bfea524bfc9c43` 因此 supersede 当前 broad P4 扫描：先关闭 target-scoped read/session reliability，再恢复广泛 P4。该中断不回退 P1-P3，也不等于 WS012 long-lived mission 完成。

2026-09-02 directive revision 45 的 `dir-923a42f71b5a44a18447` 进一步把**当前已有 reliability WIP 的收口**设为唯一 P0，并收窄本次 immediate acceptance quota：先独立核验现有 WIP/provenance，再只对该 WIP 完成匹配的 focused tests、WS012 file-scoped guard、`git diff --check` 与自然 semantic checkpoint/commit；随后只执行 **一条**隔离 candidate `ACF_HOME` 的真实 FCC `target-set -> presentation-status -> semantic-review-apply` 最小链，任何 DevSpace `running=true/sessionId` 都必须持续 poll **同一 session** 到明确 terminal，并验证 no orphan descendant / no unknown session / no duplicate side effect。该最新 user authority supersede 早先“两条 P0 directive 需要重复多轮真实 FCC 采样后才可收口”的**采样数量要求**，但不放宽 bounded/fail-visible read、exact PID tree cleanup、stdout/stderr 分离、target source-fidelity、Git/continuation safety 或 installed-state issue-resolution Gate。若这一条最小链失败，只修复使本 P0 Gate 通过所需的最小根因，不扩展 broad P4；若通过并完成 checkpoint，则 resolve 当前 P0 steering，刷新 authority 后继续 PLAN 下一项。full/release validation 仍属于后续 release Gate，不被本次 focused closure evidence 替代。

当前默认执行顺序为：

1. target-local status/review 改为读取 fresh target-scoped fact projection；只对显式 target 相关 primary/bound worktree 做必要 Git facts，保留 exact target semantic source fingerprint、source divergence、target A/B isolation、continuation liveness/effect risk 与 fail-visible semantics。不得通过复用 stale canonical snapshot 换取速度。
2. regression 必须证明 target-local status/review 不再调用 full project snapshot，同时 target source drift 仍会改变 fingerprint、单 target drift 不污染 sibling target、source divergence 仍进入 semantic fingerprint。该 reusable defect 已登记 continuation issue `8cca72c511607c67f707`；candidate checkpoint 不等于 issue resolution，仍需经过 release/global install/installed-state dogfood 后才能关闭产品 issue。
3. supplemental directive `dir-3f925bb148c049588321` 已用第二次独立 FCC dogfood supersede “只有 scoped projection 仍慢才需要 timeout”的条件假设：新的隔离 `observer target-set C:\PROJECT\fcc_workspace ...` 在 fresh `ACF_HOME` 尚未产生任何文件前持续 non-terminal 超过 203 秒，且受控终止同一 DevSpace session 后确认阻塞位于 target-set 的 project resolution / Git discovery / Windows path resolution。故本 P0 修复**必须**包含 Observer-specific bounded、fail-visible 的 project/target-read execution boundary；不得给共享 `git_support.run_git` 全局强加 timeout。timeout 必须终止 exact worker PID/process tree，stdout JSON 与 stderr diagnostics 分离，失败不得伪造 fallback project/target facts。
4. 按 directive revision 45 的当前 P0 closure quota：先完成匹配的 focused validation、WS012 file-scoped guard、`git diff --check` 与 Git semantic checkpoint；再在隔离 candidate `ACF_HOME` 上只执行一条真实 FCC `target-set -> presentation-status -> semantic-review-apply` 最小链。每个 DevSpace session 均严格 poll 到 terminal，并显式验证 no orphan descendant、no unknown session、no duplicate side effect。该最小链与 checkpoint 通过后，可将 `dir-923a42f71b5a44a18447` 以及其已 supersede 采样数量要求的 `dir-80ce80bfea524bfc9c43` / `dir-3f925bb148c049588321` 一并按 evidence disposition 为 resolved，然后恢复 PLAN 下一项；若失败，只修复当前 Gate 所需最小根因。后续 full/release validation、release/global install 与 installed-state dogfood 仍按各自 Gate 独立执行。
5. Maintenance 的 candidate validation 只能作为明确标识的 product-under-test evidence；独立 Production Observer activation 继续是 Production freshness/acceptance 的唯一来源，普通 Maintenance wake 不通过 snapshot/interpret/narrative refresh 人为养鲜。
6. release preparation 先解决 immutable version identity collision：历史 `v0.0.3.84` 已绑定旧 merge commit，禁止 reuse/repoint/retag。generation 113 已开始把 candidate metadata 切换到 `0.0.3.85`；generation 114 在正式 recovery 后重新核验本地 tag、`origin` tag 与 PyPI exact-version endpoint，三处均确认 `v0.0.3.85` / `0.0.3.85` 当前未占用，因此 `.85` 可继续作为本次候选 identity。该结论仍只是 release-preparation evidence；必须先完成 metadata/provenance checkpoint 与正式 release Gate，之后才允许进入 merge/tag/publish/global install effect protocol。
7. 新 immutable stable release + global install 后再做 installed-state P1.5/P4/credential-transport/target-read reliability dogfood，并仅从包含全部变化的最新 stable Production Observer activations 重新计算 acceptance；单次 release/pass/checkpoint 不结束 WS012 Maintenance mission。

### 7.1 P1.5 live Scheduled Task family audit baseline（2026-08-31；2026-09-01 evidence correction）

2026-08-31 已形成一版 wrapper-family 迁移假设；2026-09-01 generation 78 曾因当时取得的 surface 证据不足，将 sibling family 降级为 repository/history 驱动的 provisional hypothesis。generation 79 对真实 scheduler inventory 再次取证后确认：当前 management surface **实际能够回读目标 task 的 live task identity 与完整 scheduler prompt 文本**，覆盖 ACF、FCC WS079/WS080/WS086 与 AStockT_AI Writer/Project Observer family；此前“除当前 activation 外 sibling raw prompt 均不可见”的表述被 supersede。与此同时，surface 仍未提供 executable `argv`/environment、installed ACF version、definition fingerprint 等底层 execution identity。因此后续 evidence 必须分层：`prompt-level live audit` 可以成立，但 `full executable-definition migration/read-back` 与 installed-state acceptance 仍不得凭空外推。

- **ACF WS012 Writer**：live prompt 为 aligned-but-heavy。exact existing-checkout、stable/candidate split、每轮 stable doctor/prompt、generated `prompt + execution_policy` 作为唯一 generic authority、directive/live steering、anti-masking 与 long-lived mission 均已具备；static wrapper 保留较多高显著性 bootstrap/safety procedure。后续只允许在不损失这些 authority 的前提下收敛，不能为了“thin wrapper”本身改写用户需求。
- **ACF Project Observer**：live prompt 已明确 Production Observer-only、`read broad / write narrow / control none`、stable doctor/prompt/status、禁止 Writer ownership/recovery、anti-masking、Project/Map Review 与北京时间展示，prompt-level common core **aligned**。
- **FCC WS079 Writer**：live prompt 已使用 exact existing checkout、stable ACF、doctor/prompt/generated authority，并保留项目专属 scheduler-reliability 约束；仍夹带部分可由 generated authority 动态提供的 generic timeout/challenge/claim procedure，属于 **mostly aligned / thinning candidate**。
- **FCC WS080 Writer**：live prompt 的 exact project/worktree 与 stable doctor/prompt 方向正确，但仍显式复制较完整 challenge → timeout → reconcile → recovery generic sequence，属于最明确的 **generic-state-machine thinning candidate**。
- **FCC WS086 Writer**：live prompt 已采用 stable/prompt-driven continuation 并保留 v5.8.0 soak 项目约束，但仍有部分 generic continuation mechanics 可下沉，属于 **mostly aligned / thinning candidate**。
- **AStockT_AI Writer**：live prompt 已具备 exact checkout、stable ACF、doctor/prompt 与项目专属 Task State/roadmap 约束，但 static wrapper 仍较厚并复制部分 generic continuation procedure，属于 **aligned-but-heavy / thinning candidate**。
- **AStockT_AI Project Observer**：live prompt 已保持 observer-only、stable/observer control plane 与 Writer ownership 分离，prompt-level common core **aligned**；项目专属 runtime/target 语义继续作为 extension 保留。

该 live audit **只证明 prompt text 层面的 contract delta**。当前 surface 尚不能同时给出 executable identity/version/fingerprint 与完整 mutation provenance，因此不能把 prompt inventory 直接升级为“safe migration 已完成”或“installed P1.5 pass”。当前 execution authority 允许 sibling task inventory/read-back，但本轮没有 sibling-task mutation authority；原位迁移必须在具备相应 mutation authority 的 same-task/interactive management context 中，先保存 exact current prompt/task identity，绑定 deterministic same-task update，再对同一 task 做 exact post-update read-back。任何 executable/version/fingerprint 缺失都以 fail-visible `runtime_owned_fallback` 记录。条件未完整满足时不创建 duplicate task、不伪造 migration pass，并继续可执行的其他 authority/validation work；若未来平台明确承诺这些字段而持续无法提供，再按 reusable issue 流程单独登记。

### 7.2 P1.5 per-family thinning delta（generation 79）

后续迁移不再笼统追求“wrapper 越短越好”，而是按 live prompt audit 固定 **keep / move-to-generated / preserve-extension** 三类差分；generic continuation ownership/recovery/effect/fencing/checkpoint/release procedure 只有在 stable generated `prompt + execution_policy` 需要时动态提供，static wrapper 不维护第二套状态机：

- **ACF WS012 Writer**：`keep` exact existing checkout、stable/candidate control-plane split、authority refresh、directive/live steering、anti-masking、Git/release safety 与 long-lived mission；只清理能够由 generated authority 完整替代的重复 generic mechanics。该 family 已 aligned-but-heavy，优先级低于明确复制状态机的旧 wrapper。
- **ACF Project Observer**：`keep` fixed canonical project、Production Observer-only、`read broad / write narrow / control none`、stable Observer surface、anti-masking、Map Review 与 UTC+08:00 human display；`forbid` Writer claim/recover/effect ownership。当前 prompt-level aligned，默认 no-op，除非 exact read-back 暴露真实 delta。
- **FCC WS079 Writer**：`preserve-extension` PetroSim / scheduler-reliability / exact workspace-project safety；`move-to-generated` generic timeout、challenge、claim/recovery mechanics。迁移后仍必须保留 WS079 项目专属可靠性边界，而不是机械套用 WS012 文本。
- **FCC WS080 Writer**：`preserve-extension` multiprocess/conflict/source-first/scientific safety 与 exact worktree identity；`move-to-generated` 当前 static wrapper 中较完整的 challenge → timeout → reconcile → recover generic sequence。该 family 是 prompt-level 最优先 thinning candidate。
- **FCC WS086 Writer**：`preserve-extension` v5.8.0 soak、LM/TR/Runtime/acceptance 与节点/科学证据边界；`move-to-generated` 通用 continuation ownership/recovery mechanics。当前 mostly aligned，避免误删 soak/acceptance authority。
- **AStockT_AI Writer**：`preserve-extension` exact project checkout、Task State/plugin/roadmap 与项目特异数据/执行约束；`move-to-generated` generic continuation state-machine procedure。该 family aligned-but-heavy，迁移目标是 common-core 收敛而非项目语义削薄。
- **AStockT_AI Project Observer**：`keep` observer-only、stable Observer/control-plane 与 Writer ownership 分离，保留项目专属 target/runtime 语义为 extension；当前 prompt-level aligned，默认 no-op。

执行 Gate 对所有 family 相同：先取得 exact current task identity + raw prompt，计算 deterministic delta；只有具备该 sibling task 的 mutation authority 时才允许原位 update；update 后必须对**同一 task** exact read-back 并证明 common core、project extension 与 role separation 均未退化。缺失 executable argv/environment/installed-version/fingerprint 时只记录 `runtime_owned_fallback`，不把 prompt-level pass 冒充 full executable-definition 或 installed-state acceptance。任何不能安全证明 no-op/idempotent 的修改都不执行，也不通过创建 duplicate task 绕过 Gate。

2026-09-01 本次真实 WS012 scheduled activation 已提供一条有效 **pre-P1.5/shared-core Writer dogfood evidence**：activation input 明确要求 exact existing checkout、stable ACF canonical control plane、doctor/prompt generated plan、directive supersession、anti-masking、continuous useful work 与 long-lived mission；generation 77 stale owner 经正式 challenge timeout → reconcile → recover 转移到 generation 78，证明 scheduled Writer 确实消费 stable-generated owner/recovery protocol，而不是 static wrapper 自行实现第二套状态机。但 stable/candidate 对照也证明这**还不能算 P1.5 installed-state pass**：global stable `.83` 的 `scheduler_wrapper_contract` 只有旧 v1 字段，不含 `wrapper_family/role/runtime_execution_policy_source/named_extension_slot/p15_required_bootstrap_topics/execution_evidence_fields/volatile_fields_not_static/checkpoint_commit_gate_are_stop`；worktree candidate `.84` 才暴露这些 P1.5 machine-contract 字段。因此当前 activation 只能证明 shared core 已真实工作，不能证明 production scheduled Agent 已消费新的 P1.5 product contract。P1.5 installed-state acceptance 必须等包含这些字段的**新 immutable stable release + global install**后重新 dogfood；该证据也不外推为其他 task family 已通过。

同一系列 activation 也继续界定 **current-stable v0.0.3.83 fenced credential transport** 的真实边界：global `acf --version` 确认 canonical stable 仍为 `.83`；generation 78 期间“不携带 raw credential 调用 protected command”确定性返回 `fence_token_required`，说明 fail-closed 行为正确。generation 79 在 authenticated challenge timeout + receipt-bound reconcile 后使用同一 stable `.83` 正式 `recover`，recover 响应在**同一 execution context**返回 fresh fence credential，随后 `assert-owner` 成功，因此“stable `.83` 下 fresh owner 一概无法继续 protected writes”的表述被 supersede。既有 credential-file transport repair 仍必须保留：它解决的是跨 execution-context / scheduler handoff 时避免复制 raw high-entropy token 的 secret-safe transport，而不是替代 same-session raw credential 协议。不得因此把未发布 candidate `.84` 用作 canonical continuation writer，也不得重放已取消的 `.84` publishing identity；下一 immutable stable release/global install 仍需完成 credential-file transport 的 installed-state scheduler dogfood后才能关闭该产品级 repair。

generation 78 进一步确认一个必须在任何 package/release Gate 前先消除的 **immutable version collision risk**：annotated `v0.0.3.84` 已绑定历史 release identity，而当前 WS012 branch 在该 tag 之后已经包含 P0/P1/P1.5 新代码，`pyproject.toml`/egg metadata 却仍声明 `0.0.3.84`。因此当前 branch **禁止执行会生成可发布 `.84` artifact 的 package/release build，更禁止 publish**；否则会形成“同一版本号、不同源码”的冲突制品。实时 `pip index versions ai-context-framework` 仍显示 PyPI latest=`0.0.3.83`、`.84/.85` 均未占用，Git 仅存在 `v0.0.3.84` tag。下一稳定候选必须先按 release authority 切换到一个高于 `.84` 且 Git/PyPI 双重未占用的 immutable identity（按当前连续版本最自然是 `.85`，但正式 identity 仍由 release Gate 确认），同步 version/README/CHANGELOG/package metadata 后才允许 package/full release check。当前 generation 78 因 stable `.83` credential blocker 无法新增 canonical workspace intent/checkpoint，因此不在未认证状态下擅自改 release metadata；先把该 collision 作为 fail-visible release precondition 固化到 authority。

继续遵守 anti-masking：普通 WS012 Maintenance wake 不为维持 Dashboard 或 Project Narrative 新鲜而主动调用 production `observer snapshot/interpret/narrative-apply`；任何 Production acceptance 仍只能来自独立 Production Observer activation。

### 7.3 P1.5 → P2/P3 Gate dependency correction（generation 80）

generation 80 对 current PLAN、WS012 Workstream 与 candidate code/tests 做了 dependency audit，确认旧表述存在一个真实 circular Gate：一边要求“P1.5 live migration + interactive presentation lifecycle acceptance 全部收口后才进入 P2”，另一边又明确把 semantic review / presentation-maintenance runtime 的实现放在 P2，并把 narrow derived presentation surface 放在 P3。当前仓库证据也与后一种分层一致：`ai_context_framework/automation_contracts.py` 与 `tests/test_automation_contracts.py` 已冻结 `transient_patch / one_shot_semantic_review / durable_rule` machine contract，但尚不存在可对三生命周期做真实 end-to-end runtime acceptance 的产品 surface。继续沿用旧串行 Gate 只会产生两种错误结果：要么永久空转等待一个必须在后续阶段实现的能力，要么伪造“runtime 已验收”。两者都违反 fail-visible 与 continuous-useful-work 原则。

因此 durable phase/Gate 语义纠正为：

1. **P1.5 structural exit-to-P2 Gate**：contract/docs/template/tests 已冻结并通过；真实 task-family prompt-level audit 与 per-family thinning delta 已形成；platform/mutation authority boundary 已 fail-visible；interactive lifecycle acceptance matrix 与 P2/P3 implementation ownership 已明确。满足这些条件即可继续 P2 内部产品实现，不需要等待当前 scheduled context 无权执行的 sibling-task mutation。
2. **P2 Gate**：实现并验证 semantic review / one-shot request / durable-rule state machine、consume/cleanup/supersede/withdraw、Map Review escalation 与 independent staleness。P2 不实现 immediate presentation-only DOM/derived patch surface。
3. **P3 Gate**：实现 immediate transient derived-presentation maintenance、presentation revision/fingerprint optimistic concurrency、deterministic re-render、semantic-change escalation；并与 P2 state semantics 联调，完成三生命周期 integrated acceptance。
4. **跨阶段 operational/release Gate**：sibling Writer wrapper 原位迁移仍是 mandatory acceptance，不被取消或降级；但它在具备相应 same-task/interactive mutation authority 时执行 exact-before → deterministic same-task update → exact-after read-back。当前 context 只能 inventory/read-back 时继续 fail-visible，不阻断独立 P2/P3 实现。P4 / release / installed-state acceptance 前必须收口该 Gate。
5. **最终 acceptance 不放宽**：P4/full release/global install 前，必须同时具备真实 wrapper migration/read-back、三生命周期 runtime acceptance、new immutable stable installed-state dogfood；最终 Production acceptance 仍只从包含全部变化的最新稳定安装态重新起算。

该 correction 是依赖关系去环，不是削减用户需求：所有原 acceptance 项仍保留，只把“合同冻结”“runtime 实现”“外部 task migration”“integrated acceptance”的先后关系放回各自可实现的阶段，避免 synthetic progress 与 scheduler busywork。

### 7.4 P2 semantic lifecycle checkpoint（generation 84）

P2 semantic lifecycle 已在 `3fcac2815ee12003e17963a1f59c3669b5de38fd` 形成产品 checkpoint。当前实现把 target-local semantic review、独立 source fingerprint/staleness、one-shot review request、durable presentation rule、Map Review escalation、target narrative、problem model、route-impact 与 cross-project transfer linkage 落到 user-level Observer derived state，并通过 exact target revision + exact target source fingerprint 做 fail-closed optimistic concurrency。one-shot 成功 review 后退出 active context并仅在 audit event 保留 terminal evidence；durable rule 支持 supersede/withdraw；map-relevant signal 强制 authority reread；`route_change|major_replan` 不允许被 `decision=unchanged` 掩盖；foreign-project handler 只允许记录 transfer reference，不取得 foreign control authority。

P2 Gate 的验证证据已经收口：generation 83 的 durable full-unit effect 经正式 stale-owner challenge → receipt-backed reconcile/recover 证明 **640 tests PASS**；generation 84 重新执行 P2/Observer/Target + automation-contract focused regression 共 **83 tests PASS**，package skeleton **8 tests PASS**，并通过 file-scoped WS012 guard、`acf check --strict`、template check 与 `git diff --check`。该 checkpoint 只证明 **P2 semantic state semantics 已实现并验证**，不冒充 P3 或跨阶段 acceptance：immediate `transient_patch`、presentation revision/fingerprint concurrency、deterministic re-render、Dashboard V2 展示整合和三生命周期 integrated acceptance 仍属于 P3；sibling Scheduled Task wrapper 原位 migration/read-back 仍是进入 P4 / release 前必须完成的并行 operational Gate；最新 immutable stable release/global install 后的 installed-state dogfood 与 Production acceptance 规则也完全不变。

因此当前 implementation stage 正式推进到 **P3**：先实现 narrow transient derived-presentation maintenance + deterministic re-render 与 semantic-risk escalation，再把 transient / one-shot / durable 三生命周期接入 Chinese human-first self-contained Dashboard V2 并完成 integrated acceptance；不得把 `3fcac281` 当作 WS012 long-lived mission 完成、release ready 或 installed-state acceptance。


### 7.5 P3 Dashboard V2 / three-lifecycle integrated acceptance checkpoint（generation 88）

P3 产品实现在 `0e2137f9af74a9dda38553814e168f17745ea5f3` 形成 checkpoint：Chinese human-first self-contained Dashboard V2、immediate transient derived-presentation maintenance、presentation revision/fingerprint optimistic concurrency、deterministic re-render 与 semantic-risk escalation 已落盘。该产品 checkpoint 的既有 terminal validation 为 **650 full-unit tests PASS、93 P3 focused tests PASS、8 package-skeleton tests PASS**，并通过 file-scoped WS012 guard、strict docs、template 与 `git diff --check`。generation 87 在提交该 checkpoint 后失去 heartbeat；generation 88 通过 authenticated challenge timeout `28272700-c2c0-4f74-8253-459ba8338f8b`、reconcile receipt `bf489b27-8bc9-4916-bbdc-849d2364fd0c` 与 receipt-bound recover 正式接管，未重放任何 terminal effect，当前 effects unresolved=0。

generation 88 随后对当前 `0e2137f9` candidate 重新执行 `tests.test_observer_presentation`，**28 tests PASS**。该 focused runtime/CLI regression 已覆盖并联调三类 presentation lifecycle：one-shot request 只由正式 semantic review 消费且不能再次消费；durable rule 跨 review 保持 active 并支持 supersede/withdraw；transient patch 必须绑定 exact presentation revision/fingerprint，stale view fail-closed，semantic-risk signal 强制升级到 Map Review；正式 semantic review 会使旧 transient patch 失效；transient apply/clear 通过 deterministic re-render 更新 canonical Dashboard，同时验证不创建新 Observer snapshot/run、不改写 canonical current snapshot/run history；Dashboard V2 同时验证 human-first story、transient emphasis 与 stale-target fail-visible；integrated lifecycle teardown 验证已消费 one-shot、已清理 transient、已 supersede/withdraw durable guidance 均不会 resurrection。该证据满足 P3 Gate 所要求的 **candidate runtime integrated acceptance**，但明确不冒充新 stable installed-state dogfood 或 Production Observer acceptance。

因此 **P3 internal product/runtime Gate 已完成**，当前下一硬 Gate 收敛为此前已 fail-visible 的 **sibling Scheduled Task same-task wrapper migration/read-back operational Gate**。当前 scheduled execution context 对 sibling families 仍只有 inventory/full-prompt read-back，没有安全 mutation authority；不得创建 duplicate task，也不得把 prompt-level audit 冒充 migration pass。进入 P4 real-project dogfood 前必须在具备对应 same-task/interactive mutation authority 的上下文中，对需要迁移的 Writer family 执行 `exact-before → deterministic same-task update → exact-after read-back`，并保留各 family 的 project/scientific/Runtime/security/validation extension。ACF Project Observer 与 AStockT_AI Project Observer 继续保持 prompt-level aligned/no-op，除非 exact read-back 暴露真实 delta。该 platform boundary 不取消 P4/release Gate，也不授权 Maintenance 通过 Observer refresh 人为补 freshness。

### 7.6 Directive 36 pre-P4 Gate closeout / P4 entry（generation 93）

2026-09-01 directive `dir-ea14a004f4ef4cf8a957` 提供了新的 operational authority：WS079、WS080、WS086、AStockT_AI 四个 enabled Writer Scheduled Task 已在具备合法 scheduler mutation authority 的 interactive context 中完成原位 migration。generation 93 不沿用这一结论作为未经验证的聊天历史，而是重新读取**当前 live task identity 与 full prompt**并对照 §7.2 matrix 独立复核。当前 read-back 结果为：四个 task 均保持原 task identity / enabled Writer role 与各自 exact project/worktree/task/plan identity；generic continuation claim/challenge/reconcile/recover/workspace/effect/fencing/checkpoint/release authority 已统一下沉到 stable `acf continuation prompt + execution_policy`；WS079 的 productization/scheduler-reliability、WS080 的 scientific/multiprocess/source-first、WS086 的 Swing/soak/Runtime/acceptance、AStockT_AI 的 project/roadmap/runtime/security/validation extension 均继续保留。没有发现要求再次 mutation 的具体 family delta，也没有创建 duplicate task。

因此 generation 88 末尾记录的“当前 scheduled execution context 无 sibling mutation authority，所以 P4 前必须继续等待”的状态已被 directive 36 + current exact read-back **满足并 supersede**。该历史段落保留为当时真实 evidence，但不再是 current next action。P1.5 prompt-migration/read-back operational Gate 现已关闭，WS012 正式进入 **Observer V2 P4 real-project candidate dogfood**。这只关闭 prompt-level migration Gate：management surface 仍不提供 executable `argv`/environment/installed-version/definition-fingerprint 的字段不得推断为已验证，P1.5 installed-state acceptance 仍必须等待包含 candidate contract 的新 immutable stable release + global install。

同轮再次独立确认 immutable release identity collision：worktree `pyproject.toml` 与 `uv run acf --version` 当前仍为 `0.0.3.84`，但 canonical Git `v0.0.3.84` 已绑定历史 merge commit `729e55b846ced89d70b3726eefa80be2595af572`，与当前 HEAD `250c0b3daa0542d78a230acd9ba17db5d73dd3d2` 不同。后续 P4 candidate dogfood 绑定 audited commit，不把 candidate 冒充 installed stable；任何正式 release preparation 前必须按实时 Git/tag/PyPI/release authority 选择新的未占用 identity，禁止 reuse、repoint 或 retag `v0.0.3.84`。

### 7.7 P4 target-read reliability interruption（generation 98）

真实 FCC P4 dogfood 证明 target-local presentation status/review 的旧实现存在 scope amplification：`observer_presentation.py` 为一个 target 的 source-fingerprint 校验调用 full `build_observer_snapshot`，而 full snapshot 为 project-level consistency 会连续 2–3 次采集所有 Observer-scope worktree/workstream/continuation facts。FCC worktree 数量较大时，一次 `presentation-status` 可持续约 90 秒；DevSpace 的约 10 秒 yield 会正确返回 `running=true/sessionId`，若 scheduler 把该 handle 误判为命令终态，就会遗弃仍运行的 descendant，并最终表现为 stale continuation owner。generation 93–97 的重复 stale/recovery 不能再当成“正常 healthy other-owner conflict”掩盖该产品/执行链问题。

generation 98 已将修复边界收敛到 `observer_target_projection.py`：先读取 explicit Target Registry 与 cheap continuation topology，再只为目标相关 primary/bound worktree 采集维持既有 source-authority/divergence 判定所需的 Git facts；`presentation-status` 对全部已注册 target 使用该 fresh scoped projection，`semantic-review-apply` 进一步只投影指定 target。该路径仍复用原 Workstream/continuation machine-state 与 `target_semantic_source_fingerprint` 语义，不复用 stale canonical current snapshot，也不改变 Production Observer full snapshot 的项目级一致性合同。focused regression 结构性禁止 target-local status/review 调用 full project snapshot，并验证单 target source drift 只改变自身 fingerprint、source divergence 继续参与 fingerprint。

本轮不直接给共享 `git_support.run_git` 增加全局 timeout：该函数服务 continuation/worktree/release 等非 Observer 控制面，未经独立错误合同与跨模块回归即改变 timeout 会制造更高风险。supplemental directive `dir-3f925bb148c049588321` 已证明即使 target-scoped status 快路径正常，`target-set` 的更早 project resolution/Git/path discovery 仍可单点无界阻塞，因此当前 authority 要求把既有 read semantics 封装进 **Observer-only bounded worker boundary**：parent 仅从 worker stdout 解析 machine JSON；超时按 exact worker PID scoped 终止 descendant；以明确 `observer_target_read_timeout` / read-failure 返回，不静默降级、不改变 canonical-root/worktree-registry truth，也不修改共享 `git_support.run_git` 的错误合同。该 boundary 必须覆盖 target-set 的 project resolve 与 presentation-status/semantic-review 的 target projection，随后再以重复真实 FCC terminal/no-orphan dogfood 收口。

generation 107 对 generation 106 的真实卡死现场完成了进一步归因并修正 bounded boundary：07:32 北京时间启动的隔离 FCC `target-set` 在 fresh `ACF_HOME` 仍为空的情况下持续 non-terminal 超过 55 分钟；现场进程树只剩 outer `uv/acf/python` 链，预期的 `observer_target_projection --worker` descendant 不存在，最内层 Python 只有单一 waiting thread。与此同时，同一 worktree 中 fresh import、FCC `resolve_status_location`、`discover_git_project`、普通 `resolve_observer_project` 以及真实 `resolve_observer_project_bounded` 均可在亚秒级 terminal。结合 Windows CPython `Popen.communicate()` 在 stdout/stderr pipe 模式下会先创建 reader threads，而卡死进程始终只有单线程，可将当前产品级根因收敛为：**原实现的 30 秒 timeout 只在 `subprocess.Popen(...)` 返回之后才生效，worker process creation 本身仍是无界边界**。generation 107 因此把 worker spawn 也纳入同一个总 deadline：`Popen` 在 daemon launch helper 中执行；若 launch 本身超过 deadline，outer CLI 立即 fail-visible；若迟到的 launch 在 cancellation 后才返回，则只按该 exact worker PID/process tree scoped cleanup，防止形成新 orphan。该修复不改变共享 Git timeout，也不降低 canonical fact fidelity。generation 106 已在 authenticated challenge timeout 后通过 receipt-bound reconcile/recover 正式交接到 generation 107，原 07:32 descendant 也已按已验证 top PID `51908` 做 scoped tree cleanup并确认相关 PID 全部 terminal。下一 Gate 仍是不变的 focused/full validation + Git checkpoint + 多轮真实 FCC `target-set -> presentation-status -> semantic-review-apply` terminal/no-orphan acceptance；在该 evidence 完整前，两条 P0 directive 与 issue `8cca72c511607c67f707` 均不得提前关闭。

generation 110 在 `57e842bd35b364937c46ce808e2cf28f3b3f1ad5` checkpoint 后按 revision 46 directive 的最小 quota 执行了一条新的隔离 FCC 链。`target-set` 与 `presentation-status` 分别约 1.2 秒与 3.7 秒 terminal，但 `semantic-review-apply` 再次在 fresh target revision/source fingerprint 上持续 non-terminal 超过 202 秒；同一 DevSpace session 经 scoped `Ctrl+C` 才 terminal，随后确认没有残留 candidate/worker descendant、stdout/stderr 均未形成 terminal payload，隔离 `ACF_HOME` 也未写入 semantic state。为了避免把写入逻辑或 source projection 误判成根因，generation 110 又执行了两组 no-write 诊断：同一 candidate Python 进程内的 bounded resolve + lock + target projection 约 2.4 秒，直接 `apply_semantic_review` 约 0.015 秒；而 fresh isolated `uv run acf ... semantic-review-apply --expected-target-revision 999` 可稳定复现 launcher hang。hang 现场在 deadline 前只存在 outer `uv -> acf.exe -> venv python -> base python`，**没有** `observer_target_projection --worker` child；deadline 后最内层 Python 收敛为单一 `Wait/Executive` thread 且仍不退出，证明 daemon-thread 包裹 `Popen(Python worker)` 虽能让调用线程超时，却不能保证 Windows endpoint/policy-inspected Python bootstrap 卡住时 outer process 真正 terminal。

因此 generation 110 的最小根因修复进一步把 Windows worker bootstrap 改为 **先创建系统 `cmd.exe` 作为 exact killable top worker PID，再由该进程启动 Python target-read worker**。parent 仍只解析 worker stdout JSON、stderr 独立诊断，并保留同一个总 deadline；若真正容易被 endpoint/policy 检查的 Python child bootstrap 卡住，parent 已经持有 `cmd.exe` 的 exact PID，可用既有 `taskkill /PID <pid> /T /F` scoped 清理整棵 worker tree，而不会再次陷入“Python CreateProcess 尚未返回所以没有 PID 可清理”的状态。该修复仍不修改共享 `git_support.run_git`。新增 Windows bootstrap regression 后，target-read focused tests 10/10 PASS；完整当前 P0 focused set 共 **100 tests PASS**。更关键的是，同一 fresh isolated `uv run acf semantic-review-apply --expected-target-revision 999` no-write 复现改造后约 3 秒明确 terminal，返回预期 `observer_presentation_revision_changed`，证明 outer CLI terminality 已恢复。下一步只需要为这一最小修复补 file-scoped guard / `git diff --check` / semantic checkpoint，然后用**全新**隔离 `ACF_HOME` 重跑 revision 46 要求的唯一真实 FCC 最小链；此前诊断 home 已被 direct diagnostic review 污染，不得作为 acceptance evidence。

随后真正的 fresh acceptance 证明仅靠 `cmd.exe` top launcher 仍不足以形成严格 terminality：`target-set` 与 `presentation-status` 正常 terminal 后，真实 `semantic-review-apply` 再次在约 20 秒现场只看到 outer `uv -> acf.exe -> venv python -> base python`，连预期的 top `cmd.exe ... observer_target_projection --worker` 都尚未出现；超过 30 秒仍 non-terminal，说明 Windows process creation **对系统 launcher 本身也可能在 `Popen` 返回前阻塞**。同 session 在约 58 秒 scoped `Ctrl+C` 后 terminal，隔离 home 仍只有 `targets.json`，且无残留 worker/orphan。该现场否定了“换一个更容易启动的 executable 就足够”的假设，也确认任何仅靠 Python helper thread 包裹 `Popen` 的方案都无法单独保证真实 console process 的 terminal boundary。

generation 110 因此补上最后一层 command-level fail-stop contract，而不是继续叠加 launcher 重试：Windows **真实 `acf` console entrypoint** 一旦得到 `observer_target_read_timeout`，command adapter 先输出并 flush 结构化 timeout payload，再用 `os._exit(exit_code)` 绕过已被现场证明可能 non-terminal 的解释器清理路径；programmatic/test `acf.main(...)` 不满足真实 console-entrypoint + OS-backed stream 条件，因此不会被 fail-stop。为避免 hard exit 遗留 derived-state lock，`semantic-review-apply` 的 fresh bounded target projection 同时前移到 `acquire_observer_lock` 之前；进入锁后只做输入校验、revision/source concurrency 校验和原子 derived-state write。该变化不放宽 source freshness：external target facts 本就不受 Observer derived-state lock 保护，`apply_semantic_review` 仍以刚刚读取的 exact source fingerprint 和 target revision 做拒绝式并发校验。新 regression 覆盖真实 Windows console timeout 的 `flush -> hard fail-stop`，当前 P0 focused set **101 tests PASS**，且 8 次连续 actual `uv run acf ... --expected-target-revision 999` no-write probe 均明确 terminal。下一步仍是先 checkpoint 这一最终 terminality fix，再用新的未污染隔离 home 执行 revision 46 唯一真实 FCC 最小链；只有该链 terminal + semantic state 成功写入 + post-run no-orphan/no-unknown/no-duplicate evidence 俱全，P0 steering 才可 resolve。

generation 110 最终 P0 closure acceptance 已在 commit `d351292b7eedd53b2c8bf03c207e63867136d5fe` 后通过。全新隔离 candidate `ACF_HOME=C:\Users\lenovo\AppData\Local\Temp\acf-ws012-p0-accept2-g110-1158` 上仅注册真实 FCC `fcc-ws079` target：`target-set` 约 **0.98 秒** terminal/exit 0，`presentation-status` 约 **3.17 秒** terminal/exit 0，并得到 target revision 0 与 source fingerprint `c23fd18c168e2719f3171b823140c49838e00feb4c3297cb5aea8f3bccd75126`；随后以 fresh authority reread、exact target revision/fingerprint 执行 `semantic-review-apply`，约 **3.07 秒** terminal/exit 0，写入 `semantic_review_applied`、state/target/semantic revision 1。紧接着同一隔离 home 的只读 `presentation-status` 明确返回 `semantic_status=current`、source fingerprint 不变。post-run process audit 未发现 candidate/`observer_target_projection --worker` descendant，隔离 runtime 只有预期的 `targets.json`、`presentation/events.jsonl`、`presentation/state.json`，无残留 lock；所有本轮 DevSpace session 均已跟踪到 terminal，stable continuation effects 仍为 unresolved=0，因此没有 unknown session 或 duplicate non-idempotent side effect。至此 directive revision 46 定义的**candidate P0 reliability closure Gate 已满足**，`dir-923a42f71b5a44a18447` 以及其 supersede 采样数量要求的 `dir-80ce80bfea524bfc9c43` / `dir-3f925bb148c049588321` 可以按 evidence resolve，随后 authority 恢复 **P4 real-project candidate dogfood**。这不等于 reusable product issue `8cca72c511607c67f707` 已关闭：该 issue 仍需新 immutable release、global install 与 installed-state dogfood 后才能 resolution；candidate evidence 也不得冒充独立 Production Observer acceptance。

P4 恢复后的首个跨项目 fidelity slice 又暴露了一个与 P0 terminality 不同的真实隔离问题：candidate 使用临时 `ACF_HOME` 时，Target Registry/presentation 确实被正确隔离，但 `capture_project_continuations()` 也随 `usage_project_dir()` 改读临时 home，导致 FCC `fcc-ws079/ws080/ws086` target 虽能读取真实 Workstream/Git/source-divergence，却错误显示 `continuations=[]` / execution idle，丢失 Writer stage/liveness/effect risk；stable canonical evidence 明确证明 WS079 generation 313 stale、WS080 task `ws080-fcc-mechanistic-hourly` waiting_external、WS086 task WS086 ready。该行为违反 P1.5/P4“隔离 candidate writable runtime但保留真实 Writer execution evidence”的 contract，且不能通过复制/伪造 `~/.acf` JSON 修复。

generation 110 因此新增窄范围 **Observer-only read-home split**：默认行为完全不变；只有显式 `ACF_OBSERVER_CONTINUATION_READ_HOME=<existing absolute canonical home>` 时，Observer continuation projection 从该 home 只读，Observer Target Registry/presentation/snapshot/dashboard 仍写当前隔离 `ACF_HOME`。override 不存在、相对或非目录时 fail-visible，并且实现路径不创建、不迁移、不写 read home。unit/integration regression 已覆盖 separate-home continuation read、runtime write isolation、read-home bytes 不变与 invalid override no-create。真实 FCC fresh candidate dogfood 同时修正 WS080 continuation task-id 为 `ws080-fcc-mechanistic-hourly`；设置 isolated `ACF_HOME` + canonical read home 后，三个 target 均恢复真实 continuation evidence：WS079 continuation_count=1/stale generation313，WS080 continuation_count=1/waiting_external，WS086 target continuation_count=1/ready，source-divergence 仍 fail-visible。下一步先完成该 split 的 focused validation、docs/guard/`git diff --check` 与 semantic checkpoint，再继续 P4 target semantic review / run-evidence / presentation lifecycle；不得把这一 candidate capability冒充 installed-state 或 Production acceptance。

`db4a290f58b85d8a1c7a4a52d00a0e878f9f31c6` 已把上述 read-home split checkpoint；后续 fresh FCC P4 slice 又把 execution fidelity 向前推进了一层。当前隔离 runtime `acf-ws012-p4-fcc-canonical-read-g110-1215` 保持 Project Overview=`disabled`，原因来自 fresh `Task_Plan.md`：FCC 当前是 `GlobalOnly / Paused`，WS079/WS080/WS086 是相互独立的 scheduled Writer routes，强行生成统一 project mainline 会误导。Target Registry 进一步纠正了 WS086：旧 registration 的 `continuation_task_id=WS086` 只命中 2026-08-18 的历史 ready task；canonical continuation inventory/doctor 证明当前合法 task 是 `WS086-hourly-continuation`、generation 260、status=`paused`、stage=`PAUSED (awaiting user manual S180 execution)`，因此 registry 已改为该 task-id，presentation source fingerprint 也随之更新。与此同时 WS079 在同一 canonical read-home 上已自然推进到 generation 314 / liveness=fresh / `Stage-FLOWOPT-VECTOR-INIT-H1`，WS080 仍为 generation 262 / `waiting_external`。这一 slice 验证了 Target Registry 必须按真实 continuation task identity 呈现 Writer execution，而不能只按 Workstream id 猜测旧 task。

同一 slice 已完成两条 target-local semantic lifecycle：`fcc-ws079` review `ws012-g110-p4-ws079` 写入 semantic revision 1/current，明确呈现 generation 314 fresh Writer、当前 read-only FlowSheetOptimiser Gate 与 authority source-divergence warning；`fcc-ws080` review `ws012-g110-p4-ws080` 写入 semantic revision 1/current，明确区分 Workstream lifecycle=Active 与 continuation execution=`waiting_external`，并把“等待 materially new independent evidence/capability”记录为 expected external blocking problem，同时继续暴露 source divergence。`fcc-ws086` 尚未写入 semantic state，原因不是 target-read correctness 失败：一次 direct candidate invocation 在任何 `observer_target_projection --worker` child 出现前即 non-terminal，现场仅见 `pwsh -> venv python redirector -> base python`，最内层 Python 只有 1 个 `Wait/Executive` thread、CPU≈0.016s；同 session 78s 后 scoped `Ctrl+C` terminal，post-run no orphan、semantic target revision 仍为 0。对照 20 次纯 `uv run python -c print(...)` 启动均 89–186ms，以及同一已启动 Python 进程内 20 次 `resolve_observer_project_bounded + build_observer_target_views_bounded(fcc-ws080)` 全部约 1.98–2.83s/成功，可确认当前证据**不支持再次把它归因为 target projection 的持续性能回归**；该单次现场更接近 Windows/endpoint 下 Python bootstrap/import 前置阻塞，而且发生在 ACF worker/thread 创建之前。按 anti-busywork contract，本 wake 不重复轰炸 WS086 semantic side effect；保留 `not_reviewed` 作为 fail-visible incomplete P4 evidence，后续仅在新的 terminal execution opportunity 下补齐。

本轮还观测到 candidate entrypoint 的环境敏感性：一条 `uv run acf` WS079 semantic invocation 在无 side effect 的情况下 non-terminal 67s 后才由同 session scoped `Ctrl+C` 结束，而相同输入通过已启动的 candidate Python `cli.main(...)` 在约 3.2s terminal 成功；WS080 随后也通过 direct worktree venv Python 在约 2.8s terminal 成功。这里不能把“某个 candidate launcher 偶发 non-terminal”冒充 ACF installed-state 失败，也不能把成功的 direct-Python candidate evidence冒充 canonical Windows `acf.cmd` acceptance；真正 installed-state Windows CMD contract 仍必须在新 immutable release + global install 后独立重跑。当前 P4 可继续使用隔离 runtime 验证语义/路由/问题模型，但必须保留每个 DevSpace session 的 terminal/no-orphan 证据，并在任何新的 non-terminal 前置 bootstrap 现场出现时停止重复 side effect、优先分类 provenance。

AStockT_AI 在本 `@DevSpace Local` 主机上当前 `E:\PROJECT\AStockT_AI` 不存在，因此本 slice 没有伪造该 target 的 P4 evidence；它仍属于 P4 required target family，待可访问对应项目的合法环境后补齐。reusable issue `8cca72c511607c67f707` 继续保持 open，直到新 immutable release、global install 与 installed-state target-read/CMD dogfood 完成；上述 candidate semantic 与 read-home evidence均不满足该 resolution Gate，也不替代独立 Production Observer acceptance。

同轮 ACF/WS012 自身 target dogfood进一步确认了“read fidelity 已恢复、但个别 candidate Python bootstrap 仍可能前置卡住”的边界。fresh isolated runtime `acf-ws012-p4-acf-canonical-read-g110-1238` 通过 `ACF_OBSERVER_CONTINUATION_READ_HOME=C:\Users\lenovo\.acf` 正确读取 canonical generation110 continuation：status=running、stage=P4、lease fresh、effects unresolved=0，并保留 WS012 registry=`merged` / Workstream lifecycle=`Merging` / machine health warning 的 registry-lifecycle mismatch；target-set 与 presentation-status 均在约 1–3s terminal。随后一次 `acf-ws012` semantic review 在任何 `observer_target_projection --worker` child 出现前陷入与 WS086 相同的 pre-worker wait：现场仅 `pwsh -> venv python redirector -> base python`，最内层 Python 1 个 waiting thread；同 session 经 scoped `Ctrl+C` 在约 59s 明确 terminal，post-run no orphan、隔离 runtime 仍只有 `targets.json`，semantic target revision 保持 0/not_reviewed。该证据进一步表明当前 incomplete P4 slice 是 candidate Python process/bootstrap 环境敏感性，而不是 ACF/FCC target-read source projection 的持续性能/正确性回归；因此本 wake 不重复 semantic side effect。后续在新的可终态进程机会中再补 ACF/WS012 与 WS086 semantic lifecycle，并把任何 installed Windows CMD 结论保留到新 immutable release/global install 后的独立 installed-state dogfood。

P4 real-project presentation-maintenance lifecycle 也已在同一 FCC isolated runtime完成一条非破坏性 durable-rule round-trip：对 semantic-current 的 `fcc-ws079` 以 deterministic rule-id `ws012-g110-p4-source-divergence-rule` 添加“source divergence 必须保持突出”的 target-local presentation rule，command terminal/exit0，target revision 1→2，status 明确显示 rule active 且 semantic 仍 current；随即以 expected target revision 2 做正式 withdraw，command terminal/exit0，target revision 2→3，rule audit history 保留为 withdrawn、active rule 清空，没有在 candidate runtime 留下人为长期 presentation policy。该 round-trip 只写隔离 Observer derived state，不修改 FCC 项目/Writer control state，并补齐 P4 对 durable presentation lifecycle 的真实项目 evidence；one-shot semantic request/consume 路径本 wake 不继续，因为它依赖再次 semantic write，而当前 ACF/WS086 已有 pre-worker bootstrap incomplete 证据，继续重复同类 side effect 不符合 anti-busywork contract。

generation 114 在 `v0.0.3.85` release-preparation recovery 后取得了新的 release Gate 证据：generation 113 的 authenticated challenge 超时且无 ACK，进程审计确认没有遗留 WS012/target-projection descendant，HEAD 保持 `0c9893d31056dddbee752e9f25963187bf801da4`、effects unresolved=0，因此通过 receipt `027b7393-4f48-4376-938b-4f5fa552223e` 正式 recover 到 generation 114，并保留已审计的 `.85` metadata WIP。随后 focused package/install Gate 首次真实暴露 `ai_context_framework/observer.py=2025` 超过 repository 2000-line reviewability 上限；该失败不是 external wait，也不是应重复轰炸的已知 bootstrap lane，因此作为 release-readiness alternative lane 立即修复：把 Observer self-health status payload builder 移到现有 storage module，保持行为/API 调用语义不变，同时把 `observer.py` / `observer_storage.py` 分别收敛到 1998 / 1975 行。修复后 package-skeleton + install-script + Observer CLI focused regression 共 **56 tests PASS**；template check、`docs/ai --strict`、WS012 file-scoped guard 与 `git diff --check` 均 PASS。该证据只关闭当前 metadata/provenance + module-size focused Gate，正式 full release check / upgrade matrix / artifact smoke 仍须独立执行。

2026-09-03 `v0.0.3.85` 已被外部 durable authority 独立确认完成 merge/tag/push、GitHub trusted publishing、PyPI publication 与 global `acf.cmd` install；随后约 10:30 +08:00 出现新的 **user-level ACF state-loss incident**，`C:\Users\lenovo\.acf` 的 filesystem CreationTime 变为 `2026-09-03 10:30:43`，WS012/WS079/WS080/WS086 等 long-running continuation namespace 均从该时间点后重新初始化/恢复，旧 WS012 round/effect/directive/Observer/authorization runtime 无法从 canonical user state 恢复。该事实改变 release 后 dogfood authority：禁止因为 journal 丢失而重放任何 `.85` 前 external effect；installed-state 与 Production acceptance 必须从 recovered baseline 重新建立，旧 acceptance 不拼接。WS012 recovery generation 1 后续自身失去 heartbeat，generation 2 仅在 authenticated coordination challenge `39abb9fd-901e-499a-bd66-62da940b4d09` 超时、workspace/HEAD=`2caa8337ff0b73db3bce65caec0c80a2e517f23c` 与 effects unresolved=0 被 receipt `5ffecb9d-a7fa-4516-a8f1-14a0cd515410` reconcile 为 eligible 后才正式 recover，避免把 stale lease 当作活 owner 或直接偷锁。Production Observer 已独立恢复 post-loss activation 与 fresh snapshot/dashboard，但显式 Target Registry 曾被清空；Maintenance 只通过 installed stable `observer target-set` 恢复 `ws012-writer` registration，不执行 snapshot/interpret/narrative/render，因此不能用 Maintenance 写入人为制造 acceptance freshness，下一次独立 Production activation 才是新的 acceptance 候选样本。

同一 incident 的 root deleting process 目前**未证明**：PowerShell interactive history、PowerShell Operational log 与 Security 4688 在事故窗口均未提供删除命令/进程证据，不能把猜测写成 root cause。但源码审计独立确认了一个真实、可复用的 state-integrity hazard：`ensure_clean_target()` 对 `acf init ... --force` / `acf simplify ... --force` 可对任意 target 直接 `shutil.rmtree()`，此前没有 active `ACF_HOME` overlap protection。该风险已登记 high issue `fe35056d9392b95206b7`，并在 post-.85 candidate 中增加 `acf_home_target_protected` fail-closed guard：target 与当前 `ACF_HOME` 相等、位于其内部或作为其祖先时均拒绝 destructive context replacement；focused init/simplify regression 已验证 exact/inside/ancestor 三类 path 均保留 sentinel state。这个 fix 是 containment hardening，不宣称已证明它就是 10:30 删除的触发源；issue 需等后续 immutable release/global install 的 installed-state guard dogfood 与 deletion-origin investigation 收口/明确边界后再 resolution。

generation 14 在 generation 13 authenticated challenge `b2b0c50c-75f5-47f9-98fa-f4cf1f672058` 超时且无 ACK 后，以 fresh stable doctor 证明 HEAD=`54498042a04cdd8b7d550386d63fb1db8259c2a6`、workspace 无 conflict/unclassified path、effects unresolved=0，并通过 reconcile receipt `88c1fe6c-84d2-435a-8440-39a98edafa53` / recovery `c4a2f673-99a0-45dc-89be-eb50618702a7` 正式接管。P0 deletion-origin 调查随后完成一次新的 repository-wide destructive-sink narrowing：ACF 产品代码中可递归删除目录的 production sink 只剩 `ensure_clean_target()` 的任意 target replacement，以及 `worktree_resilient_merge.py` 中严格锚定 `<git-common-dir>/acf/quarantine/<operation-id>` 的 exact quarantine cleanup；install/update PowerShell 仅删除 ACF tool-bin 内同目录 launcher/临时 cmd，未发现任何 in-repo scheduler/helper 会把 `init/simplify --force` 的 target 指向 user-level `ACF_HOME`。因此 2026-09-03 10:30 的**具体 deleting actor 仍无直接取证**，但可执行根因类别已被缩窄为“installed ACF 暴露的 arbitrary-target destructive context replacement primitive”，而不是未界定的通用 filesystem cleanup：既有隔离 dogfood 已直接复现 stable `v0.0.3.85` 对 isolated self-target `ACF_HOME` 删除 sentinel，candidate `v0.0.3.86` 在同一路径以 `acf_home_target_protected` fail-closed 并保留 sentinel。当前新增验证再次通过 ACF_HOME guard 4/4、workspace recovery 2/2、Windows install-script 4/4，以及完整 `tests.test_continuation_cli` **113/113 PASS**；`v0.0.3.86` 本地/origin tag 仍均不存在，global stable 仍是 `v0.0.3.85`。这组证据满足“危险 ACF-controlled destructive path 可复现 + root-cause class 足够具体”的定位边界，但不冒充实际 10:30 actor 证据；`dir-1105814139ca415ea966` 在新 immutable release/global install/installed-state self-target guard 与 canonical Windows launcher dogfood 完成前继续保持 pending。当前最高价值后续动作因此从无证据追凶切回 `.86` clean candidate/release discipline，并在 installed-state Gate 后再决定 directive/相关 issue 的 terminal disposition。
