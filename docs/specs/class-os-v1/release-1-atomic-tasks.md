# Release 1 Atomic Tasks

状态：`planned`。本清单只覆盖 `release-1-manifest.md` 冻结的最小 Release 1。`1—3d` 是待实测的工程 effort 拆分目标，不是交付承诺；calendar duration 与 external blocked time 单列。首批五项工程任务后必须重估。超过 3 工程人日、跨越两个独立验收结果或无法单独回退时，必须先拆分。所有处理真实未成年人数据的任务都受数据治理批准门约束。

授权边界（2026-10-08 用户批准修订）：`implementation_authorized=synthetic-feature-development`，可按 `.ai/development/synthetic-policy.yaml` 和既有工程依赖实施 R1 平台/领域/Web/Agent 查询草稿/退出/运维测试；本地开发验收不等于依赖任务正式 complete。`.ai/gates/release-1-release-gates.yaml` 的 before_feature_task 继续约束正式任务/Eval 证据晋升，其余发布/真实数据门完全不变；不得将本地开发授权当外部签名或真实准入。详见 `docs/changes/2026-10-08-synthetic-development-admission.md`；任务行号、row hash 和业务范围不改。

统一约定：

- T-REVAL-001 先建立最小 `verify self/eval-meta/gate-graph` 入口，使评测任务可独立验收；T-RPLT-002 在不改变该接口的前提下扩展为 format/lint/type/unit/contract/e2e 的唯一验证入口。在最小入口不存在前，只允许执行 T-RGOV-001—005、T-REVAL-001 的前置工作和文档审查。
- Expected red：对应实现开始前，目标可执行规格必须失败或明确标为 `blocked-by-runner`；不得以尚未运行冒充通过。
- Recovery：默认回退本任务的代码/迁移并恢复前一兼容版本；不得删除用户数据掩盖失败。
- Stop：出现越权、无法审计、不可恢复写入、真实数据未经批准或验收口径不明确时立即停止。
- 文件范围是允许修改的主要边界；若必须越界，先更新本任务并重新评审。

## 1. 治理、规格与可执行评测

