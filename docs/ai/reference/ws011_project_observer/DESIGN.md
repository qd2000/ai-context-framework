# ACF Project Observer 完整初版设计

## 1. 定位与目标

ACF Project Observer 是**项目级自治执行可观测系统**。

它不是简单把 Workstream 编号、continuation status、Git HEAD 或 Gate 编号搬进页面，而是持续回答：

- 当前每个长期任务究竟在解决什么问题；
- 为什么现在进行这一步；
- 最近实际证明、排除或改变了什么；
- 当前是否正常推进、合理等待、停滞或异常；
- 下一步是什么，以及为什么是这个下一步；
- 原始技术标识、证据和语义解释如何互相对应。

Observer 必须把 Git、ACF、Workstream、continuation、计划、代码、测试、evidence 和可选项目运行时状态转换为**详细、准确、易懂、可追溯的人类语义进展**。

---

## 2. 管理域

采用：

> **一个项目一个 Global Observer。**

同一项目内部的多个 checkout / worktree 由同一个 Project Observer 统一观察。

当前系统不假定：

- 项目只有固定数量；
- 电脑只有固定数量；
- 项目访问工具只有某个固定 MCP 名称；
- 项目一定运行在本机、某个盘符或某个固定 DevSpace 实例。

Project Observer Core **不得硬编码任何电脑名、MCP 名称、盘符、VM 名称或具体项目路径**。

项目访问方式属于外部运行合同，由 Scheduled Task wrapper、调用方或后续 project profile 注入，例如“使用当前项目配置的 workspace/MCP 工具打开项目并执行只读观察”。Observer Core 只处理已经获得的项目路径、结构化状态和证据。

当前明确不纳入：

- 跨项目聚合 Dashboard；
- 跨电脑统一 Dashboard；
- HTTP 服务；
- 常驻 daemon / resident runtime；
- Observer 自动接管 Writer。

这些不是为了简化而删除，而是当前需求边界本身不需要。

---

## 3. Writer 与 Observer 职责边界

### Writer Agent

负责：

```text
理解任务
→ 修改代码/文档
→ 运行测试
→ 执行受控外部副作用
→ Git checkpoint
→ continuation 状态推进
```

### Observer Agent

负责：

```text
读取项目和所有相关 worktree
→ 获取一致性观察
→ 理解当前任务上下文
→ 判断实际进展与健康状态
→ 检测变化和异常
→ 生成人类可理解语义解释
→ 更新 Observer state/history
→ 生成静态 Dashboard
```

核心权限原则：

> **Read broad, write narrow, control none.**

---

## 4. 权限模型

### 4.1 广泛读取

Observer 可以按需读取整个项目管理域：

- primary checkout；
- ACF registry 中的项目 worktree；
- Workstream context/detail；
- PLAN / 当前任务规划；
- continuation state；
- Git status / log / HEAD；
- tests / evidence / reports / output；
- 当前任务必要代码；
- 当前任务必要 reference；
- 项目 profile 明确允许的 Runtime / Campaign / external status 等只读状态。

读取采用渐进式披露，不等于每小时扫描整个仓库。

### 4.2 狭窄写入

Observer 运行态只允许写用户级：

```text
~/.acf/projects/<project-id>/observer/
```

不得因为生成 Dashboard 而修改项目 Git worktree。

默认禁止写：

- 项目源码和测试；
- `docs/ai/active/`；
- Workstream PLAN；
- Git index / commit；
- continuation state / lease / effect journal；
- Runtime / Campaign 控制状态。

### 4.3 无控制权

Observer 默认禁止：

- continuation claim / challenge / recover / release；
- Workstream 状态修改；
- Runtime / Campaign submit；
- merge；
- project fix。

发现异常时执行：

```text
检测 → 解释 → Alert
```

而不是：

```text
检测 → 自动修复 Writer/control plane
```

---

## 5. 存储位置与产品边界

Observer 属于本地 operational state，不属于项目 canonical Markdown 上下文，因此统一放在：

```text
~/.acf/projects/<project-id>/observer/
```

这保证：

- 不产生 Git dirty；
- 不影响 Workstream scope；
- 不污染项目事实源；
- 不参与 Writer checkpoint；
- 不产生 continuation workspace provenance 冲突。

