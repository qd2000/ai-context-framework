本文件记录当前大任务计划和轻量子任务板。

- 当前阶段事实请查看：`active/Context.md`
- 当前正在执行的小任务请查看：`active/Current_Task.md`
- 本文件只维护当前大任务拆分、子任务状态和下一步，不记录长过程、命令输出或详细推理

---

## 大任务状态

Done

---

## 大任务名称

ACF Worktree 临时合并工作树、并发恢复与结果迁移

---

## 大任务目标

1. 将所有 `acf worktree merge` 统一改为在临时 integration worktree 中完成真实 merge、冲突解决和 post-check。
2. Primary checkout 只执行经过路径碰撞和本地状态保护的 fast-forward promotion，不再创建 no-ff merge commit。
3. 来源 worktree 继续要求 clean，同时允许 primary 中稳定、无碰撞的 staged/unstaged 小任务修改继续存在。
4. 对并发合并、短时 commit、锁竞争、HEAD 推进、Git 状态变化和 Windows 文件占用提供等待、退避、自动 replan 和 operation resume。
5. 在 promotion 前完成 required ignored/untracked artifact 的迁移和摘要验证；unknown artifact 阻止提升。
6. 通过 ACF 源码、测试、模板、文档、版本发布和真实 dogfooding 形成完整产品能力。

---

## 成功标准

1. 来源 worktree clean、identity、source HEAD 和 pre-check 合同未被削弱。
2. 无论是否冲突，每次 merge 都创建并使用临时 integration worktree。
3. Primary 中无碰撞的 staged/unstaged 修改可以保留，且不会进入候选 merge commit。
4. Primary 只通过 `git merge --ff-only <candidate-tip>` 完成 promotion；旧的 primary 直接 no-ff merge 路径不可达。
5. Primary/source HEAD 推进、有效锁竞争和短时 index 状态可自动等待或重规划，不要求用户从头重输命令。
6. required/retained artifact 在 promotion 前完成验证；unknown artifact 不会被静默删除。
7. 稳定冲突只出现在 integration worktree，可解决后通过 operation ID resume。
8. merge、artifact handoff 和 close 在中断后可幂等恢复，不使用自动 stash、reset、clean、rebase、update-ref 绕过或 force remove。
9. 模板检查、dogfooding strict check、upgrade matrix 和全部分片 unittest 通过。
10. v0.0.3.56 wheel/sdist 构建和隔离安装 worktree 生命周期 smoke 通过，并在 FCC 真实 dirty-primary 仓库完成只读 dogfooding。

---

## 规划依据

- `reference/Worktree_Merge_Resilience_Implementation_Plan.md`：定义统一 integration worktree 主链、primary promotion 保护、重试状态机、artifact handoff、冲突恢复、close 合同和测试矩阵。

---

## 当前焦点

无。

---

## 子任务

| ID | 状态 | 子任务 | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|
| T001 | Done | 冻结单一 integration 主链合同、schema 和测试夹具 | 无 | operation v2、artifact handoff v1、重试参数、临时 Git 仓库场景夹具 | `tests/test_worktree_merge_contracts.py`、`tests/worktree_scenarios.py` | 已完成 |
| T002 | Done | 结构化 primary 状态与候选路径碰撞分析 | T001 | staged/unstaged/untracked/ignored 分类；candidate write set；identical/divergent overlap | `tests/test_worktree_status.py`、`tests/test_worktree_collision.py` | 已完成 |
| T003 | Done | 每次 merge 创建 integration worktree 并生成候选 | T001,T002 | integration branch/worktree；真实 merge；干净 post-check；旧直接 merge 路径停用 | `tests/test_worktree_resilient_merge.py` | 已完成 |
| T004 | Done | Promotion 锁、状态保护、自动 replan 和 operation resume | T002,T003 | stable snapshot；heartbeat；退避；ff-only promotion；journal v2；resume | 并发锁、短时碰撞、primary/source HEAD 推进测试 | 已完成 |
| T005 | Done | Promotion 前的 ignored/untracked artifact handoff | T001,T002,T003 | artifact-plan、artifact-migrate、digest、显式分类和 required/unknown 门禁 | `tests/test_worktree_artifacts.py` | 已完成 |
| T006 | Done | Integration 冲突现场与恢复 | T003,T004 | 冲突清单；人工解决；primary 推进后吸收最新 main；resume | 冲突和 post-check 修复恢复测试 | 已完成 |
| T007 | Done | Close 重试、部分成功和崩溃恢复 | T004,T005,T006 | close journal；Windows 退避；部分成功恢复；内部 worktree/branch/ref 回收 | close transient failure 与同 operation resume 测试 | 已完成 |
| T008 | Done | 模板、文档、严格策略、灰度和发布 | T002,T003,T004,T005,T006,T007 | README/System Manual/template/config/version/release | v0.0.3.56 制品、420 项分片测试、full upgrade matrix、wheel smoke、FCC audit | 已完成 |

