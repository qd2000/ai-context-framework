本文件是本仓库 dogfooding 上下文的规则索引。

AI 默认只读取 [rules/Always_Active.md](Always_Active.md)。其他规则按任务类型读取，避免上下文噪音。

---

## 默认规则

| 文件 | 读取条件 | 作用 |
|---|---|---|
| `Always_Active.md` | 每次协作默认读取 | 核心事实边界、上下文读取顺序和维护约束 |

---

## 按需规则

| 文件 | 读取条件 | 作用 |
|---|---|---|
| `Project_Rules.md` | 涉及项目通用约束、目录维护、版本、发布和 dogfooding | 项目级默认约束 |
| `Coding_Rules.md` | 涉及 `acf.py`、测试、打包、CLI 行为 | 代码修改与验证规则 |
| `Writing_Rules.md` | 涉及 README、System Manual、上下文文档和 worklog | 文档写作规则 |
| `Review_Rules.md` | 涉及方案评审、代码评审、风险检查 | 评审输出规则 |
| `Agent_Requested.md` | AI 判断当前任务需要额外规则时 | 帮助选择额外规则 |
| `Manual_Only.md` | 用户明确要求特殊模式时 | 特殊协作模式规则 |

---

## 冲突处理

1. 用户当前消息优先。
2. 仓库根 `AGENTS.md` 优先于本索引。
3. 更具体的规则优先于更通用的规则。
4. 事实源冲突时，先指出冲突，再按事实源优先级处理。
