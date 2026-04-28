这些规则适用于本项目的大多数任务。

- 第一版优先简单可用。
- 文档内容使用中文。
- 文件名和目录名使用英文。
- 不依赖某个特定 AI 模型。
- 如果项目可用 `acf`，上下文维护优先考虑 `acf check`、`acf upgrade`、`acf plan`、`acf task`、`acf archive`、`acf knowledge`、`acf new`、`acf edit` 和 `acf writeback`。
- 写入风险较高或需要先审阅变更范围时，优先使用 `--dry-run --json`；写入后可使用 `--check-after`。
- `acf` 只负责确定性结构维护、检查和草案生成，不做事实裁决。
- `active/Task_Plan.md` 只放轻量子任务板，旧任务和旧计划应归档，Knowledge 只保存可复用经验而不是当前事实。
