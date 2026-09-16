# ACF Sensitive Data / Credential Transport Contract

本文定义 ACF CLI 的敏感数据与 owner 认证材料传输边界。它是产品安全合同，不依赖任何特定模型、MCP 实现或平台内部安全分类规则。

## 1. 数据分类

ACF 按语义而不是字段名、长度或“高熵外观”分类数据：

- **Reusable credential**：可重复证明 owner/账户/服务访问权的秘密。不得进入公共 CLI argv、JSON、generated prompt、generic diagnostics、usage log、child argv 或普通 durable state。
- **Authentication verifier**：由 credential 派生、用于本地验证但不能替代 credential 的值。canonical auth state 可以保存必要 verifier；公共 status/doctor 不应输出无业务必要的 verifier。
- **Capability handle**：指向调用方本机受限 owner context 的 opaque local handle。handle 本身可以进入公共命令参数和 JSON；它不得包含 credential 内容。
- **Public control metadata**：例如 lease id、generation、runner id、Git SHA、UUID、deterministic digest、普通 external job id。它们不是仅因名称、UUID/hex 形式或高熵外观就成为 secret。
- **Arbitrary project/diagnostic text**：可能意外携带 credential-like 内容。进入公共输出前必须应用明确的 redaction 边界；需要持久化的字段应优先保存 non-secret reference，而不是凭据本体。

## 2. Continuation owner authentication

Continuation 继续要求同时满足：

1. 正确的 active lease identity；
2. 正确的 generation fencing；
3. 对 reusable owner credential 的 possession proof；
4. verifier 比较继续使用 constant-time comparison；
5. stale-owner、workspace provenance、effect replay/recovery 规则保持 fail-closed。

隐藏 credential 不能以降低上述任何一项为代价。

### 公共传输合同

- `claim` / `recover` 成功时只向调用方交付一个本地 owner-context capability handle；公共 JSON 不返回 reusable credential。
- owner context 必须绑定 workspace、task、lease、generation、runner/issue identity 与 credential。
- owner-protected 命令只接受 capability handle 与该命令自身的非秘密业务参数；lease id / generation 仍可作为状态、审计与输出 metadata，但不再作为 owner-protected 公共输入参数。它们从 owner context 与 canonical active lease 内部读取并参与一致性/fencing 校验。
- handle 缺失、不可读、schema 非法、workspace/task 绑定错误、lease/generation/credential 不匹配或 stale generation 必须 fail-closed。
- owner-context delivery 必须发生在 fresh owner commit 前；delivery 失败不得创建新 active owner，也不得推进 generation。
- canonical lease 只保存不可逆 verifier，不保存 reusable credential。
- 正常 release 后应撤销/清理本地 owner context；即使清理异常，已释放或被新 generation 替代的旧 handle 也必须无法再次取得 owner 权限。

### 旧 transport 边界

旧 raw-secret 参数或环境变量 token-file transport 不再是可用认证旁路。`--fence-token`、`--lease-id`、`--generation` 不属于 owner-protected parser schema；旧调用仍把这些参数提交到 ACF 公共边界时，CLI 必须在不回显其值的情况下安全拒绝。

对于升级时仍存在的旧 active fenced lease，`.90` 不从 durable verifier 反推 credential，也不从旧环境变量静默读取 secret。合法旧 owner 若仍持有本地 token file，可显式执行 `acf continuation owner migrate-legacy-token-file ... --legacy-token-file <local-path> --json`：公共边界只接收本地路径，ACF 在进程内读取 credential、与当前 active lease verifier 做 constant-time 校验，并创建绑定同一 workspace/task/lease/generation/runner 的 owner context；迁移不推进 generation、不替换 owner，也不形成 takeover。

- read-only `doctor/status/prompt/reconcile` 仍可观察 lease、generation、liveness 与 recovery evidence；
- owner-protected 写操作若没有 `.90` owner-context handle，返回明确的 `owner_context_required` / migration error，不降级为未认证写入；
- 显式本地迁移成功后必须删除旧 token file；如果旧文件无法安全退休，必须撤销新 owner context 并 fail-closed，不能留下两个可用 credential transport；
- 旧 owner 若仍真实存活，应先由原执行链正常结束/释放；不得因升级而 takeover；
- 旧 owner 已结束或 lease 进入正式可恢复状态后，继续使用既有 evidence-backed reconcile/recover 语义，由新 recover 原子生成新的 owner-context handle；
- 如果旧 owner 已不再持有正确的本地 token file，则不得根据 verifier、runner id、lease id 或 generation 重建权限；只能保留旧进程，或在 stale/expired 后走正式 reconcile/recover。

