"""Narrow regression checks for retired-capability references in current authority docs.

These checks intentionally target a few exact markers instead of broad keyword bans,
so that historical archive material, negative tokens and test fixtures stay allowed.
"""

import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTEXT = ROOT / "docs" / "ai"
AUTOMATION = ROOT / "docs" / "Automation.md"

ARCHIVED_WS013_PLAN = (
    CONTEXT / "archive" / "plans" / "2026-09-18-ws013-observer-retirement-and-v0.0.3.92-plan.md"
)


class RetiredReferenceTests(unittest.TestCase):
    def read(self, path: pathlib.Path) -> str:
        return path.read_text(encoding="utf-8")

    def test_automation_doc_separates_current_contract_from_history(self):
        text = self.read(AUTOMATION)
        self.assertIn("## 当前有效自动化合同", text)
        self.assertIn("## 历史演进说明：WS012 与 Project Observer（已退役 / 已归档）", text)
        self.assertIn("没有默认后台消费者", text)

    def test_automation_doc_does_not_assign_issue_triage_to_archived_ws012(self):
        text = self.read(AUTOMATION)
        self.assertNotIn("WS012 Maintenance Writer 负责把该跨项目 issue 池", text)
        self.assertNotIn("### WS012 动态用户需求与 live steering", text)
        self.assertNotIn("正式 `:34` Production Observer 仍独立负责", text)

    def test_automation_doc_does_not_claim_trusted_publishing_is_unconfigured(self):
        text = self.read(AUTOMATION)
        self.assertNotIn("Trusted Publishing 配置仍需", text)
        self.assertNotIn("还需配置 PyPI 项目和 Trusted Publishing", text)

    def test_active_context_has_no_machine_absolute_path(self):
        text = self.read(CONTEXT / "active" / "Context.md")
        self.assertIsNone(
            re.search(r"[A-Za-z]:[\\/]", text),
            "active/Context.md must not embed machine absolute paths",
        )

    def test_active_context_does_not_restate_current_release_version(self):
        text = self.read(CONTEXT / "active" / "Context.md")
        self.assertNotIn("当前稳定发布版本", text)
        self.assertNotIn("当前已发布稳定版本", text)
        self.assertIn("不在 Context 中复制固定数字", text)

    def test_archived_ws013_plan_is_not_in_active_reference(self):
        self.assertFalse(
            (CONTEXT / "reference" / "ws013_observer_retirement_ws012_closeout").exists(),
            "terminal WS013 plan must live under archive/plans, not reference/",
        )
        self.assertTrue(ARCHIVED_WS013_PLAN.is_file())

    def test_ws011_project_observer_docs_are_marked_historical(self):
        reference_dir = CONTEXT / "reference" / "ws011_project_observer"
        for name in ("DESIGN.md", "PLAN.md", "SCHEDULED_TASK_PROMPT.md"):
            text = self.read(reference_dir / name)
            self.assertIn("Historical / Inactive", text, f"{name} must be marked historical")
        design = self.read(reference_dir / "DESIGN.md")
        self.assertNotIn("正由 WS012 继续演进，最终 authority 以 WS012 当前 PLAN 为准", design)


if __name__ == "__main__":
    unittest.main()
