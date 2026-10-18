# Release 1 P0 Executable Specifications

状态：`executable-spec`，尚未实现/运行。Owner 在团队确定后替换角色名。Fixture 全为合成数据。

## EX-R1-001 Workspace Isolation

- eval_id: E-AUTH-001
- rule_refs: R-AUTH-001
- requirement_refs: FR-PLT-001/003, NFR-SEC-002
- owner: Security/Backend
- runner_mapping: `verify integration --id E-AUTH-001`
- setup: 创建 workspace A/B、owner A/B、同名 class/student；使用独立会话。
- input_fixture: `fixtures/r1/workspace-isolation.synthetic.json`（T-REVAL-002 创建）
- action: A 会话按 B 的不可预测 ID 请求 UI/API/Query Tool/导出 preview。
- oracle: 所有入口返回相同 forbidden/not-found-safe 错误；响应、日志、trace 不包含 B 的名称/字段；产生最小拒绝 audit。
- tolerance: 仅人类文案可本地化，机器错误码固定。
- cleanup: 删除合成 workspace；确认无对象/队列残留。
- expected_red: yes，授权中间件实现前失败。

## EX-R1-002 Approval Surface Isolation

- eval_id: E-AGT-015
- rule_refs: R-SAFE-005
- requirement_refs: FR-AGT-004/005
- owner: Platform/Security
- runner_mapping: `verify contract --id E-AGT-015`
- setup: 生成 Tool/Skill/MCP catalogs 和一项 W2 proposal。
- input_fixture: 固定 Tool/Skill/MCP catalog、W2 proposal 与 approve 同义调用矩阵；全部为合成 ID。
- action: 枚举 catalog 并让 fake Agent 请求 `approval.approve`/同义调用。
- oracle: catalog/schema 中不存在 approve Tool；任意伪造名称返回 forbidden/unknown，不消费 proposal；记录安全 audit。
- tolerance: none。
- cleanup: 删除 proposal。
- expected_red: yes。

## EX-R1-003 Approval Replay and Binding

- eval_id: E-AGT-018, E-AGT-020
- rule_refs: R-SAFE-005, R-SAFE-003
- requirement_refs: FR-AGT-005
- owner: Platform/Security
- runner_mapping: `verify integration --group approval-binding`
- setup: actor/session/client A 生成批准；准备 B session/client，proposal version v1。
- input_fixture: `fixtures/r1/proposal-approval.synthetic.json`，含合成 actor/session/client/proposal/receipt 绑定；过期、拒绝、双击、跨客户端重放由 runner mutation 扩展。
- action: B 使用 token；A 双击；后台页面在没有新的受信批准绑定时尝试提交；拒绝或过期后重放同一凭据。
- oracle: 只有一次由服务端可验证的 Origin、CSRF、actor/session/client、proposal hash/version 和未消费凭据全部匹配的 A 动作可消费；其他全部拒绝且无业务写入。Page Visibility 仅作 UI 信号，不充当服务端的人类存在证明。
- tolerance: none。
- cleanup: 检查 proposal/receipt/audit 后清除合成数据。
- expected_red: yes。

## EX-R1-004 Dynamic Risk Escalation

- eval_id: E-RISK-001—005
- rule_refs: R-RISK-001
- requirement_refs: FR-AGT-003
- owner: Product/Security
- runner_mapping: `verify unit --group risk-policy-v1`
- setup: 固定 `risk_policy_version=r1.0` 表；构造普通表扬、违纪 D3、D4、批量、外发/删除矩阵。
- input_fixture: 版本化合成 canonical command payload 矩阵，覆盖动作、对象、等级、人数、外部性与可逆性。
- action: 对每行调用纯 risk evaluator。
- oracle: 等于批准矩阵；添加数据等级/人数/外发/不可逆因素绝不降低风险；R1 D4/外发被拒绝。
- tolerance: none。
- cleanup: none。
- expected_red: yes。

## EX-R1-005 Sensitive Read Audit Fail Closed