| ID / 估算 | Goal | Inputs 与文件范围 | Depends on | Expected output | Validation | Recovery / Stop |
|---|---|---|---|---|---|---|
| T-RGOV-001 / 1d | 指定数据控制、处理、安全、支持和审批责任人 | 数据治理决策；`docs/06-系统设计/数据治理与生命周期决策.md` | — | 责任矩阵含姓名/岗位、批准日期、复核日 | E-PRV-005/006 人工 protocol；双人复核 | 撤回未批准版本；任一角色空缺则停在合成数据 |
| T-RGOV-002 / 1d | 批准目的、合法依据、数据主体权利流程 | R-PRV-005/006；治理决策文档 | T-RGOV-001 | 每类数据的目的、依据、权利入口、SLA 和例外 | 隐私负责人签字；E-PRV-005, E-PRV-006, E-PRV-007, E-PRV-008 规格复核 | 标记 `pending`；未批准不准真实数据 |
| T-RGOV-003 / 1d | 完成处理方和模型供应商准入 | 数据流、供应商清单；治理决策与 ADR | T-RGOV-001 | 允许/禁止处理方、地域、保留、退出与事故条款 | 安全+隐私双签；E-PRV-009, E-PRV-010, E-PRV-011 | 禁用未批准 adapter；无批准即本地 fake |
| T-RGOV-004 / 1d | 冻结 Release 1 边界和非目标 | 审计报告；`release-1-manifest.md`；`release-1-pilot-profile.md` | T-RGOV-002, T-RGOV-003 | 签字版本、变更门、真实试点准入条件 | E-SCOPE-001/002, E-TASK-001 文档模式；产品/安全/工程三方检查 | 回退为合成原型；范围蔓延则拒绝进入实现 |
| T-RGOV-005 / 1d effort | 批准 setup/admission artifact 的签发、密钥与撤回仪式 | R-ADM-001；`.ai/gates/signed-artifact-policy.yaml`、治理决策 | T-RGOV-001, T-RGOV-002, T-RGOV-003, T-RGOV-004 | 离线 root pin/rotation、应用外 role-key registry、全角色 quorum、用途/期限/撤回；区分 reusable attestation、renewable admission、one-time setup；workspace-bound 两阶段流程 | E-ADM-004/007/008/009, E-GATE-002；产品/隐私/安全/运维签字 | 外部等待单列；任一 root、角色、quorum、lifecycle、key usage 或撤回边界未批准则仅 synthetic-only |
| T-RGOV-006 / 1d effort | 审批并签发 R1 架构决定 artifact | `docs/specs/class-os-v1/architecture*.md`；language/self-host spikes；`.ai/gates/architecture-approval.example.yaml` | T-RGOV-004, T-RSPK-001, T-RSPK-003, T-REVAL-012 | ADR-006 已依据 spike 明确 accepted/rejected；应用外签名 artifact 绑定当前 architecture、ADR-001—007、spike、constraints、release、批准者和时间 | E-ARCH-002；填充并签名 example、漏 ADR-006 或篡改任一 hash 均失败 | 未签发只允许 eval/spike；ADR-006 未收口或架构变化必须拒绝/重新签名 |
| T-REVAL-001 / 2d | 建立最小 verify 与 manifest schema/唯一性校验 | `evals/class-os-v1/**`; `.ai/gates/**`; `scripts/verify*` | T-RGOV-004 | 可在空业务仓运行的 `verify self/eval-meta`；逐 ID 唯一分类、引用存在、`required_before` enum、未知键/重复键失败；R1 case maturity 与唯一权威 eval definition 完全同步；22+ EX 均有 fixture/setup/oracle/cleanup/runner 字段 | E-GATE-001/002；未知 stage、重复键、未知 ID、maturity 漂移或缺 fixture mutation 必须失败 | 回退 runner；任何误报 green/missing=0 则停止发布 |
| T-REVAL-002 / 2d | 建立确定性合成 fixture 工厂 | executable specs；`evals/**/fixtures/**` | T-REVAL-001 | 班级、学生、事件、任务、审批、审计 fixtures | E-PRV-003/E-SEC-005；固定 seed 两次相同 | 删除合成库重建；检测到真实 PII 立即停 |
| T-REVAL-003 / 2d | 实现 workspace、敏感审计和批准核心规格 runner | E-AUTH-001/003, E-AGT-015/018/020, E-RISK-001—005, E-AUD-001—004；`evals/**/runners/**` | T-REVAL-002 | EX-R1-001—005 聚合的隔离、批准绑定、风险和敏感读测试实现前为红 | `verify security`; 负例能触发失败 | 回退 runner；无法验证 fail-closed 不实施写入 |
| T-REVAL-004 / 2d | 实现本地草稿、身份和事实领域规格 runner | E-LOCAL-001—005, E-ID-001—004, E-TIME-001/002, E-EVT-001—004, E-ATT-001, E-LEAVE-001, E-HWK-001；同上 | T-REVAL-002 | EX-R1-006—008/015—017 聚合 oracle 可执行 | `verify domain`; mutation test 至少杀死关键变体 | 回退；错误 oracle 停止领域实现 |
| T-REVAL-005 / 2d | 实现最小退出规格 runner | E-EXIT-001, E-EXP-001—005；exit fixtures/runners | T-REVAL-002 | EX-R1-009 的 schema、ledger、round-trip 与退役证明初始为红 | `verify exit`；删除 ledger/破坏 checksum/复活数据必须失败 | 保留测试产物；无法重建或证明退役则停止试点 |
| T-REVAL-006 / 1d | 在 CI 强制报告三种 eval 状态 | runner；`.github/**` 或 CI 配置、`.ai/pipeline-state.md` | T-RPLT-002, T-REVAL-003, T-REVAL-004, T-REVAL-005, T-REVAL-007, T-REVAL-008, T-REVAL-009, T-REVAL-010, T-REVAL-011, T-REVAL-012, T-REVAL-013, T-REVAL-014, T-REVAL-015, T-REVAL-016, T-REVAL-017, T-REVAL-018, T-REVAL-019, T-REVAL-020, T-REVAL-021, T-REVAL-022, T-REVAL-023, T-REVAL-024, T-REVAL-025 | catalogued/spec/green 独立计数，失败阻断 | E-TASK-001, E-GATE-002；合成破坏一条测试，CI 必须红 | 回退 CI 配置；状态混算则不得发布 |
| T-REVAL-007 / 2d | 实现会话、写审计、幂等与 owner 生命周期规格 runner | E-AUTH-005/007/009—013/015—018, E-SEC-002, E-CMD-001—004；`evals/**/runners/**` | T-REVAL-002 | EX-R1-013/014/022 的 oracle 可执行且初始为红 | `verify security command recovery`；账户接管/旁路 mutation 可复现 | 回退 runner；无法证明原子性、恢复授权或全吊销则禁写 |
| T-REVAL-008 / 3d | 实现批准、Agent/worker/语音边界与两阶段真实准入 runner | E-AGT-015—025, E-PRV-013/014, E-ADM-001—009；`evals/**/runners/**` | T-REVAL-002 | EX-R1-018—021/023 的 Web/Tool/worker/no-voice/workspace-bound ScopeAllocation/admission oracle 初始为红 | `verify contract e2e security integration architecture` | 回退 runner；任一批准/worker 旁路、音频入口、unknown pre-admission command、setup 越权或 real-mode 越界即停 |
| T-REVAL-009 / 2d | 补齐 R1 数据最小化与处理器隐私规格 | E-PRV-001/003/009—012；`evals/**/executable/privacy/**`, runners | T-REVAL-002 | projection、日志、叙事再识别、D3/D4 与处理器禁用 oracle 初始为红 | D2+ 泄露 canary 与 provider mutation | 回退规格/runner；无法检测泄露或 silent fallback 则停 |
| T-REVAL-010 / 1d | 补齐命令响应丢失可靠性规格 | E-OPS-001/003；reliability specs/runners | T-REVAL-002 | commit 前后响应丢失与 receipt 重用 oracle 初始为红 | 故障注入重复 100 次无重复副作用 | 关闭写；状态不可判定或重复即停 |
| T-REVAL-011 / 2d | 补齐 R1 Web 与人工价值/确认协议 | E-WEB-002—004, E-UX-001/006；browser specs/manual protocols | T-REVAL-002 | 设备/浏览器矩阵、网络状态、人工记录表和 runner | 两人按协议重复得到一致 gate 结论 | 保留原始记录；环境或判定不明则不宣称通过 |
| T-REVAL-012 / 2d | 补齐 R1 范围、架构与开发环境规格 | E-SCOPE-001/002, E-ARCH-001/002, E-DEV-001；executable specs/runners | T-REVAL-002 | R1 route/tool/module absence、单 Agent、签名架构批准和可重复环境 oracle | 故意注册导入/排座/外发 route/Tool、签名 example 或注入本机绝对路径后 runner 必须红 | 回退 runner；禁区/架构批准/本机依赖扫描漏检则不发布 |
| T-REVAL-013 / 2d | 补齐 R1 安全 executable specs | E-SEC-001/005—007；security specs/scanners | T-REVAL-002 | injection、secret/PII、SBOM/镜像、TLS/静态存储/密钥 oracle | E-SEC mutation 与泄露 canary | 回退 scanner；漏报密钥/高危依赖即停 |
| T-REVAL-014 / 2d | 补齐 R1 可观测 executable specs | E-OBS-001—004；telemetry specs/runners | T-REVAL-002 | correlation/error/alert/dashboard oracle，不记录学生正文/画像 | 注入 trace 断链和 PII 告警 payload 必须失败 | 关闭 exporter；无法检测断链/泄露即停 |
| T-REVAL-015 / 2d | 补齐 R1 迁移 executable specs | E-MIG-001—005；migration specs/runners | T-REVAL-002 | 空库、N-1、中断、客户端和 Tool schema 兼容 oracle | 隔离 DB 前滚/失败注入/重跑 | 保留旧库；迁移证据不完整则不升级 |
| T-REVAL-016 / 1d | 补齐 R1 a11y 人工与自动协议 | E-A11Y-002/003；a11y specs/protocols | T-REVAL-002 | 屏幕阅读器、200% 放大和窄屏环境/步骤/判定模板 | 两名执行者复现相同 pass/fail | 记录原始证据；关键流程不可达不发布 |
| T-REVAL-017 / 2d | 补齐 R1 性能 executable specs | E-PERF-003/004/006/007；performance specs/fixtures | T-REVAL-002 | 固定目标规模、设备/网络、冷热缓存、采样和 p95 oracle | 重复基准与阈值 mutation | 不宣称 SLO；环境不稳定或样本不足即停 |
| T-REVAL-018 / 2d | 补齐无外发与降级 executable specs | E-REP-008, E-LOCAL-005, E-OPS-008；negative/degradation specs | T-REVAL-002 | 外发 surface 不存在、弱网未知状态和模型停机闭环 oracle | 注册禁用 Tool/provider 故障 mutation 必须失败 | 关闭 Agent/写入；误报成功即停 |
| T-REVAL-019 / 3d | 先验证成熟签名方案并实现最小证据验证 | `.ai/gates/**`; trust-root harness | T-REVAL-001 | 先比较成熟签名/envelope 与 CI attestation 复用，输出组件删减 ADR；运行时优先一个版本化 admission bundle + 本地消费事务；自定义协议仅候选，保留须官方 RFC 8785 边界向量及完整 Ed25519 known-answer；definition/state/evidence 分离、非循环 root pin、registry generation/hash 防回滚、角色/期限/撤回与三类 lifecycle 验证 | E-GATE-002；改 vector、NFC 碰撞、自引用、少签名、撤回 key、旧 registry/同代异 hash、报告被消费、setup 未消费/重放、换 commit mutation 必须失败 | authorization 固定 false；未提交成熟方案比较/删减 ADR 或保留自定义却无官方向量证据，则不进入功能任务 |
| T-REVAL-020 / 2d | 实现 task↔requirement↔eval、DAG、闭包与三态校验 | immutable task definitions、task state、trace/manifests；gate-graph runner | T-REVAL-001, T-REVAL-019 | 只从 `release-1-task-definitions.yaml` 读取 94 项显式 depends_on/requirement_ids/eval_ids/task_body_sha256；校验依赖存在/无环、Markdown row hash、candidate/pilot 闭包和 catalogued/spec/green 分离，不解析范围字符串 | E-TASK-001, E-GATE-001/002；删依赖、改 Markdown row、伪 green 或范围表达式 mutation 必须失败 | authorization 固定 false；任何 missing=0 误报或转而解析 Markdown 范围即停 |
| T-REVAL-021 / 2d | 补齐备份、坏备份与跨主机恢复规格 | E-OPS-005—007/011；recovery specs/runners | T-REVAL-002, T-RSPK-003 | 加密快照、损坏拒绝、引用/ledger 校验、新主机重建 oracle | 隔离主机与坏密钥/坏块/缺 ledger 故障注入 | 不切换环境；恢复校验不完整则不试点 |
| T-REVAL-022 / 2d | 补齐安装、升级与环境故障规格 | E-OPS-009/010/012；self-host specs/runners | T-REVAL-002, T-RSPK-003 | clean install、doctor、升级/回滚、磁盘/证书 oracle | 三类目标主机/故障矩阵先红后绿 | 保留旧环境；无法回滚或误判健康则停 |
| T-REVAL-023 / 1d | 补齐支持包与退役规格 | E-OPS-013/014；support/retire specs | T-REVAL-002, T-RSPK-003 | 支持包脱敏、退出/撤销/清除/例外/证明 oracle | PII canary 与保留卷范围 mutation | 删除测试包；敏感泄露或误删即停 |
| T-REVAL-024 / 2d | 补齐权利请求与生命周期规格 | E-PRV-005—008, E-RET-001—004；lifecycle specs/manual protocols | T-REVAL-002 | 实际 store inventory、查阅/更正/限制/删除、备份重放和例外 oracle | 注入未知 store、删除 ledger、无限期例外必须失败 | synthetic-only；任一 store/owner/期限不明即停 |
| T-REVAL-025 / 1d | 补齐包含启动成本的价值协议 | E-VALUE-001；manual protocol/calculator | T-REVAL-002 | setup/核对/重复录入/持续维护/支持/节省时间及摊销周期模板 | 两名记录者按同一原始日志得到相同 change/stop | 不宣称净收益；任一成本项缺失则停 |

