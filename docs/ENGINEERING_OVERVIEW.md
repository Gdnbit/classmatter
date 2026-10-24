# ClassMatter 工程边界、数据流与代码地图

## 定位与证据

产品是教师外置工作记忆与事务闭环工具，不是完整学校 ERP。目标是少记、少追、少重复和少承担不清楚的责任。定性需求不构成代表性样本、责任法律结论或已验证的减负效果；没有公开原始访谈或可识别来源。真实教师研究、可用性和净负担测量保持 discovery。

## 分层与写入链

Web 的 typed client → HTTP/identity guard → QG 只读业务查询；业务变更走 strict closed command → domain validation → 风险分类 → 服务端 preview → 必要的人工 approve → BCG 原子 commit + 幂等 receipt + 同事务 audit。ISB 只管理身份生命周期。UI 不复制领域规则。会话失效、权限/版本变化或审计不可用均失败关闭，不自动重放未知结果的写请求。

`backend/src/class_os/domain/` 是封闭领域规则；`application/` 是 use case/gateway；`infrastructure/` 是 SQL/模型/记忆/凭据 adapters；`interfaces/http/` 是装配、严格 DTO 和同源路由；`backend/local.py` 是受信 operator 入口。`apps/web/src/runtime/` 是实际 UI；`shell/` 是显式 mock 演示。`contracts/` 的 generated schema 必须由 exporter 检查漂移，不能手改绕过。

## 事实、记忆和开放世界

事实与 Observation/Claim/Derived Signal/AI inference 有权威边界；学生显示名不是身份键。Person、组织与角色、关系、分组、Assignment、Evidence/Provenance、Capture/Entity Resolution、Case/Commitment/Temporal 是长期语义，不代表所有对象已实现。Conversation Memory 是短期上下文，Knowledge/RAG 是检索依据，都不是正式业务事实源。Harness、OCR、ASR、RAG、渲染与求解器是可替换能力，不进入 Stable Kernel。

扩展顺序是复用 Ontology → Domain Pack → 受控 Custom Extension → 验证后 Promotion。禁止万能 JSON/Fact 表和 Agent 任意 DDL。Capture 仅产 Draft/Candidate，仍经过领域校验与 BCG。Workflow、Scheduling、Attention、Conflict 不因长期愿景扩张 R1。任何学校多角色权限必须显式限定 responsibility/authority/scope，而非按称谓自动授予访问。

## 当前技术与限制

可选 `apps/desktop/` 是 Electron 独立 Windows Demo 宿主，复用 `apps/web` 的显式合成构建，通过本地资源协议加载，不启动后端或数据库，也不改变 Agent Harness。其单独构建、窗口/沙箱边界和进程验收见[桌面设计](desktop-demo.md)。新增桌面宿主不代表正式 R1 或原型内全部业务能力已交付。

2026-10-22 W2-01新增独立的源码开发runtime入口，复用已有R1页面和后端，托管固定自有API进程，先验证每次启动的进程proof与readiness，再开放该loopback同源。它不改变离线Demo、不初始化/迁移/启动用户数据库、不代设owner；不是全部冻结Demo页面绑定完成。临时SCRAM数据库+真实Electron已验证事实/任务经原BCG持久化及应用重启后复用，Agent fake只读/草稿不自动写入；正式发布、真实模型、完整退出仍未完成。代码与剩余项见[实现台账](implementation-ledger.md)。

数据库当前 head0016、22 张登记表、risk r1.3；没有自动迁移已存在实例。0015 显示名更正、0016 学期元数据更正均保留历史 migration 和权限约束。恢复使用经验证快照/前滚，禁止破坏性 downgrade。退出包有 core 验证及上限，但 `lifecycle_complete=false`，不是完整跨机恢复或退役实现。

Agent 复用 Pydantic AI loop 和 OpenAI-compatible adapter。原有查询/任务草稿和受控原文记录候选不包含 business-write/approve 工具；运行状态、来源回执、短期 memory 不授权业务事实。真实模型质量与 teacher research 未通过不能被 fake tests 替代。

## Agent Runtime 与未来 Work Runtime（2026-10-22 非实施研究）

[Agent 承接工作与业务记忆所有权](product/agent-owned-work-and-attention.md) 探讨了未来从“提醒教师”向“经授权由系统主动推进”的扩展。**业务事实、长期记忆、权限、等待/调度、执行证据与工作状态始终由 ClassMatter 自行治理**；Pydantic AI（现有）或 Pi（候选）只是可替换的按需 Agent Runtime。它们的 Session/compaction/内置耐久化能力均不能取代 ClassMatter 的正式领域工作状态。

[框架与社区调研](research/2026-10-22-pydantic-ai-pi-runtime-assessment.md) 推荐保留默认 Pydantic AI；[候选实验计划](research/2026-10-22-agent-runtime-and-work-evaluation-plan.md) 规定合成对照、安全 Hard Gate 和新增能力的价值验证。**三个文档均不改变 R1 范围、版本、正式业务写入/审批权限或安全准入。**

## 数据库与实时接入：下一阶段提案

[数据库与实时数据演进设计](design/database-live-data-design.md)核对当前PostgreSQL模型与完整Demo之间的缺口，并细化会话/运行、工作专题、跨页一致、变更订阅、索引、迁移和退出。当前主库与QG/BCG/ISB继续复用；“实时”不代表已存在业务订阅流，“工作专题”不等于授权workspace，“聊天可保存”不等于人物事实或长期记忆。

该文档是后续设计提案，不取代canonical SDD或批准新release。D0可先复用既有R1接口绑定真实页面；耐久聊天、工作专题及新事件表须另立后续change，并同步schema inventory/最小权限/备份/退出/生命周期验证。当前无对应新迁移、性能或真实用户验收；不把所有演示栏目接假数据后声称生产化。

## 验证与发行

保留 107 项需求、147 项 Eval、94 个原子任务及其源行哈希；合成开发准入不代表正式 task/eval promotion。`scripts/verify.ps1` 为统一入口，`all` 包括 disposable PG/浏览器与 spikes；正式 security target 与真实数据/发布签名另受 Gate 管理。

本公开仓库不携带原开发仓库历史、原始访谈、私人指令、个人截图、旧档案或运行数据。原子任务表与机器 Gate 保持原字节，避免更名破坏哈希；其历史字样只是技术兼容。依赖及来源权利必须单独核验，公开状态以 [readiness](OPEN_SOURCE_READINESS.md) 为准。