- eval_id: E-AUD-001
- rule_refs: R-AUD-001
- requirement_refs: NFR-PRV-003
- owner: Security/Backend
- runner_mapping: `verify integration --id E-AUD-001`
- setup: 合成 D2 学生姓名/详情/Timeline/事件列表与 D3 record；注入 audit durable-write failure；正常 auth。
- input_fixture: `fixtures/r1/audit-failure.synthetic.json`，配合 runner 注入唯一 canary、合成 D2/D3 projection、正常授权上下文与可控 audit-store fault adapter。
- action: 分别通过 UI API、REST 和 Query Tool 请求上述 D2/D3 投影。
- oracle: 任一学生数据字节均未写入响应，provider 未调用；返回 `AUDIT_UNAVAILABLE`；产生不含内容的最低安全信号。
- tolerance: none。
- cleanup: 恢复 audit adapter、清除合成数据。
- expected_red: yes。

## EX-R1-006 No Persistent Sensitive Draft

- eval_id: E-LOCAL-001—004
- rule_refs: R-LOCAL-001
- requirement_refs: NFR-UX-005
- owner: Web/Security
- runner_mapping: `verify e2e --group local-draft-r1`
- setup: 在事件表单输入唯一 synthetic marker；检查 localStorage/IndexedDB/Cache/cookies；准备登出和第二账号。
- input_fixture: 合成事件表单、唯一非 PII marker、两账号会话与浏览器存储快照基线。
- action: 刷新、关闭、登出、会话过期、第二账号登录。
- oracle: marker 不出现在持久浏览器存储/网络日志/第二账号；未提交状态不会被声称保存。
- tolerance: 浏览器内部不可控缓存需以 no-store/加密传输证据解释，不能包含表单正文。
- cleanup: 清站点数据、撤销会话。
- expected_red: yes。

## EX-R1-007 Multi-source Student Identifier

- eval_id: E-ID-001—003
- rule_refs: R-ID-001
- requirement_refs: FR-CLS-002/007
- owner: Domain/Data
- runner_mapping: `verify unit --group student-identifier-r1`
- setup: 两学生；校内学号变化、跨来源考号、旧编号复用、同名。
- input_fixture: `fixtures/r1/student-identifier.synthetic.json`，固定 seed 的两名合成学生及 authority/type/period/冲突编号矩阵。
- action: 执行 matching。
- oracle: 标识带 authority/type/period；冲突产生 candidate；不 merge、不移动引用。
- tolerance: candidate 排序可变但集合固定。
- cleanup: none。
- expected_red: yes。

## EX-R1-008 Fact-only Attendance/Leave/Homework

- eval_id: E-ATT-001, E-LEAVE-001, E-HWK-001
- rule_refs: R-ATT-001, R-LEAVE-001, R-HWK-001
- requirement_refs: FR-EVT-005—007, FR-TSK-004
- owner: Domain/Product
- runner_mapping: `verify unit --group fact-events-r1`
- setup: 同一学生构造跨日请假、缺勤、迟到、返校、未交、补交、更正序列。
- input_fixture: `fixtures/r1/fact-events.synthetic.json`，含合成学生与固定时钟、来源、correlation ID 的事实事件；乱序由 runner mutation 产生。
- action: 保存并查询 Timeline/Today 汇总。
- oracle: 原事件不覆盖；关联和更正可追；冲突标待核对；无出勤率/态度标签/唯一状态推断。
- tolerance: Today 排序仅按批准规则。
- cleanup: none。
- expected_red: yes。

## EX-R1-009 Minimum Exit Round-trip

- eval_id: E-EXIT-001, E-EXP-001, E-EXP-002
- rule_refs: R-EXIT-001
- requirement_refs: FR-EXP-001
- owner: Data/Ops
- runner_mapping: `verify recovery --id E-EXIT-001`
- setup: 合成 Workspace/班级/学期/学生/多来源标识/事件/任务、未结 rights request、restriction/delete tombstone、retention exception、admission/revocation ledger、历史和审计摘要。
- input_fixture: 版本化合成 exit package seed，含核心实体、全部可移植 lifecycle/admission ledger、tombstone、例外和预期计数/hash。
- action: 生成退出导出；在干净隔离环境导入；运行 reconcile。
- oracle: manifest/schema/checksum 有效；所有核心实体、可移植 lifecycle/admission ledger、关系、版本、计数和抽样 hash 一致；接收端在开放业务读写前重放 restriction/delete tombstone，已限制/删除数据不复活；未结权利请求与 retention exception 可继续处理；产生退役证明并明确列出不可移植项/依据；无 D3/D4 非必要输出。
- tolerance: 新内部 ID 可重建时必须有 old→new map；业务值零差异。
- cleanup: 销毁隔离环境和 export object。
- expected_red: yes。

## EX-R1-010 Data Lifecycle Claim