## 2. 技术风险 Spike 与平台骨架

| ID / 估算 | Goal | Inputs 与文件范围 | Depends on | Expected output | Validation | Recovery / Stop |
|---|---|---|---|---|---|---|
| T-RSPK-001 / 2d | 比较单语言与双语言实现边界并收口技术栈 ADR | `docs/specs/class-os-v1/architecture-decision.md`；`spikes/language/**` | T-RGOV-004 | 可运行薄片、资源/类型/测试复杂度数据；据证据将 ADR-006 改为明确 accepted/rejected 并列版本/替代/回退约束 | E-ARCH-001/002；相同用例与硬件基准；未收口 ADR-006 时 architecture approval 必须失败 | 删除 spike；证据不足不锁栈，ADR-006 保持 pending |
| T-RSPK-002 / 2d | 验证只读/草稿 Agent adapter、实时事件和可选 Jev 路由的隔离与降级 | Agent boundary；`spikes/agent-read-draft/**`；中文路由标注集仅作 spike evidence | T-RGOV-003, T-REVAL-008 | provider/fake 替换、超时取消、最小投影、零业务副作用；比较主模型独立/Jev+主模型/确定性过滤+Jev+主模型，记录误调用、漏调用、写意图误判、澄清/回退、延迟/成本；固定版本与 kill switch | E-AGT-001/002/009—014, E-AUD-002 | Jev 无净收益则禁用；adapter 失败则切 fake/禁用 Agent；需要 HITL 或写 Tool 则移出 R1 |
| T-RSPK-003 / 2d | 测量单机自托管资源与故障恢复 | 自托管规范；`spikes/self-host/**` | T-REVAL-002 | CPU/RAM/磁盘基线及 3 类故障记录 | E-OPS-009/011/012；新机复现 | 回退镜像；超出目标机器则改栈/范围 |
| T-RPLT-001 / 1d | 初始化单仓、编码和目录边界 | 已签名架构 artifact 与批准 ADR；repo 根配置 | T-RGOV-006 | 最小 API/Web/worker/package 目录及 UTF-8 策略 | E-ARCH-002, E-SCOPE-001, E-DEV-001；clean clone 可安装 | 删除骨架变更；artifact/hash 不匹配或工具链不兼容则停 |
| T-RPLT-002 / 2d | 扩展跨平台 `verify` 唯一入口 | T-REVAL-001 最小入口、runner、repo；`scripts/**`, build config | T-RPLT-001, T-REVAL-001 | 保持 self/eval-meta/gate-graph 并增加 format/lint/type/unit/contract/e2e 分层命令 | E-TASK-001, E-DEV-001 runner self-test；Windows/CI smoke | 回退扩展但保留最小 gate runner；退出码不可信则停 |
| T-RPLT-003 / 2d | 建立 PostgreSQL 迁移和测试库 | architecture；`db/**`, compose test config | T-RPLT-002 | 可前滚、空库重建、事务测试 fixture | E-MIG-001/003；`verify db` | 从快照恢复；迁移非兼容则拆分 |
| T-RPLT-004 / 2d | 实现单 owner workspace 与 scope | FR-PLT-001/003；domain/application/auth 文件 | T-RPLT-003, T-REVAL-003 | 所有读写必须显式 workspace_id | E-AUTH-001（EX-R1-001）；跨 workspace 属性测试 | 关闭所有写端点；发现漏 scope 即停 |
| T-RPLT-005 / 2d | 实现安全会话与再认证 | auth ADR；auth/API/Web session 文件 | T-RPLT-004, T-REVAL-007 | HttpOnly/SameSite/CSRF、会话轮换、X 级再认证 | E-AUTH-005/007, E-SEC-002（EX-R1-013） | 吊销测试会话；任一绕过即停 |
| T-RPLT-006 / 2d | 实现写前审计与事务绑定 | R-AUD-001；audit middleware/repository | T-RPLT-004, T-REVAL-007 | 审计失败则业务写不提交 | E-CMD-004（EX-R1-014）；故障注入 audit store | 禁用写 feature flag；非原子即停 |
| T-RPLT-007 / 2d | 实现敏感读响应前持久审计 | R-AUD-001；projection/audit middleware | T-RPLT-006, T-REVAL-003 | D2+ 读在审计确认后才返回 | E-AUD-001—004（EX-R1-005）；延迟/断库/取消负例 | 降级为拒绝读；先返回后记账即停 |
| T-RPLT-008 / 2d | 实现幂等命令收据 | idempotency contract；command middleware | T-RPLT-006, T-REVAL-007 | scope+actor+key 唯一收据及响应重放 | E-CMD-001—003（EX-R1-014）；并发/不同 actor 测试 | 关闭写；重复副作用即停 |
| T-RPLT-009 / 2d | 实现 W2 Approval application orchestrator | approval/risk contracts；application service | T-RPLT-010, T-RPLT-015, T-RPLT-016, T-REVAL-008 | validate→proposal→receipt→consume→commit 编排；不依赖 Agent runtime | E-AGT-021—024, E-CMD-003/004 | 关闭 W2；可绕过 receipt 或依赖 Agent SDK 即停 |
| T-RPLT-010 / 2d | 实现单调动态风险评估器 | R-RISK-001；policy domain | T-REVAL-003 | 由动作×对象×分类×数量×外部性×可逆性×认证计算，仅升级 | E-RISK-001—005（EX-R1-004）；性质测试 | 回退到最高适用风险；任何降级变体即停 |
| T-RPLT-011 / 1d | 建立脱敏遥测与关联 ID | privacy rules；telemetry config/middleware | T-RPLT-006, T-REVAL-009 | request/command/audit 关联，无 D2+ payload | E-PRV-003, E-OBS-001—004 | 关闭 exporter；检测泄露即停并轮换 |
| T-RPLT-012 / 3d | 实现 BCG 内两阶段 workspace-bound scope bootstrap 与 real-data admission verifier | R-ADM-001；BCG/admission domain/middleware/config；signed artifact policy | T-RGOV-005, T-REVAL-008, T-RPLT-006 | 默认 synthetic-only；唯一 `ScopeAllocationCommand` 验证当前外部签发/撤回快照；在本地 PostgreSQL 单事务消费 setup、写无 PII allocation/ledger/audit/receipt payload 并预留 ID；唯一键 deployment+setup；同请求重试返回原 receipt，冲突拒绝；unknown pre-admission command/field 全拒绝；最终 issued artifact 绑定 workspace/allocation/reports/模块/到期/撤回；reusable reports 和 renewable admission 不消费、每次写复核 | E-ADM-001—009（EX-R1-021）；并发只分配一次；提交前故障全回滚，提交后签名/响应丢失只补发原 receipt；跨 workspace、直接建 Class/Term/Student、冲突重放 setup、消费 report/admission、任意字符串 hash 均失败 | 强制 synthetic-only；出现第四边界、通用 bypass、应用自签、setup 承载个人数据、报告未验真或越界/过期写入即停 |
| T-RPLT-013 / 2d | 实现首次 owner bootstrap | 身份 ADR；auth bootstrap application/API | T-RPLT-003, T-RPLT-018, T-REVAL-007 | 单次短时 bootstrap secret、首 owner 创建、完成后永久关闭入口 | E-AUTH-009/010/018（EX-R1-022） | 销毁 bootstrap secret；可创建第二 owner或旁路身份边界即停 |
| T-RPLT-014 / 2d | 实现离线码恢复兑换、凭据轮换与全会话吊销 | 身份 ADR；auth recovery/session | T-RPLT-019, T-REVAL-007 | 不枚举账号；有效码仅兑换同客户端短时 session；恢复后轮换凭据并撤销旧会话/旧码 | E-AUTH-011—013/015—018（EX-R1-022） | 关闭恢复入口；未持码者获能力、码泄露或旧会话仍有效则停 |
| T-RPLT-015 / 2d | 实现 Approval proposal/receipt 状态机 | FR-AGT-004/005；approval domain/repository | T-RPLT-008, T-REVAL-003 | proposal hash/version/scope/expiry 与一次性 receipt 纯领域状态机 | E-AGT-018/020/024（EX-R1-003） | 关闭 W2；重复/跨资源消费即停 |
| T-RPLT-016 / 2d | 实现私有 approval endpoint 绑定 | Approval state；approval API/auth middleware | T-RPLT-005, T-RPLT-015, T-REVAL-008 | Origin/CSRF/actor/session/client/reauth 校验；不在 Tool catalog | E-AGT-015—020（EX-R1-002/003/019） | 关闭 endpoint；普通字段被当强人类证明或可跨会话即停 |
| T-RPLT-017 / 2d | 强制所有业务写 adapter 经过 Business Command Gateway | Architecture choke point；boundary tests/application adapters | T-RPLT-006, T-RPLT-008, T-RPLT-009, T-RPLT-012, T-REVAL-008 | REST/controller/Web/internal/worker/repository/test/future CLI 均无 W1/W2 旁路；pre-admission 只允许 ScopeAllocationCommand；worker job-state/attempt/receipt 也被分类 | E-AGT-021—025, E-ADM-009, E-CMD-001—004（EX-R1-021/023） | 禁用业务写；第四边界、unknown pre-admission type、任何 adapter/worker/repository 旁路即停 |
| T-RPLT-018 / 2d | 实现 Identity Security Command Boundary | identity architecture；identity command middleware/repositories | T-RPLT-006, T-RPLT-008, T-REVAL-007 | bootstrap/login/logout/recovery/credential/session 写入分类、限速、幂等、事务与安全审计；不得访问学生业务聚合 | E-AUTH-009/010/015/018 | 关闭身份写入口；存在第四类或 repository 旁路即停 |
| T-RPLT-019 / 2d | 实现离线恢复码生成、单次显示与哈希存储 | ADR-007；recovery kit domain/UI | T-RPLT-013, T-RPLT-018 | 高熵码套件只显示/导出一次，不经邮件/模型/日志/支持包；加盐哈希、轮换与销毁 | E-AUTH-015—017（EX-R1-022） | 撤销全部测试码；明文持久化/传输或无法轮换即停 |

