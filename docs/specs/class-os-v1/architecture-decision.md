# Architecture Decision

> 文档状态（2026-10-08）：现行规格/规划/规则；设计存在；实现/批准须另凭目标版本证据。项目完成度见 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md)；本标识不提升批准、测试或任务状态。

## ADR-001：采用分层模块化单体作为 v1 基线

状态：proposed

### Context

项目领域较多，但首期用户和吞吐量很小；最大风险是业务规则、隐私和 Agent 执行边界，不是水平扩展。团队规模和运维资源尚未确认。

### Options Considered

1. 直接全栈单应用：交付快，但容易把规则散入 UI/API。
2. 分层模块化单体：统一部署与事务，保留领域边界和未来拆分点。
3. 微服务/工作流平台：隔离强，但接口、部署、追踪和一致性成本过高。

### Decision

采用选项 2。Web 与 API 可分别部署，但业务服务、领域模块、Tool Gateway 和大部分 worker 代码在一个受控代码库和版本中。

### Why

适合小团队、低规模、强事务、规则变化和高可追溯要求；比微服务更易测试、备份和自托管，又比直接脚本更能隔离领域规则。

### Rejected Alternatives

- 不采用微服务优先：当前没有伸缩或团队边界证据。
- 不采用纯 local-first 单机数据库：用户要求跨端统一数据，自定义同步将扩大冲突与安全风险。

## ADR-002：内部 Function Tool，外部 MCP

状态：proposed

内部 Agent 通过 typed Function Tool 调用 Tool Gateway；精选只读/受控能力通过 MCP 暴露。原因是避免内部网络层冗余，同时保留外部互操作和最小权限。

## ADR-003：AI 非关键路径、单 Agent 起步

状态：proposed

基本 CRUD、校验、计算、预览和导出不依赖模型。完整 v1 只有一个班主任 Agent；Release 1 的 Agent 仅查询/草稿，provider 经 adapter 注入。Release 1 spike 只验证最小投影、超时/降级、测试替身和零业务副作用；Agent SDK HITL 延后到首次真正存在 Agent W2 Tool 的 release。Approval Service 永远独立于 Agent runtime。

## ADR-004：服务端事实源 + 有界离线草稿

状态：proposed

服务器数据库是唯一正式事实源。Release 1 的 PWA 不在 localStorage、IndexedDB 或 Cache 持久化 D2+ 草稿，只允许当前页面内存恢复；登出、会话过期或关闭即清除。拒绝完整离线双向同步；未来若证明强需求，须单独设计设备密钥、TTL、共享/丢失设备和冲突解决。

## ADR-005：事务 outbox 处理后台副作用

状态：proposed

数据库事务同时写业务状态和 outbox；worker 幂等处理重算、导出、附件和未来外发。避免“数据库已改但任务丢失”以及同步请求长时间阻塞。

## ADR-006：技术栈按已获证据分段收口

### ADR-006A：前端工程基线

状态：accepted-by-product-owner；仍须纳入最终 architecture artifact hash

工程起点采用已冻结的 React/TypeScript UX 基线，不公开私有来源标识和采集时间。前端采用 React 19、Vite 8、TypeScript、Tailwind CSS 4；接受范围是工程壳与 UX / interaction contract，不包括 prototype 的 mock store、正则判断、延时模拟、编辑器专属工具链或临时组件边界。公开候选使用普通 React/Tailwind Vite 配置，依赖版本由 lockfile、依赖安全检查和 CI 约束；这不是对原型再分发权的法律确认。

### ADR-006B：后端、数据、Harness 与部署组合

2026-10-08 开发适用补充：用户明确批准按已有 Python/FastAPI、PostgreSQL、Pydantic AI port 基线进行合成实现；Jev 默认关闭，初始 provider 使用 fake，受控 localhost。此决定允许 synthetic feature 开工，不将下述最终架构状态改成 accepted，不冒充独立签名，不获准公开部署/真实数据；正式 .ai/gates 晋升和依赖准入仍按各自规则。详见 [变更登记](../../changes/2026-10-08-synthetic-development-admission.md)。