- eval_id: E-RET-001, E-RET-002
- covered_cases_pending_runner: E-RET-003, E-RET-004, E-PRV-006, E-PRV-007, E-PRV-008
- rule_refs: R-RET-001/002
- requirement_refs: NFR-PRV-004, FR-EXP-004
- owner: Privacy/Backend
- runner_mapping: `verify integration --group lifecycle-r1`
- setup: 合成学生分布在 Release 1 的 Workspace/Class/AcademicTerm/Student/Identifier/Record/Task、退出临时包、日志、审计和备份；加载批准 lifecycle matrix。
- input_fixture: 合成逐 store locator/owner/期限/处置矩阵、rights requests、旧备份与未知 store mutation。
- action: 执行查阅、更正、限制、停用、删除请求和旧备份隔离恢复。
- oracle: 未批准期限时只允许 archive/deactivate；批准后逐 R1 store 返回状态、例外、到期和证明；旧备份恢复后重放 tombstone/限制清单；不得提前显示 deleted-complete。
- tolerance: none for state machine。
- cleanup: isolated fixture reset。
- expected_red: yes。

## EX-R1-011 Release 1 Value Gate

- eval_id: E-VALUE-001
- rule_refs: R-PROD-001, R-VALUE-001
- requirement_refs: Release 1 manifest Exit Criteria
- owner: Product
- runner_mapping: manual protocol in `cases/manual-ux.md`
- setup: 目标用户 5 日现状基线和至少 5 次实现任务；样本须含至少 5 个通知/责任压力事项，其中至少 1 个责任不清、交接或临近期限场景。
- input_fixture: 去标识的时间日志模板、40—60 人手工花名册 setup 场景、核对/重复录入/维护/支持/节省字段和固定摊销周期；责任事项另含 source、required_action、alleged/confirmed_owner、deadline、state、handoff/escalation、late_discovery/private_chase 和 evidence_retrieval。
- action: 测量记录投入、后续复用节省、错误、放弃和主观负担；检查教师能否识别必须事项、澄清或拒绝错误归责、完成/交接/升级并检索证据。
- oracle: 中位净节省 ≥30%，错误/敏感暴露不增加；责任不清事项不得静默派给班主任，遗漏/逾期不得劣于现状，完成或交接/升级证据可检索，主观责任压力单列报告。任一条件失败则 decision=change/stop。
- tolerance: 小样本须报告区间和限制，不以均值掩盖失败。
- cleanup: 按数据准入清除研究资料。
- expected_red: n/a manual。

## EX-R1-012 Self-host Rebuild

- eval_id: E-OPS-009/011
- rule_refs: R-OPS-003
- requirement_refs: NFR-OPS-001—004
- owner: Ops
- runner_mapping: `verify recovery --group self-host-r1`
- setup: 干净受支持主机；批准 artifact；加密备份；无开发者全局状态。
- input_fixture: 合成加密备份、目标主机能力清单、固定故障脚本与预期 RPO/RTO/计数/hash。
- action: install/doctor；模拟主机丢失；重建并 restore-verify。
- oracle: 全流程只用文档化命令；doctor 全绿；核心数据/审计校验；测得 RPO/RTO；support bundle 无 PII/secret。
- tolerance: 实际时间必须不超过已批准 RPO/RTO。
- cleanup: 销毁临时主机、撤销凭据。
- expected_red: yes。

## EX-R1-013 Secure Session and CSRF

- eval_id: E-AUTH-005, E-AUTH-007, E-SEC-002
- rule_refs: R-AUTH-001, R-SAFE-005
- requirement_refs: FR-PLT-002, NFR-SEC-001/002
- owner: Security/Web
- runner_mapping: `verify security --group session-csrf-r1`
- setup: 创建 owner 会话、攻击者 origin、过期会话和连续失败登录 fixture；固定测试时钟。
- input_fixture: 合成账号、合法/非法 CSRF nonce、固定 session id、过期时间和 origin 矩阵。
- action: 分别执行登录失败、会话轮换、跨源 POST、过期会话读写和 X 级近期再认证检查。
- oracle: 登录失败不泄露账户存在且触发限速；认证后 session id 轮换；非允许 origin/nonce 拒绝；过期会话不返回 D2+；X 级无近期再认证拒绝。
- tolerance: 时间边界只允许已配置的 1 秒测试时钟误差；机器错误码固定。
- cleanup: 吊销全部合成会话并清理 rate-limit key。
- expected_red: yes。

