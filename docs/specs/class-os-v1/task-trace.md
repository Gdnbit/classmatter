# Task Trace Summary

> 文档状态（2026-10-08）：现行规格/规划/规则；设计存在；实现/批准须另凭目标版本证据。项目完成度见 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md)；本标识不提升批准、测试或任务状态。

本表提供完整 v1 主工作包到规格/eval 的反向索引；单项工作包的 Inputs 与 Validation 保留更精确引用。最小 Release 1 的真正原子任务在 `release-1-atomic-tasks.md`，并由下表第二部分反向索引。

| Task(s) | Requirement/rule scope | Eval/acceptance scope | Gate |
|---|---|---|---|
| T-DISC-001 | A-006/A-007/A-008, ACC-001 | E-UX-001—008 的现状基线 | 用户任务日志 |
| T-DISC-002 | R-DEV-004, FR-IMP-006/FR-EXP-002 | E-UX-003, E-EXP-006 | sample I/O confirmation |
| T-DISC-003 | R-GRD-002, FR-GRD-001—005 | E-GRD-001—006 | 成绩规则批准 |
| T-DISC-004 | R-PRV/R-AUTH, NFR-SEC | E-PRV, E-AUTH, ACC-08/10 | 数据准入 |
| T-FOUND-001 | ADR-001—006, NFR-MNT | E-ARCH-001, E-AGT-003—014, E-OPS-008 | 架构批准 |
| T-FOUND-002—004 | R-DEV-001—003, NFR-MNT-004 | E-SCOPE-001, runner self-test | harness ready |
| T-FOUND-005 | FR-PLT-001—004 | E-AUTH-001—008, AC-01 | security foundation |
| T-FOUND-006 | NFR-SEC-006/NFR-OBS-001 | E-PRV-004, E-OBS-001 | audit required |
| T-FOUND-007 | FR-AGT-003—005/NFR-REL-001 | E-CMD-001—004, E-AGT-003—008 | command gate |
| T-FOUND-008 | ADR-005/NFR-SEC-003 | E-OPS-002—004, E-SEC-003 | storage/outbox gate |
| T-ROS-001—005 | FR-CLS-001—007 | E-ROS-001—004, E-AUTH-001/002, E-UX-002 | AC-01 |
| T-EVT-001—005 | FR-EVT/FR-TSK/NFR-UX-001 | E-EVT-001—008, E-UX-001/002, E-WEB-002/003 | AC-02 + value gate |
| T-AGT-001—006 | FR-AGT-001—010 | E-AGT-001—014, E-MIG-005, E-PRV-001/002, E-UX-006 | AC-08 |
| T-IMP-001—005 | FR-IMP-001—006 | E-IMP-001—010, E-UX-003, E-A11Y-001 | AC-03 + sample gate |
| T-GRD-001—005 | FR-GRD-001—007 | E-GRD-001—008, E-UX-004 | AC-04 + rule gate |
| T-SEA-001—005 | FR-SEA-001—004 | E-SEA-001—010, E-UX-005/006, E-A11Y-004 | AC-05 |
| T-ORG-001 | FR-GRP-001/FR-POS-001/002 | E-ORG-001—003 | domain acceptance |
| T-DOR-001—004 | FR-DOR-001—004 | E-DOR-001—006 | AC-06 + value gate |
| T-REP-001—003 | FR-REP/FR-COM | E-REP-001—008, E-UX-007 | AC-07 + golden gate |
| T-EXP-001/002 | FR-EXP-001—004 | E-EXP-001—006, E-UX-008 | AC-09 + golden gate |
| T-MCP-001 | FR-AGT-007/008 | E-AUTH-004, E-AGT-009—012 | separate enablement |
| T-HARD-001—005 | NFR-SEC/REL/PERF/UX/OBS | E-WEB/E-A11Y/E-PERF/E-SEC/E-OPS/E-MIG/E-OBS | release gate |
| T-REL-001—003 | 全部纳入的 FR/NFR | AC-01—10 + `verify all` | staging/pilot/stable approvals |
| T-EVO-001 | LR-SEM-001, LR-SEM-002, LR-EPI-001, LR-TIME-001 | E-EVO-001, E-EVO-002, E-EVO-003, E-EVO-009, AC-11, AC-14 | post-R1 ontology ADR；不改 R1 schema |
| T-EVO-002 | LR-CAP-001, LR-RES-001, LR-CTX-001, LR-KNW-001 | E-EVO-004, E-EVO-005, E-EVO-006, E-EVO-007, AC-11, AC-12 | post-R1 contract；processor/discovery gate |
| T-EVO-003 | LR-INT-001 | E-EVO-008 | Intent Catalog + wedge research；non-R1 |
| T-EVO-004 | LR-EXT-001, LR-KRN-001 | E-EVO-011, E-EVO-012, E-EVO-021, AC-13 | schema policy/migration/rollback；non-R1 |
| T-EVO-005 | LR-SEM-002, LR-COL-001 | E-EVO-002, E-EVO-013, E-EVO-016, E-EVO-017, E-EVO-018, AC-14 | single-authorizer migration/control study；non-R1 |
| T-EVO-006 | LR-TIME-001, LR-WRK-001 | E-EVO-009, E-EVO-010 | real-task evidence required；non-R1 |
| T-EVO-007 | LR-EPI-001, LR-RES-001, LR-KNW-001, LR-EXT-001, LR-DER-001 | E-EVO-005, E-EVO-007, E-EVO-011, E-EVO-014, E-EVO-019, E-EVO-020, E-EVO-021, AC-11, AC-12 | inference/derived/schema consumer invalidation；non-R1 |
| T-EVO-008 | LR-VALUE-001 | E-EVO-015, ACC-001, ACC-017, AC-15 | preregistered multidimensional Net Burden gate；non-R1 |