状态：后端语言/API 基线经 T-RSPK-001 accepted-for-development；Agent Runtime adapter 经 T-RSPK-002 accepted-for-development，Jev disabled-by-default；PostgreSQL 18 数据基线经 T-RSPK-003 accepted-for-development；最终组件削减/架构开发接受 pending；不得跳过依赖准入

候选组合：FastAPI/Python、PostgreSQL、S3 兼容对象存储、Pydantic AI v2、TypeSafe/Jev、OpenTelemetry。2026-09-20 已按官方 LICENSE、版本政策、发布记录和 ClassMatter 业务约束完成 Harness 复核，选择 Pydantic AI v2 作为 `AgentRuntimePort` 的首个 adapter；采用精确版本锁定与上游扩展点，不默认 Fork。TypeSafe/Jev 作为可选 typed decision model 进入同一 adapter 的路由 spike，不是第二套 Harness。OpenAI Agents SDK 保留为 contract-test 对照和失败回退；LangGraph/Microsoft Agent Framework 仅在复杂 durable workflow 成立后重评。

T-RSPK-001 已用相同 fixture/contract 比较 Python 3.13 + FastAPI 0.141.1 与 Node 22 + Fastify 5.12.5。两端契约一致；Fastify 冷启动和本机 p95 更好，Python 进程树 RSS、spike LOC 与锁定依赖数更小。当前低吞吐下性能差异均非瓶颈，而全 TypeScript 会迫使项目替换已选 Pydantic AI 或额外保留 Python sidecar。因此接受 TypeScript Web + Python 3.13/FastAPI 模块化单体；初始实现锁 FastAPI 0.141.1、Pydantic 2.13.5、Uvicorn 0.53.0，并以 OpenAPI/JSON Schema/stream contract 控制跨语言成本。Fastify 方案作为拒绝项保留；若 T-RSPK-002 否定 Python Agent adapter，则重新评估，不无条件维护 Python sidecar。证据见 `spikes/language/README.md` 与其 JSON evidence。

该选择不授权 Agent 写入：R1 Tool 仍只查询/草稿；任何 Tool 查询经 Query Gateway，任何未来业务写经可信 UI 和 Business Command Gateway；Harness approval 不是 authorization，Session/Memory 不是 Domain Fact。工具先由确定性 metadata/allowlist 过滤；Jev 只判断 `answer_only/read/draft_write/clarify`、领域和歧义，主模型处理自然语言、复杂参数和回答，领域服务与 BCG 决定合法性和提交。Jev 的 confidence 不是正确概率，高置信也不能自动 commit。

T-RSPK-002 已用 Pydantic AI 2.46.0/FunctionModel 与 deterministic fake 验证 project-owned port、typed Tool、provider/fake 替换、最小查询投影、草稿零业务副作用、静态 allowlist、伪造 approval/prompt injection 拒绝、Tool 输出数据通道、任意 URL/SQL/未知 Tool fail closed、超时/取消、当前事实 grounding、每轮重查、Agent-off parity、事件 cursor、audit/OTel 脱敏、SBOM 和 25 个目标环境依赖许可清单。`ag-ui-protocol` 1.0.0 可作为 adapter 依赖，但 ClassMatter 自有 event envelope 保持稳定契约，当前不引入完整 AG-UI 前端耦合。

以上版本为历史 spike 的接受基线，不是本候选当前 pin。公开候选因上游安全公告将 SDK 固定到2.53.0、optional ag-ui依赖固定到该SDK要求的0.1.22，并重跑原隔离/传输测试；本项目事件协议和只读/草稿 port 不变。版本求解、测试断言调整和回归范围见 [依赖修复记录](../../DEPENDENCY_REMEDIATION.md)，不能据此提高任何正式 Gate 或把旧实验伪称新版本验证。

