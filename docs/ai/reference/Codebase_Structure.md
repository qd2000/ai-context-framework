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

当前详细拆分规划以已归档的 [archive/workstreams/WS002.md](../archive/workstreams/WS002.md) 为准。

---

## 迁移期读取规则

当前处于 WS002.6 迁移期：`ai_context_framework.cli` 已是 console-script 入口，`acf.py` 是顶层兼容 shim。`ai_context_framework/runtime.py` 只保留 parser/main、顶层异常处理、兼容命名空间安装和旧入口承接；仍未完全下沉的 legacy helper 已按领域切到 `ai_context_framework/runtime_parts/*.py`，避免形成新的单文件巨型上下文。已迁移的命令实现以对应 `ai_context_framework/commands/*.py` 为事实来源。

Workstream 命令当前已迁移到 `ai_context_framework/commands/workstream.py`；迁移期 Workstream 兼容包装、受限 `__getattr__` 转发和未下沉 workflow helper 位于 `ai_context_framework/runtime_parts/archive_workstream.py`。`ai_context_framework/domains/workstreams.py` 是后续领域下沉目标，当前尚未创建。

---

## 目标代码地图

| 修改对象 | 优先读取文件 |
|---|---|
| CLI 参数、入口、顶层异常处理 | `ai_context_framework/cli.py`, `ai_context_framework/runtime.py`, `acf.py` shim |
| JSON 输出、错误码、next_actions | `ai_context_framework/json_contract.py`, `tests/test_cli.py` |
| 版本号同步 | `ai_context_framework/version.py`, `ai_context_framework/commands/versioning.py`, `pyproject.toml`, `uv.lock` |
| template 发现和打包校验 | `ai_context_framework/templates.py`, `ai_context_framework/validators/template_checks.py`, `pyproject.toml`, `MANIFEST.in` |
| usage log / observability | `ai_context_framework/observability.py`, `ai_context_framework/commands/log.py` |
| Markdown 表格和 section 操作 | `ai_context_framework/markdown.py`, `ai_context_framework/tables.py`, `ai_context_framework/front_matter.py` |
| `check` / `doctor` 校验逻辑 | `ai_context_framework/validators/checks.py`, `ai_context_framework/commands/status_check.py`, `ai_context_framework/commands/doctor.py`, `ai_context_framework/runtime_parts/check.py`, `ai_context_framework/runtime_parts/doctor.py` |
| Workstream 命令与本地 workflow helper | `ai_context_framework/commands/workstream.py`, `ai_context_framework/runtime_parts/archive_workstream.py` |
| 迁移期 legacy helper | `ai_context_framework/runtime_parts/*.py`；按文件名选择最窄上下文读取 |
| Workstream 领域规则下沉目标 | 后续 `ai_context_framework/domains/workstreams.py`；当前尚未创建 |
| Archive / Decision / Knowledge / Human / Feedback | 对应 `ai_context_framework/domains/*.py` 与 `ai_context_framework/commands/*.py` |

---

## 依赖边界

1. `commands/*` 只做 CLI handler：读取 argparse namespace、调用 domain/validator、组装输出。
2. 可复用业务规则放入 `domains/*` 或 `validators/*`，不允许 command handler 互相 import。
3. `templates.py` 负责源码态和安装态 template 发现，避免路径逻辑分散。
4. `observability.py` 是 usage log 的共享底座，`commands/log.py` 只承载 `acf log ...` 子命令。
5. `version.py` 是源码版本事实；`acf.py` 只 re-export `VERSION`、转发 `main()`，并通过 `__getattr__` 保留旧 import 兼容。
6. `runtime.py` 和 `runtime_parts/*` 是迁移期兼容层，不是新增业务落点；后续新增或修改业务逻辑应继续下沉到 `commands/*`、`domains/*` 或 `validators/*`，避免把任一迁移期文件变成新的长期巨型模块。