## EX-R1-014 Write Audit and Idempotency Atomicity

- eval_id: E-CMD-001—004
- rule_refs: R-SAFE-003, R-AUD-001
- requirement_refs: NFR-REL-001, NFR-PRV-003
- owner: Platform/Backend
- runner_mapping: `verify integration --group command-atomicity-r1`
- setup: 建立合成 workspace、Record create command、可控制失败点的 audit repository 与并发 barrier。
- input_fixture: 同 actor/scope/key 同 payload、同 key 异 payload、过期 expected_version、audit 写失败四组参数。
- action: 并发重放命令并在 commit 前后注入失败。
- oracle: 同 payload 只有一次业务事实并复用 receipt；异 payload 固定冲突；过期版本不写；audit 失败时业务写和 receipt 均不提交。
- tolerance: none；业务行、audit 行和 receipt 计数精确相等。
- cleanup: 回滚测试事务并确认无 outbox/receipt 残留。
- expected_red: yes。

## EX-R1-015 Temporal Interval Semantics

- eval_id: E-TIME-001, E-TIME-002
- rule_refs: R-TIME-001
- requirement_refs: NFR-REL-005
- owner: Domain
- runner_mapping: `verify unit --group temporal-interval-r1`
- setup: 固定 Asia/Shanghai 与 UTC 时钟，生成相邻、重叠、未来、无穷结束和回溯更正区间。
- input_fixture: 边界时刻、DST 无关但跨日的 ISO 时间矩阵。
- action: 执行 contains、overlaps、current-at、replace-at 和 persistence round-trip。
- oracle: 一律使用 `[from,to)`；旧 to 等于新 from 时无重叠/空档；空 to 为无穷；序列化不改变瞬时时刻；非法反向区间拒绝。
- tolerance: 时间比较无浮点容差，展示本地化不参与领域判断。
- cleanup: none。
- expected_red: yes。

## EX-R1-016 Roster Without Guardian or Merge Surface

- eval_id: E-ROS-001—004, E-RET-001
- rule_refs: R-DATA-001/002, R-ID-001, R-RET-001/002
- requirement_refs: FR-CLS-001—005/007, FR-EXP-004
- owner: Domain/API/Security
- runner_mapping: `verify contract --group roster-r1`
- setup: 两个 workspace、同名学生、多来源标识符、已停用学生；生成 API/OpenAPI/Tool catalog。
- input_fixture: 只含 R1 Student 字段，不含 guardian/merge/hard-delete schema。
- action: 创建、更新、停用、历史查询并枚举所有公开 route/schema/tool。
- oracle: scope 隔离；内部 student_id 不变；停用保留历史且 UI/API 不称 deleted；不存在 Guardian 联系字段、merge 或 hard-delete surface。
- tolerance: 人类“停用/归档”文案可本地化；机器状态固定。
- cleanup: 删除合成 workspace。
- expected_red: yes。

## EX-R1-017 Fact Event, Task, Timeline and Today Loop

- eval_id: E-EVT-001—004, E-ATT-001, E-LEAVE-001, E-HWK-001
- rule_refs: R-EVT-001/002, R-ATT-001, R-LEAVE-001, R-HWK-001
- requirement_refs: FR-EVT-001—006, FR-TSK-001/002/004/005
- owner: Domain/API/Web
- runner_mapping: `verify e2e --group fact-loop-r1`
- setup: 合成学生、固定今天、迟到/请假/返校/未交/补交事实和一项跟进任务。
- input_fixture: `fixtures/r1/fact-events.synthetic.json`；runner 基于该固定 seed 数据产生乱序、重复请求和 unknown 原因变体。
- action: 经 UI/API 创建事实、追加更正、完成任务，查询 Student Timeline 与 Today。
- oracle: 原事实不被覆盖；来源可下钻；重复请求不重复写；Today 不含 schedule/课务；不计算出勤率或唯一当前状态；未知原因保持 unknown；AI 推断/建议只存在当前会话草稿，关闭/TTL 后清除，Record/Task/Today/Timeline/Profile/Attention/priority/outbox 全部无推断 mutation。
- tolerance: 事件展示顺序仅允许稳定 tie-breaker 差异，事实集合必须一致。
- cleanup: 删除合成班级并验证 receipt/audit 引用完整。
- expected_red: yes。

