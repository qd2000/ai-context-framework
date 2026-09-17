# WS013 Observer Retirement and v0.0.3.92 Plan

本文件是 WS013 的详细执行计划。当前事实仍以 `active/Context.md`、`active/Task_Plan.md`、`active/Current_Task.md` 和 `active/workstreams/WS013.md` 为准；本计划负责保存阶段路线、产品决策、文件范围、验证矩阵和发布边界。

---

## 1. 当前状态

- 当前已发布稳定版本：`v0.0.3.91`，tag / PyPI / 全局安装已完成。
- 当前主线版本文件仍为 `0.0.3.91`；`v0.0.3.92` 是本 Workstream 的目标版本，不是当前已发布事实。
- `.91` 当前发布说明已在主线提交 `1d2d5ee` 修正为稳定发布事实，不再把 `.91` 写成 release candidate，也不再把 `.89` 写成当前安装态。
- WS013 分支：`codex/ws013-observer-retirement-ws012-closeout`。
- WS012 最终分支 tip `b134f3e` 已通过 merge commit `83aa92d` 完整进入 WS013 血缘；未采用 squash 或选择性复制。
- WS012 已在 `3109d23` 归档为 `docs/ai/archive/workstreams/WS012.md`。
- WS012 continuation 已正式结束：generation 217 为 `done/released`，lease absent，两个 Observer directive 已撤销，active / prepared / unresolved effects 均为 0，workspace 无 task-owned / unclassified path。
- WS012 worktree、branch、registry、专属 ACF_HOME、主项目 Observer 派生 runtime 和匹配的临时文件均已删除；一次清理共移除 375 个派生或临时对象，失败数为 0。
- WS012→WS013 集成回归已经取得终态：`189 tests`，`OK`，exit 0；`acf check --strict` 与 template check 通过。

---

## 2. 用户决策与产品结论

### 2.1 用户决策

经过一个多月实际使用，用户几乎不查看 Observer 或 HTML 页面，三个 Production Observer Scheduled Task 与 WS012 Scheduled Task 已删除。后续不再把持续 Observer、自动 Dashboard 或 HTML 进度页作为 ACF 核心方向。

### 2.2 产品结论

Observer 应从 ACF 核心产品中退役，而不是继续维护一个“精简但仍需长期兼容”的第二子产品。原因：

1. 它没有进入真实高频工作路径。
2. 它显著扩大 runtime、状态模型、文档、测试和 release gate。
3. 当前 `automation_prompt_execution_contract` 中 Observer 子树约占一半序列化体积，给只使用 Writer / continuation 的调用方增加无收益上下文负担。
4. 它把 ACF 推向长期 Agent runtime、派生展示状态和 HTML 产品，而 ACF 的核心定位应保持模型无关、Markdown-first、人工可审阅、渐进式暴露和确定性 CLI。

### 2.3 保留边界

保留：

- Git 历史、CHANGELOG 和 WS011 / WS012 archive；
- 与 Observer 无关、已经证明可复用的 continuation、worktree、context 和安全修复；
- 一个极薄、无副作用的退役兼容入口，用于让旧调用得到稳定的 `observer_retired` 错误与替代命令提示；
- 旧用户级 Observer 数据默认不由升级过程自动删除。

删除：

- Observer snapshot / history / semantic / glossary / narrative runtime；
- Target Registry、expected-target recovery 和 target projection；
- presentation / semantic-review / transient-patch 生命周期；
- Dashboard / HTML renderer 和 Observer-owned output 产品合同；
- Observer Scheduled Task wrapper、dogfood acceptance 和 release gate；
- Observer 专属模块、测试、smoke 和当前产品文档入口。

明确禁止：

- 为了“兼容”保留可继续增长的半套 Observer runtime；
- 在 `.92` upgrade/install 时自动递归删除用户级 `~/.acf/projects/*/observer/`；
- 删除或改写历史 CHANGELOG、archive、ADR 和已发布版本事实；
- 把按需生成一次性报告重新包装成常驻 Observer。

---

## 3. 目标架构

### 3.1 `.92` 之后的核心产品面

ACF 继续聚焦：

