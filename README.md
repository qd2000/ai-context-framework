# ai-context-framework

一个模型无关的 AI 上下文管理框架模板。

## 设计理念

人与 AI 的协作中，人作为最高决策层，AI 同时作为执行者和策略建议者。项目知识不应随 AI 工具更换或人员离开而丢失。

本框架通过分层的 Markdown 文件结构管理项目上下文，实现：

- **模型无关**：纯 Markdown，不依赖任何 AI 工具的私有格式
- **渐进式暴露**：AI 默认只读取当前有效上下文，按需读取历史和参考资料
- **单一事实源**：每类信息有唯一的权威位置，避免重复维护和冲突
- **决策可追溯**：通过 ADR（Architecture Decision Record）记录重要决策的完整推理过程

## 目录结构

```
template/
  AGENTS.md              # AI 入口文件（~115 行）
  active/                # 当前有效上下文（AI 默认读取）
    Context.md           # 当前阶段目标、事实、约束
    Current_Task.md      # 当前具体任务
  rules/                 # 规则系统（分层加载）
    Always_Active.md     # 每次必须遵守的核心规则
    Project_Rules.md     # 项目级通用规则
    Coding_Rules.md      # 代码任务规则
    Writing_Rules.md     # 写作任务规则
    Review_Rules.md      # 评审任务规则
    ...
  reference/             # 支持性资料（按需读取）
    Project_Brief.md     # 长期目标和愿景
    Architecture.md      # 架构说明
    Tech_Context.md      # 技术环境
    Decisions_Index.md   # 决策索引
    Sources_Index.md     # 外部资料索引
    System_Manual.md     # 系统详细使用手册
  decisions/             # ADR 决策记录
  worklog/               # 工作日志
  archive/               # 历史归档
```

## 使用方法

1. 将 `template/` 目录复制到你的项目中（建议放在 `docs/ai/` 下）
2. `acf.py init docs/ai` 会在项目根目录生成薄入口 `AGENTS.md`，在 `docs/ai/` 下生成完整入口 `AGENTS.md`
3. 根据项目需要填充模板中的占位符
4. AI 进入项目时，从根目录 `AGENTS.md` 开始读取

### 关于两层 AGENTS.md 的设计

这是"**渐进式暴露**"原则的实践：

| 层级 | 文件 | 内容 | 维护者 | 频率 |
|---|---|---|---|---|
| 第一层 | `./AGENTS.md` | 薄入口 + 仓库级约定 | 框架维护者 | 很少改 |
| 第二层 | `docs/ai/AGENTS.md` | 完整上下文导航 | 项目团队 + AI | 按阶段更新 |

目的是在不暴露过多细节的前提下，让 AI 能逐步了解项目上下文结构。

## 信息层级

| 层级 | 目录 | 读取时机 | 说明 |
|------|------|----------|------|
| 1 | active/ | 默认读取 | 当前阶段有效信息 |
| 2 | rules/ | Always_Active 默认，其余按需 | 行为规则 |
| 3 | reference/ | 按需 | 背景资料和索引 |
| 4 | decisions/ | 按需 | 决策详情 |
| 5 | worklog/ | 按需 | 工作历史 |
| 6 | archive/ | 仅明确要求时 | 归档内容 |

## 事实源优先级

冲突时按以下顺序判断：

1. 用户当前消息
2. Current_Task.md
3. Context.md
4. Decisions_Index.md
5. ADR 文件
6. worklog
7. archive

## 命令行工具

本仓库提供一个无第三方依赖的辅助 CLI：

```bash
uv run python acf.py init docs/ai
uv run python acf.py init docs/ai-min --profile minimal
uv run python acf.py simplify docs/ai docs/ai-min
uv run python acf.py new task docs/ai --title "实现一个维护任务" --goal "写清当前目标。"
uv run python acf.py new worklog docs/ai --summary "完成一次上下文维护。"
uv run python acf.py new adr docs/ai --title "记录一个重要决策" --summary "一句话摘要。" --decision "具体决策。"
uv run python acf.py check docs/ai
uv run python acf.py check docs/ai --strict
```

命令说明：

- `init`：从 `template/` 生成标准或简化上下文目录。
- `simplify`：从已有上下文生成只包含核心文件的简化版本，并保留真实 ADR 与 daily worklog，排除占位模板文件。
- `new task`：生成或重置 `active/Current_Task.md`，默认拒绝覆盖 Active 任务，除非传入 `--force`。
- `new worklog`：按日期生成 daily worklog，并更新 `worklog/Worklog_Index.md`。
- `new adr`：生成下一个 ADR 文件，并更新 `reference/Decisions_Index.md`。
- `check`：检查目录结构、必需文件、乱码、空文件、内部引用、状态枚举、索引一致性和占位符残留。

`check` 默认关注结构完整度；`--strict` 适合检查已投入使用的项目上下文，会把占位符残留视为错误。

## 维护与验证

修改模板或 CLI 后运行：

```bash
uv run python acf.py check template
uv run python acf.py check docs/ai --profile minimal --strict
uv run python -m unittest
```

自动化边界和后续路线见 `docs/Automation.md`。
