"""Legacy runtime functions split out for agent-friendly navigation.

Names in this module are rebound by ai_context_framework.runtime so the
migration can stay mechanical while behavior remains unchanged.
"""

from __future__ import annotations
import re

def render_empty_task_plan() -> str:
    return render_task_plan(
        "Empty",
        "无。",
        ["无。"],
        ["无。"],
        "无。",
        [],
    )


def render_feedback_inbox() -> str:
    return """本文件记录人工临时反馈、问题、需求和计划碎片。

这里允许写得不规范。它的作用是先接住重要信号，再由人或 AI 后续整理到 `active/Task_Plan.md`、`active/Context.md`、ADR、worklog 或 Knowledge。

---

## 状态说明

- Open：尚未整理；AI 看到后应先判断归属，不直接视为当前事实。
- Triaged：已判断归属，但尚未完全落盘；后续处理必须说明目标文件、计划项或草案位置。
- Planned：已进入 `active/Task_Plan.md` 或当前任务，等待按计划完成。
- Done：已处理完成，后续处理列必须给出证据位置；只在近期或当前计划仍需引用时保留在 active 表中。
- Rejected：明确不采纳或不再适用，后续处理列必须说明拒绝原因或替代位置；只在近期仍有解释价值时保留。

---

## 反馈条目

| ID | 状态 | 类型 | 内容 | 来源 | 后续处理 |
|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |

---

## 使用规则

1. 人工可以直接追加粗糙描述，不要求一开始就结构化。
2. AI 看到 Open 条目时，应先判断是否需要转入任务计划、当前事实、ADR、worklog、rules、Knowledge 或 writeback 草案。
3. AI 不应把本文件中的随想直接当作已确认事实；只有转入对应事实源或计划后，才按目标文件的事实源级别使用。
4. 状态推进顺序通常是 Open -> Triaged -> Planned -> Done；不采纳时使用 Rejected，并在后续处理列说明原因。
5. Planned 条目必须引用 `active/Task_Plan.md` 的任务 ID、`active/Current_Task.md` 的任务名称，或明确说明等待哪一类落盘动作。
6. Done 或 Rejected 条目必须保留证据位置，例如计划任务、worklog、ADR、Context、Knowledge 草案或拒绝理由。
7. active 表只长期保留 Open、Triaged、Planned，以及当前大任务仍需解释的 Done/Rejected 条目。
8. 清理阈值：当 Done/Rejected 条目超过 10 条，或条目完成超过 30 天且不再支撑当前计划时，应整理到反馈归档。
9. 反馈归档位置使用 `archive/feedback/`，归档文件按月份命名为 YYYY-MM.md；归档摘要应记录 ID、状态、类型、内容摘要、处理结果和证据位置，不复制长过程。
10. AI 执行反馈清理时，应先确认条目已有证据位置，再移动或摘要归档；不能确定是否仍需保留时，生成 writeback 草案而不是删除。
"""


def render_human_notes() -> str:
    return """# Human Notes

本文件记录人工异步写入的随笔、疑问、注释、规划草稿和待确认修改。AI 必须先分类，不得直接把本文件内容当作已确认事实。

---

## Inbox

| ID | 状态 | 类型 | 内容 | 关联位置 | AI 处理建议 | 证据 |
|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |

---

## 使用规则

1. 本文件是 human 层入口，不是 active 当前事实源。
2. `[[双链]]` 只作为人工导航，不替代 ACF 需要解析的标准路径、front matter、heading 或 table。
3. 已确认事实应转写到 `active/Context.md`、`active/Task_Plan.md`、ADR、Knowledge 或 worklog。
4. weekly / reports 中的内容默认不进入 AI 必读路径，只有在回顾、汇报或路线复盘时按需读取。
"""


def render_human_index() -> str:
    return f"""# Human Index

本文件是 human 层的可发现索引。`human/` 保存人类给 AI 上下文系统留下的主观、半结构化材料，包括理解、规划、疑问、解释、整理、随笔、复盘和汇报。

`human/` 默认不进入 AI 必读路径；只有用户明确要求整理/修改 human 内容、当前任务显式引用 human 材料，或需要追溯人工判断来源时才读取。

---

## Materials

{HUMAN_INDEX_TABLE_HEADER}
|---|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |  |

---

## 使用规则

1. `human/` 是输入信号层，不是 active 当前事实源。
2. `Human_Index.md` 只负责发现、状态和追溯，不代表索引条目已经被确认。
3. 已确认事实应整理到 `active/`、ADR、Knowledge、reference 或 worklog 的权威位置。
4. 工具可以机械同步索引；是否已整理为事实必须由人或 AI 语义判断。
"""


