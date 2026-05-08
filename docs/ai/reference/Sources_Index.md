本文件记录项目相关资料索引。

这里只保存资料摘要和用途，不保存大段原文。需要详细内容时，再打开原始资料。

---

## 资料状态说明

- To Read：待读。
- Reading：正在读。
- Read：已读。
- Useful：确认有用。
- Archived：已归档。
- Rejected：已确认不适合本项目。

---

## 核心资料

| 资料 | 类型 | 链接或位置 | 状态 | 可信度 | 和本项目的关系 | 后续动作 |
|---|---|---|---|---|---|---|
| Front Matter Metadata Plan | 设计计划 | [reference/Front_Matter_Metadata_Plan.md](Front_Matter_Metadata_Plan.md) | Useful | 高 | 记录轻量 YAML front matter 的适用文档清单、字段建议、实施阶段、check 规则和兼容性策略。 | 作为 Workstream 可选层和后续 metadata 支持的设计依据；实现前按需读取。 |
| ACF Top-Level Design | 顶层设计 | [reference/ACF_Top_Level_Design.md](ACF_Top_Level_Design.md) | Useful | 高 | 记录 ACF 的产品定位、内容分层、对象模型、CLI 分层、Workstream 闭环、audit 边界、多项目验证矩阵和升级兼容原则。 | 新增对象、规则、CLI 命令、模板结构或 upgrade 行为前必须按需读取，用于判断是否符合顶层边界。 |
| Top-Level Implementation Gap | 实施差距矩阵 | [reference/Top_Level_Implementation_Gap.md](Top_Level_Implementation_Gap.md) | Useful | 高 | 将 ACF 顶层设计逐项映射到当前实现，标记已实现、部分实现、未实现、不应实现、需补测试、需补文档和需补 upgrade 兼容项。 | 进入新代码 PR 前按需读取，优先选择 gap-driven 实施切片；当前推荐下一 PR 为 marker helper + Knowledge sync MVP。 |
| Generated Marker Sync Design | 设计文档 | [reference/Generated_Marker_Sync_Design.md](Generated_Marker_Sync_Design.md) | Useful | 高 | 定义 Knowledge、ADR 和 Archive sync 前置的 generated marker 契约、同步边界、删除策略、JSON 契约和下一代码切片。 | 实现 `knowledge sync`、`decisions sync`、`archive sync` 或通用 marker helper 前必须读取。 |
| Python argparse documentation | 文档 | https://docs.python.org/3/library/argparse.html | Useful | 高 | 用于维护 acf.py CLI 子命令、参数和帮助文本行为。 | 按需查阅，不默认读取全文。 |
| Real Project Upgrade Playbook | 操作手册 | [reference/Real_Project_Upgrade_Playbook.md](Real_Project_Upgrade_Playbook.md) | Useful | 高 | 记录 ACF v0.0.3.12 应用到真实项目时的旁路接入、旧上下文升级、Workstream optional 边界和验收表。 | 执行真实项目接入或旧上下文升级试点前按需读取；试点结果写入 worklog。 |
| Product Roadmap | 产品路线 | [reference/Product_Roadmap.md](Product_Roadmap.md) | Useful | 高 | 记录 ACF 分阶段路线、真实项目反馈准入门槛、当前已完成薄切片、Phase A-F 实施顺序和近期优先级。 | 排定新增规则、对象字段、audit/check/sync 能力或验证矩阵优先级前按需读取。 |
| Non-PetroSim Dogfooding Sample | dogfooding 样本记录 | [reference/Non_PetroSim_Dogfooding_Sample.md](Non_PetroSim_Dogfooding_Sample.md) | Useful | 高 | 记录 EcSOS `cracking-yield-prediction-system` 作为非 PetroSim 真实样本的选择理由、只读检查结果和后续写入边界。 | 进入 P3 audit rule expansion 或真实项目验证前按需读取。 |
| Upgrade Migration Plan | 设计计划 | [reference/Upgrade_Migration_Plan.md](Upgrade_Migration_Plan.md) | Useful | 高 | 记录旧版本上下文升级到新版本的阶段、兼容性原则、Workstream/front matter 可选启用策略、测试矩阵和 JSON 输出契约。 | 实现 Workstream、front matter 或模板结构变化前必须读取，并同步 init/upgrade/check 测试。 |
| Workstream Design | 设计文档 | [reference/Workstream_Design.md](Workstream_Design.md) | Useful | 高 | 记录多 agent 并行目标线治理方案、front matter 取舍、状态机、合并契约和后续 CLI/check 计划。 | 作为 T001 设计依据；后续实现 Workstream 可选层时按需读取。 |
| Workstream Lifecycle Archive Design | 设计文档 | [reference/Workstream_Lifecycle_Archive_Design.md](Workstream_Lifecycle_Archive_Design.md) | Useful | 高 | 记录 Done / Cancelled Workstream 从 active 保留到 archive 的生命周期边界、候选 helper、archive draft、显式 archive 命令、索引清理和 marker 规则。 | 修改 Workstream 归档生命周期、archive-draft、archive 命令或索引 cleanup 前必须读取；当前结论是只通过显式单个 archive 命令移动文件，不让 sync/upgrade 自动归档。 |

---

## 已否定资料

| 资料 | 否定原因 | 是否需要保留 |
|---|---|---|
| 暂无 |  |  |

---

## 使用规则

AI 使用本文件时，请注意：

1. 这里只是资料索引，不是事实来源本身。
2. 不要把资料摘要当作完整证据。
3. 需要准确引用时，应查看原始资料。
4. 资料的可信度需要显式说明。