- Markdown context / template；
- `status`、`check`、`upgrade`；
- plan / task / archive / knowledge / worklog / edit；
- Workstream / worktree 生命周期；
- continuation 的确定性 owner、effect、workspace、directive 和 recovery 协议；
- release、smoke、upgrade compatibility 和安全边界。

### 3.2 退役兼容入口

`.92` 可保留最小 `acf observer` parser，但它不得导入原 Observer 实现，不得读取或写入 Observer runtime，不得创建目录，也不得删除用户数据。调用结果应稳定返回：

```json
{
  "schema_version": 1,
  "ok": false,
  "command": "observer",
  "error_code": "observer_retired",
  "changed_files": [],
  "next_actions": [
    "Use `acf status --json` for current context state.",
    "Use `acf workstream dashboard --json` for Workstream portfolio state.",
    "Use `acf continuation doctor --json` for continuation health."
  ]
}
```

非 JSON 输出应给出同等明确的退役说明。该入口只是兼容墓碑，不是 Observer 功能保留。

---

## 4. 实施阶段

### P0 — WS012 吸收、终止和本地清理

状态：**Done**。

完成项：

- `.91` 发布事实文档同步；
- WS013 reservation / worktree / branch 创建；
- WS012 未提交 WIP 提交；
- WS012 continuation reconcile / recovery / directive withdraw / terminal release；
- WS012 完整 Git 血缘合入 WS013；
- 冲突审查与智能解决；
- WS012 Workstream archive；
- WS012 worktree / branch / registry / ACF_HOME / Observer runtime / temp 清理；
- 189 项集成回归和结构检查。

### P1 — Observer 依赖图和删除清单固化

目标：在写代码前机械确认所有当前依赖，避免删掉 Observer 后留下 import、打包、smoke 或文档断链。

操作：

1. 使用 `git grep` 盘点所有当前非历史 `observer` 引用。
2. 将命中分为：实现、CLI 注册、自动化合同、测试、打包、release gate、当前文档、历史资料。
3. 确认保留的历史路径和允许残留的退役 stub 路径。
4. 为每个删除模块找到唯一调用方和对应测试。

阶段验收：

- 形成可审阅的文件矩阵；
- 没有“删模块后才发现 release_check 仍依赖”的未知路径；
- 历史 archive 与当前产品引用已区分。

### P2 — 移除 Observer runtime 与公开产品能力

目标：删除完整 Observer 实现，只保留无副作用退役入口。

主要删除路径：

```text
ai_context_framework/observer.py
ai_context_framework/observer_dashboard.py
ai_context_framework/observer_presentation.py
ai_context_framework/observer_runtime_storage.py
ai_context_framework/observer_storage.py
ai_context_framework/observer_target_projection.py
ai_context_framework/observer_targets.py
ai_context_framework/observer_workstream_sources.py
ai_context_framework/commands/observer.py
ai_context_framework/commands/observer_presentation.py
```

主要修改路径：

```text
ai_context_framework/runtime.py
ai_context_framework/automation_contracts.py
ai_context_framework/commands/continuation_workspace.py
tests/test_automation_contracts.py
tests/test_cli.py
tests/test_continuation_cli.py
```

实现要求：

- root parser 不再导入 Observer 实现；
- `continuation prompt --json` 不再携带 Production Observer wrapper、semantic review、presentation maintenance 或 Observer dogfood acceptance；
- Writer scheduler/runtime contract 的稳定键和行为不因 Observer 删除而漂移；
- retired stub 不访问文件系统状态，不创建 `observer/`，不读取 Git 或 continuation；
- 删除后不存在 Observer 模块之间的循环或残留 import。

### P3 — 删除 Observer 测试、smoke、打包与输出产物

删除或改写：

```text
tests/test_observer_cli.py
tests/test_observer_presentation.py
tests/test_observer_target_projection.py
tests/test_observer_targets.py
scripts/minimal_smoke.py
scripts/release_check.py
ai_context_framework.egg-info/SOURCES.txt
`output/observer/` 下的 notes 与 candidate 产物（本阶段删除）
```

要求：

- minimal smoke 不再创建 Observer project 或 Dashboard；
- release check 不再要求 `observer status/snapshot` 或 `dashboard.html`；
- package 不再包含 Observer 实现模块；
- 增加 retired stub 的 focused regression；
- 不保留为了删除功能而失去意义的大型 fixture。