def render_task_plan(
    status: str,
    title: str,
    goals: Sequence[str],
    success: Sequence[str],
    focus: str,
    rows: Sequence[dict[str, str]],
) -> str:
    rendered_rows = [
        render_table_row(
            [
                row.get("ID", ""),
                row.get("状态", ""),
                row.get("子任务", ""),
                row.get("依赖", ""),
                row.get("输出物", ""),
                row.get("证据", ""),
                row.get("下一步", ""),
            ]
        )
        for row in rows
    ] or ["| 暂无 |  |  |  |  |  |  |"]
    return f"""本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

{status}

---

## 大任务名称

{title}

---

## 大任务目标

{numbered_list(goals)}

---

## 成功标准

{numbered_list(success)}

---

## 规划依据

{render_plan_reference_section(())}

---

## 当前焦点

{focus}

---

## 子任务

{TASK_TABLE_HEADER}
|---|---|---|---|---|---|---|
{chr(10).join(rendered_rows)}

---

## 任务阶段

{TASK_STAGE_TABLE_HEADER}
|---|---|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |  |  |

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 子任务完成证据优先引用 worklog、测试结果或输出文件路径。
3. 当前大任务依赖 reference 规划时，必须在 `## 规划依据` 列出路径和一句话用途。
4. 已失效的大任务计划应归档到 `archive/plans/`。
5. 不要把历史过程、完整日志或详细推理写入本文件。
"""


def render_archive_index() -> str:
    return f"""本文件记录历史归档索引。

请注意：

- archive 是历史材料，不是当前事实源。
- 默认不要读取 archive；只有需要追溯旧任务、旧计划或比较历史版本时才读取。

---

## 归档条目

{ARCHIVE_INDEX_MARKER_START}
{ARCHIVE_TABLE_HEADER}
|---|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |  |
{ARCHIVE_INDEX_MARKER_END}
"""


def render_knowledge_index() -> str:
    return f"""本文件记录可复用经验索引。

这里只保存从 worklog、ADR、任务复盘或评测中提炼出的经验、模式、反例和判断方法，不保存当前事实、不保存一次性过程、不重复 ADR 或 rules。

---

## Knowledge 状态说明

- Draft：初步提炼，待验证。
- Active：当前可复用经验。
- Promoted：已升级为 rules、ADR、手册或其他权威位置。
- Stale：可能过时，需要重新评估。
- Rejected：提炼错误或不再适用。

---

## Knowledge 条目

{KNOWLEDGE_INDEX_MARKER_START}
{KNOWLEDGE_TABLE_HEADER}
|---|---|---|---|---|---|
| 暂无 |  |  |  |  |  |
{KNOWLEDGE_INDEX_MARKER_END}

---

## 使用规则

1. Knowledge 不是当前事实源。
2. 每条 Knowledge 必须引用来源。
3. Knowledge 只记录可迁移判断，不复述当前状态。
4. 如果经验升级为强约束或重要决策，应标记为 Promoted，并指向新的权威位置。
"""


def upgrade_notes_block(target: str) -> str:
    if target == "agents":
        body = """## ACF Current Schema Upgrade Notes

- 默认读取顺序应包含 `active/Feedback_Inbox.md` 和 `active/Task_Plan.md`，并位于 `active/Current_Task.md` 之前。
- 结构化维护优先使用 `acf plan`、`acf plan reference`、`acf task`、`acf archive` 和 `acf knowledge`。
- `active/Task_Plan.md` 的 `## 规划依据` 用于追溯当前大任务必须对齐的 reference 文档。
- Feedback_Inbox 已处理条目的长期归档位置是 `archive/feedback/`。
- 旧任务或旧计划不会由 `acf upgrade` 自动移动；需要归档时显式运行 archive 命令。"""
    else:
        body = """## ACF Current Schema Upgrade Notes

- `acf upgrade [target]` 只补齐 Feedback_Inbox、Task_Plan、archive、archive/feedback、Knowledge 结构和 active -> reference 规划依据追溯入口。
- 推荐升级流程：`acf upgrade --dry-run --json` -> 审阅 changed_files -> `acf upgrade --check-after --json` -> `acf check --strict --json`。
- Active `active/Current_Task.md` 不会被覆盖，旧任务归档请显式使用 `acf archive current-task` 或 `acf archive task-plan`。"""
    return f"\n\n{UPGRADE_NOTES_START}\n{body}\n{UPGRADE_NOTES_END}\n"