ACF 的项目权威上下文仍保持 Markdown-first、可人工审阅；Observer JSON/HTML 与 continuation JSON 一样属于本地运行态。

---

## 6. 输出格式

常规 Observer 输出只需要：

```text
结构化 Observer State
+
自包含静态 HTML
```

默认不生成 `dashboard.md`。

Markdown 只在以下场景生成：

- 用户明确要求导出；
- 需要形成长期项目报告；
- 需要进入 Knowledge / Worklog / Archive；
- 需要 Git 审阅。

---

## 7. Dashboard 形式

当前采用**自包含静态 HTML**。

不启动 `127.0.0.1:<port>`，不引入 HTTP server、WebSocket、常驻进程或 Windows 服务。

`dashboard.html` 必须能直接通过 `file://` 打开；页面所需当前状态和历史摘要由 renderer 内嵌，不依赖浏览器从本地再 `fetch` JSON。

HTML 只是展示层，不是状态事实源；任何时候都可以从 Observer state 重建。

时间合同固定为：Observer structured state/history/semantic 中的 canonical 时间戳继续统一保存为 UTC；`dashboard.html` 中所有人类可见时间统一渲染为北京时间 `UTC+08:00` 并明确标注。展示时区转换不得改写底层 UTC、事件排序、dedupe、fingerprint 或 provenance 时间事实。

---

## 8. Observer 数据结构

建议结构：

```text
observer/
├─ state/
│  ├─ current.json
│  ├─ timeline.jsonl
│  ├─ observations.jsonl
│  ├─ alerts.jsonl
│  └─ runs.jsonl
│
├─ workstreams/
│  └─ <workstream-id>/
│     ├─ current.json
│     └─ timeline.jsonl
│
├─ semantic/
│  ├─ glossary.json
│  └─ interpretations.jsonl
│
├─ history/
├─ archive/
├─ lock.json
├─ observer_status.json
└─ dashboard.html
```

所有核心结构必须从第一版开始带：

- `schema_version`；
- `project_id`；
- `observed_at`；
- source / provenance；
- canonical identity；
- semantic interpretation version。

后续 schema 升级必须支持 deterministic migration。

---

## 9. Current State

`state/current.json` 表示 Observer 最近一次**成功且通过一致性检查**的项目当前状态。

包括：

- Observer 更新时间；
- data age；
- overall health；
- 当前 Workstreams；
- alerts；
- 每个 Workstream 的 execution / progress / health；
- 本轮 snapshot consistency；
- 当前语义解释版本。

该文件覆盖更新，不承担历史保存职责。

---

## 10. 历史保存原则

核心原则：

> **所有有信息价值的项目进展历史默认永久保存，除非用户明确要求删除。**

必须永久保存的 meaningful history 包括：

- Workstream 创建和完成；
- Stage / 研究路线变化；
- 关键实验、验证和失败；
- 新证据；
- commit；
- blocker 出现和解除；
- owner 转移；
- Runtime / Campaign 关键结果；
- Gate 结论；
- 语义解释发生实质更新。

不因为时间久、worktree 生命周期长或文件增长而自动删除。

---

## 11. History 不等于重复 Snapshot

连续多个完全相同的小时级观察没有新增项目信息，不需要重复保存完整快照。

例如：

```text
09:00 running C04
10:00 running C04
11:00 running C04
```

可以保持 current 不变，同时每个 Observer activation 只在 `runs.jsonl` 留轻量 liveness 记录。

长时间无变化本身具有信息价值，因此可以生成里程碑式 observation，例如“连续 6h 无 meaningful progress”“连续 12h 无 meaningful progress”，而不是每小时复制全量状态。

---

## 12. 历史分片但不删除

长期 history 增长时允许：

```text
history/
├─ 2026-08.jsonl
├─ 2026-09.jsonl
└─ ...
```

或按 Workstream 生命周期分片。

要求：

- 不丢数据；
- 不自动清除；
- 有索引；
- 能完整重建历史。

这是 **rotation without deletion**，不是 retention cleanup。

---

## 13. Observer 自身运行与健康

每次 activation 在 `runs.jsonl` 留轻量记录：

```json
{
  "run_id": "...",
  "started_at": "...",
  "finished_at": "...",
  "status": "success",
  "workstreams_scanned": 3
}
```

`observer_status.json` 至少包含：

