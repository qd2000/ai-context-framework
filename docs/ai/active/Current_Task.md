本文件记录当前正在处理的具体任务。

- 长期目标请查看：`reference/Project_Brief.md`
- 当前阶段目标请查看：`active/Context.md`
- 本文件只维护当前具体任务

如果用户在当前对话中提出了新的具体需求，并且该需求与本文件冲突，以用户当前消息为准。

---

## 当前任务状态

Done

说明：

- Active：当前任务正在进行
- Paused：当前任务暂停
- Done：当前任务已完成
- Empty：暂无需要写入文件的当前任务

---

## 任务名称

引入 uv dogfooding Python 运行环境

---

## 本次任务目标

1. 新增最小 `pyproject.toml`，声明 `requires-python = ">=3.10"` 且无依赖。
2. 使用 `uv lock` 生成 `uv.lock`。
3. 将本仓库 Python 运行约定改为优先使用 `uv run python ...`。
4. 更新根 `AGENTS.md`、`rules/Project_Rules.md`、README、`../Automation.md` 和当前上下文。
5. 不把 uv 要求写入通用 `template/` 规则。

---

## 任务背景

本仓库已经开始 dogfooding 自己的上下文框架，并持续增加 Python CLI 能力。为了避免不同解释器或全局环境影响验证结果，需要把本仓库自身的 Python 运行入口固定到项目 uv 环境。

---

## 输入材料

- 用户批准的 uv dogfooding 计划。
- 当前 `acf.py` CLI 和测试。
- 当前 dogfooding 上下文。

---

## 输出要求

- `pyproject.toml`
- `uv.lock`
- `.gitignore` 忽略 `.venv/`
- README 和 dogfooding 规则中的 Python 示例使用 `uv run python ...`
- 当前上下文记录 uv 环境事实和验证要求

---

## 成功标准

1. `uv lock --check` 通过。
2. `uv run python acf.py check docs/ai --profile minimal --strict` 通过。
3. `uv run python acf.py check template` 通过。
4. `uv run python -m unittest` 通过。
5. `uv run python -m py_compile acf.py tests\test_cli.py` 通过。
6. 通用 `template/` 不新增 uv 专属要求。

---

## 失败信号

1. 仍在本仓库维护规则中要求直接运行 `python ...`。
2. `uv.lock` 与 `pyproject.toml` 不一致。
3. 新增了第三方依赖。
4. uv 要求泄漏到通用模板规则中。

---

## 约束条件

1. 继续保持无第三方运行依赖。
2. Python 版本约束为 `>=3.10`。
3. uv 要求只作用于本仓库 dogfooding 和维护流程。
4. 不实现新的 CLI 功能。

---

## 不允许做的事

- 不把 uv 作为生成模板的默认要求。
- 不引入依赖包。
- 不删除已有 dogfooding 文件。

---

## 需要 AI 协助判断的问题

本任务已完成。下一步优先判断 `new adr`、`new task`、`new source` 的最小接口。

---

## 完成后的回写要求

已写入：

1. `active/Context.md`：更新 uv 运行环境事实和约束。
2. `rules/Project_Rules.md`：新增本仓库 Python 运行规则。
3. `worklog/Worklog_Index.md` 和 daily worklog：记录本次工作。
4. README、`../Automation.md`、根 `AGENTS.md`：更新维护命令。
