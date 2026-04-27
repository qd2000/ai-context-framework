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

补充 acf 任意目录安装与验收说明

---

## 本次任务目标

1. 说明如何把 acf 安装到 PATH，使任意目录可直接运行 acf。
2. 区分本仓库开发入口、可安装工具入口和上下文自动发现行为。
3. 增加测试防止 console script 配置被误删。

---

## 任务背景

任意目录安装与验收说明已补充。

---

## 输入材料

- pyproject.toml 的 project.scripts 配置。
- README.md 命令行工具章节。
- template/reference/System_Manual.md CLI 辅助工具章节。

---

## 输出要求

- README 已增加全局安装和任意目录验证说明。
- System Manual 已增加 CLI 可用性和安装方式提示。
- tests/test_cli.py 已覆盖 console script 打包入口配置。

---

## 成功标准

1. 文档明确 uv tool install -e .、uv tool update-shell、where/which acf 和 acf status --json 验收路径。
2. 说明任意目录可运行 acf 不等于任意目录都有上下文。
3. 完整 uv 验证通过。

---

## 失败信号

1. 目标无法验证。
2. 任务范围需要重新确认。

---

## 约束条件

1. 不新增第三方运行依赖。
2. 不实际执行全局安装修改用户环境。
3. 不改变 CLI 行为。

---

## 不允许做的事

- 本轮不发布 PyPI。

---

## 需要 AI 协助判断的问题

1. 无。

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 应写入 `active/Context.md` 的新增当前事实。
2. 应写入 `reference/Decisions_Index.md` 或 ADR 的重要决策。
3. 应写入 rules 的新增规则。
4. 应归档到 archive 的历史内容。