- `last_started`；
- `last_success`；
- `last_failure`；
- `last_duration`；
- Observer version；
- scanned worktrees；
- errors；
- current data age。

Dashboard 顶部必须明显显示最后更新时间和数据是否陈旧，防止旧页面被误认为实时状态。

---

## 14. 一致性快照

Writer 可能在 Observer 读取期间修改项目。

Observer 开始读取前记录 fingerprint，例如：

- Git HEAD；
- relevant worktree dirty digest；
- continuation generation / state updated_at；
- Workstream status；
- 项目 profile 声明的关键 external identity。

读取结束后重新获取 fingerprint。

若开始与结束 fingerprint 不一致：

1. 自动重新读取一次；
2. 如果仍变化，标记 `snapshot_consistency=unstable`；
3. 不生成高置信度的新语义结论；
4. Dashboard 明确说明本次是部分一致快照。

禁止把两个不同时间点的状态拼接成一个看似确定的项目事实。

---

## 15. Observer 自身互斥

Observer 使用自己的轻量 `lock.json`，只保护 Observer 输出。

它与 continuation lease、Workstream ownership、Writer effect 完全独立。

若下一次 activation 到来时前一个 Observer 仍健康运行：

- 不覆盖对方输出；
- 记录 overlap；
- 安全退出或仅做不落盘观察。

Observer lock 不得成为 Writer 的新阻塞条件。

---

## 16. 真正无副作用的观察接口

Observer 为了读取状态不得：

- ACK challenge；
- 修改 lease；
- 改 workspace ownership；
- 更新 continuation 控制状态；
- 触发 recover。

长期产品接口应提供明确 Observer-safe 只读入口，例如：

```text
acf observer snapshot
```

并在需要时提供底层 `continuation inspect --read-only` 类能力。

如果已有 status/doctor 命令存在任何可观察写入，Observer Core 必须绕开这些控制面副作用或提供专门只读路径。

---

## 17. Execution、Progress、Health 分离

Dashboard 必须把三个维度分开：

### Execution State

- running；
- waiting_external；
- idle；
- blocked；
- done。

### Progress State

- advancing；
- unchanged；
- slow；
- regressing；
- unknown。

### Health State

- healthy；
- warning；
- critical。

例如一个 Workstream 可以同时是：

```text
Execution: waiting_external
Progress: 两小时没有新阶段
Health: healthy
```

因为“合理等待”不是故障。

---

## 18. 不制造假百分比

只有存在明确分母时才允许百分比，例如：

- 28 / 64 experiments；
- 7 / 10 数据批次；
- 明确冻结的 Gate 总数。

开放研究任务不得凭感觉生成 `73%` 一类假精度。

开放研究应展示：

- 当前阶段；
- 已解决问题；
- 当前问题；
- 尚未解决问题；
- 最近逻辑推进；
- 下一决策点。

---

## 19. Semantic Observation Layer

Observer 的核心能力不是“机器状态采集”，而是 **Project Progress Interpreter**。

完整链路：

```text
Git / ACF / Workstream / Runtime / Evidence
                    +
PLAN / 必要 reference / 必要代码与测试
                    ↓
             Fact Normalization
                    ↓
          Semantic Interpretation
                    ↓
          Human Progress Narrative
                    ↓
                Dashboard
```

语义解释发生在 Observer state 层，HTML 只是 renderer。

---

## 20. Canonical Identity 与人类语义并存

任何翻译都不能替换原始技术身份。

例如原始：

```text
P0 C04 riser inlet/section source-state crosswalk
```

主页面可以显示：

> 提升管入口及分段状态来源梳理

同时必须保留：

```text
原始标识：P0 C04 riser inlet/section source-state crosswalk
```

原始名称可放在次级文字、tooltip、折叠技术详情或 monospace badge 中，保证随时可定位、搜索和核对。

---

## 21. 详细语义进展要求

不能只展示 `C04 进行中` 或 `已完成 C14`。

每个核心 Workstream 的当前解释至少回答：

1. **当前在解决什么**；
2. **为什么现在做这个**；
3. **最近真正证明、排除或改变了什么**；
4. **这个结论意味着什么**；
5. **下一步是什么，为什么是它**。

例如：