def append_upgrade_notes_if_needed(text: str, target: str) -> str:
    text = migrate_legacy_acf_markers(text)
    if has_upgrade_notes_marker(text):
        return text
    return text.rstrip() + upgrade_notes_block(target)


def section_exists(text: str, heading: str) -> bool:
    try:
        find_section(text.splitlines(), heading)
    except SystemExit:
        return False
    return True


def template_section_body(rel_path: str, heading: str) -> str | None:
    path = TEMPLATE_DIR / rel_path
    if not path.exists():
        return None
    try:
        section = find_section(read_text(path).splitlines(), heading)
    except SystemExit:
        return None
    return section_body(read_text(path).splitlines(), section)


def replace_section_from_template(text: str, rel_path: str, heading: str) -> str:
    if not section_exists(text, heading):
        return text
    body = template_section_body(rel_path, heading)
    if body is None:
        return text
    return replace_section_text(text, heading, body)


def add_context_curation_prompt_entry(text: str) -> str:
    if "reference/Context_Curation_Prompt.md" in text:
        return text
    if has_upgrade_notes_marker(text):
        return text
    row = "| 需要整理、归纳、精简上下文 | `reference/Context_Curation_Prompt.md` |"
    sentence = "需要整理、归纳、精简上下文时，按需读取 `reference/Context_Curation_Prompt.md`。"
    system_manual_row = "| 需要了解系统详细用法 | `reference/System_Manual.md` |"
    knowledge_row_arrow = "| 需要追溯可复用经验 | `reference/Knowledge_Index.md` → `reference/knowledge/*.md` |"
    knowledge_row_ascii = "| 需要追溯可复用经验 | `reference/Knowledge_Index.md` -> `reference/knowledge/*.md` |"
    if system_manual_row in text:
        return text.replace(system_manual_row, f"{row}\n{system_manual_row}")
    if knowledge_row_arrow in text:
        return text.replace(knowledge_row_arrow, f"{knowledge_row_arrow}\n{row}")
    if knowledge_row_ascii in text:
        return text.replace(knowledge_row_ascii, f"{knowledge_row_ascii}\n{row}")
    cli_boundary = "`acf` 只负责结构化落盘、检查和草案生成，不替代人或 AI 对事实和语义的判断。"
    if cli_boundary in text:
        return text.replace(cli_boundary, f"{cli_boundary}\n\n{sentence}")
    cli_heading = "## CLI 辅助维护\n\n"
    if cli_heading in text:
        return text.replace(cli_heading, f"{cli_heading}{sentence}\n\n")
    if "acf new" in text or "acf plan" in text:
        return text.rstrip() + "\n\n" + sentence + "\n"
    return text


