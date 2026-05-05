这些规则适用于本项目的大多数任务。

- 第一版优先简单可用。
- 文档内容使用中文。
- 文件名和目录名使用英文。
- 不依赖某个特定 AI 模型。
- 如果项目可用 `acf`，上下文维护优先考虑 `acf check`、`acf upgrade`、`acf plan`、`acf task`、`acf archive`、`acf knowledge`、`acf new`、`acf edit` 和 `acf writeback`。
- 写入风险较高或需要先审阅变更范围时，优先使用 `--dry-run --json`；写入后可使用 `--check-after`。
- `acf` 只负责确定性结构维护、检查和草案生成，不做事实裁决。
- `active/Task_Plan.md` 只放轻量子任务板，旧任务和旧计划应归档，Knowledge 只保存可复用经验而不是当前事实。
- 修改模板目录结构、默认上下文结构或 `acf upgrade` 补齐逻辑时，必须评估旧版本上下文能否通过 `acf upgrade` 良好升级；新增结构应同步到 upgrade 文件清单、打包清单、文档、init/upgrade 测试和 upgrade compatibility runner。
