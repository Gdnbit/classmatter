# Implementation Plan: ClassMatter v1

> 文档状态（2026-10-08）：现行规格/规划/规则；设计存在；实现/批准须另凭目标版本证据。项目完成度见 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md)；本标识不提升批准、测试或任务状态。

状态：`canonical-plan / release-1-frozen / open-world-evolution-deferred`。任务编排基于 eval-first；架构、数据治理责任人与真实样例尚未批准，因此 Release 1 真实数据试点之前的确认任务是强门。本文原有的人日区间缺少基准数据，已撤回；最小 Release 1 以 `release-1-manifest.md` 和 `release-1-atomic-tasks.md` 为唯一实施范围，并在首批五项工程任务后基于实际 cycle time 重估。

Release 1 的文件级代码落点与 94 项任务波次编排见[公开工程边界说明](../../ENGINEERING_OVERVIEW.md)和 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md)。二者是本计划的执行导航，不改变本目录中 Requirement、Eval、Task 和 Gate 的权威定义；冲突时以机器清单、原子任务和已批准 ADR 为准。

## 1. Delivery Strategy

采用纵向切片，而不是先做完所有数据库再做 UI：

```text
R0 发现/安全/退出骨架
→ R1 最小学生事实事件闭环
→ R2 成绩导入与分析
→ R3 座位/组织（宿舍按证据）
→ R4 报告/迁移/精选 MCP
→ pilot hardening
```

每个切片都经过：rule/eval → domain → application → API/tool → UI → audit/metrics → E2E → 用户验收。

## 2. Provisional Stack Decision Gate

2026-10-07 对齐：React/Vite 已冻结，Python/FastAPI、PostgreSQL 18、Pydantic AI adapter 和 DSSE 已获分段开发证据；不从零选栈，也不声称 production 组合已批准。Release 1 以 T-RSPK-001—003、T-REVAL-019 和 ADR 为准；Agent 只读/草稿，HITL 不是 R1 内核门。

参考 spike 组合：

- Web/PWA：已接受 React/Vite + TypeScript/Tailwind，不另起 Next.js；
- API/domain：FastAPI + Python；
- Data：PostgreSQL；对象存储使用 adapter；
- Worker：同代码库独立进程 + transactional outbox；
- Agent：Pydantic AI v2 adapter（经 `AgentRuntimePort`，OpenAI Agents SDK 作为对照/回退）；TypeSafe/Jev 仅作为可关闭的 typed 路由层，经中文标注集证明收益后启用；
- Observability：OpenTelemetry 兼容；
- Packaging：容器化单主机试点。

完整 v1 的 T-FOUND-001 主工作包须比较单语言后端/全栈及不采用 Agent SDK 的替代。共同标准：本地可重复、测试替身容易、敏感 trace 可关闭/脱敏、自托管资源可接受、许可证清楚；只有未来引入 Agent 写操作时才验证相应 HITL 恢复能力。R1 的 Web 批准由应用服务负责，不依赖 Agent SDK HITL。工具选择采用“确定性 capability filter → 可选 Jev typed route → 主模型 → Tool Gateway”的顺序；无论模型或置信度如何，业务提交仍由 BCG 确定性执行。详细收口步骤见 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md)。

## 3. Work Breakdown and Milestones

### M0：Business and Architecture Ready

范围：访谈、样例确认、数据流、ADR、技术 spike、repo/harness。\
出口：A-003/A-004/A-010 有决定；architecture approved；治理责任与处理方准入有决定；合成 eval runner 可执行。\

### M1：Secure Foundation

范围：workspace/auth/scope、基础 schema、audit、idempotency/outbox、对象隔离、CI/CD。\
出口：E-AUTH、E-CMD、E-PRV、E-SEC 基础套件通过；敏感读写审计均为 fail-closed。\

### M2：Student Event Vertical Slice

范围：class/term/roster、事实事件、任务、Today（不含课务）、手机 UI、基础 Agent 查询和事件草案，以及最小退出导出往返。\
出口：AC-01、AC-02、AC-08 的相关子集；任何真实写入前，退出导出已在干净环境往返通过；真机试用达到早期门槛。\

### M3：Import and Grades

前置：真实脱敏样例与口径确认。\
范围：文件隔离、Excel/CSV adapter、mapping workbench、考试/成绩、确定性指标、分析 UI/Agent。\
出口：AC-03、AC-04；E-IMP/E-GRD 全部目标项通过。\

### M4：Seating and Organization

范围：layout、约束 DSL、solver、独立 validator、SeatMap、proposal/approval/apply/undo、职务/分组。\
出口：AC-05；硬约束 property tests 零违反。\

### M5：Dormitory Decision Slice

前置：A-008 确认且频率/价值通过。\
范围：DormMap、床位分配/交换/历史；不默认集成学校宿管系统。\
出口：AC-06；未通过价值门则 deferred。\

### M6：Reports, Formal Formats and MCP