def upgraded_agents_text(text: str, include_human: bool = False) -> str:
    text = migrate_legacy_acf_markers(text)
    original = text
    text = text.replace("## 会话结束回写要求", "## 会话结束回写建议")
    if "active/Task_Plan.md" not in text:
        replacements = (
            (
                "3. `active/Current_Task.md`（仅当任务状态为 Active 时）",
                "3. `active/Task_Plan.md`\n4. `active/Current_Task.md`（仅当任务状态为 Active 时）",
            ),
            (
                "3. `active/Current_Task.md`（仅当该文件存在且任务状态为 Active 时）",
                "3. `active/Task_Plan.md`\n4. `active/Current_Task.md`（仅当该文件存在且任务状态为 Active 时）",
            ),
        )
        for old, new in replacements:
            text = text.replace(old, new)
    if "active/Feedback_Inbox.md" not in text and "active/Context.md" in text:
        text = text.replace(
            "2. `rules/Always_Active.md`\n3. `active/Task_Plan.md`",
            "2. `rules/Always_Active.md`\n3. `active/Feedback_Inbox.md`（仅当存在 Open 条目或需要整理人工反馈时）\n4. `active/Task_Plan.md`",
        )
        text = text.replace(
            "4. `active/Current_Task.md`",
            "5. `active/Current_Task.md`",
        )

    text = text.replace(
        "新增或更新当前任务、资料索引、worklog、ADR、section 或 table 时",
        "新增或更新当前计划、当前任务、资料索引、Knowledge 草案、归档、worklog、ADR、section 或 table 时",
    )
    text = text.replace(
        "新增或更新当前计划、当前任务、资料索引、Knowledge 草案、归档、worklog、ADR、section 或 table 时",
        "新增或更新当前计划、规划依据、当前任务、资料索引、Knowledge 草案、归档、worklog、ADR、section 或 table 时",
    )
    text = text.replace(
        "`acf plan`、`acf task`",
        "`acf plan`（包括 `acf plan reference`）、`acf task`",
    )
    text = text.replace(
        "新增或更新当前任务、资料索引、worklog、ADR、section 或 table 时",
        "新增或更新当前计划、当前任务、资料索引、Knowledge 草案、归档、worklog、ADR、section 或 table 时",
    )
    if "不应默认重复打印完整回写建议清单" not in text and section_exists(text, "## 会话结束回写建议"):
        text = replace_section_from_template(text, "AGENTS.md", "## 会话结束回写建议")
    if "active/Feedback_Inbox.md" not in text and section_exists(text, "## 事实源优先级"):
        text = replace_section_from_template(text, "AGENTS.md", "## 事实源优先级")
    if "## 注意力治理与上下文预算" not in text and "## 会话结束回写建议" in text:
        body = template_section_body("AGENTS.md", "## 注意力治理与上下文预算")
        if body is not None:
            text = text.replace(
                "## 会话结束回写建议",
                f"## 注意力治理与上下文预算\n\n{body}\n\n---\n\n## 会话结束回写建议",
            )
    if "archive/feedback" not in text and section_exists(text, "## 目录结构"):
        text = replace_section_from_template(text, "AGENTS.md", "## 目录结构")
    if include_human and "human/Human_Notes.md" not in text and not has_upgrade_notes_marker(text):
        for heading in ("## 目录结构", "## 按需读取指引", "## 事实源优先级", "## 目标信息来源"):
            if section_exists(text, heading):
                text = replace_section_from_template(text, "AGENTS.md", heading)
    text = add_context_curation_prompt_entry(text)
    if "active/Task_Plan.md" not in text and not has_upgrade_notes_marker(text):
        text = append_upgrade_notes_if_needed(text, "agents")
    elif "acf plan" not in text and not has_upgrade_notes_marker(text):
        text = append_upgrade_notes_if_needed(text, "agents")
    return text


def upgraded_feedback_inbox_text(text: str) -> str:
    text = migrate_legacy_acf_markers(text)
    if "archive/feedback/" in text and "只在近期或当前计划仍需引用时保留" in text:
        return text
    if section_exists(text, "## 状态说明"):
        text = replace_section_from_template(text, "active/Feedback_Inbox.md", "## 状态说明")
    if section_exists(text, "## 使用规则"):
        text = replace_section_from_template(text, "active/Feedback_Inbox.md", "## 使用规则")
    return text


def upgraded_project_rules_text(text: str) -> str:
    text = migrate_legacy_acf_markers(text)
    if "旧版本上下文" in text and "`acf upgrade`" in text and "upgrade compatibility" in text:
        return text
    addition = "- 修改模板目录结构、默认上下文结构或 `acf upgrade` 补齐逻辑时，必须评估旧版本上下文能否通过 `acf upgrade` 良好升级；新增结构应同步到 upgrade 文件清单、打包清单、文档、init/upgrade 测试和 upgrade compatibility runner。"
    return text.rstrip() + "\n" + addition + "\n"