## 3. Release 1 领域与 API

| ID / 估算 | Goal | Inputs 与文件范围 | Depends on | Expected output | Validation | Recovery / Stop |
|---|---|---|---|---|---|---|
| T-RDOM-001 / 1d | 定义 `[valid_from, valid_to)` 时间语义 | R-TIME-001；domain temporal types | T-RPLT-003, T-REVAL-004 | UTC 存储、时区展示、开闭区间 helper | E-TIME-001/002（EX-R1-015）；DST/边界性质测试 | 回退类型；歧义时间拒绝写入 |
| T-RDOM-002 / 2d | 实现 Class、Term、Student 聚合 | domain model；domain/repository/migration | T-RDOM-001, T-RPLT-004 | 最小聚合和乐观版本 | E-CLS-001, E-ROS-001/004；unit + repository contract | 前滚移除未用字段；身份边界不清则停 |
| T-RDOM-003 / 2d | 实现多源 StudentIdentifier | R-ID-001；identifier migration/domain | T-RDOM-002, T-REVAL-004 | source+value+有效期唯一，学生可多标识 | E-ID-001—003（EX-R1-007） | 禁止自动关联；冲突进入候选队列 |
| T-RDOM-004 / 1d | 实现重复候选但禁止合并 | DuplicateCandidate；identity domain policy/tests | T-RDOM-003, T-REVAL-004 | 提示相似项，只能保持分离/人工修正标识符的纯领域决定 | E-ID-003/004（EX-R1-007）；无 merge domain command | 回退策略；发现隐式合并即停 |
| T-RDOM-005 / 2d | 实现花名册 repository | FR-CLS；roster domain/repository/migration | T-RDOM-003, T-REVAL-004 | create/update/deactivate persistence、scope 与版本；无 hard delete/Guardian 字段 | E-ROS-001—004, E-RET-001（EX-R1-016） | 回退迁移/仓储；不可导出的字段不得落库 |
| T-RDOM-006 / 2d | 实现事实型 Record 聚合与 repository | R-ATT/LEAVE/HWK；record domain/repository/migration | T-RDOM-002, T-RDOM-001 | append/correct/supersede，不生成比率或唯一当前状态 | E-ATT-001, E-LEAVE-001, E-HWK-001（EX-R1-008/017） | 回退迁移；隐式聚合或覆盖原事实即停 |
| T-RDOM-007 / 2d | 实现请假关联 Command handler | leave rule；leave application handler | T-RDOM-006, T-RPLT-017 | 申请、批准事实、销假事实经 Command Gateway 关联 | E-LEAVE-001, E-AGT-021/022 | 禁止覆盖原事实；无法追溯或可旁路即停 |
| T-RDOM-008 / 2d | 实现作业事实 Command handler | homework rule；homework application handler | T-RDOM-006, T-RPLT-017 | 只表达已记录事实，经统一风险/批准/审计写入 | E-HWK-001, E-AGT-021/022 | 关闭 handler；出现推断标签或旁路即停 |
| T-RDOM-009 / 2d | 实现简单 Task 聚合与 repository | FR-TSK；task domain/repository/migration | T-RDOM-002, T-REVAL-004 | not-started/in-progress/waiting/done/cancelled/overdue、due_at、完成证据、关联学生/事件 | E-EVT-004, E-TSK-001, E-CMD-003；状态机 unit | 回退迁移；状态转换歧义则停 |
| T-RDOM-010 / 2d | 实现 Timeline 与 Today 查询 | R1 manifest；query/projection/API | T-RDOM-005, T-RDOM-006, T-RDOM-007, T-RDOM-008, T-RDOM-009, T-RPLT-007 | 今天任务、最近事实、无“当天课务” | E-AUD-001, E-EVT-001/004, E-ATT-001（EX-R1-005/017） | 降级为空视图；跨 scope/推断状态即停 |
| T-RDOM-011 / 2d | 实现 Class/Term/Student Command handlers | FR-CLS；roster application/API | T-RDOM-002, T-RDOM-003, T-RDOM-004, T-RDOM-005, T-RPLT-017 | create/update/archive/deactivate 经 admission/auth/risk/idempotency/approval/audit | E-ROS-001—004, E-AGT-021—024 | 关闭 route；Guardian/merge/hard-delete surface 或旁路即停 |
| T-RDOM-012 / 2d | 实现通用事实 Record Command handlers | FR-EVT；record application/API | T-RDOM-006, T-RPLT-017 | W1/W2 按 canonical payload 分流；D4/附件/批量拒绝 | E-EVT-001—003, E-RISK-001—005, E-AGT-021—024 | 关闭 route；客户端风险可降级或 W2 无 receipt 即停 |
| T-RDOM-013 / 2d | 实现 Task Command handlers | FR-TSK；task application/API | T-RDOM-009, T-RPLT-017 | 创建/转换/完成/取消经统一 Gateway，超时可查 receipt | E-EVT-004, E-CMD-001—003, E-OPS-001/003 | 关闭 route；重复或非法状态写入即停 |

