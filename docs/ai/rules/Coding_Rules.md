本文件记录本仓库代码修改规则。

---

## Python 与 CLI

1. 修改 Python 代码优先保持无第三方运行依赖。
2. 本仓库运行 Python 代码优先使用 `uv run python ...`。
3. 本仓库运行 CLI 优先使用 `uv run acf ...`。
4. CLI 写命令应继续支持 JSON、dry-run、changed files、error_code 和 next_actions 契约。
5. 新增 CLI 子命令时，应补充 unittest 覆盖和帮助文档。

---

## 测试要求

涉及 CLI 行为时，至少运行：

1. `uv run python -m unittest`
2. `uv run python -m py_compile acf.py tests\test_cli.py`

涉及模板或上下文检查时，额外运行：

1. `uv run acf check template`
2. `uv run acf check --strict`

---

## 版本要求

1. 修改 CLI 对外行为、模板结构、打包文件或命令契约时，需要判断是否更新 version number。
2. 仅修改注释、内部文档错别字或不影响交付物的本地记录时，可以不更新版本。
3. 需要更新版本时，优先使用 `uv run acf version set <version>`。