### P4 — 当前文档和模板同步

修改：

```text
README.md
CHANGELOG.md
docs/Automation.md
docs/ai/reference/System_Manual.md
template/reference/System_Manual.md
docs/ai/active/Context.md
```

要求：

- 当前文档不再列出 Observer 为产品能力；
- 不再提供 Observer Scheduled Task、Dashboard、Target Registry 或 presentation lifecycle 的操作教程；
- `.89` 的 Observer Beta、WS011/WS012 的过程只保留为历史记录；
- 文档明确旧用户数据不被自动删除；
- 替代入口只指向现有确定性 CLI，不虚构新的可视化能力；
- template、README、dogfooding manual 和 Automation 语义一致。

### P5 — 完整验证和兼容性审计

必跑命令：

```powershell
uv run acf check template
uv run acf check --strict
uv run python -m unittest
uv run python scripts/minimal_smoke.py --acf uv run acf
uv run python scripts/upgrade_matrix.py --mode full --acf uv run acf
uv run python scripts/release_check.py --mode full
```

专项断言：

1. `uv run acf continuation prompt --json` 中不存在 Observer contract 子树。
2. `uv run acf observer --json` 或兼容子命令返回 `observer_retired`，`changed_files=[]`。
3. 在隔离 `ACF_HOME` 下调用 retired stub 前后目录树和文件 hash 不变。
4. package source / wheel 中不存在 Observer 实现模块。
5. `git grep` 的当前产品命中只允许：退役 stub、退役说明和历史资料。
6. `status`、`check`、`workstream`、`worktree`、`continuation` 的完整回归通过。
7. 没有新增第三方运行依赖。

### P6 — 版本更新与 `v0.0.3.92` 发布

只有 P1–P5 全部闭合后才执行：

```powershell
uv run acf version set v0.0.3.92
uv run acf version show --json
```

随后：

1. 更新 CHANGELOG 的 `.92` 用户可见说明；
2. 重跑完整 release gate；
3. 合并到 master；
4. 创建 immutable `v0.0.3.92` tag；
5. push / PyPI publish；
6. 使用 `scripts/update_acf.ps1` 完成 Windows 全局安装和 `acf.cmd` canonicalization；
7. installed-state 验证 version / status / check / workstream / continuation / retired observer stub；
8. 禁止移动或重用 `.90`、`.91` tag。

### P7 — WS013 收尾

- 将 WS013 标记 ReadyToMerge / Merging / Done；
- 记录 merge resolution 和验证证据；
- 归档 WS013；
- 移除 WS013 worktree / branch / continuation 运行态；
- 最终 `acf status --json` 回到 global-only，无活动 Workstream。

---

## 5. 文件矩阵

| 类别 | 处理 | 主要路径 |
|---|---|---|
| Observer 实现 | 删除 | `ai_context_framework/observer*.py`、`commands/observer*.py` |
| CLI 注册 | 改为 retired stub | `ai_context_framework/runtime.py` |
| 自动化合同 | 删除 Observer 子树 | `ai_context_framework/automation_contracts.py`、continuation prompt adapter |
| 测试 | 删除专项大套件，增加 stub/无副作用回归 | `tests/test_observer*.py`、automation/CLI/continuation tests |
| smoke / release | 移除 Dashboard 前置 | `scripts/minimal_smoke.py`、`scripts/release_check.py` |
| 文档 | 当前文档删除产品说明，历史保留 | README、Automation、两份 System Manual、CHANGELOG、Context |
| 打包 | 不再包含 Observer 模块 | `SOURCES.txt`、wheel/sdist 检查 |
| 输出 | 删除仓库内 Observer candidate/notes | `output/observer/` |
| 用户数据 | 默认不自动删 | `~/.acf/projects/*/observer/` |
| 历史 | 保留 | CHANGELOG、`docs/ai/archive/`、WS011/WS012 reference/history |

---

## 6. 高风险点与优先验证

