# Tool Gap Review 2026-06-08

本文件记录一次基于外部工具官方资料、第一性原理和本仓库 dogfooding 现状的 ACF 问题梳理。它是候选问题和方向，不替代 [Top_Level_Implementation_Gap.md](Top_Level_Implementation_Gap.md)、[Product_Roadmap.md](Product_Roadmap.md) 或当前任务计划。

---

## 状态

Draft

---

## 摘要

ACF 当前结构检查、doctor 和模块化主链路已经稳定，但从真实使用角度看，主要问题已经从“能不能维护 Markdown 上下文”转向“如何降低安装摩擦、读取选择成本、多 agent 协作成本、跨工具重复配置成本，以及如何把使用日志转成可复现评测”。

---

## 调研依据

本轮只采用官方或一手资料作为外部参照：

1. [Claude Code memory](https://code.claude.com/docs/en/memory)：CLAUDE.md、path-scoped rules、auto memory、/memory 审计入口。
2. [Cursor Rules](https://docs.cursor.com/context/rules)：Always / Auto Attached / Agent Requested / Manual rule 类型、`.cursor/rules`、AGENTS.md 支持和 Memories。
3. [Cline Memory Bank](https://docs.cline.bot/features/memory-bank)：分层 Markdown 记忆、activeContext / progress、/newtask / /smol 和上下文压缩。
4. [aider repository map](https://aider.chat/docs/repomap.html)：用符号级 repo map 在 token budget 内提供全仓库结构感。
5. [aider conventions](https://aider.chat/docs/usage/conventions.html)：用 read-only conventions 文件稳定编码偏好。
6. [MCP server concepts](https://modelcontextprotocol.io/docs/learn/server-concepts)：Tools / Resources / Prompts 的分层、用户批准、activity logs 和 resource discovery。
7. [OpenAI Codex introduction](https://openai.com/index/introducing-codex/) 与 [Codex GA](https://openai.com/index/codex-now-generally-available/)：并行云任务、隔离环境、PR / review / CI 集成。
8. [OpenAI self-improving tax agents with Codex](https://openai.com/index/building-self-improving-tax-agents-with-codex/)：用生产 trace、只读证据、目标 eval 和 reusable skills/docs 形成改进闭环。

---

## 当前基线

已验证事实：

1. `acf doctor docs/ai --json` 当前返回 clean：无 findings，`check.ok=true`。
2. `acf check --strict` 和 `acf check template` 已通过；模板占位符 warning 属于预期。
3. `v0.0.3.49` 已完成 package 化，`acf.py` 是兼容 shim，console script 指向 `ai_context_framework.cli:main`。
4. 当前已有 `review stale`、`audit context`、`doctor`、`curate draft`、`workstream`、`feedback`、`human`、`log` 和 sync MVP。

因此下列问题不是当前上下文损坏，而是产品能力、安装体验、评测闭环和多工具生态的候选 gap。

---

## 第一性原理

AI 上下文工具的核心任务不是“保存更多信息”，而是：

1. 在正确时间暴露正确上下文。
2. 让写入路径有唯一权威位置。
3. 让可机械判断的问题自动检查或修复。
4. 让需要语义判断的问题进入可审阅草案。
5. 让多个 agent 或多个会话不会互相踩状态。
6. 让真实使用产生可复现的改进证据。
7. 让工具链安装、入口和跨工具配置足够低摩擦。

ACF 的强项在 2、3、4；当前主要缺口在 1、5、6、7。

---

## 问题清单

| ID | 问题 | 证据 / 推理 | 影响 | 候选方向 | 优先级 |
|---|---|---|---|---|---|
| G001 | 安装和本地环境健康诊断不足 | 本轮 `uv run acf` 被 uv cache lock 和 `.venv/Scripts/acf.exe` 权限拒绝阻塞；旧 `build/` 目录 ACL 也会影响 `pip install .`。这类问题不属于 context check。 | 用户会误以为 CLI 坏了，或不知道该清 cache、换入口还是重装工具。 | 增加 `acf doctor install` 或 `acf env doctor` 只读诊断：版本、console script、template data、uv cache/venv/script 权限、ignored build 目录、推荐恢复步骤。 | P1 |
| G002 | 安装态回归测试仍是补丁状态 | 当前新增测试验证安装后的 console script 可在源码树外 init/status，但还未纳入正式提交。 | package 化后最容易坏的是安装态路径和 data-files；源码入口测试无法覆盖。 | 合并安装态测试；若 full unittest 过慢，拆到 `tests/test_install_smoke.py` 或 smoke runner，但不要丢失安装态覆盖。 | P1 |
| G003 | 缺少“本次任务应读取什么”的自动 context pack | ACF 依赖 AGENTS 默认顺序、Current_Task 输入材料和人工判断；Claude/Cursor/Cline/aider 都在减少默认上下文、按路径或结构选择上下文。 | 新 agent 仍可能读太多或读错文件；复杂任务前置成本高。 | 新增只读 `acf context pack [target] --goal ... --files ... --json`：输出推荐读取清单、原因、路径、估算行数/token、是否默认读。先做建议，不自动注入。 | P1 |
| G004 | 缺少 path-scoped rules / resource discovery 的 ACF 原生表达 | Cursor / Claude 都支持按 glob 或目录触发规则；MCP 把 read-only resources 和 action tools 分层。ACF 当前 rules 是 always/requested/manual，但没有文件路径触发矩阵。 | 大仓库和 monorepo 中规则噪声会变高，agent 需要人工知道该读哪个规则。 | 在 rules index 或 rule front matter 中增加可选 `paths` / `applies_to`，先让 `acf check` 校验路径和 `acf context pack` 推荐，不改变默认 AGENTS 行为。 | P1 |
| G005 | Workstream 命令能力强，但多 agent UX 仍重 | F019 已记录“多个 agents 同时处理多个任务和多个 workstream 要更顺手”；当前命令多、状态多、人工需要知道何时 guard/sync/ready/archive。 | 并行场景下流程正确但摩擦大，容易漏 guard、漏 merge request 或状态推进。 | 增加 `acf workstream next-actions` / `dashboard --json` 增强：按每条 WS 给出下一条安全命令、阻塞原因、冲突文件、批量 guard/sync 建议。 | P1 |
| G006 | 跨工具指令文件重复维护 | Claude 建议用 CLAUDE.md import AGENTS.md；Cursor 支持 AGENTS.md 但更强能力在 `.cursor/rules`；aider 用 read-only conventions。ACF 当前只生成 AGENTS 两层入口。 | 用户同时用 Codex、Claude Code、Cursor、Cline、aider 时，需要维护多份近似说明。 | 提供 `acf export tool-config claude|cursor|cline|aider --dry-run`，生成导入 AGENTS 的薄 shim 或规则映射草案，不把 tool-specific 文件变成权威事实源。 | P2 |
| G007 | 没有 MCP adapter，CLI 难被工具以 Resources / Prompts 方式发现 | MCP 明确区分 tools、resources、prompts。ACF 现在是 CLI，人类和 agent 需要记命令；外部 agent 不能自然枚举“可读上下文资源”。 | 集成门槛高，尤其是 IDE/agent 平台无法直接把 ACF 当 resource provider。 | 后置设计可选 `acf mcp` 或独立 adapter：resources 暴露 active/reference 索引，prompts 暴露维护流程，tools 只包装安全命令。保持可选，不新增核心运行时依赖。 | P2 |
| G008 | 使用日志还没有形成 eval / fixture 闭环 | `acf log` 已能记录 usage event，OpenAI Codex 资料强调从 trace、只读证据、targeted evals 和 reusable docs 形成改进闭环。ACF 日志目前主要用于排障和统计。 | 真实摩擦难转成回归测试，问题会重复靠人工记忆。 | 增加 `acf log suggest-fixtures` 或手册流程：从失败事件、doctor findings、用户反馈生成 candidate fixture / worklog draft。先出草案，不自动写测试。 | P2 |
| G009 | Memory / Knowledge 晋升链路仍偏人工 | Claude auto memory 和 Cline Memory Bank 都提供“会话后保留有用经验”的路径。ACF 有 Knowledge draft、human、feedback、worklog，但缺少发现重复模式的提示。 | 同类纠错可能反复出现，AI 需要靠人提醒把经验沉淀。 | `acf memory review` 或扩展 `doctor`：扫描近期 feedback/human/log/worklog，提出 Knowledge draft 候选。只生成草案。 | P2 |
| G010 | repo 结构地图仍是手写 reference，不是自动 orientation cache | aider repo map 证明符号级结构摘要能帮助 agent 判断该读哪些文件。ACF 目前有 [Codebase_Structure.md](Codebase_Structure.md)，但需人工更新。 | 模块化后结构变化会让 agent 读错入口；手写结构地图容易过期。 | 增加 `acf code-map --json|--markdown`，用 Python AST/文件树生成轻量模块地图；不引入第三方依赖，先仅覆盖 Python 包。 | P2 |
| G011 | 数据 / source lineage 仍是弱规则 | doctor 已能报告本地 path/hash 证据，但 Sources_Index 仍偏人工表格。 | 数据分析类项目中“哪个数据源、哪个副本、哪个 hash、哪个产物”仍容易漂移。 | 增加可选 `source hash/update/check`，把 hash、generated_at、derived_from 写到 source index 或 sidecar marker；语义解释仍走 draft。 | P2 |
| G012 | 时间戳格式未工具化 | F017 已 Triaged。当前审阅标记仍是日期级，部分“上次更新”字段手写。 | 多 agent 并行和长期维护时，日期级信息不足以判断先后顺序。 | 设计统一 `YYYY-MM-DD HH:mm TZ` 或 ISO minute 格式；让 `review/curate/new worklog` 生成，不要求 AI 手写。 | P2 |
| G013 | error_code 和恢复手册不够系统 | JSON contract 存在，但没有完整错误目录、恢复路径和“哪些错误可自动 retry”。 | AI 能解析 error_code，但不知道下一步是否安全执行。 | 生成候选错误目录文档，由测试或常量驱动，列出 error_code、含义、常见原因、可重试性、恢复命令。 | P2 |
| G014 | authority / threshold 配置仍较硬编码 | 当前严格保持低复杂度是合理的；但不同项目可能需要不同 authority path、active 过厚阈值、规则触发范围。 | 真实项目扩展时，要么误伤，要么只能改代码。 | 后置评估极小 `acf.config.json` 或 Markdown config section；只配置阈值和路径，不引入通用策略语言。 | P3 |
| G015 | 生成元数据和源码事实边界仍容易混淆 | 本轮尝试 `uv --no-cache run` 触发 egg-info stat 变化；README 改动也可能让 tracked PKG-INFO 镜像概念变得模糊。 | 开发者可能误提交构建副产物，或不知道 egg-info 哪些字段是权威。 | 明确 egg-info 只作为版本同步兼容元数据，或评估停止跟踪部分生成元数据；先写规则，不急改打包结构。 | P3 |

---

## 严格复审补充

本节来自多视角只读审阅和本地命令复核，写法刻意保持通俗。这里的“已验证”表示本轮用命令或文件内容确认过；“候选风险”表示当前设计或流程上存在明显风险，但还需要单独设计或测试。

### 已验证问题

1. **默认 Context 里还有旧本机路径。**
   - 证据：[active/Context.md](../active/Context.md) 的“当前相关路径”仍写 `E:\Codes\Tools\ai-context-framework`，但 `acf status` 识别当前项目根为 `D:\qiudong\Projects\ai-context-framework`。
   - 为什么重要：AI 或用户可能照旧路径执行命令，直接跑错目录。
   - 建议：active 当前事实尽量不用个人绝对路径；必须记录时由工具生成或让 doctor 检查路径是否与 `acf status` 一致。

2. **Feedback_Inbox 有“计划中但计划不存在”的条目。**
   - 证据：F015 / F016 写着已进入 [active/Task_Plan.md](../active/Task_Plan.md) 的 T001/T004/T002，但当前 Task_Plan 是 Empty；`review stale` 也报告 F015/F016/F017 已陈旧。
   - 为什么重要：人和 AI 会以为这些需求已有计划，实际没有落点，容易长期悬空。
   - 建议：把已完成的条目标 Done，有待处理的降回 Triaged 或重新建任务；给 doctor 增加“Planned feedback 是否真的有计划/任务/草案证据”的检查。

3. **Feedback_Inbox 已完成条目太多，active 层像历史账本。**
   - 证据：`acf feedback archive-candidates docs/ai --json` 显示 15 条 Done 可归档；文件自身规则要求 Done/Rejected 超过 10 条时应整理归档。
   - 为什么重要：当前信号会被历史已完成事项淹没。
   - 建议：按月份归档 Done 条目；后续让 dashboard 或 doctor 提醒“active feedback 过厚”。

4. **`doctor clean` 容易被误解成“上下文完全没问题”。**
   - 证据：`acf doctor docs/ai --json` clean，但 `acf review stale docs/ai --json` 仍报告 3 条 stale feedback 和 1 个陈旧 Knowledge draft。
   - 为什么重要：结构健康不等于当前事实新鲜；用户只跑 doctor 会漏掉悬空事项。
   - 建议：doctor 的 summary 或 next_actions 明确提示 stale review；文档里区分 doctor、review stale、audit context 的用途。

5. **README 和手册里的个人路径示例容易复制失败。**
   - 证据：README 安装示例仍写 `E:\Codes\Tools\ai-context-framework` 和 `/mnt/e/Codes/Tools/ai-context-framework`。
   - 为什么重要：新用户复制命令会直接失败；本机路径也会很快过期。
   - 建议：统一改成 `cd <ai-context-framework 仓库根目录>` 或“进入本仓库根目录”。

6. **版本号示例使用旧真实版本，容易误复制。**
   - 证据：dogfooding 手册示例还有 `v0.0.3.30`，模板手册示例还有 `v0.0.3.25`。
   - 为什么重要：用户复制后可能预览或执行错误的版本设置。
   - 建议：示例统一用 `vX.Y.Z`、`v0.0.3.NEXT` 或“目标版本号”，避免真实旧版本。

### 候选风险

1. **README 更像发布说明，不像新手入口。**
   - 为什么重要：用户还没知道怎么开始，就先看到 Workstream、doctor、marker、sync 等内部概念。
   - 建议：README 顶部改成“这是什么、5 分钟怎么开始、出问题跑什么命令”；版本亮点移到后面。

2. **常用命令太多，用户不知道先用哪几个。**
   - 为什么重要：命令越多越需要入口导览，否则用户会在 check / audit / doctor / curate / workstream 之间迷路。
   - 建议：增加 `acf next` 或增强 `status`，给 1-3 条下一步命令；文档分成日常、排障、高级三层。

3. **推荐安装方式没有被自动测到。**
   - 为什么重要：README 推荐 `uv tool install .`，但新增回归测试覆盖的是 `pip install` 到临时 venv，不是 uv tool 链路。
   - 建议：发布前增加 `uv tool install --reinstall .` smoke；普通单元测试可保留较轻的 pip 安装测试。

4. **安装态测试可能依赖网络或构建缓存。**
   - 为什么重要：`pyproject.toml` 需要 `setuptools>=61`；干净离线 CI 中 `pip install` 可能要拉构建依赖。
   - 建议：把完整安装链路放到 integration/release check；或在 CI 中显式准备 build dependency。

5. **缺少 CI 或统一 release check，发布门禁靠人记。**
   - 为什么重要：template check、strict check、unittest、minimal smoke、upgrade matrix、wheel smoke 任一漏跑都可能放出坏包。
   - 建议：增加最小 CI 或 `scripts/release_check.py`，至少覆盖 Windows + Linux、Python 3.10/3.12、源码入口和安装入口。

6. **minimal smoke 可能写用户级 ACF_HOME。**
   - 为什么重要：usage log 默认写用户目录；smoke 应该只碰临时目录，避免污染本机或 CI。
   - 建议：smoke runner 默认设置临时 `ACF_HOME`。

7. **发布产物 wheel/sdist 还缺直接验证。**
   - 为什么重要：源码目录可安装，不等于 wheel/sdist 一定带齐模板 data-files。
   - 建议：release check 增加 build wheel/sdist -> 临时 venv 安装 wheel -> `acf init` / `check`。

8. **strict check 有日期敏感风险。**
   - 为什么重要：某些 keep-active 检查用当前日期；今天通过的 fixture 过几天可能失败。
   - 建议：给相关检查增加 `--today` 或测试注入日期，避免 CI 结果随日期漂。

9. **Workstream guard 更偏事后检查，不够事前防撞。**
   - 为什么重要：两个 agent 同时改同一批文件时，可能做完才发现越界或撞车。
   - 建议：Workstream context packet 增加 preflight：当前 dirty 状态、已 claim 文件、潜在冲突文件和建议 guard 命令。

10. **草案缺少统一看板。**
    - 为什么重要：writeback draft、curation draft、doctor report、archive draft、Knowledge draft 都不进默认读取路径是正确的，但没人看就会变成未完成事项黑洞。
    - 建议：增加 `acf draft status`，只列草案类型、年龄、路径和建议动作，不读取正文。

11. **代码还有迁移期兼容层债务。**
    - 为什么重要：`runtime.py` 和 `runtime_parts/*` 仍承担兼容命名空间和旧 helper，下次改命令时容易不知道应该改 command、domain、validator 还是 runtime part。
    - 建议：为 `runtime_parts` 制定收口计划；新增业务只能进 `commands/*`、`domains/*`、`validators/*`，并逐步把 Workstream 领域逻辑下沉到明确 domain 模块。

---

## 不建议立即做

1. 不做自动事实裁决或自动 Context merge。
2. 不引入向量库、数据库或常驻 agent runtime。
3. 不把 Workstream 扩展成调度系统。
4. 不把 tool-specific 规则文件提升为权威事实源。
5. 不把 high-risk audit heuristic 直接接入 strict。

---

## 建议下一步

1. 先清理已验证的 active 层问题：旧项目根路径、F015/F016/F017 状态、Done feedback 归档候选。
2. 合并安装文档和安装态 console script 回归测试，同时补 `uv tool install` / wheel smoke 到 release check。
3. 将 G003、G005、G008 作为下一批可验证薄切片候选：context pack、workstream next-actions、log-to-fixture draft。
4. 将 G006/G007 作为生态集成方向，但不要进入核心 CLI 主线，避免过早引入工具绑定。
5. 将 G012 与 F017 合并设计，避免重复讨论时间戳格式。

---

## 后续动作

按优先级选择下一批问题进入 Feedback 或 Task Plan。