中文路由 corpus 已固定 320 条 synthetic case，并提供三组 prediction 评分器；但本机没有提交经过校准的 TypeSafe/主模型 provider run，因此不能声称 Jev 或任一模型的语义准确率、延迟或成本收益。按 fail-closed 决策，R1 **默认关闭 Jev**，保留 kill switch 与未来补跑入口；这不阻止 Pydantic AI adapter 和确定性 capability filter 进入开发基线。Pydantic AI adapter 失败时切 deterministic fake/禁用 Agent，直接 UI 保持可用，不自研通用 loop。T-RGOV-006 只能签署包含最终 ADR-006 全文 hash 的架构 artifact；T-REVAL-019 组件削减和架构开发接受完成前仍不得加入持久化业务写路径。证据见 `spikes/agent-read-draft/` 与 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md)。

T-RSPK-003 已在官方页面链接的 PostgreSQL 18.6 Windows portable binaries 上完成真实 synthetic drill：2 条固定任务数据经 restart 投影相等，`pg_dump -Fc` 后在第二个独立 cluster `pg_restore` 投影相等，数据库完全停止时查询 fail closed；单机观测为约 125 MiB PostgreSQL process-tree RSS、47.677 MiB 初始 cluster、约 3.3 KiB synthetic backup，CPU probe/冷启/重启/恢复数据均随 evidence 保存且不外推为容量/RTO。Docker Desktop 4.77.0 因宿主机遗留 inference socket error 1920 无法启动；未执行 factory reset，故容器 clean-host、镜像 digest、升级/回滚和三目标主机 doctor 仍由 T-ROPS/T-REVAL-022 完成，不能因 portable drill 假称 E-OPS-009/011/012 implemented-green。PostgreSQL 18 作为 transactional baseline accepted-for-development；S3/object store、完整容器拓扑与生产 retention 尚未获准。

### ADR-006C：签名 envelope 与准入组件减法

ADR-006B 数据实施补充（2026-10-08，synthetic development only）：采用 SQLAlchemy Core 2.0.54 + Alembic 1.20.0，驱动复用 Psycopg 3.3.6。事务/迁移使用上游实现，不自建 ORM 或迁移框架；domain 不 import 它们。迁移仅由发布/开发 CLI 执行，不在 HTTP 启动、Agent 或请求路径执行；runtime 和 migration capability 分离。先证明 PostgreSQL 18 空库升级、重复运行、事务回滚与未知 revision 拒绝；不启用自动 autogenerate/stamp/create_all 绕过迁移历史。该开发决定不改变最终架构签名状态。

状态：T-REVAL-019 accepted-for-development；production authorization=false；正式 root/key ceremony 与外部角色批准 pending

采用 DSSE v1 替换候选 `CLASS-OS-SIGNATURE-V1` 自定义字节协议。Python baseline 精确锁定 in-toto 3.1.0、securesystemslib 1.5.1、cryptography 50.0.1 和 rfc8785 0.1.4。verifier 对 DSSE exact bytes 验签后才解析 payload，并要求 strict I-JSON、无 duplicate key、无 post-NFC key collision、RFC 8785 重序列化逐字节相等。RFC 8785 本身不做 Unicode normalization，因此 verifier 只拒绝规范化后 key collision，绝不改写已签字符串。

DSSE 只承担 envelope integrity/type binding，不承担 key management、identity、role 或 authorization。`keyid` 只缩小外部 registry 中待验公钥集合；signer、role、key usage、validity、revocation 与 quorum 全部来自已 pin 的应用外 registry。registry 拒绝重复 key id、signer id 或 public key，防止同一 principal 跨角色重复计数；generation/hash/previous-hash 防回滚规则继续保留。reusable/renewable artifact 永不消费，只有 scope setup 与 allocation/ledger/audit 在同一 PostgreSQL 事务内一次性消费。

