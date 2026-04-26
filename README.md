# ai-context-framework

一个模型无关的 AI 上下文管理框架模板。

## 设计理念

人与 AI 的协作中，人作为最高决策层，AI 同时作为执行者和策略建议者。项目知识不应随 AI 工具更换或人员离开而丢失。

本框架通过分层的 Markdown 文件结构管理项目上下文，实现：

- **模型无关**：纯 Markdown，不依赖任何 AI 工具的私有格式
- **渐进式暴露**：AI 默认只读取当前有效上下文，按需读取历史和参考资料
- **单一事实源**：每类信息有唯一的权威位置，避免重复维护和冲突
- **决策可追溯**：通过 ADR（Architecture Decision Record）记录重要决策的完整推理过程

## 目录���构

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
2. 在项目根目录放置 `AGENTS.md`（或 `CLAUDE.md`），指向上下文目录
3. 根据项目需要填充模板中的占位符
4. AI 进入项目时，从 `AGENTS.md` 开始读取

## 信息层级

| 层级 | 目录 | 读取时机 | 说明 |
|------|------|----------|------|
| 1 | active/ | 默认读取 | 当前阶段有效信息 |
| 2 | rules/ | Always_Active 默认，其余按需 | 行为规则 |
| 3 | reference/ | 按需 | 背景资料和索引 |
| 4 | decisions/ | 按需 | 决策详情 |
| 5 | worklog/ | 按需 | 工作历史 |
| 6 | archive/ | 仅明确要求时 | 归档内容 |

## 事实��优先级

冲突时按以下顺序判断：

1. 用户当前消息
2. Current_Task.md
3. Context.md
4. Decisions_Index.md
5. ADR 文件
6. worklog
7. archive