前置：报告/导出 golden 确认。\
范围：claim-level 事实卡驱动的报告草稿、沟通草稿、正式格式和精选只读 MCP。核心退出导出不是本阶段附属功能，已在 Release 1 真实写入前完成。\
出口：AC-07、AC-09；无自动外发。\

### M7：Pilot Hardening and Release

范围：性能、可访问性、安全、备份恢复、迁移、告警、runbook、隐私复核、灰度。\
出口：AC-10 和发布门全部通过。\

完整 v1 当前不提供承诺排期。只有 Release 1 原子任务可以进入执行队列；等待治理批准的时间单列，不混入工程 cycle time。后续 milestone 必须经过 Release 1 价值门、重新拆分为 1—3 天任务并依据实测吞吐量估算。

## 4. Critical Path

```text
用户任务日志/样例
→ 输出与成绩口径确认
→ 架构/数据流批准
→ auth/audit/idempotency
→ roster/fact-events + minimum exit export roundtrip
→ real import adapter
→ grades
→ seating/other modules
→ reports/export
→ recovery/security/UX pilot gate
```

Agent runtime spike可与样例收集并行，但 Agent 写入依赖 approval/audit foundation。

### Post-R1：开放世界演进轨

`LR-*`、`E-EVO-*` 与 `T-EVO-*` 只定义长期语义、发现任务和未来 release 的准入条件，不加入上述 R0—R1 执行队列。演进顺序固定为：复用 Stable Kernel Ontology → 经证据选择 Domain Pack → 受控 Custom Extension → 通过迁移、回滚、安全和 Net Burden Gate 后 Promotion。任何未来 Capture、Memory、Knowledge、Workflow 或 Extension 的持久化变更仍必须经过 Business Command Gateway；Agent 和扩展不得执行任意 DDL。获胜 wedge 只能通过独立 release change、适用需求/eval/task 清单和重新批准进入实施。

## 5. Parallel Workstreams

| Stream | 可并行内容 | 不可越过的依赖 |
|---|---|---|
| Product/UX | 访谈、原型、术语、确认卡测试 | 不把未确认原型变成 golden |
| Domain/API | 领域模型、纯规则、repository contracts | auth/audit/idempotency foundation |
| Web/PWA | design tokens、shell、mock contract components | 不自行定义业务规则 |
| Agent | Skill、Tool schema、fake provider eval | Tool Gateway/policy contract |
| Data/Import | parser sandbox、synthetic fixture | 生产 mapping 依赖真实样例 |
| QA/Security | runner、auth matrix、fault injection、scans | 发布前全套集成 |
| DevOps | local/CI/staging、backup harness | 生产部署需数据准入 |

## 6. Branch and Change Strategy

- 一项原子任务一条短分支/变更集；
- migration 与兼容代码同一任务或显式依赖任务；
- feature flag 保护未完成的 Agent 写入、MCP、宿舍和外发；
- schema/tool 破坏性变化新版本并保留兼容窗口；
- 不长期维护“完整前端分支”和“完整后端分支”再大合并。

## 7. Definition of Ready per Feature

- 需求 approved 或明确 prototype-only；
- 规则、案例、输出契约和 open assumptions 已审查；
- eval 已存在且能红/能执行，或 runner 任务是唯一前置；
- 文件 scope、依赖、迁移、权限、审计和回滚清晰；
- UI flow/contract 可用；
- 资源许可已批准。

## 8. Definition of Done per Feature

- FR/eval/task/code 追溯；
- domain + application + contract + integration + E2E 测试；
- auth、field projection、audit、idempotency、observability；
- migration、rollback/compensation、runbook；
- responsive/a11y/manual UX 证据；
- 无 P0/P1 缺陷；
- 文档和 release notes 更新。

## 9. Validation Layers

1. Static：format、lint、type、schema、dependency boundaries。
2. Unit：纯规则、状态机、匹配、计算、solver validator。
3. Contract：REST、Tool/MCP、event/outbox、adapter。
4. Integration：DB transaction、RLS/policy、object storage、worker。
5. E2E：真实浏览器关键任务。
6. Agent eval：意图、Tool selection、grounding、injection、approval。
7. Non-functional：performance、a11y、security、fault/recovery。
8. Business：目标用户任务和输出 golden review。

## 10. Rollback Strategy

- 应用：上一不可变镜像；
- 数据库：优先兼容迁移和前滚修复，破坏性变更前备份/演练；
- 业务变更：版本化 undo 或补偿 Command；
- Agent/Tool：feature flag、tool version 回退、provider kill switch；
- 输出：撤销短期链接，保留审计；
- 发布：canary/小用户灰度，指标恶化立即关闭新能力。

## 11. Stop/Go Decisions

- M0 未完成：不实现生产业务功能；
- M2 未证明事件闭环价值：不扩大到全模块；
- M3 无确认样例：只做 parser framework，不做“万能导入”；
- Agent 增加时间/错误/隐私负担：降级为只读或草稿；
- 宿舍频率不足：M5 deferred；
- 生产安全/恢复门失败：不试点。
