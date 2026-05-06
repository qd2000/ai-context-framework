本文件记录当前正在处理的具体任务。

- 长期目标请查看：`reference/Project_Brief.md`
- 当前阶段目标请查看：`active/Context.md`
- 当前大任务计划请查看：`active/Task_Plan.md`
- 本文件只维护当前具体任务

如果用户在当前对话中提出了新的具体需求，并且该需求与本文件冲突，以用户当前消息为准。

---

## 当前任务状态

Active

---

## 任务名称

PR 1：Task Stage registry

---

## 所属大任务

P0 governance hardening: task-stage registry, authority write gate, merge resolution, active retention gate

---

## 子任务 ID

T001

---

## 本次任务目标

1. 在 `Task_Plan.md` 模板中新增 `## 任务阶段` 表。
2. 支持 `T001.4` 这类阶段编号，但要求必须注册。
3. `Current_Task.md` 引用阶段编号时，普通 check 和 strict check 都必须验证该阶段存在。
4. 阶段父任务必须存在于 `## 子任务` 表。
5. 阶段绑定的 Workstream 必须存在；如果被当作当前执行线，不能是 Done / Cancelled。

---

## 任务背景

FCC dogfooding 暴露了 `T001.4` 这类阶段编号可以凭空出现在 `Current_Task.md` 中，而 `Task_Plan.md` 没有对应注册表。该问题不应依赖 AI 或人工复核发现，应由 `acf check` 机械拦截。

---

## 输入材料

- `active/Task_Plan.md`
- `active/Current_Task.md`
- `../../template/active/Task_Plan.md`
- `acf.py`
- `tests/test_cli.py`
- `reference/Workstream_Design.md`

---

## 输出要求

1. 新增 stage ID regex，例如 `TASK_STAGE_ID_RE = T\d{3}\.\d+`。
2. 新增 `## 任务阶段` 表解析。
3. 新增 Current_Task 阶段引用检查。
4. 新增单元测试覆盖未注册阶段、父任务缺失、Workstream 缺失、Done/Cancelled 当前执行线。
5. 更新模板和相关文档。

---

## 成功标准

1. 未注册 `T001.4` 在普通 check 和 strict check 中都失败。
2. 父任务不存在时失败。
3. 当前执行线绑定 Done / Cancelled Workstream 时失败。
4. 阶段表中引用 Done / Cancelled Workstream 作为历史依赖或 evidence 不误伤。
5. 基线验证命令通过。

---

## 失败信号

1. 为了支持 `T001.4` 引入 task object 单文件。
2. 让旧项目因缺少 `## 任务阶段` 表直接失败。
3. 把历史依赖中的 Done Workstream 误判为当前执行线错误。
4. 未同步模板、测试和设计文档。

---

## 约束条件

1. 本阶段只做确定性门禁，不做语义事实裁决。
2. 保持无第三方运行依赖。
3. 保持旧项目兼容；缺少阶段表本身不应报错，只有引用阶段编号时才要求注册。

---

## 不允许做的事

- 不新增 active/tasks/T001.4.md。
- 不把 Task_Plan 全面改造成对象系统。
- 不引入 content audit 到默认 strict。
- 不自动修改 FCC 项目内容。

---

## 需要 AI 协助判断的问题

1. 阶段表字段是否足够支持 FCC 这类复杂项目。
2. Current_Task 中如何稳定识别“当前执行线”而不是历史 evidence。
3. 普通 check 与 strict check 的错误等级是否需要进一步细分。

---

## 完成后的回写要求

任务完成后，请整理以下内容，供人审核后写回项目系统：

1. 应写入 `active/Context.md` 的新增当前事实。
2. 应写入 `reference/Workstream_Design.md` 的设计规则。
3. 应写入 `../../Automation.md` 的路线和验证命令。
4. 应写入 worklog 的实现和验证摘要。