实现接口不接受 raw registry：admission verifier 只接收由独立 DSSE root verifier 产生的 `VerifiedRegistrySnapshot`。root verifier 要求 pinned offline-root + security + operations 三角色 registry quorum，再验证 generation/hash/previous-hash；artifact verifier 使用统一 profile table 固定 `artifact_type → payloadType → lifecycle → roles/key usage → strict fields`，并把 release、commit、definition bundle、environment、deployment 和 workspace 与受信调用上下文比较。key `status` 是必填且只有 active key 可计入 quorum；setup operation/max=1、shadow result、receipt 禁止业务内容和嵌套 context binding 都由 executable policy 执行。引用不是裸 ID；缺少 external reference-verifier port 必须 fail closed。该 port 返回绑定 canonical payload/type/lifecycle/digest/registry/roles 的 `VerifiedArtifactReference`，父 artifact 只用这个已验证 payload 检查 receipt owner/class/term scope、封闭 R1 module 集和 shadow `go`，不信任 locator metadata 决定 type/result/scope。非空 `referenced_artifact_ids` 还要求父 DSSE 签入逐项 ID/type/digest 和 catalog ID/URI/digest；release-verifier 签名的 catalog 只提供 ID→URI，公共 admission 对未验证 closure 必须拒绝，closure 结果精确绑定父 payload digest、catalog digest、registry snapshot、ExpectedContext 与完整有序结果。受信应用组合固定 concrete verifier，不能由请求或插件注入。Gate report 是 release/environment 级 artifact，不伪造 workspace 字段；candidate 与 pilot 槽位分别绑定 `before_release_candidate` / `before_pilot_readiness`，且 artifact ID/digest 必须不同。T-REVAL-020 follow-on 已证明受控 rooted-store 的 URI fetch、payload digest、DSSE/policy、typed nested/generic reference，以及 PostgreSQL 主键/unique nonce 支撑的 durable global artifact identity；live synthetic drill 覆盖并发、冲突无半写、重启和停机 fail closed。Windows 扁平本地 artifact root 的 synthetic native final-component no-follow 已证明，但生产 root/父目录 ACL、轮换与部署自检仍未证明。`PostgresIdentityLedger` 只观察 artifact identity，不消费 one-time capability；setup consumption、scope allocation、ledger、audit 和 receipt 仍必须在 Business Command Gateway 的同一 PostgreSQL 事务中另行证明。

GitHub Artifact Attestations/Sigstore 可用于 CI build、SBOM 和 evidence provenance，但不能表达 ClassMatter 产品/隐私/安全/运维批准，不能进入 runtime availability path。R1 不建设在线 signing service、key registry service、transparency-log dependency 或每类 artifact 微服务。正式证据是一个版本化 DSSE payload family + schema/policy registry；definition、mutable state 和 evidence 仍分离。

拒绝 JWS 是因为当前不需要其算法/头部/令牌生态复杂度；拒绝自研 framing 是因为 DSSE PAE 已提供无歧义的 type/payload 绑定；拒绝用 GitHub/Sigstore 代替业务授权是因为 CI identity 与学校/产品治理角色不是同一信任域。官方 DSSE PAE、RFC 8032 test 1、RFC 8785 与 mutation evidence 位于 `spikes/signature-envelope/`。

## ADR-007：Release 1 单 owner 身份生命周期

状态：proposed；真实试点前必须接受安全评审。

### Decision

Release 1 自托管拓扑不依赖学校外部 IdP：使用成熟认证库提供本地单 owner 凭据、服务端会话、一次性首次 bootstrap 和离线恢复码。bootstrap 生成高熵一次性恢复码套件，只显示/导出一次，服务端只保存加盐哈希；首次 owner 创建后 bootstrap 入口永久关闭。持码者通过 Identity Security Boundary 在同一受限会话兑换短时单次恢复能力；成功后轮换凭据、吊销全部旧会话与旧恢复码，并只显示一次新套件。R1 不提供管理员数据库改 owner、邮件找回或“无恢复码”后门；恢复码与加密备份密钥均丢失时，应用内恢复不可用并明确进入 stop/外部治理流程。

