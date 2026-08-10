"""Template discovery and profile file inventories."""

from __future__ import annotations

import sysconfig
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]


def find_template_dir() -> Path:
    source_template = SOURCE_ROOT / "template"
    installed_template = (
        Path(sysconfig.get_path("data"))
        / "share"
        / "ai-context-framework"
        / "template"
    )

    # Some installers leave a partial ``site-packages/template`` directory
    # while installing data-files under the interpreter's data prefix. Only
    # treat the source path as authoritative when its root marker is present;
    # otherwise prefer the complete installed data-files location.
    if (source_template / "AGENTS.md").is_file():
        return source_template

    if installed_template.is_dir():
        return installed_template

    return source_template


TEMPLATE_DIR = find_template_dir()

STANDARD_DIRS = (
    "active",
    "human",
    "human/weekly",
    "human/reports",
    "rules",
    "reference",
    "reference/sources",
    "reference/knowledge",
    "decisions",
    "worklog",
    "worklog/daily",
    "worklog/knowledge-drafts",
    "archive",
    "archive/tasks",
    "archive/plans",
    "archive/feedback",
)

STANDARD_FILES = (
    "AGENTS.md",
    "active/Context.md",
    "active/Current_Task.md",
    "active/Feedback_Inbox.md",
    "active/Task_Plan.md",
    "human/Human_Index.md",
    "human/Human_Notes.md",
    "human/weekly/.gitkeep",
    "human/reports/.gitkeep",
    "rules/Always_Active.md",
    "rules/Project_Rules.md",
    "rules/Coding_Rules.md",
    "rules/Writing_Rules.md",
    "rules/Review_Rules.md",
    "rules/Rules_Index.md",
    "rules/Agent_Requested.md",
    "rules/Manual_Only.md",
    "reference/Project_Brief.md",
    "reference/Architecture.md",
    "reference/Tech_Context.md",
    "reference/Decisions_Index.md",
    "reference/Knowledge_Index.md",
    "reference/Context_Curation_Prompt.md",
    "reference/Sources_Index.md",
    "reference/sources/.gitkeep",
    "reference/knowledge/.gitkeep",
    "reference/System_Manual.md",
    "decisions/ADR-0001-template.md",
    "worklog/Worklog_Index.md",
    "worklog/daily/YYYY-MM-DD.md",
    "worklog/knowledge-drafts/.gitkeep",
    "archive/Archive_Index.md",
    "archive/tasks/.gitkeep",
    "archive/plans/.gitkeep",
    "archive/feedback/.gitkeep",
)

MINIMAL_DIRS = (
    "active",
    "rules",
    "reference",
    "reference/knowledge",
    "decisions",
    "worklog",
    "worklog/daily",
    "worklog/knowledge-drafts",
    "archive",
    "archive/tasks",
    "archive/plans",
    "archive/feedback",
)

MINIMAL_FILES = (
    "AGENTS.md",
    "active/Context.md",
    "active/Current_Task.md",
    "active/Feedback_Inbox.md",
    "active/Task_Plan.md",
    "rules/Always_Active.md",
    "rules/Project_Rules.md",
    "reference/Project_Brief.md",
    "reference/Decisions_Index.md",
    "reference/Knowledge_Index.md",
    "reference/Context_Curation_Prompt.md",
    "reference/Sources_Index.md",
    "reference/knowledge/.gitkeep",
    "worklog/Worklog_Index.md",
    "worklog/knowledge-drafts/.gitkeep",
    "archive/Archive_Index.md",
    "archive/tasks/.gitkeep",
    "archive/plans/.gitkeep",
    "archive/feedback/.gitkeep",
)