## 4. 最小生命周期执行

| ID / 估算 | Goal | Inputs 与文件范围 | Depends on | Expected output | Validation | Recovery / Stop |
|---|---|---|---|---|---|---|
| T-RLIFE-001 / 2d | 建立 schema 驱动 R1 store inventory/locator | schema/repository/volume/queue/provider/ops 清单；lifecycle config | T-RGOV-002, T-RPLT-003 | 覆盖业务、identity/session/recovery、approval/command receipt、outbox、Agent/model、admission/revocation、audit/telemetry/support、export/backup；逐项期限、owner、例外 | E-RET-002/004；注入未知表/卷/queue/provider 后 gate 必须红 | 强制 synthetic-only；任一 store 未分类或政策未批准即停 |
| T-RLIFE-002 / 2d | 实现停用/归档领域语义 | R-RET-001/002；lifecycle domain/application | T-RLIFE-001, T-RDOM-011 | deactivate/archive 保留历史；无 delete-complete 状态或 hard-delete command | E-RET-001, E-ROS-004（EX-R1-010/016） | 关闭动作；出现删除完成状态即停 |
| T-RLIFE-003 / 3d | 实现权利请求 case 与逐 store 处置账本 | approved rights process；versioned store inventory；lifecycle application/repository | T-RLIFE-001, T-RPLT-017, T-RPLT-018 | access/correct/restrict/export/delete request、身份验证、逐 store 状态/例外/到期；基础设施 store 不漏项 | E-PRV-006—008, E-RET-002/004（EX-R1-010） | 仅登记不自动物理删；无法列出 store/例外则停 |
| T-RLIFE-004 / 2d | 实现 restriction/delete tombstone 与恢复/导入重放 | lifecycle ledger；backup/exit restore hooks | T-RLIFE-003, T-ROPS-006 | 恢复备份或导入退出包时先重放限制/删除清单，保留未结请求/例外，不复活数据 | E-RET-003, E-EXIT-001, E-OPS-006/007 | 隔离恢复不切换；重放失败、ledger 缺失或数据复活则停 |
| T-RLIFE-005 / 2d | 实现 candidate-time 实际 store inventory scanner 与双向核对器 | schema/repository/volume/queue/provider/telemetry/support/export/backup 发现规则；lifecycle matrix | T-RLIFE-001, T-RPLT-014, T-RPLT-015, T-RPLT-017, T-RPLT-019, T-RAGT-003, T-REXP-002, T-ROPS-005 | verifier 在每次 candidate gate 针对 exact target commit 现场生成 inventory，不复用旧清单；与批准 matrix 双向一致；每个实际 store 有 locator/owner/期限/处置/证明；evidence 绑定 candidate target commit | E-RET-002/004, E-TASK-001/E-GATE-002；在任务完成后注入未知 store、换 commit 或删除登记必须红 | 保持 synthetic-only；任何实际 store 未登记、evidence commit 不等或扫描器非现场执行即不组候选 |

