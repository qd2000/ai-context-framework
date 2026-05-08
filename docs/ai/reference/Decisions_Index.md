本文件是项目重要决策索引。

这里不记录完整决策过程，只记录决策摘要、状态和对应 ADR 文件。详细理由请查看 `decisions/` 中的具体 ADR。

---

## 决策状态说明

- Active：当前有效。
- Proposed：已提出，但尚未最终确认。
- Superseded：已被新决策替代。
- Rejected：已否定，不应继续推进。
- Deprecated：不推荐继续使用，但可能仍有历史影响。

---

## 当前有效决策

<!-- ACF:DECISIONS:INDEX-GENERATED:START -->
| ID | 标题 | 状态 | 摘要 | 详情 |
|---|---|---|---|---|
| ADR-0001 | 使用 `docs/ai` minimal 实例进行 dogfooding | Active | 使用 `docs/ai/` 作为本仓库真实 dogfooding 上下文实例，并采用 minimal profile 初始化。 | `decisions/ADR-0001.md` |
| ADR-0002 | 使用 uv 管理本仓库 Python 运行环境 | Active | 本仓库提交 pyproject.toml 和 uv.lock，Python 代码运行与验证优先使用 uv run python；该约束只写入本仓库 dogfooding 上下文，不写入通用 template 规则。 | `decisions/ADR-0002.md` |
| ADR-0003 | 采用两层 AGENTS.md 入口结构 | Active | 采用两层 AGENTS.md 入口结构： | `decisions/ADR-0003.md` |
| ADR-0004 | 将 acf 演进为可安装的 AI-facing 上下文维护 CLI | Active | 将 acf 从仓库内脚本逐步演进为可安装命令，支持自动发现上下文、机器可读输出、安全结构化编辑和写后检查；语义判断仍由人或 AI 完成，CLI 只负责确定性落盘和校验。 | `decisions/ADR-0004.md` |
| ADR-0005 | 使用可选 Workstream 层管理并行目标线 | Active | 引入可选 Workstream 层，用于表达并行目标线。 | `decisions/ADR-0005.md` |
<!-- ACF:DECISIONS:INDEX-GENERATED:END -->

---

## 待确认决策

| ID | 标题 | 状态 | 摘要 | 需要确认的问题 |
|---|---|---|---|---|
| 暂无 |  |  |  |  |

---

## 已替代决策

| ID | 标题 | 状态 | 被哪个决策替代 | 原因 |
|---|---|---|---|---|
| 暂无 |  |  |  |

---

## 已否定方案

| 方案 | 状态 | 否定原因 | 是否允许重新评估 |
|---|---|---|---|
| 根目录直接铺开 `active/`、`rules/`、`reference/` | Rejected | 会污染仓库根结构，并容易和 `template/` 产品模板混淆。 | 可以在项目规模明显扩大且需要根级上下文时重新评估 |
| 根 `AGENTS.md` 和 `AGENTS.md` 双入口重复维护完整事实 | Rejected | 容易产生事实漂移和重复维护成本。 | 不建议，除非未来工具不支持转发入口 |

---

## 使用规则

AI 使用本文件时，请注意：

1. 先阅读本索引，再决定是否打开具体 ADR。
2. 不要重复推进已否定方案，除非用户明确要求重新评估。
3. 如果索引和旧 worklog 冲突，以本索引为准。
4. 如果需要理解决策原因，请读取对应 ADR 文件。
