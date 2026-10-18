# Architecture Confirmation

> 文档状态（2026-10-08）：现行规格/规划/规则；设计存在；实现/批准须另凭目标版本证据。项目完成度见 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md)；本标识不提升批准、测试或任务状态。

## Proposed Flow

2026-10-08 阶段修订：用户已批准合成 feature 开发与正式晋升/真实数据/上线分离，见 [开发准入登记](../../changes/2026-10-08-synthetic-development-admission.md)。本文后续所述“只能 spike/必须 before_feature_task 后开工”对合成实现的限制已被该明确决定取代；正式 architecture/definition 签名及晋升仍 pending，不能改写成 accepted 或绕过运行时权限。受控 synthetic 开发可复用已有技术基线继续，不重复等待生产批准。

响应式 Web/PWA、REST、Agent/MCP 和 worker 先进入明确边界：只读进入 Query Gateway，学生/班级业务写进入 Business Command Gateway，bootstrap/登录/恢复/session 写进入 Identity Security Boundary；不存在未分类写入口。三类边界再调用模块化 Application/Domain/Identity Services 与 PostgreSQL；后台副作用通过 outbox 登记并回到 Business Command Gateway；R1 Agent/MCP 仅查询/草稿。

## Reviewed Alternatives

1. Direct pipeline：开发快，但不满足规则隔离、审计和长期演进。
2. Layered modular monolith：当前推荐。
3. Plugin/adapter/workflow engine：provider adapter 保留；完整工作流引擎延迟到 durable workflow 需求成立。
4. Microservices：当前拒绝。

## Decision

采用同一主仓库、前后端运行时分离、后端 layered modular monolith。前端工程基线与冻结 prototype 已由用户确认；T-RSPK-001 已接受 Python 3.13/FastAPI 后端语言与 API 基线，TypeScript/Fastify 后端作为当前拒绝项保留。T-RSPK-002 已接受 Pydantic AI 2.46.0 经项目自有 `AgentRuntimePort` 的只读/草稿 adapter、deterministic fake、静态 capability filter、项目事件 envelope 和最小 OTel/audit 投影；AG-UI 仅保留为 wire adapter，不进入 Kernel。TypeSafe/Jev 因没有经过校准的 provider 对照，R1 默认关闭。T-RSPK-003 已接受 PostgreSQL 18 作为 transactional development baseline，并以 synthetic restart/backup/outage/restore drill 证明基本可恢复性；容器 clean-host、镜像 digest、升级/回滚和运维 doctor 未由本 spike 证明。T-REVAL-019 已删除自定义签名 framing，接受 DSSE v1/in-toto/securesystemslib + Ed25519 + RFC 8785 的 verifier 开发基线，CI attestation 与 runtime business authorization 保持分离。以上开发接受不构成真实数据、Agent 写入、生产部署或最终签名 architecture approval。

本候选仅对上述SDK历史版本做同主版本安全维护：当前 Pydantic AI 2.53.0，详情及回归边界见 [依赖修复](../../DEPENDENCY_REMEDIATION.md)。不改 AgentRuntimePort、事件协议、批准角色或 Gate，不把维护变更等同正式 architecture approval。

## Confirmation Evidence

- Status: partial-product-confirmation；最终 architecture approval pending
- Date: 工程方向已有开发基线；正式签名日期 pending（不公开私人确认记录）
- Approvers: product owner 已确认 prototype freeze 与主仓库方向；security/architecture/operations pending
- Signed artifact: pending；模板 `.ai/gates/architecture-approval.example.yaml`
- Required binding: architecture hash、ADR-001—007（含 ADR-006A/B/C）hash、spike evidence、constraints hash、definition bundle、release、issued_at/not_before/expires_at、artifact_id/nonce；按 `signed-artifact-policy.yaml` 的 DSSE policy 校验角色、全角色 quorum、key usage、有效期、撤回与重放
- Development decision: project owner 于 2026-09-21 要求持续本地实施、自主修正与阶段验收；该请求允许继续 Gate runner、spike、eval 与不产生业务能力的 foundation work，但不改变 machine `before_feature_task` gate。业务 feature task 只有在该 machine gate 真实 green 后才可 promotion；不得把 owner 请求写成 security/architecture/operations 签名，也不允许真实数据、真实试点或 production release。