def upgraded_system_manual_text(text: str) -> str:
    text = migrate_legacy_acf_markers(text)
    text = text.replace(
        "每次重要协作结束后，AI 应输出标准化的回写建议（格式见 AGENTS.md）。\n\n最终是否写入，由用户决定。",
        "重要协作结束后，AI 不应默认重复打印完整回写建议清单。应先判断哪些内容可以确定落盘，优先使用 `acf plan`、`acf task`、`acf edit`、`acf new worklog`、`acf knowledge draft`、`acf archive` 或 `acf writeback draft` 写入对应文件或草案。\n\n最终回复只报告实际修改的文件、生成的草案、执行的检查和仍需人工判断的风险。没有变化的类别不需要输出“无需更新”。",
    )
    text = text.replace(
        "Feedback_Inbox、Task_Plan、archive 和 Knowledge",
        "Feedback_Inbox、Task_Plan、archive、archive/feedback 和 Knowledge",
    )
    text = text.replace(
        "`active/Task_Plan.md`、archive 和 Knowledge",
        "`active/Task_Plan.md`、archive、archive/feedback 和 Knowledge",
    )
    if "acf upgrade [target]" not in text:
        marker = "### 14.2 常用命令"
        if marker not in text:
            marker = "### 15.2 常用命令"
        if marker in text:
            text = text.replace(
                marker,
                marker
                + "\n\n"
                + "- `acf upgrade [target]`：非破坏式补齐当前版本需要的 Feedback_Inbox、Task_Plan、archive、archive/feedback、Knowledge 结构和 active -> reference 规划依据追溯入口。\n"
                + "- `acf plan init|add-task|set-task|focus|complete|status [target]` / `acf plan reference list|add|remove [target]`：维护当前大任务计划、子任务板和 `## 规划依据`，并在完成后标记计划 Done。\n"
                + "- `acf task start|done|block|clear [target]`：从任务板启动、完成、阻塞或清空当前小任务。\n"
                + "- `acf archive current-task|task-plan|list [target]`：归档旧当前任务或旧大任务计划，并维护归档索引。\n",
            )
    if "旧版本上下文升级" not in text and "CLI 辅助工具" in text:
        insertion = """\n\n### 旧版本上下文升级\n\n推荐流程：`acf status --json` -> `acf upgrade --dry-run --json` -> 审阅 changed_files -> `acf upgrade --check-after --json` -> `acf check --strict --json`。\n\n`upgrade` 只补齐缺失结构和 active -> reference 规划依据追溯入口，不移动旧内容、不自动归档任务、不覆盖 Active `active/Current_Task.md`。旧任务或旧计划需要归档时，升级后显式运行 `acf archive current-task` 或 `acf archive task-plan`；已处理反馈需要长期保存时整理到 `archive/feedback/`。\n"""
        text = text.rstrip() + insertion + "\n"
    if "PowerShell 中反引号是转义字符" not in text:
        text = text.rstrip() + "\n\nPowerShell 中反引号是转义字符。写入包含 Markdown 反引号或多行正文时，优先使用 `--input <file>`。\n"
    if "Feedback_Inbox 生命周期" not in text and section_exists(text, "## 1. active/ 使用规则"):
        body = template_section_body("reference/System_Manual.md", "### 1.2 Feedback_Inbox 生命周期")
        if body is None:
            body = template_section_body("reference/System_Manual.md", "### 1.1 Feedback_Inbox 生命周期")
        if body is not None:
            marker = "\n---\n\n## 2. rules/ 读取策略"
            insertion = f"\n### 1.2 Feedback_Inbox 生命周期\n\n{body}\n\n---\n\n## 2. rules/ 读取策略"
            text = text.replace(marker, insertion)
    if "注意力治理规则" not in text and section_exists(text, "## 13. 更新项目上下文的规则"):
        text = replace_section_from_template(text, "reference/System_Manual.md", "## 13. 更新项目上下文的规则")
    if "Context_Curation_Prompt.md" not in text and "## 4. reference/ 使用规则" in text:
        prompt_row = "| 需要整理、归纳、精简上下文 | `reference/Context_Curation_Prompt.md` |"
        knowledge_row = "| 需要追溯可复用经验 | `reference/Knowledge_Index.md` |"
        if knowledge_row in text:
            text = text.replace(knowledge_row, f"{knowledge_row}\n{prompt_row}")
        prompt_note = "`Context_Curation_Prompt.md` 是按需读取的 AI 整理提示词模板。它用于帮助 AI 归纳、精简、去重并提出上下文整理建议；默认产物是整理建议，不是文件修改。除非用户明确要求落盘，否则不要根据该 prompt 自动修改上下文文件。"
        if prompt_note not in text and "不要默认读取所有 reference 文件。" in text:
            text = text.replace(
                "不要默认读取所有 reference 文件。",
                "不要默认读取所有 reference 文件。\n\n" + prompt_note,
            )
    if "上下文整理提示词模板" not in text and "## 5. reference/ 文件含义" in text:
        system_manual_line = "- **System_Manual.md**：本文件，系统详细使用手册。"
        prompt_line = "- **Context_Curation_Prompt.md**：上下文整理提示词模板，仅在需要整理、归纳、精简上下文时按需读取；不进入默认读取路径。"
        if system_manual_line in text:
            text = text.replace(system_manual_line, f"{prompt_line}\n{system_manual_line}")
    if "旧版本上下文升级" not in text and "CLI 辅助工具" in text:
        insertion = """\n\n### 旧版本上下文升级\n\n推荐流程：`acf status --json` -> `acf upgrade --dry-run --json` -> 审阅 changed_files -> `acf upgrade --check-after --json` -> `acf check --strict --json`。\n\n`upgrade` 只补齐缺失结构和 active -> reference 规划依据追溯入口，不移动旧内容、不自动归档任务、不覆盖 Active `active/Current_Task.md`。旧任务或旧计划需要归档时，升级后显式运行 `acf archive current-task` 或 `acf archive task-plan`；已处理反馈需要长期保存时整理到 `archive/feedback/`。\n"""
        text = text.rstrip() + insertion + "\n"
    if "修改 `template/`、默认上下文结构、打包清单或 `acf upgrade` 行为" not in text and "旧版本上下文升级" in text:
        addition = "\n\n维护本框架时，如果修改 `template/`、默认上下文结构、打包清单或 `acf upgrade` 行为，必须同时评估旧版本上下文的升级路径。新增结构应同步到 init 文件清单、upgrade 补齐清单、`pyproject.toml` data-files、文档、init/upgrade 单元测试和 upgrade compatibility runner；入口或手册变更不能安全重排旧文档时，应通过 marker notes 非破坏式提示。\n"
        text = text.rstrip() + addition
    if "acf upgrade [target]" not in text and not has_upgrade_notes_marker(text):
        text = append_upgrade_notes_if_needed(text, "manual")
    if "PowerShell 中反引号是转义字符" not in text:
        text = text.rstrip() + "\n\nPowerShell 中反引号是转义字符。写入包含 Markdown 反引号或多行正文时，优先使用 `--input <file>`。\n"
    return text