> 正在确认当前软件版本中提升管入口和各分段真正公开了哪些状态，并区分直接可读状态、可由公开公式转换的状态、其他模块负责的状态和软件内部未公开状态。前面的循环与产品侧边界已经基本关闭，现在必须明确反应器入口状态来源，才能继续构建不伪造未知关系的机理模型。上一阶段已确认某公开接口无法可靠给出目标能量负荷，因此不再继续盲目增加运行测试，该量保持为不可观测状态。当前来源映射完成后，再决定哪些状态能够进入模型实现、哪些继续保留为显式未知。

---

## 22. Meaningful Progress Event

Observer 应将低级事件：

```text
commit
test
checkpoint
stage change
runtime terminal observation
```

组合为人类可理解的 meaningful progress event。

机器事件仍保留在技术详情中，主 Timeline 展示的是“做了什么、证明什么、意味着什么”。

---

## 23. Semantic Glossary

维护：

```text
semantic/glossary.json
```

用于稳定解释项目内部英文缩写、编号和术语。

每个条目至少包含：

- canonical term；
- human display name；
- explanation；
- confidence；
- provenance；
- interpretation version。

Glossary 是 Observer 解释缓存，不是项目权威事实源。

---

## 24. Interpretation History

语义解释允许随证据改进，但不能静默覆盖历史。

例如：

```text
v1: 提升管入口状态映射
v2: 提升管入口及轴向分段状态来源与归属梳理
```

记录 `semantic_interpretation_updated`，保存：

- canonical identity；
- old interpretation；
- new interpretation；
- observed_at；
- change reason；
- provenance。

---

## 25. Semantic Confidence

重要语义判断必须带 confidence：

- `authoritative`：项目权威文档直接定义；
- `high`：多个独立上下文一致支持；
- `medium`：证据明显支持但不是正式定义；
- `low`：暂译或仍存在歧义。

低置信度解释必须在 Dashboard 标注“暂译 / 当前理解”，并同时展示 canonical name。

---

## 26. Provenance

重要结论尽可能携带来源：

- stage 来源 continuation / Workstream；
- 当前目标来源 PLAN；
- 最近成果来源 commit + evidence；
- external waiting 来源 Runtime/Campaign authority；
- semantic translation 来源 glossary / 文档定义。

技术详情应可展开看到：

- 文件路径；
- commit；
- effect / external identity；
- evidence ref；
- observed_at。

Observer 解释项目，但不能替项目创造事实。

---

## 27. 上下文读取策略

Observer 读取权限宽，但遵守渐进式披露：

```text
第一层：Workstream + continuation + PLAN
↓ 不足
当前 Gate / 当前阶段文档
↓ 不足
最近 evidence / commit
↓ 不足
必要代码和测试
```

目标是**语义足够完整**，而不是文件读取数量最大。

---

## 28. 增量语义更新

每小时不能完全重新写一篇项目总结。

每轮使用：

```text
上一版 semantic state
+ 本轮真实新事实
→ 判断什么发生变化
→ 只更新受影响部分
```

避免表述漂移、重复作文、同一术语不断换译法。

上一版 semantic state 只用于 diff，不是事实源；与当前项目事实冲突时必须以项目事实为准。

Semantic source fingerprint 必须覆盖会让人类叙述失真的稳定/物质事实，例如 continuation ownership generation 与 unresolved effect risk；不得仅因为 heartbeat 刷新或 terminal effect 历史计数累加而失效。这样既避免把 owner/effect 已变化的旧叙述继续标为 `current`，也避免无意义的高频语义抖动。

---

## 29. Alert 系统

至少分：

### Critical

- control-plane deadlock；
- unresolved non-idempotent effect；
- workspace conflict；
- Observer 数据严重陈旧；
- 权威状态互相矛盾；
- snapshot 无法得到可信一致视图。

### Warning

- 长时间没有 meaningful progress；
- 等待异常延长；
- semantic confidence 太低；
- external job 长期无新证据。

### Info

- 正常 waiting_external；
- 新 Stage；
- 正常 owner contention；
- 新 checkpoint；
- 普通状态变化。

每个 Alert 必须解释为什么重要，不只显示 severity 名称。

---

## 30. 颜色设计

颜色用于引导注意力，不做装饰，也不作为唯一信息载体。

固定语义建议：