### Constraints

- 密码哈希算法和参数由安全基线/库配置管理，不自行实现密码学；
- 恢复响应不枚举账号；恢复码只保存哈希，尝试受限速；短时恢复 session 绑定同一客户端、时效和单次消费；
- 恢复码必须通过用户主动保存的离线介质交付，不经邮件、模型、日志或支持包传输；
- 受支持部署要求 host root/DBA 是经治理授权的 trusted operator；应用禁止提供数据库脚本作为正常 owner 恢复路径，但不声称能技术阻止控制主机/数据库/镜像的管理员绕过应用。需要抵抗该主体时必须采用应用外不可变审计、硬件密钥或远程证明并新增 ADR；
- 后续接入学校 IdP 时新增 adapter/迁移 ADR，不静默改变现有身份语义。

## ADR-008：开放世界语义采用 typed core + governed extension

状态：accepted-as-long-term-design-constraint；`class-os-r1` non-applicable；future release approval required

### Context

班主任长期工作会不断遇到未预先建模的对象和流程。把所有内容塞入万能 JSON/Fact 表会失去约束、权限、迁移、审计和可解释性；让 Agent 修改生产 Schema 或执行 DDL 会形成不可控写入口。

### Decision

采用 `Stable Kernel → Domain Pack → Controlled Extension → Promotion`。核心领域继续使用 typed aggregate；JSONB 只用于已验证 extension payload、Draft 或 provider metadata。通用 Claim 必须引用 owning Domain 注册的 `PropositionSchema/version`，其 subject 端点、discriminated value、purpose 和 sensitivity 均为 allowlist，未知类型 fail closed，不能成为伪 EAV。Agent 仅能经 typed Command 提交 `SchemaProposal`；Extension Service 经过授权、风险、版本、生命周期和迁移校验后，仍通过 Business Command Gateway 创建 logical schema。物理 schema 只随版本化发布迁移。SchemaVersion 进入依赖图，回滚时表单、validator、workflow、index、Tool schema、saved query 和 export consumer 必须失效、降级或重建。

### Rejected Alternatives

- 单一 `facts(type,json)` 表承载全部业务；
- 任意 EAV/无约束图关系；
- Agent 或管理员 UI 直接执行生产 DDL；
- 因未来开放世界需求现在引入图数据库或完整低代码平台。

## ADR-009：Context、Memory、Knowledge 与 Domain Fact 分离

状态：accepted-as-long-term-design-constraint；`class-os-r1` non-applicable；future release approval required

### Decision

Active/Working Context、Harness Session、Conversation/Preference Memory、Knowledge、RAG Index 和 Domain Fact 分别拥有权威性、owner、scope、purpose 和 lifecycle。Memory/Knowledge/RAG 不能覆盖 Domain Fact；Preference 必须由教师确认且可撤销；RAG 是可重建索引。来源更正、限制或删除必须使派生 summary/profile/index/artifact/attention/trigger 失效或重建。

## ADR-010：Temporal 为底层语义，编排能力保持上层可替换

状态：accepted-as-long-term-design-constraint；`class-os-r1` non-applicable；future release approval required

### Decision

Canonical Model 区分 occurred、recorded、valid/effective 和 system/transaction time，并保留时区与精度。Calendar 是投影；Workflow、Scheduling、Attention、Conflict 位于 Application/Domain Pack 层，runtime/solver 属于 Shared Capability。Trigger 默认生成 Draft/Review Item，不能成为绕过 BCG 的自动写入口。

### Consequence

本决定不向 Release 1 增加日历、工作流、排班或主动提醒功能，只约束后续设计。