1. **Writer contract 被误删**：`automation_contracts.py` 同时包含 Writer 与 Observer，必须先拆除 Observer 子树，不能删除整个模块。
2. **root runtime import 失败**：删除 `commands/observer.py` 前先替换 parser 注册，否则所有 CLI 都会启动失败。
3. **release gate 暗含 Dashboard**：`minimal_smoke.py` 和 `release_check.py` 当前直接验证 Observer，需要同步修改。
4. **文档漂移**：README、Automation、dogfooding manual 和 template manual 必须同批更新。
5. **打包残留**：egg-info / sdist / wheel 中的 SOURCES 必须重新生成并检查。
6. **历史误删**：archive 和 CHANGELOG 中的 Observer 内容是历史事实，不能因产品退役而删除。
7. **用户数据破坏**：`.92` 不能把本次获得明确授权的本机清理扩大成默认升级行为。
8. **过早 bump**：在删除实现和验证完成前保持版本文件为 `.91`；否则未完成代码会冒充 `.92`。

---

## 7. 成功标准

1. WS012 已完整吸收、终止、归档并清理，无 branch/worktree/registry/continuation/temp 残留。
2. ACF 安装包不再包含 Observer runtime、Dashboard、Target Registry 或 presentation lifecycle 实现。
3. continuation prompt 不再携带 Observer 合同和 dogfood acceptance。
4. `acf observer` 仅为稳定、无副作用的退役提示，或在最终评审中被证明可以安全彻底移除；不得保留半套产品。
5. 当前文档和模板不再把 Observer 写成现有能力；历史发布记录保持完整。
6. 升级不会自动删除任何用户级 Observer 数据。
7. 全量单元测试、strict/template check、minimal smoke、full upgrade matrix、release check 和 package smoke 全部通过。
8. `v0.0.3.92` 完成 immutable tag、PyPI publish、全局安装和 installed-state 验证。
9. WS013 最终归档，主线回到无活动 Workstream 状态。

---

## 8. 当前下一步

P1–P3 已闭合（依赖矩阵见第 9 节；实现、测试、打包、smoke 与当前文档同步已完成）。执行 T004/P5：逐条运行 strict/template、全量 unittest、minimal smoke、full upgrade matrix、release check，并补足 wheel/sdist 内容审计与 `git grep` 残留词面审计，形成可发布候选。版本文件保持 `0.0.3.91`；只有 P5 七项专项断言全部通过后才进入 P6 bump。

---

## 9. P1 依赖矩阵与安全删除顺序（T001 产出）

审计时间：2026-09-17。审计方法：`git grep` 全量盘点 + 模块 import 图 + 保留模块功能性耦合扫描。

### 9.1 核心结论

1. 10 个 Observer 待删模块彼此自成闭环；仓库内**没有任何保留的生产模块 import 任一 Observer 实现模块**。
2. 该闭环只有两个对外出口：`ai_context_framework/runtime.py`（import + parser 注册）与测试文件。
3. 唯一"隐形的功能性耦合"是 `ai_context_framework/commands/continuation_workspace.py`：该文件不含 `observer` 字面量，但在输出中嵌入 `automation_prompt_execution_contract()`，因此 Observer 契约键删除后其输出结构会变化，必须与 `tests/test_continuation_cli.py` 的契约断言同批处理。

### 9.2 模块依赖拓扑（A import B）

| 模块 | 内部依赖（其他待删模块） | 保留代码导入者 | 测试导入者 |
|---|---|---|---|
| `observer_dashboard.py` | 无 | 无 | `test_observer_presentation.py` |
| `observer_runtime_storage.py` | 无 | 无 | 无 |
| `observer_workstream_sources.py` | 无 | 无 | 无 |
| `observer_storage.py` | `observer_dashboard`、`observer_runtime_storage` | 无 | `test_observer_targets/presentation/cli` |
| `observer_targets.py` | `observer_storage` | 无 | `test_observer_targets.py` |
| `observer_presentation.py` | `observer_storage` | 无 | `test_observer_presentation.py` |
| `observer.py` | `observer_storage`、`observer_targets`、`observer_presentation`、`observer_workstream_sources` | 无 | `test_observer_*.py`（3 个） |
| `observer_target_projection.py` | `observer`、`observer_storage`、`observer_targets` | 无 | `test_observer_target_projection.py` |
| `commands/observer_presentation.py` | `observer`、`observer_target_projection`、`observer_presentation`、`observer_storage` | 无 | 无 |
| `commands/observer.py` | `commands/observer_presentation`、`observer`、`observer_target_projection`、`observer_storage`、`observer_targets` | `runtime.py:51` import、`runtime.py:1209` 注册 | 经 CLI 子进程间接使用 |