- **红色**：Critical、明确故障、必须关注的阻塞、数据不可信；
- **琥珀/黄色**：Warning、异常等待、需要关注、中低置信度解释；
- **绿色**：健康、明确通过的验证、稳定正常状态；
- **蓝色**：当前正在推进、当前关注点、Active、一般信息性状态；
- **灰色**：canonical identity、历史状态、辅助 metadata、非当前信息。

颜色必须同时配合：

- 文本；
- 状态名称；
- 图标/符号；
- 必要边框或 badge。

不得仅靠颜色表达严重性，以保证色觉差异、黑白打印和显示异常下仍能理解。

---

## 31. 字体与视觉层级

不使用巨大标题或超大数字制造重点。

页面重点主要依赖：

- 颜色；
- 信息层级；
- 空间；
- 分组；
- 边框；
- badge。

建议范围：

- 页面标题约 22–24px；
- section 约 17–20px；
- Workstream 主标题约 16–18px；
- 正文约 14–16px；
- 技术 metadata 约 12–14px；
- 重要数值通常不超过 24–28px。

核心目标是适合持续阅读，而不是营销页面。

---

## 32. Dashboard 信息结构

第一屏回答：

> 项目现在整体怎么样？

建议：

```text
项目总览
├─ Observer 更新时间 / data age
├─ Overall Health
├─ Active Workstreams
├─ 当前 Alerts
└─ 最近重大进展
```

每个 Workstream 至少展示：

```text
人类语义标题 + 简洁编号
Canonical ID / 原始名称

当前目标
当前正在解决的问题
为什么这一步重要

最近实际进展
最近证明 / 排除 / 改变的内容
这些结果意味着什么

当前阻塞 / 等待
是否属于正常等待

下一步
为什么是这个下一步

Execution / Progress / Health

技术详情
├─ worktree / branch / HEAD
├─ continuation generation / lease summary
├─ unresolved effect summary
├─ canonical stage
└─ evidence / provenance
```

---

## 33. Timeline、搜索与展开

每个 Workstream 提供人类语义 Timeline，并可展开原始技术证据。

静态 HTML 可以使用内联 JavaScript 提供：

- Workstream 筛选；
- Alert 筛选；
- 技术详情展开；
- Timeline 折叠；
- canonical term 搜索。

不需要 HTTP 服务。

---

## 34. Secrets 与敏感信息过滤

Observer 读取权限很大，因此禁止复制：

- API key；
- token；
- password；
- license 内容；
- private key；
- fence token；
- credential；
- 完整敏感环境变量。

若只需要表达存在性，记录类似：

```text
credential_present=true
```

而不是值本身。

---

## 35. Project Profile 与工具抽象

Observer Core 保持项目无关。

项目可以提供 observation / semantic profile，例如：

```text
Observer Core
+ Project Observation Profile
+ Project Access Adapter / Scheduled Wrapper
```

Profile 可声明：

- 项目特有状态源；
- 项目术语和语义解释边界；
- 可选 Runtime / external read-only probes；
- 哪些事实源属于 authoritative/high/medium；
- 哪些目录可按需读取。

Project Access Adapter / wrapper 负责“如何进入项目”，包括当前可用的 workspace/MCP 工具，但这些名称不得进入 Observer Core schema 或通用产品文档的固定假设。

---

## 36. Scheduled Task 角色

Scheduled Task 只是 Observer 的定时唤醒器，不是 Observer 本体。

正式运行时，一个项目只维护一个 production Observer Scheduled Task；它固定观察项目 primary checkout，并调用稳定安装态 Observer workflow。开发/维护 Writer 必须使用另一个任务与独立 Workstream，不能把 production watchdog 和 Writer 合成同一个 scheduler owner。

production Observer 的权限边界保持：

```text
read broad
write ~/.acf/projects/<project-id>/observer/ only
control none
```

它不得 claim/challenge/recover Writer、修改 Git/Workstream、升级工具或直接修代码。发现问题只输出 Alert/diagnostic，由独立 Maintenance Workstream 修复。

生产 Observer 与 Maintenance Writer 应错峰运行，给 Writer 的真实变化留出稳定观察间隔。具体分钟属于项目 wrapper/调度配置，不进入 Observer Core schema；ACF 自身当前 dogfood 采用 Writer `:04`、Observer `:34`。

每轮必须：

1. 使用项目配置的访问工具进入项目；
2. 获取本轮新鲜工具证据；
3. 运行/推进 Observer；
4. 更新用户级 observer state/history；
5. 更新静态 HTML；
6. 简要汇报本轮重要变化。

