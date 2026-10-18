# Long-term Evolution Requirements

> 文档状态（2026-10-08）：长期设计/发现；non-R1；无当前实现授权。项目完成度见 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md)；本标识不提升批准、测试或任务状态。

状态：`canonical / non-R1 / implementation-deferred`\
版本：`0.3.1-open-world-integration`

本文是长期演进需求的 canonical source，与 [R1 Requirements](requirements.md) 分离。这样 R1 requirement manifest 只覆盖其声明的 107 个 `FR-*`/`NFR-*`；本文 15 个 `LR-*` 均为 `applicable: false`，不得被 R1 runner 静默吸收或遗漏。任何 `LR-*` 进入实现，必须由新的 release applicability manifest 逐项分类，并同时建立 requirement → rule/case → architecture/domain → API/tool → eval → task → release 的双向追溯。

## Requirements

- **LR-SEM-001 [long-term-invariant]**：长期模型必须区分 Workspace/Scope/Subject/Identifier 与 Person/User/Student/Guardian/Teacher；统一 Person 只复用身份引用，不得把不同角色、目的和专业数据合成万能画像或万能表。（`rule_id`: R-SEM-001；`case_id`: C-060）
- **LR-SEM-002 [long-term-invariant]**：RoleBinding、ResponsibilityAssignment、Availability、Relationship、Membership 和 Assignment 是描述性领域事实；唯一 AuthorityGrant/PolicySet 由 `identity-access` 拥有。角色、责任、成员资格或可用性不得自动推出访问/写入权限；旧 `Membership.role` 迁移不得自动生成 Grant，冲突、缺失或过期一律拒绝。（`rule_id`: R-ORG-001；`case_id`: C-061）
- **LR-EPI-001 [long-term-invariant]**：Domain Fact、Observation、SelfReport、Claim、Evidence、Derived Signal、AI Inference 与 Draft/Candidate 必须具有不同类型、状态和展示。AI Inference 不得自动晋升为人物事实，也不得未经单独规则与人工决定改变权限、纪律、风险分、任务优先级、外发、Attention 或长期画像。（`rule_id`: R-EPI-001；`case_id`: C-062）
- **LR-CAP-001 [long-term-invariant]**：任何 Channel/Capture/Connector 只可通过 typed Command 生成受控 Envelope、Draft、Candidate 或 Proposal；正式业务数据必须经过实体解析、owning Domain 校验和 Business Command Gateway，所有中间态持久化同样不得绕过 BCG。（`rule_id`: R-CAP-001；`case_id`: C-063）
- **LR-RES-001 [long-term-invariant]**：Entity Resolution 必须保留候选、来源、证据、冲突、决策和可撤销性；同名、昵称、转发或低置信不得自动合并，错误绑定必须触发派生失效传播。（`rule_id`: R-RES-001；`case_id`: C-064）
- **LR-CTX-001 [long-term-invariant]**：Active/Working Context、Harness Session、Conversation Memory 和 Preference Memory 只用于选择、连续性和可撤销偏好；它们不是权限或业务事实源，冲突时以授权 Query 返回的 Domain Fact 为准。Memory 的持久化命令和读取投影分别受 BCG/Query Gateway 约束。（`rule_id`: R-CTX-001；`case_id`: C-065）
- **LR-KNW-001 [long-term-invariant]**：Knowledge 必须版本化并记录 scope、有效期、citation、owner 和 supersession；RAG Index 是可重建副本，不得替代或覆盖 Domain Fact。Knowledge/RAG 的写入和读取分别经过 BCG 与 Query Gateway，不得持有跨 scope 索引凭证。（`rule_id`: R-KNW-001；`case_id`: C-066）
- **LR-INT-001 [long-term-invariant]**：每个进入产品的 Intent 必须登记 outcome、scope、实体、权限、purpose、risk floor、歧义策略、允许工具、写 Command、回退、审计、Eval 和 release 状态；缺信息时澄清、给候选或拒绝，不得猜测越权动作。（`rule_id`: R-INT-001；`case_id`: C-067）
- **LR-TIME-001 [long-term-invariant]**：长期时间模型必须区分 occurred、recorded、valid/effective 和 system/transaction time，并保存原始表达、时区、精度、置信与回溯更正；Calendar 是权限限定 Projection，不是事实源。（`rule_id`: R-TIME-001, R-TIME-002；`case_id`: C-054, C-068）
- **LR-WRK-001 [discovery]**：Commitment、Case、Decision、Workflow、Playbook、Trigger、ScheduleItem 与现有 Event/Task 分工明确；Workflow/Review 中间态的每次持久迁移均使用 typed Command 经 BCG，所有查询经 Query Gateway；Trigger 默认只产生 Draft/Review Item。（`rule_id`: R-WRK-001；`case_id`: C-069；`assumption_id`: A-023）
- **LR-EXT-001 [long-term-invariant]**：扩展顺序固定为复用 Ontology → 配置 Domain Pack → 受控 Custom Extension → 经验证 Promotion；Agent 只能经 typed Command 提交 SchemaProposal，逻辑 schema 由 Extension Service 经 BCG 建立，物理 schema 只由版本化发布迁移；禁止任意 DDL、万能 JSON/Fact 表和无约束关系。schema/version 也是依赖图节点，回滚必须使表单、validator、workflow、索引、Tool schema、saved query 和导出模板失效或降级。（`rule_id`: R-EXT-001；`case_id`: C-070；`assumption_id`: A-024）
- **LR-KRN-001 [long-term-invariant]**：Stable Kernel 只拥有稳定业务契约；Harness、OCR、ASR、RAG、Artifact renderer、workflow runtime、connector runner 和 Scheduling Solver 必须作为可替换 Shared Capability，经稳定 port 接入且无权限裁决或直接写入能力。（`rule_id`: R-KRN-001；`case_id`: C-071）
- **LR-COL-001 [discovery]**：任课教师、年级主任、德育、心理老师、校医、宿管等协作必须使用唯一 `identity-access` 授权决定、purpose/scope/有效期 AuthorityGrant、专业 compartment 和最小披露式转介/升级/交接；不据此提前建设学校 ERP。（`rule_id`: R-COLLAB-001；`case_id`: C-072；`assumption_id`: A-021, A-025）
- **LR-DER-001 [long-term-invariant]**：来源事实、知识、身份绑定或 schema version 更正、限制、删除或失效时，AIInference、summary、profile、RAG、artifact、attention、trigger、cache、表单、validator、workflow、Tool schema、saved query、导出模板与备份处理队列必须依赖可枚举的 versioned source refs 失效/重建或显式标记 stale，未完成前不得继续作为最新证据。（`rule_id`: R-DER-001；`case_id`: C-073）
- **LR-VALUE-001 [discovery-gate]**：新增字段、Capture、Memory、Connector、Review、Workflow、Reminder 或 AI 能力必须使用预注册的多维 Net Burden Gate：时间净值、wrong-person/错误非劣、backlog 上限与清偿时间、onboarding 与持续维护分开、隐私/安全/运维 hard guardrail；明确样本、周期、缺失值和决策人。任一 hard guardrail 失败或没有真实净收益时停止、缩小或删除，不得用任意权重合成单一分数掩盖伤害。（`rule_id`: R-VALUE-001, R-VALUE-002；`case_id`: C-055, C-074；`assumption_id`: A-018, A-020, A-022, A-026）

## Applicability Contract

- `class-os-r1`: 15/15 `excluded / non-applicable`，且不进入 `.ai/gates/release-1-requirements.yaml`，因为该文件只以 [requirements.md](requirements.md) 的 107 个 R1-source requirements 为 universe；
- future release：必须新建覆盖本文全部 LR 的 machine applicability manifest，不允许未分类 ID；
- maturity：`long-term-invariant` 表示约束未来设计选择，不表示功能已验证或已实现；`discovery`/`discovery-gate` 仍是假设；
- 当前证据：全部 `E-EVO-*` 为 catalogued/non-R1，`T-EVO-*` 为定义/发现任务，`implemented-green=0`。