ADR-008—010 是 `non-R1` 长期设计约束，不属于当前 R1 approval artifact 的 required binding，也不声称已获得架构签名批准。任何 future release 选择开放世界语义、Memory/Knowledge 或 Temporal/Workflow 能力时，必须把适用 ADR 及其当时内容 hash 加入该 release 的新 definition/approval bundle；不得沿用 R1 的 ADR-001—007 binding 作为替代批准。

## 2026-10-07 开发准入交接（未批准）

核对基线为主仓库 `5c4030ce3ea58451afc695bf8307d1bab2cef1b7`；这只是本次材料盘点的已同步 commit，不是获批 target commit。以后正式签发必须选择最终 clean checkout，不能沿用旧摘要或在文档中硬填批准 hash。本节不改变 ADR、Requirement、Eval、Task 或 Gate 的机器状态。

### 已有证据与仍待证明的内容

- 语言、Agent、PostgreSQL、签名组件均已有隔离开发证据；Agent 追加的 lifecycle/ASGI/TCP/browser 验证已提交于上述基线，见 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md) 和 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md)。这些证明只读/草稿传输及故障清理，不证明真实 provider、正式身份、生产 Web 接线、业务持久化或部署。
- 现有架构绑定候选固定读取 architecture、ADR-001—007、项目宪章及 language/agent/self-host/signature 四份 JSON。Agent JSON 是 routing corpus 结果，不自动包含后续浏览器测试。评审须同时阅读上述补充证据；不能声称四个 JSON 已覆盖全部后续测试，也不擅自扩展 signed payload 的字段或放宽候选 verifier。
- `binding_hashes()` 当前会明确拒绝非 `accepted` 的 ADR-006B。这不是需要绕过的测试故障；尚未最终接受的 ADR 不能生成可批准的架构绑定。后续先形成真实接受决定，再对最终版本运行既有候选及正式证据流程。

### 应用外需要提供的决定与制品

| 顺序 | 当前缺口 | 所需行动 / 验收边界 |
|---|---|---|
| 1 | 治理责任人及受信 root/registry 尚无正式证据 | 由真实人员确认治理角色、初始 root pin 和外部 role-key registry；按既有 policy 的独立主体、key usage、期限及撤回规则提供公有验证材料。私钥不交给应用、Agent 或 GitHub；不得用测试密钥替代 |
| 2 | definition approval `pending`，artifact/hash 均 null | product/privacy/security/engineering 按当前 definition bundle 签署；不是 owner 的一般实施授权，也不是 CI 构建签名 |
| 3 | ADR-006B 最终组件削减/开发接受 pending | 对现有 Python/FastAPI、PostgreSQL、Pydantic AI port、Jev 默认关闭及单体部署边界作接受/拒绝决定；对象存储、完整生产拓扑等未获证据的选择保留未决，不要求先实现生产 BCG/部署才批准开发 |
| 4 | architecture approval null | product/security/architecture/operations 对最终 architecture、ADR-001—007（含 006A/B/C）、spike、constraints、definition bundle 和目标版本绑定签署 DSSE 制品；仓库 example 永远无效，不直接填 example 当批准 |
| 5 | 前置任务状态与四个 Eval 尚无目标版本正式证据 | 由受信 evidence/verifier 流程验证签名、exact target commit 与定义/环境绑定，并形成 state-transition / gate report；不能把当前只读诊断脚本当作完整准入实现 |

现有诊断 `python scripts/verify_manifests.py task-graph` 返回 12 个未 complete 前置任务、4 个 catalogued Eval（E-ARCH-002、E-GATE-001/002、E-TASK-001），`authorization=false`。诊断完整集合见 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md)，最终仍以机器 DAG/selector 为准。即使取得外部签名，仍须完成可信验证与证据接线，不能据文件存在直接开工。

### 交接后的执行边界

先核验外部决定与制品是否满足现有规则，再做相应证据绑定/准入接线；实际 `before_feature_task` 通过后才领取正式 W2/W3 底座和 roster→Record/Task→Today/Timeline 切片。生产身份、事务、恢复与真实数据准入留在各自后续 Gate，避免循环前置。没有新外部证据时，已完成的隔离 spike 不重复运行或扩大为业务功能；向 owner 请求真实批准人和外部验证材料的取得方式，而不是要求教师补填业务账本。
