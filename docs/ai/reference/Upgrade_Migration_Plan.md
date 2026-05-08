# Upgrade Migration Plan

本文件记录 ACF 后续升级迁移的详细规划，重点覆盖 Workstream 可选层、front matter metadata 支持，以及旧版本上下文如何完整升级到新版本。

---

## 目标

1. 让旧版本 ACF 上下文可以非破坏式升级到新版本结构。
2. 保持 Workstream 和 front matter 都是 optional，不让旧项目因为没有新结构而检查失败。
3. 明确 `acf upgrade` 应如何发现旧结构、补齐新结构、迁移可确定 section，并保留无法安全迁移的人工提示。
4. 为 init、upgrade、check、template data-files 和单元测试提供同一套迁移矩阵。

---

## 升级原则

1. 非破坏式优先：不覆盖用户自定义正文，不移动 active 当前任务，不删除未知文件。
2. 幂等：同一目标重复运行 upgrade 不应重复追加同一段内容或产生不同结果。
3. Optional first：Workstream 层、front matter 和 metadata 检查只在相关结构存在或用户显式启用后生效。
4. Dry-run first：所有高风险升级都必须支持 `--dry-run --json`，输出 changed files 和 next actions。
5. Marker notes 优先：无法识别旧段落或自定义结构时，追加 marker notes，而不是重排或重写全文。
6. 事实不自动升格：upgrade 只补结构和说明，不把反馈、worklog 或草案自动写成当前事实。
7. 兼容检查：新版本 check 必须能接受旧项目的合法缺省结构。

---

## 版本识别

第一版可以不引入全局 schema 文件，而是通过结构探测判断目标状态。

建议探测项：

| 探测项 | 旧状态信号 | 新状态信号 | 处理 |
|---|---|---|---|
| Feedback Inbox | 缺少 active/Feedback_Inbox | 存在 Feedback Inbox 且有生命周期规则 | 补文件或补 section |
| Task Plan | 缺少 active/Task_Plan | 存在轻量任务板 | 补文件，保留 Current_Task |
| archive feedback | 缺少 archive/feedback 目录 | 目录存在 | 补目录 |
| Knowledge | 缺少 Knowledge index 或目录 | index 和目录存在 | 补结构 |
| Workstream | 缺少 Workstreams 索引 | 缺省合法 | 不自动启用；仅在显式命令中创建 |
| Front matter | 旧详情文件无 metadata | 缺省合法 | 不自动迁移；仅新文件采用 |
| System Manual | 缺少升级规则或旧命令说明 | 相关 section 存在 | section 级迁移或 marker notes |
| AGENTS 读取顺序 | 缺少 Feedback 或 Task_Plan 读取说明 | 读取顺序完整 | 能识别旧段落时替换；否则 marker notes |

后续如果引入 `context_schema_version`，也应作为辅助信号，而不是唯一事实源。

---

## 升级阶段

### 阶段 0：预检查

执行：

```bash
uv run acf status --json
uv run acf check <context> --json
```

目标：

1. 定位 project root 和 context root。
2. 判断 profile。
3. 收集已有结构、缺失文件、检查错误和 warning。
4. 判断是否存在 active 当前任务，避免自动覆盖。

输出要求：

1. JSON 中列出 detected features。
2. JSON 中列出 planned changes。
3. 如果目标目录不是 ACF context，返回输入错误而不是创建混合结构。

### 阶段 1：结构补齐

可自动补齐：

1. 缺失的标准目录。
2. 缺失的 active 基础文件。
3. 缺失的 archive、archive/feedback 和 Knowledge 目录。
4. 缺失的根薄入口，仅在规则允许时生成。

不可自动启用：

1. Workstream 索引和详情目录，除非用户运行 `acf workstream init`。
2. front matter 批量迁移。
3. 对用户自定义规则和手册的全文重写。

### 阶段 2：可识别 section 迁移

对已知模板文件，如果旧 section 可被稳定识别，可以做 section 级替换或追加：

1. `AGENTS`：补默认读取顺序和会话结束回写协议。
2. `Feedback_Inbox`：补状态说明、使用规则和归档规则。
3. `Project_Rules`：补版本和 upgrade 兼容性规则。
4. `System_Manual`：补 upgrade、feedback、metadata 或 workstream 说明。