### 9.3 安全删除顺序

必须先完成第 0 步（替换 CLI 注册），再执行 1–10 的模块删除；顺序按"无入边优先"：

| 步 | 动作 | 前置 |
|---|---|---|
| 0 | `commands/observer.py` 内容替换为退役 stub（保持 `register_observer_parser(subparsers, add_json_argument)` 签名；`runtime.py` 因此无需改动） | 无 |
| 1 | 删除 `observer_dashboard.py` | 0 |
| 2 | 删除 `observer_runtime_storage.py` | 0 |
| 3 | 删除 `observer_workstream_sources.py` | 0 |
| 4 | 删除 `observer_storage.py` | 1、2 |
| 5 | 删除 `observer_targets.py` | 4 |
| 6 | 删除 `observer_presentation.py` | 4 |
| 7 | 删除 `observer.py` | 3、4、5、6 |
| 8 | 删除 `observer_target_projection.py` | 4、5、7 |
| 9 | 删除 `commands/observer_presentation.py` | 6、7、8 |

### 9.4 保留文件修改清单（非 Observer 模块）

| 文件 | 修改点 | 说明 |
|---|---|---|
| `ai_context_framework/runtime.py` | 无需改动 | 第 51 行 import 与第 1209 行注册签名保持不变；`commands/observer.py` 整体替换为退役 stub |
| `ai_context_framework/automation_contracts.py` | 删除 Observer 子树 | 见 9.5 |
| `ai_context_framework/commands/continuation_workspace.py` | 无需改代码 | 仅输出结构变化，同步改测试断言 |
| `tests/test_automation_contracts.py` | 删除 observer import 与 4 个 observer 测试；改写 roles 断言 | 见 9.7 |
| `tests/test_continuation_cli.py` | 改写 9300-9349+ 契约断言 | 保留 Writer 断言 |
| `scripts/minimal_smoke.py` | 删除 585-632 方法与 642 场景注册 | 其余场景自洽 |
| `scripts/release_check.py` | 删除 199-220 与 225-227 | 其余流程自洽 |
| `scripts/upgrade_matrix.py` | 无需处理 | 无 Observer 断言 |
| `tests/test_cli.py` | 无需处理 | 第 3105 行仅为哨兵文件名 |

### 9.5 automation_contracts.py 拆分边界

保留（Writer 契约，行为不得漂移）：

- 第 21-23 行 schema 常量；第 30-86 行 Writer 常量与列表；
- 第 141-161 行 `_copy_identity`、`_constraint_slot`；
- 第 164-286 行 `writer_scheduler_wrapper_contract`、`writer_continuous_execution_contract`、`writer_runtime_prompt_contract`；
- 第 281 行 `must_not_embed` 中的 `production_observer_semantic_state_machine` token：**保留**（属 Writer 契约稳定键，`tests/test_automation_contracts.py:102` 对其有断言；删除会构成 Writer 行为漂移）。

删除（Observer 子树）：

- 第 24-27 行 schema 常量；第 88-138 行 Observer 常量与列表；
- 第 289-547 行 `production_observer_wrapper_contract`、`observer_semantic_review_contract`、`observer_execution_evidence_contract`、`presentation_maintenance_contract`；
- `__all__` 中所有 `OBSERVER_*`、`PRESENTATION_MAINTENANCE_LIFECYCLES` 与 4 个 Observer 契约函数；
- `automation_prompt_execution_contract()` 中：`roles` 的 `production_observer_scheduler_wrapper`；`production_observer_scheduler_wrapper` / `observer_semantic_review` / `observer_execution_evidence` / `presentation_maintenance` 四个键；`dogfood_acceptance.task_families` 的 `acf_observer` / `fcc_observer` / `astockt_ai_observer`；`presentation_lifecycle_cases` 与 `agent_first_cases` 全部。