def upgraded_task_plan_text(text: str) -> tuple[str, str | None]:
    if section_exists(text, PLAN_REFERENCE_HEADING):
        return text, None
    body = render_plan_reference_section((), upgrade_prompt=True)
    try:
        return insert_section_after(text, "## 成功标准", PLAN_REFERENCE_HEADING, body), None
    except SystemExit:
        pass
    try:
        return insert_section_before(text, "## 当前焦点", PLAN_REFERENCE_HEADING, body), None
    except SystemExit:
        return text, "active/Task_Plan.md: could not safely insert ## 规划依据; no known anchor matched"


def upgraded_current_task_text(text: str) -> tuple[str, str | None]:
    if not current_task_has_active_status(text):
        return text, None
    try:
        section = find_section(text.splitlines(), "## 输入材料")
    except SystemExit:
        return text, "active/Current_Task.md: could not append plan reference prompt because ## 输入材料 was not found"
    if CURRENT_TASK_REFERENCE_PROMPT in text:
        return text, None
    body_lines, suffix = section_content_and_suffix(text.splitlines(), section)
    stripped = [line.strip() for line in body_lines if line.strip()]
    if stripped == [PLAN_REFERENCE_EMPTY]:
        body_lines = [CURRENT_TASK_REFERENCE_PROMPT]
    else:
        insert_at = len(body_lines)
        while insert_at > 0 and not body_lines[insert_at - 1].strip():
            insert_at -= 1
        body_lines.insert(insert_at, CURRENT_TASK_REFERENCE_PROMPT)
    return apply_section_body(text.splitlines(), section, body_lines, suffix), None


