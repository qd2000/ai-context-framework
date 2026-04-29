本文件记录本仓库技术环境。

---

## 技术栈

- 语言：Python。
- Python 版本：`>=3.10`。
- 包管理：uv。
- 测试工具：Python 标准库 `unittest`。
- 打包：`pyproject.toml` + setuptools。
- 运行时依赖：当前不引入第三方运行依赖。

---

## 目标运行环境

| 环境 | 是否必须支持 | 备注 |
|---|---|---|
| Windows | 是 | 当前主要 dogfooding 环境是 Windows PowerShell。 |
| Linux | 应支持 | 纯 Python 与普通文件路径应保持兼容。 |
| macOS | 应支持 | 纯 Python 与普通文件路径应保持兼容。 |

---

## 关键技术约束

1. 上下文文件必须保持普通 Markdown。
2. CLI 输出应同时支持人类可读文本和机器可读 JSON。
3. 写命令应支持 dry-run 和 changed_files。
4. usage log 不记录正文输入、stdin、Markdown diff 或完整 stdout/stderr。
5. 版本号需要同步 CLI 常量、包配置和相关元数据。

---

## 外部工具依赖

| 工具 | 用途 | 是否必需 | 替代方案 |
|---|---|---|---|
| uv | 本仓库开发、测试和 CLI 运行 | 开发期必需 | 直接使用 Python 运行部分命令 |
| git | 差异检查和版本管理 | 开发期必需 | 无 |

---

## 技术债记录

1. `acf.py` 仍是单文件 CLI，后续命令继续增长时需要拆分模块。
2. `uv.lock` 和 egg-info 在版本更新时需要保持同步。
3. 标准模板中的示例文件包含占位符，真实项目 strict 检查需要区别模板源和项目实例。