跨边界借用：`observer_execution_evidence_contract` 借用 Writer 常量 `WRITER_EXECUTION_EVIDENCE_FIELDS` —— 删函数、保留常量。

### 9.6 退役 stub 设计与 write_scope 约束

- **实现位置**：`ai_context_framework/commands/observer.py` 保留文件名，内容整体替换为极薄 stub；`runtime.py` 的 import 与 `register_observer_parser(subparsers, add_json_argument)` 调用签名保持不变，避免 root parser 启动风险。
- **行为约束**：不 import 任何 Observer 实现模块；不读取文件系统 / Git / continuation；不创建目录；不删除用户数据。
- **输出契约**：JSON 输出 `{"schema_version": 1, "ok": false, "command": "observer", "error_code": "observer_retired", "message": "...", "changed_files": [], "next_actions": [...]}`（`message` 与 ACF 既有失败契约惯例一致）；非 JSON 输出给出同等明确的退役说明与替代命令。
- **参数容忍**：为兼容旧调用（如 `acf observer status <path> --json`），parser 需接受并忽略旧子命令与位置参数（`nargs=argparse.REMAINDER` 或等价方式），保证任何旧形式返回 `observer_retired` 而非 argparse 用法错误。
- **write_scope 约束**：`json_contract.py` / `constants.py` **不在** WS013 write_scope 内，stub 不得依赖对它们的修改；payload 在 stub 内自包含构造，仅 import 既有 `json_enabled` / `print_json` / `set_result_payload` / `JSON_SCHEMA_VERSION` 等只读符号。
- **exit code**：stub 直接返回非 0（`EXIT_RUNTIME_ERROR`），不新增 `json_contract.error_next_actions` 映射。

### 9.7 测试处理清单

| 文件 | 处理 |
|---|---|
| `tests/test_observer_cli.py` | 整体删除 |
| `tests/test_observer_presentation.py` | 整体删除 |
| `tests/test_observer_targets.py` | 整体删除 |
| `tests/test_observer_target_projection.py` | 整体删除 |
| `tests/test_automation_contracts.py` | 删除 Observer import 与 `test_production_observer_wrapper_*`、`test_semantic_review_*`、`test_presentation_maintenance_*`、`test_execution_evidence_*`；roles 断言改写为仅 Writer；第 102 行 `must_not_embed` 断言保留 |
| `tests/test_continuation_cli.py` | 改写 9300-9349+ 的 Observer / presentation 契约断言；16 处自由文本标签无需处理 |
| `tests/test_cli.py` | 第 3105 行哨兵文件名与 Observer 无功能耦合，无需处理 |
| 新增 | `observer_retired` stub 的无副作用 focused 回归（含隔离 `ACF_HOME` 前后目录树/hash 不变断言） |

### 9.8 打包与产物

| 目标 | 处理 |
|---|---|
| `pyproject.toml` / `MANIFEST.in` | 无 observer 引用（自动发现），无需修改 |
| `ai_context_framework.egg-info/SOURCES.txt` | 已删除 observer 模块与测试条目（保留 stub 行） |
| `ai_context_framework.egg-info/PKG-INFO` | README 快照，README 更新后重生成 |
| `output/observer/` notes 与 candidate 产物 | 已删除 |

### 9.9 历史保留边界

| 保留（不得删除或改写） | 理由 |
|---|---|
| Git 历史、`CHANGELOG.md` 既有条目 | 已发布版本事实 |
| `docs/ai/archive/workstreams/WS012*.md` | 历史证据 |
| `docs/ai/reference/ws011_project_observer/` | 历史设计与证据 |
| 用户级 `~/.acf/projects/*/observer/` 数据 | 不得自动删除 |
| `docs/Automation.md` 中 Observer 的历史说明段落 | 保留为历史记录，仅移除"当前能力"表述 |

### 9.10 允许残留的 observer 词面

删除完成后，`git grep` 当前产品面的 observer 命中只允许出现在：

1. 退役 stub（`commands/observer.py`）与 `runtime.py` 注册；
2. 退役说明（README / CHANGELOG / Automation / 两份 System Manual / Context）；
3. 历史资料（archive / WS011 / WS012 / 本 PLAN）；
4. Writer 契约中的历史兼容负向 token（`automation_contracts.py` 第 281 行）。