---

## 任务阶段

| ID | 状态 | 父任务 | 名称 | 归属 Workstream | 依赖 | 输出物 | 证据 | 下一步 |
|---|---|---|---|---|---|---|---|---|
| T001.1 | Done | T001 | 合同、默认参数和场景夹具 | 无。 | 无。 | schema、Python 合同和临时 Git 仓库夹具 | 合同测试通过 | 已完成 |
| T002.1 | Done | T002 | Primary 状态和碰撞分析 | 无。 | T001.1 | porcelain v2、candidate write set、路径碰撞分类 | 状态和碰撞测试通过 | 已完成 |
| T003.1 | Done | T003 | Integration 候选主链 | 无。 | T001.1,T002.1 | 每次创建临时 worktree、merge、post-check | 生命周期测试通过 | 已完成 |
| T004.1 | Done | T004 | Promotion 并发保护和恢复 | 无。 | T002.1,T003.1 | 锁、退避、stable snapshot、ff-only、resume | 并发与 replan 测试通过 | 已完成 |
| T005.1 | Done | T005 | Artifact handoff | 无。 | T001.1,T002.1,T003.1 | ignored/untracked 迁移和 promotion 门禁 | artifact 测试通过 | 已完成 |
| T006.1 | Done | T006 | 冲突现场和 resume | 无。 | T003.1,T004.1 | integration conflict、人工解决和最新 main 吸收 | 冲突恢复测试通过 | 已完成 |
| T007.1 | Done | T007 | Close 韧性 | 无。 | T004.1,T005.1,T006.1 | close journal、重试和部分成功恢复 | close 恢复测试通过 | 已完成 |
| T008.1 | Done | T008 | 严格策略、文档、灰度和发布 | 无。 | T002.1-T007.1 | 文档、模板、版本、制品和 dogfooding | full matrix、wheel smoke、FCC audit | 已完成 |

---

## 使用规则

1. 本文件保持轻量，只放任务板和必要摘要。
2. 详细行为、重试参数、错误分类和测试矩阵以 `reference/Worktree_Merge_Resilience_Implementation_Plan.md` 为唯一权威位置。
3. 正式实现只修改 ACF 源码仓库；下游项目只承担场景验证和版本升级，不维护私有 ACF fork。
4. `require_clean` 只作为同一 integration 引擎的严格前置策略，不作为旧引擎回退。
5. 已完成计划需要长期保留时归档到 `archive/plans/`；在发布提交完成前保留本文件作为当前发布证据入口。

---

<!-- ACF:ARCHIVE:RECORD:START -->
- archived_at: 2026-08-20
- item_type: Plan
- item_id: ACF Worktree 临时合并工作树、并发恢复与结果迁移
- source_path: active/Task_Plan.md
- archive_path: `archive/plans/2026-08-20-acf-worktree-临时合并工作树-并发恢复与结果迁移.md`
- status: Archived
- archive_reason: WS009 post-merge primary maintenance: archive terminal retained Task_Plan after v0.0.3.66 release.
<!-- ACF:ARCHIVE:RECORD:END -->