def ensure_upgrade_structure(root: Path, dry_run: bool) -> tuple[list[Path], list[str]]:
    profile = infer_context_profile(root)
    planned = [
        root / "active" / "Feedback_Inbox.md",
        root / "active" / "Task_Plan.md",
        root / "active" / "Current_Task.md",
        root / "archive" / "Archive_Index.md",
        root / "reference" / "Knowledge_Index.md",
        root / "reference" / "Context_Curation_Prompt.md",
        root / "archive" / "tasks" / ".gitkeep",
        root / "archive" / "plans" / ".gitkeep",
        root / "archive" / "feedback" / ".gitkeep",
        root / "reference" / "knowledge" / ".gitkeep",
        root / "worklog" / "knowledge-drafts" / ".gitkeep",
    ]
    if profile == "standard":
        planned.extend(human_layer_paths(root))
    changed = [path for path in planned if not path.exists()]
    agents = root / "AGENTS.md"
    feedback = root / "active" / "Feedback_Inbox.md"
    task_plan = root / "active" / "Task_Plan.md"
    current_task = root / "active" / "Current_Task.md"
    project_rules = root / "rules" / "Project_Rules.md"
    manual = root / "reference" / "System_Manual.md"
    warnings: list[str] = []
    if task_plan.exists():
        original_plan = read_text(task_plan)
        updated_plan, warning = upgraded_task_plan_text(original_plan)
        if updated_plan != original_plan:
            changed.append(task_plan)
        if warning:
            warnings.append(f"{task_plan}: {warning}")
    if current_task.exists():
        original_task = read_text(current_task)
        updated_task, warning = upgraded_current_task_text(original_task)
        if updated_task != original_task:
            changed.append(current_task)
        if warning:
            warnings.append(f"{current_task}: {warning}")
    if agents.exists():
        original_agents = read_text(agents)
        updated_agents = upgraded_agents_text(original_agents, include_human=profile == "standard")
        if updated_agents != original_agents:
            changed.append(agents)
            if not has_upgrade_notes_marker(original_agents) and has_upgrade_notes_marker(updated_agents):
                warnings.append(f"{agents}: append upgrade notes because no known AGENTS.md pattern matched")
    if feedback.exists():
        original_feedback = read_text(feedback)
        updated_feedback = upgraded_feedback_inbox_text(original_feedback)
        if updated_feedback != original_feedback:
            changed.append(feedback)
    if project_rules.exists():
        original_rules = read_text(project_rules)
        updated_rules = upgraded_project_rules_text(original_rules)
        if updated_rules != original_rules:
            changed.append(project_rules)
    if manual.exists():
        original_manual = read_text(manual)
        updated_manual = upgraded_system_manual_text(original_manual)
        if updated_manual != original_manual:
            changed.append(manual)
            if not has_upgrade_notes_marker(original_manual) and has_upgrade_notes_marker(updated_manual):
                warnings.append(f"{manual}: append upgrade notes because no known System_Manual.md pattern matched")

    if dry_run:
        return changed, warnings

    for path in planned:
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.name == "Task_Plan.md":
            path.write_text(render_empty_task_plan(), encoding="utf-8")
        elif path.name == "Feedback_Inbox.md":
            template_feedback = TEMPLATE_DIR / "active" / "Feedback_Inbox.md"
            path.write_text(read_text(template_feedback) if template_feedback.exists() else render_feedback_inbox(), encoding="utf-8")
        elif path.name == "Archive_Index.md":
            path.write_text(render_archive_index(), encoding="utf-8")
        elif path.name == "Knowledge_Index.md":
            path.write_text(render_knowledge_index(), encoding="utf-8")
        elif path.name == "Context_Curation_Prompt.md":
            template_prompt = TEMPLATE_DIR / "reference" / "Context_Curation_Prompt.md"
            path.write_text(read_text(template_prompt) if template_prompt.exists() else "", encoding="utf-8")
        elif path.name == "Human_Notes.md":
            template_human = TEMPLATE_DIR / "human" / "Human_Notes.md"
            path.write_text(read_text(template_human) if template_human.exists() else render_human_notes(), encoding="utf-8")
        elif path.name == "Human_Index.md":
            template_human_index = TEMPLATE_DIR / "human" / "Human_Index.md"
            path.write_text(read_text(template_human_index) if template_human_index.exists() else render_human_index(), encoding="utf-8")
        else:
            path.write_text("", encoding="utf-8")

    if agents.exists():
        text = read_text(agents)
        updated = upgraded_agents_text(text)
        if updated != text:
            agents.write_text(updated, encoding="utf-8")

    if feedback.exists():
        text = read_text(feedback)
        updated = upgraded_feedback_inbox_text(text)
        if updated != text:
            feedback.write_text(updated, encoding="utf-8")

    if task_plan.exists():
        text = read_text(task_plan)
        updated, _warning = upgraded_task_plan_text(text)
        if updated != text:
            task_plan.write_text(updated, encoding="utf-8")

    if current_task.exists():
        text = read_text(current_task)
        updated, _warning = upgraded_current_task_text(text)
        if updated != text:
            current_task.write_text(updated, encoding="utf-8")

    if project_rules.exists():
        text = read_text(project_rules)
        updated = upgraded_project_rules_text(text)
        if updated != text:
            project_rules.write_text(updated, encoding="utf-8")

    if manual.exists():
        text = read_text(manual)
        updated = upgraded_system_manual_text(text)
        if updated != text:
            manual.write_text(updated, encoding="utf-8")

    return changed, warnings