`doctor` / `prompt` 必须把“active lease 存在、但当前 generation 没有可验证 owner-context capability”投影为显式 `owner_context_migration_required`，而不是把同 runner 继续标成可写 current owner。合法旧 owner 可以显式使用本地 token-file migration；若没有该本地 possession proof，fresh lease 只保护仍在运行的旧进程/等待原执行链收口，不能重新开放 raw-secret argv/environment transport。

owner-context 文件系统边界也属于认证合同：capability directory 和 handle 不得经 symbolic link、junction 或其他 reparse point 重定向；读取应尽量基于单一已打开 fd 做 regular-file、link-count、size 与平台可证明的权限/owner 校验。POSIX 要求私有 mode 与当前 uid；Windows 标准库无法可靠证明 inherited ACL，因此只声明 reparse/regular-file 等可验证约束，不把 `chmod` 结果冒充 owner-only ACL 证明。

## 3. Public JSON / prompt / log

- continuation 公共输出在最终 emit 边界统一移除 ACF reusable credential 与无业务必要的 auth verifier，并对明确 credential-like 文本做 redaction。
- generated prompt 的 JSON 与非 JSON 路径使用同一 public sanitization contract。
- usage event log 继续只记录 command/result metadata，不记录原始 argv、正文输入或 owner credential。
- `acf log feedback` 虽然是显式正文记录接口，也不得把明确 credential-like 内容持久化；此类输入必须 fail-closed，而不是“先写入再依赖展示层脱敏”。
- redaction 不能把普通 UUID、SHA、digest、generation 或 job id 当作 secret。

## 4. `continuation execution run`

`execution run` 是受监督本地进程接口，不是通用 secret manager 或环境 sandbox。

- ACF 不在结果中回显完整 child argv；只返回非敏感命令摘要和已有 process/effect 审计身份。
- 明确 credential-bearing child argv 必须 fail-closed；业务命令需要凭据时应使用 child-local credential file、OS credential mechanism 或其他不把 reusable credential 放入 ACF 公共命令文本的机制。
- child stdout/stderr 使用 bounded in-memory capture；不得先把 raw child output 写入通用临时文件。超过边界或无法完整 drain 时整体省略诊断正文，完整短输出在公共返回前对明确 credential-like 文本做 redaction。
- supervised child 的 stdin 固定为 null device，不继承调用方交互 stdin，避免把调用方输入面隐式委托给业务进程。
- 为兼容真实业务运行，普通 non-credential parent environment 继续继承；明确 credential-keyed / credential-shaped 环境变量和 ACF 自己的 owner credential/capability transport 不得委托给 child。业务进程确需凭据时应使用 child-local credential file、OS credential mechanism 或其他显式最小权限边界。该规则是 credential containment，不宣称提供通用环境 sandbox。
- effect identity/replay protection 不依赖完整 child argv 回显，因此删除 argv 回显不得削弱 deterministic execution identity。

## 5. Effect / recovery external identity

- `logical_key`、`external_id`、milestone、evidence reference 等用于 identity/recovery/audit，不是 secret store。
- 普通 scheduler/job/run id、UUID、SHA、digest 必须继续可用。
- 新写入的明确 credential-like 内容应在公共输入边界 fail-closed；旧 durable record 不应仅因升级而被静默改写。
- 对需要读取旧 record 的 public list/status 路径，credential-like legacy 内容必须在输出边界 redacted；内部 identity matching/recovery 仍使用 canonical 原值，不能用 redacted 值做事实裁决。

## 6. 验收不以平台误报为目标

OpenAI、MCP 或其他 command transport 的安全拒绝只能作为 dogfood 信号。ACF 验收依据是上述语义安全合同：secret 不穿越公共边界、认证强度不下降、普通 metadata 不误拒、失败保持可审计且 fail-closed。不得通过改名、编码、拆分或隐藏字段来“通过扫描”。
