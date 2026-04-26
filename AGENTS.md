# ai-context-framework

本仓库维护一个模型无关的 AI 上下文管理框架。

## 仓库约定

- 文档内容默认使用中文。
- 文件名和目录名使用英文。
- 不依赖特定 AI 模型或私有上下文格式。
- `template/` 下的文件是可复制模板，占位符（如 `【内容】`）不是当前项目事实。
- 修改 `template/` 时，应保证复制到新项目后仍能独立使用。

## 当前项目事实

- 本仓库的核心产物是 `template/` 标准上下文模板。
- `acf.py` 是无第三方依赖的辅助 CLI，用于生成、简化和检查上下文模板。
- `.omx/` 是本地运行态目录，不属于项目交付物。

## 任务规则

- 涉及模板结构修改时，同步检查 `README.md`、`template/AGENTS.md` 和 `template/reference/System_Manual.md` 是否一致。
- 涉及 CLI 修改时，运行 `python acf.py check template` 和相关测试。
- 涉及维护流程或 subagent 边界时，同步更新 `docs/Automation.md`。
- 不要把 `template/active/` 中的占位内容当作本仓库当前任务事实。
- 不要新增运行时依赖，除非用户明确要求。