## EX-R1-018 Agent Read and Draft Boundary

- eval_id: E-AGT-001/002/009—014, E-AUD-002
- rule_refs: R-AGT-001—005, R-SAFE-001/005, R-AUD-001
- requirement_refs: FR-AGT-001—006/009/010
- owner: Agent Platform/Security
- runner_mapping: `verify contract --group agent-boundary-r1`
- setup: deterministic fake Agent、Tool allowlist、跨 workspace/注入/超时/伪系统消息 fixtures。
- input_fixture: 合成记录与含 prompt injection 的事实文本。
- action: 枚举并调用查询/草稿能力，同时请求 write/apply/approve/merge/send 和任意 URL/SQL/file。
- oracle: catalog 仅含最小查询/草稿；草稿无副作用；注入不改变 policy；未取证事实不可声称成功；敏感投影在 audit 回执前不调用 provider。
- tolerance: 草稿自由文本可变化，但引用集合、禁区和副作用计数固定。
- cleanup: 清除 fake 会话，确认业务表零新增。
- expected_red: yes。

## EX-R1-019 Approval UI Attack Matrix

- eval_id: E-AGT-016/017/019—024
- rule_refs: R-SAFE-005, R-RISK-001
- requirement_refs: FR-AGT-004/005
- owner: Web/Security
- runner_mapping: `verify e2e --group approval-ui-attacks-r1`
- setup: 受信 UI、攻击 origin/iframe、前台/后台页、W2/X proposal、固定时钟与两个客户端实例。
- input_fixture: 合法/非法 nonce、过期近期认证、重复点击、拒绝后重放矩阵。
- action: 逐项尝试跨站、嵌入、后台消费、换客户端、双击、过期 X 批准、直接 REST W2 commit、内部 adapter 绕过、客户端降风险和 receipt 跨 Command/版本重放。
- oracle: CSP/frame-ancestors 阻止嵌入；CSRF/origin/session/client/hash/version 任一不符均拒绝；后台/拒绝/过期不可消费；合法批准最多一次；X 级要求近期重认证；所有 adapter 经过同一 Gateway，客户端风险值不能降级，W2 无匹配 receipt 必拒绝。
- tolerance: none；proposal 消费计数必须为 0 或 1。
- cleanup: 撤销所有未消费 proposal 与会话。
- expected_red: yes。

## EX-R1-020 No Voice Surface

- eval_id: E-PRV-013/014
- rule_refs: R-VOICE-001, R-PRV-006
- requirement_refs: NFR-UX-006, NFR-PRV-002
- owner: Web/Privacy/Security
- runner_mapping: `verify e2e security --group voice-text-only-r1`
- setup: 浏览器媒体 API spy、网络代理、route/schema/Tool catalog 和 storage inspector。
- input_fixture: 合成音频 Blob 与语音/转写同义请求，不含真实学生信息。
- action: 枚举 UI/API/Tool 并尝试调用录音、系统/浏览器转写、音频上传或外部 adapter。
- oracle: Release 1 不存在语音/音频入口；所有同义 API 请求固定拒绝；网络、缓存、对象存储、日志和 trace 不出现音频 bytes 或外部转写调用。
- tolerance: none for audio bytes/provider calls。
- cleanup: 清理浏览器上下文。
- expected_red: yes。

## EX-R1-021 Two-stage Real-data Admission State Machine