不得无工具直接回答，也不得根据聊天历史重建当前状态。

长期产品目标应让 Scheduled Task 只调用稳定的 Observer CLI/workflow，而不是每小时让模型从零重新设计 Dashboard。

### Anti-masking

正式 production Observer 已上线后，开发/维护 Writer 的普通 wake **不得例行运行 `observer snapshot` / render 来保持 Dashboard 新鲜**。Maintenance 应先读取 runs/status/current/dashboard mtime 判断 production task 是否真实按期成功；否则 production scheduler 即使已经失效，Maintenance 的手工刷新也会把 data age 与 Dashboard freshness 伪装成正常。

Maintenance 只有在修复后验证、明确诊断实验、release smoke、installed-state dogfood 或 migration 时才允许主动刷新 Observer；执行前必须先保留故障前 evidence，并把该刷新标记为 maintenance verification，而不能算作 production scheduler 成功证据。

快捷入口同样只维护一个 canonical shortcut；目标变化时更新原 shortcut，不按版本或时间戳无限创建副本。

---

## 37. Observer 与 ACF Product Issue

Observer 可以产生 `suspected_acf_issue` Alert，但正式产品 issue 默认仍由 Writer / Maintenance Agent / 明确 issue 流程记录。

原因：避免 Observer 成为 control-plane writer、重复 fingerprint 或把语义误判直接写成产品缺陷。

Observer 自身开发 dogfood 中发现的可复用 Observer/ACF 缺陷，应由当前开发 Workstream 按正式 `acf continuation issue` 流程记录。

---

## 38. Workstream 生命周期

Workstream 完成后不删除 Observer 历史。

从：

```text
observer/workstreams/<id>/
```

转入：

```text
observer/archive/<id>/
```

保留：

- timeline；
- final semantic summary；
- canonical mappings；
- alerts history；
- evidence refs。

生命周期是 Active → Archived，不是 Active → Deleted。

---

## 39. 原子写入

`current.json`、`observer_status.json`、`dashboard.html` 等覆盖文件采用：

```text
write temp
→ validate
→ atomic replace
```

Timeline/history 采用 append-only 或可验证分片写入。

如果 HTML render 失败，保留上一份有效 Dashboard，并在 self-health 中记录失败，不能留下半截页面。

---

## 40. ACF 自身 dogfood 与发布原则

`ai-context-framework` 本身也是一个独立项目，而且是 Project Observer 的第一个强制 dogfood 项目。

WS011 开发期间采用明确双控制面：

### WS011 continuation 控制面

使用当前已安装稳定 ACF 管理：

- ownership；
- continuation；
- recovery；
- checkpoint；
- issue reporting。

### Observer 产品-under-test

从第一版可运行命令开始，**只使用 WS011 worktree 内开发态 `uv run acf observer ...` 观察 ACF 项目自身**。

要求：

- 不等待发布后才 dogfood；
- 每个实质阶段都运行真实 ACF Project Observer；
- Dashboard 必须真实解释 ACF 自己的 WS011 以及项目状态；
- 发现问题立即形成稳定 issue fingerprint；
- 根据 dogfood 反馈持续修改实现、schema、语义解释和 Dashboard；
- 不为了让 dogfood 通过而绕过 Observer 的 read-broad/write-narrow/control-none 边界。

只有在：

1. 功能验收完成；
2. ACF 自 dogfood 连续多轮稳定；
3. 已知 Observer 相关高严重度 issue 收口；
4. 全量/发布检查通过；
5. 文档、模板、CLI、测试同步；

之后才允许：

```text
merge
→ release
→ PyPI publish
→ 全局稳定 ACF 更新
```

未达到发布门槛前，开发态 Observer 不应替换全局稳定控制面。

---

## 41. 最终产品原则

ACF Project Observer 的核心原则：

> **广泛读取，狭窄写入，不参与 Writer 控制。**
>
> **项目访问工具由运行合同注入，Observer Core 不硬编码电脑、MCP 或项目实例。**
>
> **机器状态必须转成人类语义，但原始技术身份永远可追溯。**
>
> **进展历史默认永久保存，不因为时间自动删除。**
>
> **颜色负责引导注意力，文字负责传递真实含义，不用夸张字号制造重点。**
>
> **Dashboard 是展示层，Observer State 才是观测数据层。**
>
> **Observer 解释项目，但不能替项目创造事实。**
>
> **ACF 自己必须先用开发态 Observer 完成真实 dogfood，再允许全局/PyPI 发布。**