## 5. Web 与 Agent 草稿能力

| ID / 估算 | Goal | Inputs 与文件范围 | Depends on | Expected output | Validation | Recovery / Stop |
|---|---|---|---|---|---|---|
| T-RWEB-001 / 2d | 实现移动优先 shell 与登录 | UX spec；Web shell/auth pages | T-RPLT-005, T-RPLT-014, T-REVAL-008, T-REVAL-011 | 320px 可用、键盘可达、会话/离线码恢复明确；无录音/转写/音频入口 | E-AUTH-005/007/011—013/015—018, E-PRV-013/014, E-A11Y-002/003 | 回退静态 shell；关键控件不可达、恢复码泄露/后门或出现语音 surface 则停 |
| T-RWEB-002 / 2d | 实现花名册列表与编辑 | roster API；Web roster files | T-RDOM-010, T-RDOM-011, T-RWEB-001 | 搜索、查看、显式编辑、冲突反馈；无 Guardian/merge/delete | E-ROS-001—004, E-RET-001；scope/auth/idempotency E2E | 关闭编辑 flag；错人写入即停 |
| T-RWEB-003 / 3d | 实现事实事件表单 | Record API；Web record forms | T-RDOM-007, T-RDOM-008, T-RDOM-012, T-RWEB-001, T-RWEB-005 | 内存态恢复；W1 显式提交、W2 走可信批准卡；无 D2+ 持久离线缓存 | E-LOCAL-001—005, E-ATT-001, E-LEAVE-001, E-HWK-001, E-AGT-016—024 | 清空内存草稿；发现持久敏感草稿或确认绕过即停 |
| T-RWEB-004 / 2d | 实现 Today/Timeline 和任务操作 | query/task API；Web views | T-RDOM-010, T-RDOM-013, T-RWEB-001 | 事实来源、任务状态、无课务入口 | E-EVT-001/004, E-AUD-001, E-WEB-002—004 | 关闭视图；来源不明则停 |
| T-RWEB-005 / 3d | 实现可信批准卡 | approval API；Web approval components | T-RPLT-009, T-RPLT-016, T-RWEB-001, T-REVAL-008 | 风险原因、diff、对象/数量、过期、一次性操作 | E-AGT-015—024, E-RISK-001—005（EX-R1-002—004/019） | kill switch；绑定信息不可见或不匹配即停 |
| T-RWEB-006 / 2d | 实现 Class/Term 建立、切换与归档界面 | class/term API；Web context/setup pages | T-RDOM-011, T-RWEB-001, T-RWEB-005 | 首次建立当前班级/学期、显式切换、编辑与 W2 归档；归档后只读历史 | E-CLS-001, E-AGT-016—024 | 关闭 setup route；无批准归档、归档后仍可新写或上下文含混即停 |
| T-RAGT-001 / 2d | 定义只读与草稿 Tool schemas | R1 manifest；schema source/API types | T-RDOM-005, T-RDOM-006, T-RDOM-007, T-RDOM-008, T-RDOM-009, T-RDOM-010, T-REVAL-008, T-REVAL-012 | 仅 search/get/list/draft，无 approve/apply/merge/external send | E-AGT-001/002/011/015；schema allowlist | 禁用 Agent；发现越界 schema 即停 |
| T-RAGT-002 / 2d | 实现 Tool Gateway 投影与审计 | Tool schemas；gateway/application | T-RAGT-001, T-RPLT-007 | scope、最小字段、敏感读审计、速率限额 | E-AGT-001/009—012, E-AUD-001/002 | kill switch；原始 repository 暴露即停 |
| T-RAGT-003 / 3d | 接入可替换 Agent runtime 与 fake | approved adapter；agent runtime files | T-RAGT-002, T-RSPK-002 | provider adapter、deterministic fake、超时/取消/重试 | E-AGT-013/014, E-OPS-008；外部 provider 默认关闭 | 切 fake/禁用；未经准入外传即停 |
| T-RAGT-004 / 2d | 实现查询与事件草稿 Skill | SOP；skills/prompts/evals | T-RAGT-003, T-RWEB-003, T-REVAL-008 | 声明未知、引用事实、只生成草稿交 UI | E-AGT-001/002/009—014, E-AUD-002（EX-R1-018） | 禁用 skill；幻觉写入或弱化确认即停 |

