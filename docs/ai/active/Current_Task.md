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

让 `docs/ai` dogfooding 上下文通过 strict 检查

---

## 本次任务目标

1. 改进 `acf.py check --strict`，使其区分真实项目文件和明确模板文件。
2. 清理 `reference/Sources_Index.md` 中的占位符，使资料索引成为真实空索引。
3. 更新 dogfooding 规则，使 CLI 修改时验证 `docs/ai` strict 检查。
4. 补充测试覆盖 strict 忽略明确模板文件的行为。

---

## 任务背景

`docs/ai` 初始化后，minimal 实例仍包含 `decisions/ADR-0001-template.md`、`worklog/daily/YYYY-MM-DD.md` 和未填的 `reference/Sources_Index.md`。这导致真实 dogfooding 上下文无法通过 `--strict`。其中前两者是明确模板文件，应允许保留占位符；资料索引是项目事实文件，应替换为真实空索引。

---

## 输入材料

- `python acf.py check docs/ai --profile minimal --strict` 的失败输出。
- `active/Context.md` 中记录的 strict dogfooding 开放问题。
- `acf.py` 当前的 placeholder 检查逻辑。

---

## 输出要求

- `acf.py check --strict` 只把非模板文件占位符作为错误。
- `reference/Sources_Index.md` 不再保留占位符。
- `docs/ai` strict 检查通过。
- 相关文档和测试同步更新。

---

## 成功标准

1. `python acf.py check docs/ai --profile minimal --strict` 通过。
2. `python acf.py check template` 通过。
3. `python -m unittest` 通过。
4. `python -m py_compile acf.py tests\test_cli.py` 通过。
5. `reference/Sources_Index.md` 不含占位符。

---

## 失败信号

1. `--strict` 对真实项目上下文仍因明确模板文件失败。
2. `--strict` 对普通项目文件中的占位符不再报错。
3. 模板自身检查或单元测试回归失败。

---

## 约束条件

1. 不删除当前 generated 模板文件。
2. 不引入新依赖。
3. 不改变 `template/` 作为产品模板的占位符语义。

---

## 不允许做的事

- 不把所有占位符都静默忽略。
- 不让 strict 对真实项目文件失去约束力。
- 不实现下一批 `new ...` 命令。

---

## 需要 AI 协助判断的问题

本任务已完成。后续优先判断 `new worklog`、`new adr`、`new task`、`new source` 的最小接口。

---

## 完成后的回写要求

已写入：

1. `active/Context.md`：更新 strict dogfooding 当前事实和开放问题。
2. `worklog/daily/2026-04-26.md`：追加本次工作记录。
3. `../Automation.md` 和根 `AGENTS.md`：更新 dogfooding 验证规则。