---

## 42. WS012 计划扩展：Project Narrative / Architecture Map / Logical Milestone Flow

> 状态：**Planned in WS012，当前稳定版尚未实现。**

现有 Dashboard 已经能回答“项目现在是否健康”“当前 Workstream 在做什么”“最近发生了什么”，但仍然缺少长期阅读所需的项目级叙事骨架。WS012 将增加一个独立的 **Project Narrative** derived semantic layer，使 Dashboard 还能稳定回答：

1. 项目的整体目标是什么；
2. 主要架构模块是什么、它们之间如何关联；
3. 项目沿什么逻辑路线演进到当前阶段；
4. 哪些 milestone 已完成、当前位于哪里、后续逻辑是什么；
5. 每个节点由哪些项目 authority / evidence 支撑。

计划数据结构：

```text
Project Narrative
├─ overall_goal
│  ├─ summary
│  └─ provenance
├─ architecture
│  ├─ nodes[]
│  └─ edges[]
├─ milestones[]
│  ├─ id / title / status
│  ├─ depends_on / next
│  ├─ summary / implication
│  └─ evidence / provenance
└─ current_position
```

该层必须继续遵守 Observer 的事实边界：

- Narrative 是 derived semantic state，不替代 `Context.md`、Task Plan、Workstream、ADR、Git 或其他项目 authority；
- model/agent 可以根据已授权的项目上下文生成语义解释，ACF CLI 只负责确定性的 schema 校验、版本化、source fingerprint、stale 判定、历史保存和渲染；
- 不默认扫描全部仓库；继续从项目入口、active authority、plan refs、Workstream context 与可选 Project Observation Profile 渐进读取；
- 每个总体目标、architecture node/edge、milestone 和 current position 必须保留 provenance；
- source fingerprint 与当前项目 authority 不一致时，旧 Narrative 必须显示为 `stale`，不能继续作为 current project story；
- 缺少足够 authority 时允许显示 Unknown/Not interpreted，不为了填满流程图而推造历史。

Dashboard 信息结构扩展为：

```text
Project Overview
├─ Overall Goal
├─ Architecture Map
├─ Logical Milestone Flow / Project Evolution
├─ Current Position
├─ Overall Health / Alerts
├─ Current Workstreams
├─ Meaningful Timeline
└─ Technical provenance
```

其中 Logical Milestone Flow 不是最近事件流水账，而是跨版本持续存在的**逻辑进度链**。Timeline 继续记录“什么时候发生了什么”，Milestone Flow 负责解释“为什么这些工作按这个逻辑串起来”。两者不能互相替代。

### 42.1 可视化与颜色语义

Project Map 继续输出单一、自包含、`file://` 可打开的静态 HTML：

- 不引入 React、Mermaid runtime、Graphviz runtime、外部 CDN 或 HTTP daemon；
- architecture / flow 优先使用确定性 HTML/CSS 与 inline SVG；
- SVG 只作为 renderer 输出，不成为新的私有事实格式；
- 节点文本、状态和 provenance 必须在不看颜色时仍然可理解。

建议视觉语义：

| 含义 | 建议色系 |
| --- | --- |
| Overall Goal | Indigo |
| Architecture category | Blue / Cyan / Violet |
| Completed | Emerald |
| Current / Active | Blue |
| Maintenance | Purple |
| Waiting | Amber |
| Warning | Orange |
| Critical / Blocked | Red |
| Future / Planned | Slate |

颜色用于形成视觉层级，不替代文字、图标和 canonical status。

### 42.2 与 Production Observer 的关系

Project Narrative 的刷新仍由正式 Production Observer 流程驱动。Maintenance Writer 可以在实现/修复验证、release smoke 或 installed-state dogfood 时显式生成测试数据，但普通 `:04` wake 不得为了让 Project Map 看起来“更新了”而例行刷新 production Observer runtime。

因此 WS012 的 anti-masking contract 对新增 Project Narrative 同样有效：如果 `:34` scheduler 没有真正运行，Dashboard/Project Map 应该自然变 stale，而不是由 Maintenance 替它续命。