如果无法识别旧 section，追加 marker notes：

```text
<!-- ACF:UPGRADE:NOTES:START -->
...
<!-- ACF:UPGRADE:NOTES:END -->
```

同一 marker 块必须幂等更新，不重复追加。

### 阶段 3：可选能力提示

upgrade 可以提示但不自动执行：

1. 可运行 `acf workstream init` 启用 Workstream 层。
2. 可运行未来的 `acf metadata preview` 查看 front matter 迁移候选。
3. 可运行 `acf check --strict` 验证模板和上下文。

提示应进入 JSON `next_actions`，不要直接修改权威事实。

### 阶段 4：写后验证

当用户传入 `--check-after`：

1. 运行普通 check。
2. 如果传入 `--strict`，运行 strict check。
3. check 失败时返回 `check_failed`，但保留已写入文件，并明确 next actions。

---

## Workstream 升级策略

Workstream 是 optional layer。

`acf upgrade` 默认行为：

1. 不创建 Workstreams 索引。
2. 不创建 Workstream 详情目录。
3. 不创建 archive/workstreams。
4. 不要求旧项目存在 Workstream 文件。
5. 不因缺少 Workstream 结构产生 warning 或 error。
6. 不修改默认读取顺序，除非模板入口需要补“有 Active workstream 时按需读取”的说明。
7. 只在 `next_actions` 中提示可选启用路径。

显式启用行为：

```bash
uv run acf workstream init --json --check-after
```

启用后创建：

```text
active/Workstreams.md
active/workstreams/
archive/workstreams/
```

启用后 check 才校验 Workstream 一致性。

Workstream check 触发条件：

| 条件 | 行为 |
|---|---|
| 没有 Workstreams 索引 | 不运行 Workstream check，不报错，不 warning |
| 存在 Workstreams 索引 | 校验索引、详情目录、详情文件和状态一致性 |
| 存在详情目录但无索引 | warning；strict 下 error |
| 存在 Active/Blocked/ReadyToMerge | AGENTS 允许按需读取索引和对应详情 |
| 只有 Done/Cancelled 且索引状态 Inactive | 不应增加默认读取噪音 |

---

## Front Matter 升级策略

Front matter 是新增文件优先能力。

`acf upgrade` 默认行为：

1. 不给旧 ADR、旧 worklog、旧 Knowledge 草案批量添加 front matter。
2. 不因为旧文件缺少 front matter 报错。
3. 只在 System Manual 或相关参考文档中补充 metadata 规则说明。

Front matter check 触发条件：

| 文件状态 | 行为 |
|---|---|
| 旧 ADR / 旧 worklog / 旧 Knowledge 没有 front matter | 不报错，不 warning |
| 新 Workstream 详情文件 | 必须有 metadata |
| 文件有 front matter | 解析极小 YAML 子集，报告语法诊断 |
| 文件有 metadata 且声明了 schema | 校验 required、enum、list/scalar、typed scope 和路径规范 |
| metadata 与索引冲突 | 普通 check warning；strict 可升级为 error，具体以对应文档类型规则为准 |

未来可选迁移：

```bash
uv run acf metadata preview <file>
uv run acf metadata apply <file>
```

迁移限制：

1. 必须 dry-run first。
2. 只处理单文件或明确范围。
3. 只从确定性 section 或 index 行提取元数据。
4. 无法确定字段时生成 TODO 或跳过，不猜测。

---

## Parallel / Workstream 接口升级策略

Parallel 支持通过 Workstream 结构实现，不引入 agent runtime。

升级只补协议和模板，不启动任何并行执行能力。

接口分层：

1. 文档层：Workstreams 索引和详情模板。
2. CLI 结构层：`acf workstream ...` 维护状态、owner、写入范围和合并请求。
3. Check 层：检测 Workstream 文件完整性和写入范围冲突。
4. Runtime 外部层：Codex 或其他 agent runtime 只消费这些文件，不由 ACF 调度。

---

## Data Files 与 Init 同步

新增模板或结构时必须同步：