## 6. 退出、自托管与试点门

| ID / 估算 | Goal | Inputs 与文件范围 | Depends on | Expected output | Validation | Recovery / Stop |
|---|---|---|---|---|---|---|
| T-REXP-001 / 2d | 定义最小退出包 schema 与版本 | R-EXIT-001；export schema/docs | T-RDOM-003, T-RDOM-006, T-RDOM-009, T-RLIFE-001, T-REVAL-005 | Workspace/Class/AcademicTerm/Student/StudentIdentifier/Record/Task、rights-request/restriction/delete/retention/admission ledger、必要 audit refs、引用图、schema version/checksum/不可移植声明 | E-EXP-001/003, E-EXIT-001；合成 schema golden 与未知字段兼容测试 | 保留上一 schema；缺核心实体或 lifecycle ledger 不得写真实数据 |
| T-REXP-002 / 3d | 实现授权导出、worker 与审计 | export schema；application/API/worker | T-REXP-001, T-RPLT-007, T-RPLT-017 | API 只经 Business Command Gateway 登记导出；worker 的 job-state/attempt/receipt 与产物发布受同一边界和审计约束；用户可下载加密或受控退出包 | E-EXP-003—005, E-AUD-003, E-AGT-025 | 撤销链接、删除临时包；worker/repository 旁路或越权即停 |
| T-REXP-003 / 3d | 实现干净环境导入往返与退役证明验证器 | export package；import verifier/evals | T-REXP-002, T-REVAL-005 | 核心/ledger 引用、计数、哈希一致；开放前重放 tombstone；退役证明与不可移植项可诊断 | E-EXIT-001, E-EXP-001/002, E-RET-003（EX-R1-009）；删除 ledger/复活数据/破坏包必须失败 | 丢弃目标测试库；不可恢复、无法证明退役或数据复活则停止真实写 |
| T-ROPS-001 / 2d | 构建固定单机容器拓扑 | self-host spec；deploy/compose/images | T-RSPK-003, T-RPLT-011, T-REVAL-010 | 固定版本、非 root、healthcheck、持久卷清单、TLS/静态存储/密钥边界 | E-OPS-009/011, E-SEC-007；clean host 启动扫描 | 回退上一镜像；隐式云依赖或密钥进入镜像即停 |
| T-ROPS-002 / 2d | 实现 install 与 doctor | ops spec；deploy/scripts/runbook | T-ROPS-001, T-REVAL-005 | 前置检查、安装、资源/时间/证书/磁盘诊断 | E-OPS-009/012（EX-R1-012）；三类故障有可操作错误 | 卸载新实例不碰数据卷；误判健康则停 |
| T-ROPS-003 / 2d | 实现加密备份生成与保留 | retention decisions；backup job/scripts | T-ROPS-001, T-REXP-003 | 一致性快照、加密、校验和、保留、失败告警 | E-OPS-005/007 | 保留上一有效备份；密钥/一致性不明则停 |
| T-ROPS-004 / 3d | 实现升级 dry-run 与回滚 | ops spec；upgrade/migration runbooks | T-ROPS-002, T-ROPS-003 | preflight、N/N-1 兼容迁移、失败回滚/前滚修复 | E-OPS-010, E-MIG-001—004 | 回滚镜像/前滚修复；无有效备份不升级 |
| T-ROPS-005 / 2d | 实现磁盘/证书告警与脱敏支持包 | ops spec；monitoring/support scripts | T-ROPS-002 | 阈值告警、轮换提醒、无 D2+ payload 支持包 | E-OPS-012/013, E-OBS-003 | 禁用支持包；发现敏感信息立即删除并停 |
| T-ROPS-006 / 3d | 实现隔离主机恢复与应用完整性校验 | backup + exit schemas；restore scripts/runbook | T-ROPS-003, T-REXP-003 | 新主机恢复、引用/计数/hash 校验、坏备份拒绝切换 | E-OPS-006/007/011（EX-R1-012） | 保留原环境；校验失败不切换 |
| T-ROPS-007 / 2d | 实现安全卸载与退役 | ops/lifecycle/exit specs；retire script/runbook | T-ROPS-002, T-REXP-003, T-RLIFE-003 | 先导出含 lifecycle ledger 的包、验证接收/退役证明、撤销凭据、停服务、按政策清除或记录例外，不误删备份 | E-EXIT-001, E-OPS-014, E-RET-002/004 | 默认保留数据卷；ledger、接收证明、范围或例外不清则停 |
| T-RREL-001 / 2d | 组装 Release 1 候选并执行全门禁 | 全部 R1 任务；release config/evidence | T-REVAL-006, T-RPLT-012, T-RPLT-014, T-RPLT-017, T-RLIFE-001, T-RLIFE-002, T-RLIFE-003, T-RLIFE-004, T-RLIFE-005, T-RWEB-002, T-RWEB-003, T-RWEB-004, T-RWEB-005, T-RWEB-006, T-RAGT-004, T-REXP-003, T-ROPS-001, T-ROPS-002, T-ROPS-003, T-ROPS-004, T-ROPS-005, T-ROPS-006, T-ROPS-007 | 不可变候选、SBOM、签名、机器 gate 结果和证据索引；candidate gate 在 exact target commit 现场运行 store scanner，不接受 T-RLIFE-005 的旧 inventory | E-SEC-005/006, E-RET-002/004, E-TASK-001/E-GATE-002 + `verify all`; selector 中全部 eval 有目标版本 green 证据且 inventory evidence target_commit 完全相等 | 撤下候选；任一 required eval 非绿、未知 store 或 stale inventory 不发布 |
| T-RREL-002 / 2d effort / 5 business-day calendar | 完成合成数据 shadow 与净减负测量 | 候选版本；eval results/ops logs；R1 pilot profile | T-RREL-001 | 首次建班/40—60 人手工 roster/核对/重复录入成本，连续 5 日维护/支持/复用节省，摊销周期与故障/恢复/退出证据 | E-VALUE-001, E-UX-001；原始时间日志、计算表和退出往返 | 日历等待单列；成本项缺失、净收益不成立或出现数据/审批绕过即 change/stop |
| T-RREL-003 / 3d effort | 执行两阶段最小真实试点准入与退出演练 | 所有治理签字、candidate/shadow/value/pilot-readiness reports；`release-1-pilot-profile.md` | T-RGOV-001, T-RGOV-002, T-RGOV-003, T-RGOV-004, T-RGOV-005, T-RPLT-012, T-RLIFE-004, T-RREL-002, T-ROPS-001, T-ROPS-002, T-ROPS-003, T-ROPS-004, T-ROPS-005, T-ROPS-006, T-ROPS-007 | BCG ScopeAllocationCommand 原子消费 workspace-bound setup 并生成 ledger receipt；最终 renewable admission 绑定全部已验真 reports 与 scope，书面 go/change/stop | manifest 全部 required eval、E-SCOPE-002、E-ADM-001—009、E-OPS-009—014 全绿；报告可重复验证、setup 不可重放、before-any-real-write 每次写生效；首/末日导出 | 立即撤回 admission、停写、导出并回退；第四边界、跨 workspace、setup 越权/重放、report 被消费或证据缺失不得开始 |

## 7. 重估与控制规则

完成首批五项可计时工程任务（不含等待外部签字）后，由项目负责人记录实际 cycle time、返工比例、blocked time 和评测维护成本，并更新剩余任务估算。未经这次重估，不给出全量 v1 的承诺日期；62 个主工作包也不得机械相加成项目排期。

任何新增需求必须先进入 change record，补齐 rule/case/eval/trace，再决定加入 Release 1、后续 release 或拒绝。Release 1 范围的默认处理是拒绝扩张。
