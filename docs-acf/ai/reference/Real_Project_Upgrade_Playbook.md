本文件记录 ACF v0.0.3.12 应用到真实项目时的试点接入和旧上下文升级流程。

本文件是操作 playbook，不是当前项目事实源。执行结果应记录到对应项目的 worklog 或本仓库试点记录中。

---

## 核心原则

1. 先 dry-run，后正式写入。
2. 先分支或备份，后迁移。
3. 默认不启用 Workstream。
4. 默认不批量添加 front matter。
5. 不重排原有文档，不覆盖用户正文。
6. 旧项目不应因为缺少 Workstream 或 metadata 被新版本 check 打扰。

---

## 试点项目选择

第一轮应选择低风险真实项目：

1. 有真实文档系统，但结构不要过度混乱。
2. 当前上下文有持续使用价值。
3. 可以接受新建 `docs/ai/` 或等价上下文目录。
4. 使用 git 或具备完整备份。
5. 暂时不需要多个 agent 并行。

第一轮目标不是完整迁移历史，而是验证 ACF v0.0.3.12 能否在真实项目中稳定完成上下文发现、非破坏式补齐、检查输出和默认 optional 行为。

---

## 无 ACF 项目的旁路接入

不要打散或重排原有文档。优先新建旁路 ACF 上下文：

```text
<project>/
  AGENTS.md
  docs/
    ai/
      active/
      reference/
      decisions/
      worklog/
      archive/
```

建议流程：

```powershell
cd <project>
uv run acf init docs/ai --profile standard --json
uv run acf status --json
uv run acf check docs/ai --strict --json
```

第一轮只建立索引和当前事实，不迁移全部历史。

常见映射：

| 原有内容 | ACF 目标位置 |
|---|---|
| 当前项目事实、阶段目标 | [active/Context.md](../active/Context.md) |
| 当前任务 | [active/Current_Task.md](../active/Current_Task.md) |
| 多步骤计划 | [active/Task_Plan.md](../active/Task_Plan.md) |
| 长期背景 | [reference/Project_Brief.md](Project_Brief.md) |
| 架构说明 | [reference/Architecture.md](Architecture.md) |
| 技术环境 | [reference/Tech_Context.md](Tech_Context.md) |
| 重要决策 | `decisions/ADR-xxxx dot md` |
| 历史过程 | `worklog/` |
| 临时想法或需求 | [active/Feedback_Inbox.md](../active/Feedback_Inbox.md) |

---

## 旧 ACF 上下文升级

### 0. 分支或备份

```powershell
git checkout -b upgrade-acf-v0.0.3.12
git status
```

非 git 项目应先复制一份目录。

### 1. 识别当前状态

```powershell
uv run acf status --json
uv run acf check docs/ai --json
```

先看普通 check，不要一开始就 strict。

### 2. dry-run upgrade

```powershell
uv run acf upgrade docs/ai --dry-run --json
```

重点审查：

1. `detected_features`
2. `planned_changes`
3. `skipped_changes`
4. `next_actions`
5. 失败时的 `error_code` 和 `message`

### 3. 审查 planned_changes

重点确认：

1. 是否补齐 [active/Feedback_Inbox.md](../active/Feedback_Inbox.md)。
2. 是否补齐 [active/Task_Plan.md](../active/Task_Plan.md)。
3. 是否补齐 `archive/feedback/`。
4. 是否补齐 Knowledge 结构。
5. 是否只做保守 section 迁移或追加 marker notes。
6. 是否没有覆盖用户自定义正文。
7. 是否没有默认创建 Workstream 结构。

如果存在不理解的权威文件改动，应先停下人工审查。

### 4. 正式 upgrade

```powershell
uv run acf upgrade docs/ai --json --check-after
uv run acf check docs/ai --strict --json
```

### 5. diff 审查

```powershell
git diff -- docs/ai
```

人工确认：

1. 没有覆盖用户正文。
2. 没有移动 active 当前任务。
3. 没有自动把历史记录升格为当前事实。
4. marker notes 没有重复追加。
5. 旧项目没有因为缺 Workstream 或 front matter 报错。