def upgrade_managed_paths(root: Path) -> list[Path]:
    paths = [
        root / "active" / "Feedback_Inbox.md",
        root / "active" / "Task_Plan.md",
        root / "archive" / "Archive_Index.md",
        root / "reference" / "Knowledge_Index.md",
        root / "reference" / "Context_Curation_Prompt.md",
        root / "archive" / "tasks" / ".gitkeep",
        root / "archive" / "plans" / ".gitkeep",
        root / "archive" / "feedback" / ".gitkeep",
        root / "reference" / "knowledge" / ".gitkeep",
        root / "worklog" / "knowledge-drafts" / ".gitkeep",
        root / "AGENTS.md",
        root / "rules" / "Project_Rules.md",
        root / "reference" / "System_Manual.md",
    ]
    if infer_context_profile(root) == "standard":
        paths.extend(human_layer_paths(root))
    return paths


def upgrade_detected_features(root: Path) -> list[str]:
    features: list[str] = []
    feature_paths = [
        ("context_agents", root / "AGENTS.md"),
        ("task_plan", root / "active" / "Task_Plan.md"),
        ("feedback_inbox", root / "active" / "Feedback_Inbox.md"),
        ("archive", root / "archive" / "Archive_Index.md"),
        ("feedback_archive", root / "archive" / "feedback"),
        ("knowledge", root / "reference" / "Knowledge_Index.md"),
        ("context_curation_prompt", root / "reference" / "Context_Curation_Prompt.md"),
        ("system_manual", root / "reference" / "System_Manual.md"),
        ("human", root / "human" / "Human_Notes.md"),
        ("workstreams", root / "active" / "Workstreams.md"),
    ]
    for name, path in feature_paths:
        if path.exists():
            features.append(name)
    return features


def upgrade_contract_payload(root: Path, changed_files: Sequence[Path]) -> dict[str, object]:
    changed_resolved = {path.resolve() for path in changed_files}
    planned_changes = [
        {"path": str(path.resolve()), "action": "create_or_update"}
        for path in changed_files
    ]
    skipped_changes = [
        {"path": str(path.resolve()), "reason": "already_current"}
        for path in upgrade_managed_paths(root)
        if path.resolve() not in changed_resolved and path.exists()
    ]
    return {
        "detected_features": upgrade_detected_features(root),
        "planned_changes": planned_changes,
        "skipped_changes": skipped_changes,
    }


def upgrade_command(args: argparse.Namespace) -> int:
    return init_upgrade_commands.upgrade_command(
        args,
        maybe_check_after=maybe_check_after,
        ensure_upgrade_structure=ensure_upgrade_structure,
        upgrade_contract_payload=upgrade_contract_payload,
    )


