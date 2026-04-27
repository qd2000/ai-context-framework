这些规则适用于本项目的大多数任务。

- 第一版优先简单可用。
- 文档内容使用中文。
- 文件名和目录名使用英文。
- 不依赖某个特定 AI 模型。
- 本仓库运行 Python 代码时，优先使用项目 uv 环境：`uv run python ...`。
- 当前项目使用 `pyproject.toml` 和 `uv.lock` 固定 uv 解析结果，不新增第三方依赖。
- 修改当前任务时优先使用 `uv run python acf.py new task ...`。
- 添加资料索引时优先使用 `uv run python acf.py new source ...`，并只记录摘要、可信度、相关性和后续动作，不保存大段原文。
- 记录重要设计决策时优先使用 `uv run python acf.py new adr ...`，并确保编号不与既有 ADR 冲突。
- 记录当天整理后工作记录时优先使用 `uv run python acf.py new worklog ...`；同日已有记录时，按当前 CLI 能力审慎使用 `--force` 或人工合并。
- 修改 `template/` 前先判断该内容是否属于可复用产品模板；本仓库 dogfooding 专属要求应写入根入口、`docs/ai/` 或维护文档。
- 修改 `template/` 后必须同步检查 README、template 入口说明、System Manual 和 `../Automation.md` 是否一致。
- 对可确定的重复维护动作，优先补 CLI 或 check 规则，而不是只补说明文字。
