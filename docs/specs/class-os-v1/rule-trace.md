# Rule Trace: ClassMatter v1

2026-10-15 实现追溯：原R-DATA-002/R-POS-001 → FR-CLS-001（R1 included）→ roster TermMetadata/ChangeTerm与QG/BCG → 私有term.update十字段/metadata.v1投影 → test_term_metadata.py、Web term-metadata/18命令收据/真实browser → T-RDOM-011/T-RWEB-006（关联T-RWEB-002/T-RPLT-006/007/011）→ class-os-r1。E-CLS-001/E-ROS-004/E-AGT-016—024/E-CMD/E-AUD为已有约束，不将合成测试计成正式Eval green；原需求语义/任务source row/依赖/Gate无变化，risk与grant显式变化见 [开发登记](../../changes/2026-10-08-synthetic-development-admission.md)。

> 文档状态（2026-10-08）：现行规格/规划/规则；设计存在；实现/批准须另凭目标版本证据。项目完成度见 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md)；本标识不提升批准、测试或任务状态。

状态：`review`。`planned` 表示已有规格、eval 和任务但未实现；`deferred` 表示有明确解除条件。

| rule_id | requirement | eval_case | task | status |
|---|---|---|---|---|
| R-POS-001 | FR-PLT-001, FR-CLS-001/005 | E-AUTH-001, E-ROS-004 | T-DISC-001, T-ROS-001—005 | planned |
| R-POS-002 | Out of Scope | E-SCOPE-001（文档检查待 runner） | T-DISC-001, T-FOUND-004 | planned |
| R-UX-001 | FR-AGT, NFR-PERF-004 | E-UX-002, E-PERF-003 | T-AGT-003—005 | planned |
| R-UX-002 | FR-TSK-004, FR-SEA-001 | E-UX-002, E-WEB-001/002 | T-ROS-005, T-EVT-004, T-SEA-005 | planned |
| R-UX-003 | FR-EVT-001, NFR-UX-001/002 | E-UX-001/003, E-WEB-002 | T-EVT-004, T-IMP-004 | planned |
| R-UX-004 | FR-AGT-003, NFR-UX-003 | E-AGT-003, E-UX-006 | T-AGT-001/002/005 | planned |
| R-DATA-001 | FR-CLS-002/004 | E-ROS-001 | T-ROS-001/002/004/005 | planned |
| R-DATA-002 | FR-CLS-001/003/005, FR-GRP-001, FR-EXP-004 | E-CLS-001, E-ROS-004, E-SEA-010, E-DOR-006 | T-ROS-001/002, T-RDOM-002/011, T-SEA-001, T-DOR-002 | planned |
| R-DATA-003 | FR-EVT-003, FR-GRD-006, FR-REP-002 | E-EVT-003, E-GRD-007, E-REP-005 | T-EVT-001, T-GRD-004/005, T-REP-001/002 | planned |
| R-DATA-004 | FR-EXP-001/002, NFR-MNT-001/003 | E-EXP-001/002/006 | T-EXP-001/002, T-FOUND-001 | planned |
| R-STU-001 | FR-CLS-002/007, FR-IMP-002 | E-ROS-002/003, E-IMP-004/005 | T-ROS-003, T-IMP-003 | planned |
| R-STU-002 | FR-CLS-006 | E-AUTH-002, E-PRV-001 | T-FOUND-005, T-ROS-004/005 | planned |
| R-IMP-001 | FR-IMP-001—003 | E-IMP-001—009 | T-IMP-001—004 | planned |
| R-IMP-002 | FR-IMP-004 | E-IMP-010, E-CMD-004 | T-IMP-005 | planned; assumption |
| R-EVT-001 | FR-EVT-001/002/005/006 | E-EVT-001/006/008 | T-EVT-001/002/004 | planned |
| R-EVT-002 | FR-EVT-004, FR-TSK-001—003 | E-EVT-004, E-TSK-001 | T-DISC-001, T-EVT-003, T-RDOM-009/013 | needs-example |
| R-GRD-001 | FR-GRD-003 | E-GRD-001—004 | T-GRD-002 | planned |
| R-GRD-002 | FR-GRD-001—005 | E-GRD-001—006 | T-DISC-003, T-GRD-001/002 | deferred until sample/rule confirmation |
| R-GRD-003 | FR-GRD-004—006 | E-GRD-005/007, E-UX-004 | T-GRD-004/005 | planned |
| R-SEA-001 | FR-SEA-002/003 | E-SEA-002—004/007 | T-SEA-002/003/004 | planned |
| R-SEA-002 | FR-SEA-002/003 | E-SEA-006 | T-DISC-001, T-SEA-002/003 | needs-example |
| R-SEA-003 | FR-SEA-004 | E-SEA-008—010, E-UX-006 | T-SEA-004/005 | planned |
| R-DOR-001 | FR-DOR-001/002 | E-DOR-001—004 | T-DOR-001—003 | conditional/deferred |
| R-DOR-002 | FR-DOR-003/004 | E-DOR-005/006 | T-DOR-003/004 | conditional/deferred |
| R-POSN-001 | FR-POS-001, FR-DOR-001 | E-ORG-001/002 | T-ORG-001 | planned |
| R-REP-001 | FR-REP-001/003, FR-COM-001 | E-REP-001/004/006 | T-REP-001—003 | planned |
| R-REP-002 | FR-REP-002 | E-REP-001—003, E-AGT-014 | T-REP-001/003 | planned; assumption |
| R-COM-001 | FR-COM-001/002 | E-REP-006/008 | T-REP-002/003 | planned |
| R-AGT-001 | FR-AGT-002 | Skill lint + E-AGT-001/002 | T-AGT-004 | planned |
| R-AGT-002 | FR-AGT-001/006, NFR-MNT-001 | E-AGT-001/013/014 | T-AGT-002/003 | planned |
| R-AGT-003 | FR-AGT-001 | E-AGT-011, E-SEC-001 | T-AGT-001/002/006 | planned |
| R-AGT-004 | FR-AGT-007/008 | E-AUTH-004, E-MIG-005 | T-AGT-001/002, T-MCP-001 | planned |
| R-AGT-005 | FR-AGT-009 | E-ARCH-001（文档/配置检查） | T-FOUND-001, T-AGT-003 | planned |
| R-SAFE-001 | FR-AGT-003/004 | E-AGT-001—003 | T-FOUND-007, T-AGT-001/002 | planned |
| R-SAFE-002 | FR-AGT-004/005, FR-SEA-004 | E-AGT-003—008, E-UX-006 | T-FOUND-007, T-AGT-005 | planned |
| R-SAFE-003 | NFR-REL-001, FR-IMP-004 | E-CMD-001—004, E-OPS-001—004 | T-FOUND-007/008 | planned |
| R-SAFE-004 | FR-CLS-007, FR-DOR-004, FR-EXP-004 | E-SEA-010, E-DOR-006, E-OPS-003 | T-ROS-003, T-SEA-004, T-DOR-003 | planned |
| R-PRV-001 | NFR-SEC-001/003/004, FR-EXP-003 | E-PRV-001—004, E-EXP-003/004, E-SEC-007 | T-DISC-004, T-AGT-002, T-HARD-003, T-ROPS-001 | planned |
| R-PRV-002 | NFR-SEC-004 | E-PRV-002 | T-DISC-004, T-AGT-002 | planned |
| R-PRV-003 | NFR-SEC-005 | E-SEC-005, E-PRV-003 | T-FOUND-003/004, T-HARD-003 | planned |
| R-PRV-004 | NFR-SEC-006, NFR-OBS-001 | E-PRV-004, E-OBS-001 | T-FOUND-006, T-HARD-005 | planned |
| R-AUTH-001 | FR-PLT-001—004, NFR-SEC-002 | E-AUTH-001—008 | T-FOUND-005, T-HARD-003 | planned; role details open |
| R-AUTH-REC-001 | FR-PLT-002/007 | E-AUTH-015—018 | T-RGOV-006, T-RPLT-013/014/018/019 | proposed; offline recovery-code scheme |
| R-OPS-001 | NFR-REL-003/004 | E-OPS-005—007, E-MIG-001—003 | T-HARD-004, T-REL-003 | planned; RPO/RTO open |
| R-OPS-002 | NFR-REL-002 | E-OPS-001/003, E-WEB-003 | T-EVT-004, T-HARD-004 | planned |
| R-DEV-001 | Process requirements, NFR-MNT-004 | runner self-tests, E-SCOPE-001, E-DEV-001 | T-FOUND-004, T-REVAL-012, T-RPLT-001/002, all implementation tasks | planned |
| R-DEV-002 | Traceability requirements, NFR-MNT-004 | trace checker (T-FOUND-004), E-DEV-001 | T-FOUND-004, T-REVAL-001/012, T-REL-001 | planned |
| R-DEV-003 | NFR-MNT-002 | dependency boundary tests, resource review | T-FOUND-002, all module tasks | planned |
| R-DEV-004 | FR-IMP-006, FR-EXP-002 | E-UX-003, E-EXP-006 | T-DISC-002/003, T-IMP-002/005, T-EXP-002 | blocked-by-sample |
| R-PRV-005 | NFR-PRV-001 | E-PRV-005—008 | T-RGOV-001/002, T-RREL-003 | approval-required; synthetic only |
| R-PRV-006 | NFR-PRV-002 | E-PRV-009—011 | T-RGOV-003, T-RAGT-003 | approval-required; external processors disabled |
| R-SAFE-005 | FR-AGT-004/005 | E-AGT-015—024 | T-RPLT-009/015/016/017, T-RWEB-005 | planned; approval channel isolated from Agent |
| R-RISK-001 | FR-AGT-003 | E-RISK-001—005 | T-RPLT-010, T-RWEB-005 | planned |
| R-EXIT-001 | FR-EXP-001 | E-EXIT-001 | T-REXP-001—003, T-RREL-003 | pre-real-write gate |
| R-OPS-003 | NFR-OPS-001—004 | E-OPS-009—014 | T-RSPK-003, T-ROPS-001—007 | approval-required before pilot |
| R-AUD-001 | NFR-PRV-003 | E-AUD-001—004 | T-RPLT-006/007, T-RAGT-002 | planned; fail closed |
| R-VOICE-001 | NFR-UX-006 | E-PRV-013/014 | T-REVAL-008, T-RWEB-001 | planned; no voice/audio surface in R1 |
| R-LOCAL-001 | NFR-UX-005 | E-LOCAL-001—006 | T-REVAL-004, T-RWEB-003 | planned; no persistent D2+ draft |
| R-ID-001 | FR-CLS-002/007 | E-ID-001—004 | T-RDOM-003/004 | planned; merge excluded |
| R-ATT-001 | FR-EVT-005/007, FR-TSK-004 | E-ATT-001 | T-RDOM-006/010 | planned; facts only |
| R-LEAVE-001 | FR-EVT-006 | E-LEAVE-001 | T-RDOM-007 | planned; linked facts |
| R-HWK-001 | FR-EVT-005/007 | E-HWK-001 | T-RDOM-008 | planned; facts only |
| R-RET-001 | FR-EXP-004, NFR-PRV-004 | E-RET-001—004 | T-RGOV-002, T-ROPS-003/004 | approval-required |
| R-RET-002 | FR-EXP-004, NFR-PRV-004 | E-RET-001—004 | T-RGOV-002, T-ROPS-003/004 | approval-required; no false delete claim |
| R-TIME-001 | NFR-REL-005 | E-TIME-001/002 | T-RDOM-001 | planned |
| R-REP-003 | FR-REP-002 | E-REP-009—012 | post-R1 report tasks | deferred after Release 1 |
| R-IMP-003 | FR-IMP-004 | E-IMP-011—015 | post-R1 import decomposition | deferred after Release 1/sample gate |
| R-DEV-005 | Process requirements | E-TASK-001 | T-REVAL-006, all Release 1 atomic tasks | planned |
| R-VALUE-001 | Release/value gate | E-VALUE-001 | T-RREL-002/003 | planned; stop expansion by default |
| R-ADM-001 | FR-PLT-006, NFR-PRV-005 | E-ADM-001—009 | T-RGOV-005, T-RPLT-012, T-RREL-003 | approval-required; BCG-only workspace-bound ScopeAllocationCommand; runtime synthetic-only default |
| R-SEM-001 | LR-SEM-001 | E-EVO-001 | T-EVO-001 | canonical-invariant; non-R1 |
| R-ORG-001 | LR-SEM-002 | E-EVO-002, E-EVO-016, E-EVO-017, E-EVO-018 | T-EVO-001, T-EVO-005 | long-term invariant; non-R1 |
| R-EPI-001 | LR-EPI-001 | E-EVO-003, E-EVO-019, E-EVO-020 | T-EVO-001, T-EVO-007 | long-term invariant; non-R1 |
| R-CAP-001 | LR-CAP-001 | E-EVO-004 | T-EVO-002 | canonical-invariant; capability deferred |
| R-RES-001 | LR-RES-001 | E-EVO-005, E-EVO-020 | T-EVO-002, T-EVO-007 | long-term invariant; capability deferred |
| R-CTX-001 | LR-CTX-001 | E-EVO-006 | T-EVO-002 | canonical-invariant; non-R1 |
| R-KNW-001 | LR-KNW-001 | E-EVO-007, E-EVO-020 | T-EVO-002, T-EVO-007 | long-term invariant; capability deferred |
| R-INT-001 | LR-INT-001 | E-EVO-008 | T-EVO-003 | canonical-invariant; R1 only existing intents |
| R-TIME-002 | LR-TIME-001 | E-EVO-009 | T-EVO-001, T-EVO-006 | long-term invariant; expanded capability deferred |
| R-WRK-001 | LR-WRK-001 | E-EVO-010 | T-EVO-006 | discovery; non-R1 |
| R-EXT-001 | LR-EXT-001 | E-EVO-011, E-EVO-021 | T-EVO-004, T-EVO-007 | long-term invariant; implementation future |
| R-KRN-001 | LR-KRN-001 | E-EVO-012 | T-EVO-001, T-EVO-004 | long-term invariant; provider neutral |
| R-COLLAB-001 | LR-COL-001 | E-EVO-013, E-EVO-018 | T-EVO-005 | discovery; non-R1 |
| R-DER-001 | LR-DER-001 | E-EVO-014, E-EVO-019, E-EVO-020, E-EVO-021 | T-EVO-007 | long-term invariant; non-R1 implementation |
| R-VALUE-002 | LR-VALUE-001 | E-EVO-015 | T-EVO-008 | discovery gate; no feature promotion without evidence |
| R-PROD-001 | Product Priority Invariant; Release 1 Exit Criteria | E-VALUE-001; ACC-018; AC-16 | T-DISC-001, T-REVAL-025, T-RREL-002/003 | confirmed first principle; strengthens value oracle; no R1 feature expansion |

## Known Eval IDs to Add to Runner

`E-SCOPE-001`：检查 v1 不出现招生/收费/人事/全校排课实现入口。\
`E-ARCH-001`：检查默认只有一个业务 Agent 注册，新增 Agent 必须有 ADR/eval 引用。

审计新增的 Eval ID 已在 `evals/class-os-v1/cases/audit-regressions.md` 登记；其中 Release 1 P0 的可执行 oracle 见 `evals/class-os-v1/executable/release-1-p0.md`。`planned` 只表示规格和任务已存在，不表示 runner 已实现或测试已通过。

开放世界长期约束见 `evals/class-os-v1/cases/open-world-evolution.md`。`E-EVO-001—021` 均为 `catalogued/non-R1`；如果未来进入 release，必须建立可执行规格并创建该 release 的机器 definition bundle，不能修改当前 R1 gate 来“顺带”启用。