- eval_id: E-ADM-001—009
- rule_refs: R-ADM-001, R-EXIT-001, R-PRV-005
- requirement_refs: FR-PLT-006, NFR-PRV-005
- owner: Security/Platform/Operations
- runner_mapping: `verify security integration --group real-data-admission-r1`
- setup: `synthetic-only` 部署、外部测试签名器、candidate/shadow-value/pilot-readiness 签名报告、合法/篡改/过期/撤回 setup 与 admission artifacts、两个 deployment/class/academic-term/user 范围，以及填满并正确签名的仓库 example/fingerprint 副本。
- input_fixture: 合成身份、一次性 setup capability、预分配空 scope/allocation receipt、带 provenance 的 synthetic/real-mode payload与报告签名/撤回矩阵；不含真实学生信息。
- action: 用 setup capability 经 `ScopeAllocationCommand` 预留 ID；再通过 UI/REST/internal/worker/repository/test/CLI 发送未知 pre-admission type、多余字段、跨 workspace 请求和直接 Class/Term/Student/事实/任务写，并重放 capability；最后对合法/伪造/任意字符串 hash 的 final artifact 尝试写入、跨范围、到期和撤回，同时请求退出导出。
- oracle: BCG 的唯一 pre-admission 分支只单次写无 PII 的 workspace-bound ScopeAllocation ledger，不创建 Class/Term 等业务实体；consume 与 ledger 原子；unknown command/field、跨 workspace 和任意业务写拒绝。只有应用外、唯一 ID、`issued`、非 example fingerprint，且签名/quorum/release/deployment/owner/workspace/allocation/class/term/module/expiry 与经 verifier 验真的 candidate、shadow/value、pilot-readiness 报告全部匹配，才允许 real-pilot 写；report/admission 可重复校验但不消费，setup 只能消费一次；撤回后下一写失败但退出仍可用。
- tolerance: artifact 到期判断只允许固定测试时钟 1 秒误差。
- fault_variants: E-ADM-007/008/009 增加并发相同 setup、冲突 payload、提交前每个写点故障、提交成功后签名失败/响应丢失；外部状态查询失败；registry 低代/同代异 hash/断 previous hash/过期，以及 API 或 worker 未停净时拒绝切换。
- transaction_oracle: 本地 PostgreSQL 唯一 deployment+setup，consume/allocation/ledger/audit/receipt payload 同事务；失败前零提交，成功后恰一条分配，同请求重试只交付原 receipt，冲突拒绝；外部无 consumed 状态和分布式事务。ledger 绑定有效 generation/hash；撤销激活期间无写入，激活后下一写拒绝，过期/失败保持停写。
- cleanup: 撤销测试 artifact、删除合成 workspace、验证密钥不在应用容器。
- expected_red: yes。

## EX-R1-023 Business Command Gateway Bypass Matrix

- eval_id: E-AGT-025
- rule_refs: R-SAFE-005, R-DEV-003
- requirement_refs: FR-AGT-003/004, NFR-MNT-002
- owner: Architecture/Security/Platform
- runner_mapping: `verify architecture security --group business-command-boundary-r1`
- setup: 对 REST/controller/internal service/worker/repository/test/future CLI 建立依赖图与运行时 mutation；准备 W1/W2 command、worker job-state/attempt/receipt 和 audit fault。
- input_fixture: 合成 W1/W2 canonical payload、有效/无效 approval receipt、worker retry/timeout 序列及逐入口旁路变体。
- action: 每个入口分别尝试直接写业务 store、job-state、attempt 或 receipt，并尝试跳过风险、幂等、批准或审计。
- oracle: 静态 scanner 或运行时 guard 对每个旁路固定失败；合法路径只能调用 Business Command Gateway；W2 必须消费绑定 receipt；worker 重试不产生重复副作用；未知入口 fail closed。
- tolerance: none。
- cleanup: 回滚合成事务、清空 worker queue/receipt 并确认 audit correlation 完整。
- expected_red: yes。

## EX-R1-022 Owner Bootstrap and Offline-code Recovery

- eval_id: E-AUTH-009—013, E-AUTH-015—018
- covered_cases_pending_runner: E-AUTH-014
- rule_refs: R-AUTH-001, R-AUTH-REC-001, R-PRV-001
- requirement_refs: FR-PLT-002, FR-PLT-007
- owner: Security/Platform/Operations
- runner_mapping: `verify security recovery --group owner-lifecycle-r1`
- setup: 空部署、已有 owner 部署、固定时钟、只显示一次的离线恢复码、两条已登录会话，以及 controller/worker/repository 旁路 mutation。
- input_fixture: 合成 owner 标识；合法/过期/篡改/重放/跨客户端恢复码与暴力尝试序列。
- action: 首次/重复 bootstrap、保存恢复码、以有效/无效码兑换同会话短时 recovery session、恢复凭据、扫描日志/支持包并尝试绕过 Identity Security Boundary。
- oracle: bootstrap 只成功一次且 secret 失效；未持码请求不枚举账号也不取得能力；恢复码只存哈希、单次且限速；成功后轮换凭据、吊销全部旧会话/旧码并只显示一次新套件；码值不进入日志/模型/支持包；直接身份 store 写入失败。
- tolerance: 固定测试时钟 1 秒误差；机器错误码一致。
- cleanup: 吊销所有合成凭据和会话，销毁测试 secret、恢复码 hash 和 recovery session。
- expected_red: yes。
