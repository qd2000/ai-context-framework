# ai-context-framework

本仓库维护一个模型无关的 AI 上下文管理框架。

默认从真实 dogfooding 上下文进入：

1. 先读取 `docs/ai/AGENTS.md`
2. 再按其中的读取顺序读取当前有效上下文

## 仓库级约定

- 文档内容默认使用中文。
- 文件名和目录名使用英文。
- 不依赖特定 AI 模型或私有上下文格式。
- 不要新增运行时依赖，除非用户明确要求。
- `template/` 下的文件是可复制产品模板，占位符（如 `【内容】`）不是当前项目事实。
- `docs/ai/` 是本仓库真实使用中的 AI 上下文实例。
- `.omx/` 是本地运行态目录，不属于项目交付物。

## 修改规则

- 修改 `template/` 时，同步检查 `README.md`、`template/AGENTS.md` 和 `template/reference/System_Manual.md` 是否一致。
- 修改 CLI 时，运行 `python acf.py check template`、`python acf.py check docs/ai --profile minimal` 和 `python -m unittest`。
- 修改维护流程或 subagent 边界时，同步更新 `docs/Automation.md`。
- 不要把 `template/active/` 中的占位内容当作本仓库当前任务事实。