1. `template/` 文件。
2. `pyproject.toml` data-files。
3. `acf init` 文件清单。
4. `acf upgrade` 补齐清单。
5. `acf check template` 的 data-files 检查。
6. README 和 System Manual。
7. init/upgrade 单元测试。

Workstream 结构若保持 optional，`init` 是否默认生成空索引需要单独判断：

1. 如果默认生成空索引，用户会看到新层，但 check 更容易发现结构漂移。
2. 如果默认不生成，默认上下文更轻，旧项目兼容性更好。

当前建议：旧项目 upgrade 不生成；新项目 init 可暂不生成，先通过 `acf workstream init` 显式启用。

实际生成的 Workstream 索引和详情文件必须统一使用 `.md` 后缀；upgrade、init、check 和 JSON 输出必须使用同一套路径规范化逻辑。

---

## 测试矩阵

必须覆盖：

| 场景 | 预期 |
|---|---|
| 最新 template check | 通过 |
| 旧 minimal context upgrade dry-run | 只报告计划变更 |
| 旧 minimal context upgrade 正式执行 | 补齐缺失结构，check 通过 |
| 旧 standard context upgrade dry-run | 幂等，无重复 marker |
| 旧 standard context upgrade 正式执行两次 | 第二次 no changes needed，不重复 marker |
| 自定义 AGENTS / System Manual | 不覆盖正文，追加或更新 marker notes |
| 缺少 Feedback Inbox | 补文件 |
| 缺少 archive/feedback | 补目录 |
| 无 Workstream 结构 | check 不报错 |
| 显式 workstream init 后 | Workstream check 生效 |
| 仅有 Done/Cancelled workstream 且索引 Inactive | 默认读取不变重，check 通过 |
| Workstreams 索引存在但详情目录缺失 | check error |
| 详情存在但索引缺行 | 普通 check warning，strict error |
| 旧 ADR 无 front matter | check 不报错 |
| 旧 worklog 无 front matter | check 不报错 |
| 旧 Knowledge 无 front matter | check 不报错 |
| 新 ADR 有 front matter | index 一致性可检查 |
| 新 Workstream 详情无 front matter | check error |
| 新 metadata 文件缺 required 字段 | check error |
| 新 metadata 文件 enum 不合法 | check error |
| typed write_scope 缺类型或路径不规范 | check error |
| 重复运行 upgrade | changed files 稳定，不重复追加内容 |

---

## JSON 输出契约

upgrade JSON 应包含：

```json
{
  "schema_version": 1,
  "ok": true,
  "command": "upgrade",
  "detected_features": [],
  "planned_changes": [],
  "changed_files": [],
  "skipped_changes": [],
  "next_actions": []
}
```

失败时应包含 `error_code`、`message` 和 `next_actions`。

字段语义：

| 字段 | 语义 |
|---|---|
| `detected_features` | 结构探测结果，例如 feedback_inbox、task_plan、knowledge、workstream、front_matter、custom_agents |
| `planned_changes` | dry-run 或执行前确定会写入的结构、section 或 marker notes |
| `changed_files` | 实际写入或 dry-run 将写入的文件路径 |
| `skipped_changes` | 因 optional、已存在、无法安全迁移或用户自定义而跳过的动作 |
| `next_actions` | 用户或 AI 可选后续动作，例如运行 workstream init、metadata preview 或 strict check |

`upgrade --dry-run --json` 必须填充 `planned_changes` 和 `changed_files`，但不得写入文件。正式 upgrade 后若无变化，应返回 ok，并在 `next_actions` 中说明无后续必需动作。

---

## 版本策略

如果只是补 optional 结构、文档说明和新命令，且旧项目 check 不新增错误，可用 patch。

如果 `init` 默认输出结构明显变化，或 `check --strict` 对旧项目产生新错误，应考虑 minor，或至少在 README、System Manual 和 worklog 中记录 migration note。

---

## 当前结论

Workstream、front matter 和 parallel 支持都必须通过 upgrade 兼容性约束落地。默认升级应补结构、补说明、保留用户内容；显式命令才启用 Workstream 或 metadata 迁移。这样可以完整支持旧版本到新版本的路径，同时不破坏 ACF 的 Markdown-first 和人工可审阅边界。