任务范围表示如 `FR-EVT` 时，指 Requirements 中该前缀下的全部编号；可执行 runner 使用展开后的显式 ID 清单，不能依赖字符串范围解析。

`T-EVO-*` 是长期定义/发现任务，不是 Release 1 原子任务。只有新 release change 批准后才能拆分为该 release 的机器 task definitions；不得写入 `.ai/gates/release-1-task-definitions.yaml` 或 state。

## Release 1 原子任务反向索引

| Task(s) | Requirement/rule scope | Eval/acceptance scope | Gate |
|---|---|---|---|
| T-RGOV-001—004, T-RGOV-006 | R-PRV-005/006, R-RET-001/002, R-OPS-003, R-DEV-003 | E-PRV-005—012, E-RET-001—004, E-ARCH-002 | governance + processor + architecture approval |
| T-RGOV-005, T-RPLT-012 | R-ADM-001, FR-PLT-006, NFR-PRV-005 | E-ADM-001—009 | BCG-only workspace-bound allocation + runtime real-data admission |
| T-REVAL-001—025 | R-DEV-001/002/005, R-OPS-003, R-RET-001/002, R-VALUE-001 | `.ai/gates/release-1-evals.yaml`, E-TASK-001, E-GATE-001/002, E-DEV-001, required E-ID 全集 | executable runner + honest status + security/ops/lifecycle/value protocols |
| T-RSPK-001—003 | ADR/read-draft Agent/self-host | E-ARCH-001, E-AGT-001/002/009—014, E-LOCAL-001—006 | architecture evidence; no Agent HITL dependency |
| T-RPLT-001—011 | FR-PLT, NFR-SEC/PRV/OBS, R-RISK-001, R-AUD-001 | E-AUTH-001/005/007, E-CMD-001—004, E-RISK-001—005, E-AUD-001—004 | secure foundation |
| T-RPLT-013—019 | FR-PLT-002/007, FR-AGT-003—005 | E-AUTH-009—018, E-AGT-015—025 | owner lifecycle + classified identity/business command boundaries |
| T-RDOM-001—005 | FR-CLS-001/002/003/007, R-ID-001, R-TIME-001 | E-CLS-001, E-ID-001—004, E-TIME-001/002, E-ROS-001—004 | roster boundary |
| T-RDOM-006—013 | FR-EVT-001/002/003/005/006, FR-TSK-001/002/004 | E-EVT-001—004, E-TSK-001, E-ATT-001, E-LEAVE-001, E-HWK-001, E-AGT-021—025 | fact-event/task slice through Gateway |
| T-RLIFE-001—005 | FR-EXP-004, NFR-PRV-004 | E-PRV-006—008, E-RET-001—004 | lifecycle before real pilot; final store reconciliation |
| T-RWEB-001—006 | NFR-UX-001/003—006, included FR-CLS/EVT/TSK/AGT | E-CLS-001, E-WEB-002—004, E-LOCAL-001—005, E-AGT-015—025 | mobile + trusted UI |
| T-RAGT-001—004 | FR-AGT-001/002/006/009/010 | E-AGT-001/002/009—015, E-AUD-002 | no Agent commit/approve |
| T-REXP-001—003 | FR-EXP-001/003, R-EXIT-001 | E-EXIT-001, E-EXP-001—005, E-AUD-003 | before-real-write exit gate |
| T-ROPS-001—007 | NFR-OPS-001—004, NFR-SEC-001, R-OPS-003 | E-OPS-005—014, E-MIG-001—004, E-SEC-007 | supported self-host |
| T-RREL-001—003 | Exact IDs in `.ai/gates/release-1-requirements.yaml` | required E-IDs in `.ai/gates/release-1-evals.yaml` + E-VALUE-001 | synthetic shadow, signed admission, approved pilot |
| T-DISC-001, T-REVAL-025, T-RREL-002/003 | R-PROD-001, R-VALUE-001, A-027 | E-VALUE-001, ACC-018, AC-16, C-075 | responsibility-risk baseline + value protocol + R1 value gate；不改变机器任务集合 |