---

## 审查包覆盖要求

真实项目试点不应只保存当前 `git diff`。不同项目状态需要不同证据：

1. 已正式提交 upgrade 的项目，应包含最近提交的摘要和内容，例如：

```powershell
git show --stat HEAD
git show HEAD -- AGENTS.md docs/ai
```

2. 尚未提交但已有工作树变更的项目，应包含：

```powershell
git status --short
git diff --stat
git diff -- AGENTS.md docs/ai
```

3. 新 init 项目如果文件仍是 untracked，`git diff` 可能为空，应额外包含：

```powershell
git ls-files --others --exclude-standard
Get-ChildItem docs/ai -Recurse -File
```

或者先 staged 后再生成 staged diff：

```powershell
git add AGENTS.md docs/ai
git diff --cached --stat
git diff --cached -- AGENTS.md docs/ai
```

审查包必须能回答：改了哪些文件、这些文件是已提交/未提交/未跟踪、是否有业务代码被修改。

---

## PowerShell UTF-8 输出

如果用 PowerShell 生成审查包，先设置 UTF-8 输出，避免中文 JSON 或 Markdown 内容 mojibake：

```powershell
$env:PYTHONUTF8 = "1"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$OutputEncoding = [System.Text.UTF8Encoding]::new()
```

审查包中的 JSON 输出应保留原始 UTF-8 文本，不应经过会破坏中文的重定向或转码流程。

---

## Workstream 启用规则

第一轮真实项目接入默认不要启用 Workstream。

只有满足以下条件之一时，才运行：

```powershell
uv run acf workstream init docs/ai --json --check-after
```

启用条件：

1. 多个 agents 同时处理不同目标线。
2. 需要声明独立写入范围。
3. 子 agent 需要稳定记录发现和待合并结论。
4. 需要把 ReadyToMerge 和 Done 分开审查。

启用后才会创建 [active/Workstreams.md](../active/Workstreams.md)、`active/workstreams/` 和 `archive/workstreams/`，也只有这时 `acf check` 才执行 Workstream 一致性检查。

---

## Front Matter 迁移规则

不要批量给旧 ADR、旧 worklog 或旧 Knowledge 添加 front matter。

当前策略：

1. 旧文件没有 metadata 不报错。
2. 新 Workstream 详情必须有 front matter。
3. 新 ADR、Knowledge 或 worklog 可在后续按需采用 metadata。
4. AGENTS、rules、System Manual、Architecture、Project Brief 这类叙述型文档不优先改造。

---

## 验收表模板

```markdown
# ACF v0.0.3.12 Upgrade Acceptance

## 项目

- 项目路径：
- 原 ACF 版本：
- 目标版本：v0.0.3.12
- 是否已有 ACF 上下文：
- 是否启用 Workstream：否 / 是

## 执行命令

- acf status:
- acf check:
- acf upgrade dry-run:
- acf upgrade --check-after:
- acf check --strict:

## 结果

- changed files:
- skipped changes:
- next actions:
- warnings:
- errors:

## 人工审查

- 是否覆盖用户正文：否
- 是否移动 active 当前任务：否
- 是否自动启用 Workstream：否
- 是否批量添加 front matter：否
- 是否有 marker notes：是 / 否
- 是否需要人工处理：

## 结论

- 通过 / 暂缓 / 回滚
- 证据：
```

---

## 推广前判断

试点通过后，再推广到更多项目。不要批量运行正式 upgrade。

推广前至少确认：

1. 一个真实项目的 dry-run 和正式路径可审查。
2. strict check 的问题有明确解释。
3. git diff 没有非预期重排。
4. Workstream 未被默认启用。
5. 旧文件未被批量 metadata 迁移。
6. 试点项目连续使用 1 到 2 次真实会话后仍能维护。

后续候选能力应进入新反馈或新计划，不进入当前试点计划：

1. 自动 ID 分配。
2. `workstream archive` 命令。
3. `workstream changed` / git diff scope 检查。
4. claim override with reason。
