本文件记录 ACF 代码结构、模块边界和 agent 读取路径。当前由 WS002 初始化，后续随 `acf.py` 模块化拆分同步维护。

---

## 状态

Draft

---

## 维护原则

1. 代码结构优先服务 AI agent 的低上下文维护。
2. 每个模块保持单一职责，避免新的巨型 `common` / `utils` 文件。
3. CLI 行为、JSON 契约、错误码和退出码在模块化迁移期间保持不变。
4. 新增命令必须有明确模块归属，不应继续把实现写回顶层 `acf.py`。

---

## 当前规划

当前详细拆分规划以 [active/workstreams/WS002.md](../active/workstreams/WS002.md) 为准。

---

## 迁移期读取规则

WS002.1 / WS002.2 期间，`acf.py` 仍是实际运行实现入口。agent 修改命令行为前仍应先读取 `acf.py` 中的现有实现，再结合本文件确认目标落点。只有当某个模块在 WS002 阶段证据中标记为已迁移后，才把目标 package 文件当作该领域的事实来源。

---

## 目标代码地图

| 修改对象 | 优先读取文件 |
|---|---|
| CLI 参数、入口、顶层异常处理 | `ai_context_framework/cli.py`, `acf.py` |
| JSON 输出、错误码、next_actions | `ai_context_framework/json_contract.py`, `tests/test_cli.py` |
| 版本号同步 | `ai_context_framework/version.py`, `ai_context_framework/commands/versioning.py`, `pyproject.toml`, `uv.lock` |
| template 发现和打包校验 | `ai_context_framework/templates.py`, `ai_context_framework/validators/template_checks.py`, `pyproject.toml`, `MANIFEST.in` |
| usage log / observability | `ai_context_framework/observability.py`, `ai_context_framework/commands/log.py` |
| Markdown 表格和 section 操作 | `ai_context_framework/markdown.py`, `ai_context_framework/tables.py`, `ai_context_framework/front_matter.py` |
| `check` / `doctor` 校验逻辑 | `ai_context_framework/validators/checks.py`, `ai_context_framework/commands/status_check.py`, `ai_context_framework/commands/doctor.py` |
| Workstream 功能 | `ai_context_framework/domains/workstreams.py`, `ai_context_framework/commands/workstream.py` |
| Archive / Decision / Knowledge / Human / Feedback | 对应 `ai_context_framework/domains/*.py` 与 `ai_context_framework/commands/*.py` |

---

## 依赖边界

1. `commands/*` 只做 CLI handler：读取 argparse namespace、调用 domain/validator、组装输出。
2. 可复用业务规则放入 `domains/*` 或 `validators/*`，不允许 command handler 互相 import。
3. `templates.py` 负责源码态和安装态 template 发现，避免路径逻辑分散。
4. `observability.py` 是 usage log 的共享底座，`commands/log.py` 只承载 `acf log ...` 子命令。
5. `version.py` 是源码版本事实；最终 `acf.py` 只 re-export `VERSION` 并转发 `main()`。
