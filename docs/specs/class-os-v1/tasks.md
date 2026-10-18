# Master Work Packages: ClassMatter v1

> 文档状态（2026-10-08）：现行规格/规划/规则；设计存在；实现/批准须另凭目标版本证据。项目完成度见 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md)；本标识不提升批准、测试或任务状态。

状态：`planned-epics`。本文保留完整 v1 的 62 个主工作包，用于范围分解与中长期追踪，不再声称它们都是可直接领取的原子任务。最小 Release 1 的 1—3 天原子任务见 `release-1-atomic-tasks.md`。任务顺序服从 `plan.md`。没有用户明确授权时，这些是实施计划，不代表可以开始处理真实数据或部署。

统一约定：`verify <suite>` 代表 T-FOUND-004 建立的跨平台验证入口；若该任务未完成，后续实现任务停止。

## D. Discovery and confirmation

- [ ] **T-DISC-001：完成目标班主任任务日志**
  - Goal：取得至少 5 个工作日的任务、触发、步骤、耗时、重复和风险基线；重点建立通知发现、责任归属、期限、催办、后果、交接/升级、证据和主观责任压力基线。
  - Inputs：business-brief、定性需求摘要、R-PROD-001、A-006/A-007/A-008/A-027、发现阶段计划。
  - File scope：`handoff/raw/behavior-notes/**`、`handoff/normalized/**`、`docs/specs/class-os-v1/requirements.md`。
  - Depends on：无。
  - Expected output：脱敏日志、任务频率—负担矩阵、责任压力事件表、优先级修订；每个责任事项记录 source、显式/隐式责任人、deadline、late discovery/private chase、handoff/escalation 和 completion evidence。
  - Validation：业务负责人检查覆盖 5 日、时间口径、责任风险字段和脱敏；`verify docs`。
  - Rollback/recovery：保留原始授权副本；错误归类以新版本覆盖，不删除来源。
  - Stop condition：未取得数据授权或内容无法安全脱敏。

- [ ] **T-DISC-002：收集并确认候选输入样例**
  - Goal：获得花名册、成绩、座位、宿舍、事件的最小脱敏样例。
  - Inputs：sample-io-confirmation、source-inventory、R-DEV-004。
  - File scope：`handoff/raw/examples/**`、`handoff/normalized/examples.normalized/**`、`.ai/confirmation/sample-io-confirmation.md`。
  - Depends on：T-DISC-001。
  - Expected output：登记、脱敏、哈希和 confirmation_status 明确的样例。
  - Validation：无直接身份信息；来源/规则/case 可追；业务用户签字确认。
  - Rollback/recovery：发现泄露立即隔离并按事件流程处理，重新生成最小样例。
  - Stop condition：学校/用户未授权、无法可靠去标识化或样例版本不明。

- [ ] **T-DISC-003：冻结成绩和学期口径**
  - Goal：确认满分、缺考、并列、总分、排名、四舍五入、学期和转班规则。
  - Inputs：R-GRD-002、A-005/A-015、确认样例。
  - File scope：`handoff/normalized/rulebook.md`、`examples.catalog.md`、`output-contract.md`、`evals/class-os-v1/golden/**`。
  - Depends on：T-DISC-002。
  - Expected output：confirmed rule version 与真实 golden。
  - Validation：每条口径至少一个正常和边界案例；业务用户批准。
  - Rollback/recovery：保留旧规则版本，错误确认标记 superseded。
  - Stop condition：学校口径冲突未解决。

- [ ] **T-DISC-004：批准数据流与真实数据准入**
  - Goal：确认学校使用边界、模型数据流、保留期、用户角色和运维责任。
  - Inputs：A-003/A-010、security/privacy spec、部署设计。
  - File scope：`docs/06-系统设计/安全隐私与威胁模型.md`、`docs/08-运维与治理/**`、`.ai/confirmation/**`。
  - Depends on：T-DISC-001。
  - Expected output：签署的数据流、风险接受/缓解、准入清单。
  - Validation：隐私/安全/业务三方评审；无未处理高风险。
  - Rollback/recovery：撤销准入，回到合成数据环境。
  - Stop condition：真实数据合法/授权基础不明确。

## F. Foundation

- [ ] **T-FOUND-001：技术与 Agent runtime spike**
  - Goal：验证候选 Web/API/DB/worker/runtime 组合与替代方案。
  - Inputs：ADR-001—006、resource-review、E-AGT/E-OPS 关键案例。
  - File scope：`spikes/architecture/**`、`docs/specs/class-os-v1/architecture*.md`、`resource-review.md`。
  - Depends on：T-DISC-004 可对真实部署 deferred，但使用合成数据。
  - Expected output：资源测量、HITL 恢复、fake provider、trace 脱敏、部署和许可比较。
  - Validation：运行 spike 脚本；评审每个 exit criterion；不得以演示视频代替结果。
  - Rollback/recovery：spike 隔离，不合并实验依赖到生产路径。
  - Stop condition：任何候选无法安全关闭敏感 tracing、无法测试替身或许可不明。

- [ ] **T-FOUND-002：建立仓库与模块骨架**
  - Goal：创建 web/api/domain/contracts/infra/tests 的窄边界和依赖规则。
  - Inputs：approved ADR、module-boundaries。
  - File scope：`apps/web/**`、`services/api/**`、`packages/contracts/**`、`infra/**`、根配置。
  - Depends on：T-FOUND-001、architecture confirmation approved。
  - Expected output：可构建空壳、dependency boundary 检查、开发说明。
  - Validation：`verify static`、`verify build`。
  - Rollback/recovery：删除仅本任务新增的空壳需评审；保留 spike 记录。
  - Stop condition：技术栈/目录责任仍未批准。

- [ ] **T-FOUND-003：建立本地与 CI 环境**
  - Goal：用合成数据一键启动依赖并在 CI 重复验证。
  - Inputs：deployment design、T-FOUND-002。
  - File scope：`infra/dev/**`、`.github/**` 或选定 CI、`docs/07-实施与测试/**`。
  - Depends on：T-FOUND-002。
  - Expected output：不可变依赖、缓存、artifact、secret scanning 和最小 pipeline。
  - Validation：全新环境从零执行 build/test；`verify all` 空套件通过。
  - Rollback/recovery：回退 CI 配置和镜像标签；不修改宿主全局环境。
  - Stop condition：需要未记录的个人机器 secret 或手工步骤。

- [ ] **T-FOUND-004：实现统一 eval runner**
  - Goal：将文档定义的 suite 映射为本地/CI 可执行命令和机器可读报告。
  - Inputs：`evals/class-os-v1/**`、harness-map。
  - File scope：`tools/verify/**`、`evals/**`、根任务配置。
  - Depends on：T-FOUND-002/003。
  - Expected output：`verify docs|unit|contract|integration|e2e|security|performance|recovery|all`。
  - Validation：故意加入一个失败 fixture，runner 必须非零退出并定位 eval_id，之后撤销 fixture。
  - Rollback/recovery：runner 独立，不改业务逻辑；恢复到上个可运行版本。
  - Stop condition：suite 不能在 CI 和本地使用同一入口。

- [ ] **T-FOUND-005：实现 workspace 身份与授权骨架**
  - Goal：建立主体、workspace、membership、scope 和字段策略的服务端授权。
  - Inputs：FR-PLT-001—004、E-AUTH-001—008。
  - File scope：`services/api/src/domain/identity_access/**`、`application/auth/**`、`tests/auth/**`。
  - Depends on：T-FOUND-004。
  - Expected output：deny-by-default policy 与 fake identity adapter。
  - Validation：`verify unit`、`verify integration --filter E-AUTH`。
  - Rollback/recovery：schema 使用兼容迁移；feature flag 阻止真实登录。
  - Stop condition：认证库安全状态/许可不明或授权只能靠前端。

- [ ] **T-FOUND-006：实现业务审计骨架**
  - Goal：追加业务 audit，区分日志/trace 并提供范围查询。
  - Inputs：FR-AGT-006、NFR-SEC-006、E-PRV-004/E-OBS-001。
  - File scope：`services/api/src/domain/audit/**`、`infrastructure/audit/**`、`tests/audit/**`。
  - Depends on：T-FOUND-005。
  - Expected output：append/query、redaction、request_id 关联。
  - Validation：`verify integration --filter E-PRV-004,E-OBS-001`；PII 日志扫描。
  - Rollback/recovery：审计失败必须使关键事务失败；不得静默降级。
  - Stop condition：audit 需要保存完整敏感 payload 才能工作。

- [ ] **T-FOUND-007：实现 Command 幂等、版本和批准状态机**
  - Goal：统一 proposal/approval/receipt 和乐观并发。
  - Inputs：FR-AGT-003—005、E-CMD-001—004、E-AGT-003—008。
  - File scope：`services/api/src/domain/capabilities/**`、`application/commands/**`、`tests/commands/**`。
  - Depends on：T-FOUND-005/006。
  - Expected output：可复用 Command pipeline，无具体业务 Command。
  - Validation：`verify unit/integration --filter E-CMD,E-AGT-003..008`。
  - Rollback/recovery：仅兼容迁移；发现重复写立即禁用写 Tool。
  - Stop condition：批准未绑定 actor/scope/hash/version/expiry 任一项。

- [ ] **T-FOUND-008：实现对象隔离与 transactional outbox**
  - Goal：安全 staging 附件/导入/导出并保证后台任务可靠。
  - Inputs：ADR-005、NFR-SEC-003、E-OPS-002—004。
  - File scope：`services/api/src/infrastructure/storage/**`、`outbox/**`、`worker/**`、`tests/ops/**`。
  - Depends on：T-FOUND-006/007。
  - Expected output：storage adapter、quarantine、outbox worker、清理策略。
  - Validation：`verify integration/recovery --filter E-OPS-002..004,E-SEC-003`。
  - Rollback/recovery：停止 worker；保留 outbox 待重放；孤儿对象隔离。
  - Stop condition：对象可匿名访问或 worker 无幂等。

## R. Roster and class context

- [ ] **T-ROS-001：实现 Class/Term/Student/Enrollment 领域模型**
  - Goal：建立学生中心聚合与时间有效关系。
  - Inputs：FR-CLS-001—005、E-ROS-001/004。
  - File scope：`services/api/src/domain/roster/**`、`tests/unit/roster/**`。
  - Depends on：T-FOUND-005/007。
  - Expected output：纯领域模型、状态转换和 repository ports。
  - Validation：`verify unit --filter E-ROS-001,E-ROS-004`。
  - Rollback/recovery：无数据库写前可回退；模型变化保留 migration plan。
  - Stop condition：班级/学期/转班规则冲突未显式配置。

- [ ] **T-ROS-002：实现 roster 持久化与迁移**
  - Goal：落地 workspace-scoped schema、约束和 repository。
  - Inputs：T-ROS-001、data dictionary、E-AUTH/E-MIG。
  - File scope：`services/api/src/infrastructure/db/roster/**`、`migrations/**`、`tests/integration/roster/**`。
  - Depends on：T-ROS-001。
  - Expected output：向前迁移、索引、版本列、集成测试。
  - Validation：`verify integration --filter E-ROS,E-AUTH-001`、`verify migration`。
  - Rollback/recovery：空环境可回退；有数据环境优先前滚修复。
  - Stop condition：无法在数据库层阻止跨 workspace 引用。

- [ ] **T-ROS-003：实现学生匹配与合并 proposal**
  - Goal：按稳定标识匹配，同名/冲突进入人工流程。
  - Inputs：FR-CLS-002/007、E-ROS-002/003、E-IMP-004/005。
  - File scope：`services/api/src/domain/roster/matching/**`、`application/roster/**`、`tests/roster/**`。
  - Depends on：T-ROS-002。
  - Expected output：deterministic matcher、candidate evidence、merge proposal。
  - Validation：`verify unit/integration --filter E-ROS-002,E-ROS-003`。
  - Rollback/recovery：合并只经批准；保留重定向和反向恢复。
  - Stop condition：需要仅凭姓名自动合并。

- [ ] **T-ROS-004：实现 roster API 与合同**
  - Goal：提供 class/student CRUD、search、context 和 field projection。
  - Inputs：API contract、FR-CLS、E-AUTH。
  - File scope：`services/api/src/adapters/http/roster/**`、`packages/contracts/roster/**`、`tests/contract/roster/**`。
  - Depends on：T-ROS-002/003。
  - Expected output：versioned schemas、错误码、契约快照。
  - Validation：`verify contract/integration --filter E-ROS,E-AUTH`。
  - Rollback/recovery：兼容旧 schema；破坏变更新版本。
  - Stop condition：API 暴露 guardian 字段而无 field scope。

- [ ] **T-ROS-005：实现班级/学生 UI 与 Student 360 壳**
  - Goal：从 UI 直接管理并聚合可用领域数据。
  - Inputs：UX spec、FR-CLS-001—006、E-UX-002。
  - File scope：`apps/web/src/features/roster/**`、`tests/e2e/roster/**`。
  - Depends on：T-ROS-004。
  - Expected output：列表、搜索、详情、空/错/权限/加载状态。
  - Validation：`verify e2e --filter E-ROS,E-UX-002`、a11y smoke。
  - Rollback/recovery：feature flag；不删除后端数据。
  - Stop condition：UI 自行拼接越权字段或复制业务规则。

## E. Events, tasks and Today

- [ ] **T-EVT-001：实现统一 Record 与 Attendance/Homework 扩展**
  - Goal：区分事实/观察/会话内推断草稿并支持常用事件类型；R1 不持久化推断。
  - Inputs：FR-EVT-001—003/005/006、E-EVT-001/003/008。
  - File scope：`services/api/src/domain/records/**`、`tests/unit/records/**`。
  - Depends on：T-ROS-001。
  - Expected output：只含 typed 事实/教师观察的领域状态、validators、timeline query port；推断草稿无 repository/schema。
  - Validation：`verify unit --filter E-EVT-001,E-EVT-003,E-EVT-008`。
  - Rollback/recovery：事件类型版本化；不覆盖历史含义。
  - Stop condition：出现 RecordInference repository/schema，或 AI inference 持久化/影响业务排序、Task、Attention、Profile、外发。

- [ ] **T-EVT-002：实现 Record persistence、API 与审计**
  - Goal：事务保存记录、版本和审计，并提供查询汇总。
  - Inputs：T-EVT-001、FR-EVT、E-EVT-002/007。
  - File scope：`services/api/src/application/records/**`、`infrastructure/db/records/**`、`adapters/http/records/**`、相关测试。
  - Depends on：T-EVT-001、T-FOUND-006/007。
  - Expected output：create/correct/list/summary endpoints。
  - Validation：`verify integration/contract --filter E-EVT`。
  - Rollback/recovery：纠正使用新版本/补偿，不物理覆盖证据。
  - Stop condition：幂等或 audit 测试失败。

- [ ] **T-EVT-003：实现 Task/FollowUp 生命周期与 Today projection**
  - Goal：从事件或人工输入创建任务并可靠聚合 Today。
  - Inputs：FR-TSK-001—005、E-EVT-004。
  - File scope：`services/api/src/domain/tasks/**`、`application/tasks/**`、`tests/tasks/**`。
  - Depends on：T-EVT-002、T-FOUND-008。
  - Expected output：状态机、source ref、projection/rebuild。
  - Validation：`verify unit/integration --filter E-EVT-004`；projection rebuild 对比。
  - Rollback/recovery：投影可重建；任务更正保留事件。
  - Stop condition：黑箱“风险学生”进入 Today。

- [ ] **T-EVT-004：实现手机快速记录与 Today UI**
  - Goal：完成移动端短路径及断网草案状态。
  - Inputs：UX spec、FR-EVT/TSK、E-UX-001/E-WEB-002/003。
  - File scope：`apps/web/src/features/today/**`、`features/records/**`、PWA draft adapter、E2E。
  - Depends on：T-EVT-002/003。
  - Expected output：快速选择、编辑转写、提交/待同步/冲突反馈。
  - Validation：`verify e2e --filter E-UX-001,E-WEB-002,E-WEB-003`；目标手机人工测试。
  - Rollback/recovery：关闭离线草稿 flag；未提交草稿可导出/清除。
  - Stop condition：断网可能重复写或敏感草稿长期明文保存。

- [ ] **T-EVT-005：完成事件闭环业务验收**
  - Goal：对比现状和实现，决定是否进入后续模块。
  - Inputs：ACC-001/002、T-DISC-001、E-UX-001/002。
  - File scope：`evals/class-os-v1/results/**`、`docs/07-实施与测试/主实施路线图.md`。
  - Depends on：T-EVT-004、T-EXP-001。
  - Expected output：时间/步骤/错误/信任证据、最小退出导出往返证据与 go/change/stop 决定。
  - Validation：业务负责人复核原始测量和结论；从导出包在干净环境恢复学生、事件与任务的引用完整性。
  - Rollback/recovery：不通过则关闭 release flag，保留数据导出。
  - Stop condition：未达到价值门或隐私成本增加。

## A. Agent capability slice

- [ ] **T-AGT-001：定义 Tool schema 单一来源与生成链**
  - Goal：内部 Function Tool、REST 类型和 MCP schema 不漂移。
  - Inputs：FR-AGT-001—003、API contract、E-MIG-005。
  - File scope：`packages/contracts/tools/**`、`tools/schema-generation/**`、快照测试。
  - Depends on：T-FOUND-004/007。
  - Expected output：versioned catalog、metadata、生成器和 compatibility check。
  - Validation：`verify contract --filter E-MIG-005`。
  - Rollback/recovery：保留旧 version；生成失败不覆盖已发布 schema。
  - Stop condition：tool description/schema 无法评审或版本化。

- [ ] **T-AGT-002：实现 Tool Gateway 与 context policy**
  - Goal：统一授权、字段最小化、风险和结果 envelope。
  - Inputs：FR-AGT-001—005/010、E-AGT-001—003、E-PRV-001/002。
  - File scope：`services/api/src/application/tool_gateway/**`、`domain/context_policy/**`、测试。
  - Depends on：T-AGT-001、T-FOUND-005/007。
  - Expected output：query/draft/command adapters、policy result、presentation allowlist。
  - Validation：`verify integration/security --filter E-AGT-001..003,E-PRV-001..002`。
  - Rollback/recovery：全局 kill switch 禁用 Agent/MCP，UI API 继续可用。
  - Stop condition：Gateway 不能保证服务端权限或字段过滤。

- [ ] **T-AGT-003：实现 runtime/provider adapter 与 fake model**
  - Goal：封装 Agent 会话、tool loop 和模型调用，可在测试中完全替换。
  - Inputs：ADR-003/006、FR-AGT-006/009、E-AGT-013/014。
  - File scope：`services/api/src/adapters/agent/**`、`adapters/model/**`、`tests/agent/**`。
  - Depends on：T-FOUND-001、T-AGT-002。
  - Expected output：fake provider、timeout/cancel、redacted trace、cost metadata。
  - Validation：`verify integration --filter E-AGT-013,E-AGT-014,E-OPS-008`。
  - Rollback/recovery：切换 fake/disabled provider；不影响基本业务 API。
  - Stop condition：运行时要求记录不可控的敏感 payload。

- [ ] **T-AGT-004：实现 Skill metadata 与首批只读/草案 Skill**
  - Goal：提供学生查询、事件记录草案和 Today 查询 SOP。
  - Inputs：FR-AGT-002、R-AGT-001、behavior-guidelines。
  - File scope：`skills/**`、`evals/class-os-v1/cases/agent-and-security.md`。
  - Depends on：T-AGT-003、T-ROS-004、T-EVT-002/003。
  - Expected output：版本化 Skill、权限/数据/禁区/回退声明。
  - Validation：Agent eval 确认只调用允许 Tool、不编造成功、不越权。
  - Rollback/recovery：按 Skill version 回退；不改业务事实。
  - Stop condition：Skill 含业务计算或绕过 Tool 的指令。

- [ ] **T-AGT-005：实现结构化 Agent 面板与 ConfirmAction**
  - Goal：展示范围、调用、草案、diff、批准与失败状态。
  - Inputs：UX spec、FR-AGT-004—006、E-UX-006。
  - File scope：`apps/web/src/features/agent/**`、`components/ConfirmAction/**`、E2E。
  - Depends on：T-AGT-002/003、T-FOUND-007。
  - Expected output：allowlisted components、approval/deny/edit flow。
  - Validation：`verify e2e/a11y --filter E-AGT-003..008,E-UX-006`。
  - Rollback/recovery：禁用 Agent panel；直接 UI 保留。
  - Stop condition：确认只能在自然语言气泡中完成或无法显示 diff。

- [ ] **T-AGT-006：完成 injection 与越权红队 eval**
  - Goal：验证用户输入、导入数据和 Tool 输出均不能提升权限。
  - Inputs：E-AGT-009—012、threat model。
  - File scope：`evals/class-os-v1/adversarial/**`、`tests/security/agent/**`、必要修复范围。
  - Depends on：T-AGT-002—005。
  - Expected output：可重复恶意语料集、失败证据和风险签核。
  - Validation：`verify security --filter E-AGT-009..012`。
  - Rollback/recovery：关闭受影响 Tool/MCP/Agent；保持直接 UI。
  - Stop condition：任一攻击能访问未授权数据或提交无批准写入。

## I. Import and grades

- [ ] **T-IMP-001：实现隔离文件接收与安全检查**
  - Goal：安全接收 Excel/CSV，限制资源并保持正式数据不变。
  - Inputs：FR-IMP-001、NFR-SEC-003、E-IMP-002/007/008。
  - File scope：`services/api/src/infrastructure/imports/quarantine/**`、`worker/file_scan/**`、相关测试。
  - Depends on：T-FOUND-008、T-DISC-004。
  - Expected output：size/type/hash/scan、短期 object、清理任务。
  - Validation：`verify security/integration --filter E-IMP-002,E-IMP-007,E-IMP-008`。
  - Rollback/recovery：禁用上传；隔离对象按 incident policy 处理。
  - Stop condition：解析器可执行宏/外链或突破资源上限。

- [ ] **T-IMP-002：实现 canonical parser 与 Excel/CSV adapters**
  - Goal：保留 sheet/row/cell/raw value 并安全规范化。
  - Inputs：FR-IMP-002、module-boundaries、确认输入样例。
  - File scope：`services/api/src/adapters/imports/**`、`domain/interchange/rows/**`、测试 fixture。
  - Depends on：T-IMP-001、T-DISC-002（生产）；无样例时仅 synthetic prototype。
  - Expected output：adapter contract、错误码、映射候选。
  - Validation：`verify unit/contract --filter E-IMP-001..008`。
  - Rollback/recovery：按 adapter version 回退；原文件仍隔离。
  - Stop condition：真实样例未确认却准备标记 production-ready。

- [ ] **T-IMP-003：实现 mapping、匹配和预览服务**
  - Goal：产生逐行问题和新增/修改/冲突 diff。
  - Inputs：FR-IMP-002/003/005、T-ROS-003、E-IMP-003—006。
  - File scope：`services/api/src/domain/interchange/**`、`application/imports/preview/**`、测试。
  - Depends on：T-IMP-002、T-ROS-003。
  - Expected output：mapping version、normalized rows、preview snapshot。
  - Validation：`verify unit/integration --filter E-IMP-003..006`。
  - Rollback/recovery：预览可重建；过期/错误 mapping 不写正式数据。
  - Stop condition：匹配结果不能追到源行或自动合并同名学生。

- [ ] **T-IMP-004：实现 Import Workbench UI**
  - Goal：完成上传—映射—错误定位—预览—确认体验。
  - Inputs：UX spec、FR-IMP-001—005、E-UX-003/E-A11Y-001。
  - File scope：`apps/web/src/features/imports/**`、E2E/a11y tests。
  - Depends on：T-IMP-003。
  - Expected output：可恢复批次、键盘错误导航、状态与取消。
  - Validation：`verify e2e/a11y --filter E-UX-003,E-A11Y-001`。
  - Rollback/recovery：隐藏 production commit；保留 download issues。
  - Stop condition：用户无法区分预览和已提交。

- [ ] **T-IMP-005：实现导入批准、事务提交和报告**
  - Goal：原子/显式部分提交，支持幂等和审计。
  - Inputs：FR-IMP-004/006、E-IMP-009/010、确认样例。
  - File scope：`services/api/src/application/imports/commit/**`、DB/outbox、`apps/web` 确认卡、测试。
  - Depends on：T-IMP-004、T-DISC-002/003、T-FOUND-007。
  - Expected output：proposal、approval、commit receipt、排除清单和 audit。
  - Validation：`verify integration/e2e --filter E-IMP-009,E-IMP-010,E-CMD`。
  - Rollback/recovery：批次级补偿或版本回退；不覆盖来源证据。
  - Stop condition：样例/口径未确认或部分成功语义不明确。

- [ ] **T-GRD-001：实现 Exam/Subject/Score 领域模型**
  - Goal：明确 score state 和版本化考试口径。
  - Inputs：FR-GRD-001/002/007、T-DISC-003、E-GRD-002/003。
  - File scope：`services/api/src/domain/grades/model/**`、单元测试。
  - Depends on：T-DISC-003、T-ROS-001。
  - Expected output：领域实体、不变量、correction state。
  - Validation：`verify unit --filter E-GRD-002,E-GRD-003,E-GRD-008`。
  - Rollback/recovery：规则版本不可覆盖；迁移保留旧值。
  - Stop condition：缺考/免考/未录入仍用 0 表示。

- [ ] **T-GRD-002：实现确定性成绩计算库**
  - Goal：计算总分、均分、名次、差值、偏科和证据。
  - Inputs：FR-GRD-003—005、confirmed GradeRuleVersion、golden。
  - File scope：`services/api/src/domain/grades/calculations/**`、`tests/unit/grades/**`、golden tests。
  - Depends on：T-GRD-001、T-DISC-003。
  - Expected output：纯函数、property/metamorphic tests、rule version 输出。
  - Validation：`verify unit --filter E-GRD-001..006`。
  - Rollback/recovery：保留旧 calculator version；重新生成派生快照。
  - Stop condition：golden/口径未确认或计算依赖模型。

- [ ] **T-GRD-003：实现成绩持久化、重算 worker 和 API**
  - Goal：从 import batch 建立成绩事实并可靠生成 metric snapshot。
  - Inputs：T-GRD-001/002、FR-GRD-006/007、E-GRD-006/008。
  - File scope：`services/api/src/application/grades/**`、DB/worker/API/contracts、集成测试。
  - Depends on：T-IMP-005、T-FOUND-008、T-GRD-002。
  - Expected output：queries、correction proposal、recalculation outbox。
  - Validation：`verify integration/contract --filter E-GRD,E-OPS-004`。
  - Rollback/recovery：重算可重放；更正使用补偿记录。
  - Stop condition：派生值无 rule/source version。

- [ ] **T-GRD-004：实现成绩分析 UI**
  - Goal：提供学生趋势、班级分布、证据下钻和数据不足状态。
  - Inputs：FR-GRD-004—006、UX spec、E-UX-004。
  - File scope：`apps/web/src/features/grades/**`、E2E/a11y tests。
  - Depends on：T-GRD-003。
  - Expected output：图表/表格、口径说明、筛选和空/错状态。
  - Validation：`verify e2e/a11y --filter E-GRD-004..007,E-UX-004`。
  - Rollback/recovery：feature flag 隐藏分析，不影响成绩事实。
  - Stop condition：图表无法显示计算证据或使用贬损标签。

- [ ] **T-GRD-005：实现成绩解释 Skill/Tool**
  - Goal：Agent 基于确定性结果回答，不自行计算或推断原因。
  - Inputs：FR-AGT-006、FR-GRD-004—006、E-GRD-007/E-AGT-014。
  - File scope：`skills/grade-analysis/**`、Tool catalog/adapter、Agent eval。
  - Depends on：T-GRD-003、T-AGT-004。
  - Expected output：只读 Tool、证据引用和数据不足回退。
  - Validation：`verify agent --filter E-GRD-005,E-GRD-007,E-AGT-014`。
  - Rollback/recovery：禁用 Skill/Tool；结构化分析保留。
  - Stop condition：模型重新计算数字或输出无依据标签。

## S. Seating and organization

- [ ] **T-SEA-001：实现 ClassroomLayout 与 Assignment 模型**
  - Goal：版本化布局、槽位和有效分配不变量。
  - Inputs：FR-SEA-001、E-SEA-001/002。
  - File scope：`services/api/src/domain/seating/model/**`、unit tests。
  - Depends on：T-ROS-001、T-FOUND-007。
  - Expected output：layout/slot/assignment、唯一性约束。
  - Validation：`verify unit --filter E-SEA-001,E-SEA-002`。
  - Rollback/recovery：布局版本保留；不原地破坏已引用 slot。
  - Stop condition：历史 assignment 无法绑定布局版本。

- [ ] **T-SEA-002：定义约束 DSL 与独立 validator**
  - Goal：区分 hard/soft，给出稳定冲突和评分结构。
  - Inputs：FR-SEA-002/003、R-SEA-001/002、E-SEA-003/004/006。
  - File scope：`services/api/src/domain/seating/constraints/**`、tests。
  - Depends on：T-DISC-001、T-SEA-001。
  - Expected output：versioned constraint types、validator、conflict set。
  - Validation：`verify unit --filter E-SEA-003,E-SEA-004,E-SEA-006`。
  - Rollback/recovery：新增 constraint 用新 version；保留旧方案可解释性。
  - Stop condition：软权重被假设成业务真值或 hard 可被评分抵消。

- [ ] **T-SEA-003：实现 deterministic solver adapter**
  - Goal：生成多个可重复候选并在超时时安全失败。
  - Inputs：T-SEA-002、E-SEA-005/E-PERF-005、resource-review。
  - File scope：`services/api/src/domain/seating/solver/**`、performance/property tests。
  - Depends on：T-SEA-002、许可审批。
  - Expected output：solver interface、seed/version、候选评分。
  - Validation：`verify unit/performance --filter E-SEA-005,E-PERF-005`，所有候选再过独立 validator。
  - Rollback/recovery：切换上一 solver version；不影响手动排座。
  - Stop condition：外部算法许可不清或 solver 绕过 validator。

- [ ] **T-SEA-004：实现 seat plan/query/apply/undo 服务**
  - Goal：打通 proposal、批准、版本校验、历史和撤销。
  - Inputs：FR-SEA-003/004、E-SEA-007—010。
  - File scope：`services/api/src/application/seating/**`、DB/API/Tool contracts、tests。
  - Depends on：T-SEA-003、T-FOUND-007。
  - Expected output：seat.plan/validate/apply/undo 与 audit。
  - Validation：`verify integration/contract --filter E-SEA-007..010`。
  - Rollback/recovery：全局禁用 apply；保留 plan/query/manual export。
  - Stop condition：旧批准可提交或 hard violation 可落库。

- [ ] **T-SEA-005：实现 SeatMap UI 和排座 Agent Skill**
  - Goal：可视约束、候选、diff、键盘调整和受控批准。
  - Inputs：UX spec、FR-SEA、E-UX-005/E-A11Y-004。
  - File scope：`apps/web/src/features/seating/**`、`skills/seating/**`、E2E/agent/a11y tests。
  - Depends on：T-SEA-004、T-AGT-005。
  - Expected output：SeatMap、ConstraintReport、ConfirmAction、Skill。
  - Validation：`verify e2e/agent/a11y --filter E-UX-005,E-A11Y-004,E-SEA`。
  - Rollback/recovery：禁用 Agent/apply，保留手动草案。
  - Stop condition：冲突只用颜色表示或确认卡无新旧布局。

- [ ] **T-ORG-001：实现职务、分组和值日模型与 UI**
  - Goal：支持多职务任期、互斥规则、分组和值日历史。
  - Inputs：FR-GRP-001、FR-POS-001/002、E-ORG-001—003。
  - File scope：`services/api/src/domain/organization/**`、API/contracts、`apps/web/src/features/organization/**`、tests。
  - Depends on：T-ROS-002、T-FOUND-007。
  - Expected output：CRUD、assignment proposal、history、候选不自动应用。
  - Validation：`verify unit/integration/e2e --filter E-ORG`。
  - Rollback/recovery：assignment 版本/补偿；feature flag。
  - Stop condition：推荐根据成绩/行为自动决定职务。

## DOR. Dormitory optional slice

- [ ] **T-DOR-001：确认宿舍价值与学校边界**
  - Goal：解除 A-008，决定 implement/defer 和是否存在外部正式系统。
  - Inputs：T-DISC-001、A-008、CON-003。
  - File scope：`handoff/normalized/**`、requirements/plan/trace。
  - Depends on：T-EVT-005。
  - Expected output：业务频率、规则、样例和明确决定。
  - Validation：目标用户/业务负责人批准。
  - Rollback/recovery：若 deferred，保留规格不创建代码。
  - Stop condition：职责/授权不清。

- [ ] **T-DOR-002：实现 DormLayout/Bed/Assignment 领域模型**
  - Goal：独立于 seating 实现床位不变量和历史。
  - Inputs：FR-DOR-001/002、E-DOR-001—003/006。
  - File scope：`services/api/src/domain/dormitory/**`、unit tests。
  - Depends on：T-DOR-001=implement、T-ROS-001。
  - Expected output：layout、assignment、rule validator。
  - Validation：`verify unit --filter E-DOR-001..003,E-DOR-006`。
  - Rollback/recovery：版本化布局；不复用 seating 规则实现。
  - Stop condition：试图用一个巨型 Location service 混合两域规则。

- [ ] **T-DOR-003：实现分配/移动/交换 proposal 与 API**
  - Goal：原子交换、并发控制、审计和历史。
  - Inputs：FR-DOR-002—004、E-DOR-004/005。
  - File scope：`services/api/src/application/dormitory/**`、DB/API/Tool contracts、tests。
  - Depends on：T-DOR-002、T-FOUND-007。
  - Expected output：preview/apply/undo or compensate。
  - Validation：`verify integration --filter E-DOR-004,E-DOR-005,E-CMD`。
  - Rollback/recovery：禁用写入；使用补偿 assignment。
  - Stop condition：交换出现可观察的中间双占状态。

- [ ] **T-DOR-004：实现 DormMap UI 与验收**
  - Goal：展示空床、占用、差异、冲突、生效时间和历史。
  - Inputs：FR-DOR-001—004、UX spec、AC-06。
  - File scope：`apps/web/src/features/dormitory/**`、E2E/a11y tests。
  - Depends on：T-DOR-003。
  - Expected output：DormMap、ConfirmAction、history。
  - Validation：`verify e2e/a11y --filter E-DOR`；目标用户验收。
  - Rollback/recovery：feature flag；导出已有数据。
  - Stop condition：用户无法区分 ClassMatter 记录与学校正式宿管状态。

## P. Reports, communication and export

- [ ] **T-REP-001：实现可追溯报告事实快照**
  - Goal：确定性汇总并为每个事实块保存 entity/version 引用。
  - Inputs：FR-REP-001/002、E-REP-001—003。
  - File scope：`services/api/src/domain/reporting/**`、`application/reporting/sources/**`、tests。
  - Depends on：T-EVT-003；成绩报告另依赖 T-GRD-003。
  - Expected output：source snapshot、stale detection、empty result。
  - Validation：`verify unit/integration --filter E-REP-001..003`。
  - Rollback/recovery：快照不可覆盖；派生草稿可重新生成。
  - Stop condition：事实文本无 source refs。

- [ ] **T-REP-002：实现报告/沟通生成 Skill 与安全扫描**
  - Goal：组织中文草稿，区分事实/建议并拦截标签和敏感字段。
  - Inputs：FR-REP/COM、E-REP-005/006/008、A-009。
  - File scope：`skills/reporting/**`、Tool adapter、content policy、agent eval。
  - Depends on：T-REP-001、T-AGT-004、A-009 确认首版边界。
  - Expected output：draft generator、policy findings、无发送 Tool。
  - Validation：`verify agent/security --filter E-REP-005,E-REP-006,E-REP-008`。
  - Rollback/recovery：禁用生成；确定性事实汇总保留。
  - Stop condition：生成等同发送或诊断/贬损内容可直接 finalize。

- [ ] **T-REP-003：实现草稿编辑、finalize 和状态 UI**
  - Goal：让教师核对来源、编辑并生成正式版本。
  - Inputs：FR-REP-003、FR-COM-003、E-REP-004/007、E-UX-007。
  - File scope：`apps/web/src/features/reports/**`、reporting application/API、E2E。
  - Depends on：T-REP-001/002、确认报告 golden（production）。
  - Expected output：draft/review/final、source drawer、copied/confirmed_sent 状态。
  - Validation：`verify e2e --filter E-REP-004,E-REP-007,E-UX-007`。
  - Rollback/recovery：正式版本不可覆盖；新 revision 修正。
  - Stop condition：未确认输出样例却冻结正式格式。

- [ ] **T-EXP-001：实现版本化核心 JSON/CSV 导出模型**
  - Goal：提供可读、可校验、可重新导入的核心数据包。
  - Inputs：FR-EXP-001/003、E-EXP-001—004。
  - File scope：`services/api/src/domain/interchange/export/**`、renderers、contracts/tests。
  - Depends on：T-FOUND-008、T-ROS-002、T-EVT-002。
  - Expected output：manifest、schema version、checksum、field projection、audit。
  - Validation：`verify contract/integration --filter E-EXP-001..004`。
  - Rollback/recovery：renderer version 回退；撤销未下载短期链接。
  - Stop condition：默认导出含 D3/D4 或无法说明 scope。

- [ ] **T-EXP-002：实现正式 Excel/PDF/打印输出**
  - Goal：按用户确认样例渲染座位、宿舍、成绩和报告。
  - Inputs：FR-EXP-002、output-contract、confirmed golden、E-EXP-006。
  - File scope：`services/api/src/adapters/export/**`、golden fixtures、visual tests。
  - Depends on：T-DISC-002/003、T-EXP-001、对应领域模块。
  - Expected output：版本化模板、视觉/结构 golden tests。
  - Validation：`verify golden/visual --filter E-EXP-006`；业务签核。
  - Rollback/recovery：保留旧 renderer/version；不覆盖旧导出。
  - Stop condition：golden 未确认、字体/模板许可不明或布局无法稳定复现。

- [ ] **T-MCP-001：实现精选只读 MCP adapter**
  - Goal：对可信客户端暴露最小 class/student/task/grade query。
  - Inputs：FR-AGT-007/008、ADR-002、E-AUTH-004/E-AGT-009—012。
  - File scope：`services/api/src/adapters/mcp/**`、contracts/security tests。
  - Depends on：T-AGT-002、T-AGT-006、T-DISC-004。
  - Expected output：独立 client scope、allowlist、rate limit、audit、revoke。
  - Validation：`verify contract/security --filter E-AUTH-004,E-AGT-009..012`。
  - Rollback/recovery：关闭 MCP listener/撤销 client；内部 Function Tool 保留。
  - Stop condition：需要公网暴露全部 Tool 或身份/撤销机制不清。

## H. Hardening, release and operations

- [ ] **T-HARD-001：完成跨浏览器、移动和可访问性硬化**
  - Goal：关键任务通过支持矩阵和 WCAG 适用检查。
  - Inputs：E-WEB、E-A11Y、manual UX catalog。
  - File scope：`apps/web/**`、E2E/a11y config/results、支持矩阵文档。
  - Depends on：目标 release slice UI 完成。
  - Expected output：自动/人工报告和修复。
  - Validation：`verify e2e/a11y --filter E-WEB,E-A11Y`。
  - Rollback/recovery：回退造成回归的 UI 变更；保留测试证据。
  - Stop condition：关键动作在目标手机/键盘/读屏下不可完成。

- [ ] **T-HARD-002：完成性能与容量验证**
  - Goal：在候选目标规模验证 API、导入、Agent 和 solver。
  - Inputs：NFR-PERF、E-PERF、实际规模修订。
  - File scope：`tests/performance/**`、profiling results、容量计划。
  - Depends on：目标 release slice 集成。
  - Expected output：可重复负载、p50/p95/p99、资源与瓶颈。
  - Validation：`verify performance`。
  - Rollback/recovery：关闭高成本功能/降低批次；回退优化前版本。
  - Stop condition：测试数据规模无业务依据或需要暴露真实数据。

- [ ] **T-HARD-003：完成安全与隐私评审**
  - Goal：关闭 threat register 和发布门中的 High/Critical。
  - Inputs：security spec、E-SEC/E-PRV/E-AUTH/E-AGT adversarial。
  - File scope：`tests/security/**`、威胁模型、风险登记、必要修复范围。
  - Depends on：release candidate。
  - Expected output：扫描、手工测试、数据流和批准证据。
  - Validation：`verify security` + 独立评审。
  - Rollback/recovery：禁用/回退风险功能，轮换测试凭据。
  - Stop condition：任何未处置 Critical/High 或真实数据准入不完整。

- [ ] **T-HARD-004：完成迁移、备份恢复与故障注入**
  - Goal：证明升级、中断、备份和模型降级可恢复。
  - Inputs：E-MIG、E-OPS、deployment/backup runbooks。
  - File scope：`migrations/**`、`infra/backup/**`、`tests/recovery/**`、证据文档。
  - Depends on：release candidate、staging ready。
  - Expected output：dry-run、恢复校验、RPO/RTO 测量、故障报告。
  - Validation：`verify migration/recovery --filter E-MIG,E-OPS`。
  - Rollback/recovery：演练仅 staging/隔离环境；不破坏生产。
  - Stop condition：备份无法恢复或审计/附件不一致。

- [ ] **T-HARD-005：建立可观测性、告警和 runbook**
  - Goal：让关键错误可发现、可关联、无敏感泄露。
  - Inputs：NFR-OBS、E-OBS、部署设计。
  - File scope：`services/**/telemetry/**`、`infra/observability/**`、`docs/08-运维与治理/**`。
  - Depends on：T-FOUND-006/008、release candidate。
  - Expected output：dashboard、alerts、owners、runbooks、PII scan。
  - Validation：`verify integration/security --filter E-OBS,E-PRV-003`；模拟告警。
  - Rollback/recovery：回退 telemetry config；审计链不可关闭。
  - Stop condition：告警/trace 需要学生身份作维度。

- [ ] **T-REL-001：执行 staging 发布候选验收**
  - Goal：运行目标 slice 全套自动和人工门。
  - Inputs：acceptance、quality gates、release checklist。
  - File scope：`evals/class-os-v1/results/**`、release evidence/docs。
  - Depends on：T-HARD-001—005。
  - Expected output：版本化验收包、已知问题和 go/no-go 建议。
  - Validation：`verify all`；业务/架构/安全/运维签核。
  - Rollback/recovery：不晋级 pilot；修复后产生新候选版本。
  - Stop condition：P0/P1 失败或跳过无批准。

- [ ] **T-REL-002：执行自愿参与的目标教师试点与灰度评估**
  - Goal：在最小真实范围验证价值、可靠性和支持流程。
  - Inputs：T-REL-001、真实数据准入、pilot plan。
  - File scope：部署配置、`evals/**/results/**`、发布/反馈文档；禁止复制生产数据到仓库。
  - Depends on：T-DISC-004、T-REL-001、用户批准。
  - Expected output：试点指标、事件记录、用户反馈、继续/改变/停止决定。
  - Validation：核心指标、审计、备份、回滚和支持复盘。
  - Rollback/recovery：关闭 feature flag/回退镜像；提供最终导出；按批准恢复数据。
  - Stop condition：数据泄露、重复写、不可恢复损坏、错误外发或用户要求停止。

- [ ] **T-REL-003：完成稳定发布与交接**
  - Goal：形成可重复发布、运维责任和版本生命周期。
  - Inputs：试点通过、operations docs、SLO/RPO/RTO 批准。
  - File scope：`infra/release/**`、`docs/08-运维与治理/**`、release notes。
  - Depends on：T-REL-002 go。
  - Expected output：production release、SBOM、迁移/回滚、support ownership、培训材料。
  - Validation：发布后 smoke、audit、backup、monitor checks；负责人签核。
  - Rollback/recovery：按已演练 runbook 回滚；必要时冻结写入并导出。
  - Stop condition：责任人、告警、备份或回滚任一缺失。

## O. Open-world semantics and evolution（post-R1 / definition & discovery only）

本组不属于 Release 1 atomic DAG，不授权生产实现。每项只在对应假设、数据处理和新 release scope 获批后执行。

- [ ] **T-EVO-001：冻结 Canonical Ontology 与时态关系 ADR**
  - Goal：以最小 typed core 定义 Person/Organization/Role/Responsibility/Authority、Relationship/Assignment、epistemic kinds 和 Temporal，不产生万能根表。
  - Inputs：LR-SEM-001、LR-SEM-002、LR-EPI-001、LR-TIME-001、ADR-008、ADR-010、E-EVO-001、E-EVO-002、E-EVO-003、E-EVO-009。
  - File scope：`docs/06-系统设计/**`、`docs/specs/class-os-v1/architecture*.md`、schema design fixtures；不改 R1 migrations。
  - Depends on：用户审阅；A-021 初步控制权访谈。
  - Expected output：accepted ADR、typed aggregate/value-object proposal、反例、兼容/迁移说明。
  - Validation：`verify docs --filter E-EVO-001,E-EVO-002,E-EVO-003,E-EVO-009`。
  - Rollback/recovery：撤回未批准 ADR；不产生数据库变更。
  - Stop condition：设计依赖万能 Person/JSON/Fact，或 Role 自动授予 Authority。

- [ ] **T-EVO-002：定义 Capture、Resolution 与 Context Authority 契约**
  - Goal：冻结 ChannelEnvelope→CaptureDraft→ResolutionCandidate→typed Command→BCG，以及 Memory/Knowledge/Fact 权威矩阵。
  - Inputs：LR-CAP-001、LR-RES-001、LR-CTX-001、LR-KNW-001、E-EVO-004、E-EVO-005、E-EVO-006、E-EVO-007、处理器和生命周期模板。
  - File scope：contract schemas、`docs/06-系统设计/**`、合成 fixtures；不得注册生产 Channel。
  - Depends on：T-EVO-001；A-019、A-020、A-022、A-026 仍可为 open，但必须成为 stop gate。
  - Expected output：版本化 contract、去重/删除传播/错误绑定撤回协议、最小 synthetic fixtures。
  - Validation：`verify contract/security --filter E-EVO-004,E-EVO-005,E-EVO-006,E-EVO-007`。
  - Rollback/recovery：删除未发布 contract version；保持 R1 adapter registry 不变。
  - Stop condition：任何 extractor/Memory/Knowledge 可直写事实或持有 approval/BCG credential。

- [ ] **T-EVO-003：建立 Intent Catalog 和四个 wedge 任务脚本**
  - Goal：为事件、沟通草稿、图片/手写 Capture、固定表单复用定义等价任务、歧义和回退。
  - Inputs：LR-INT-001、E-EVO-008、A-006、A-018、五日任务日志。
  - File scope：Intent schema/catalog、discovery scripts、脱敏/合成 fixtures。
  - Depends on：T-DISC-001；没有真实数据时只使用合成原型。
  - Expected output：Intent entries、ambiguity cases、direct-UI fallback、比较协议。
  - Validation：`verify docs/agent --filter E-EVO-008` + 用户任务脚本评审。
  - Rollback/recovery：未验证 intent 保持 disabled/discovery。
  - Stop condition：Intent catalog 被当成运行时 Tool allowlist，或缺 purpose/permission/risk。

- [ ] **T-EVO-004：定义 Controlled Extension policy 与 Promotion 演练**
  - Goal：证明受控 logical schema 可导出、迁移、回滚，并阻止任意 DDL/JSON/关系。
  - Inputs：LR-EXT-001、LR-KRN-001、ADR-008、E-EVO-011、E-EVO-012、E-EVO-021。
  - File scope：schema policy、synthetic proposal fixtures、migration design docs；不接触生产 DB。
  - Depends on：T-EVO-001；A-024 有至少三类重复需求证据后才允许实现 spike。
  - Expected output：allowlist schema、proposal/review/promotion/retirement contract、失败案例。
  - Validation：`verify contract/security/migration --filter E-EVO-011,E-EVO-012,E-EVO-021`。
  - Rollback/recovery：只在临时隔离数据库演练；删除临时环境，不修改 R1 schema。
  - Stop condition：无法导出/回滚，或需要 Agent/运行时 DDL、万能 EAV/Fact。

- [ ] **T-EVO-005：完成多角色最小披露与控制权研究**
  - Goal：验证班主任、任课教师、年级主任、德育、心理、校医、宿管的责任/权限/交接，而不建立 ERP。
  - Inputs：LR-SEM-002、LR-COL-001、E-EVO-002、E-EVO-013、E-EVO-016、E-EVO-017、E-EVO-018、A-021、A-025、数据治理模板。
  - File scope：用户研究、权限卡片、handoff synthetic scenarios、ADR 草案。
  - Depends on：学校/角色参与者与隐私负责人可用。
  - Expected output：控制权选项、purpose/field matrix、professional compartment、handoff receipt 模型。
  - Validation：独立隐私/安全评审 + `verify docs --filter E-EVO-002,E-EVO-013,E-EVO-016,E-EVO-017,E-EVO-018`。
  - Rollback/recovery：研究材料脱敏并按批准期限删除；不启用账号/权限。
  - Stop condition：个人 Memory 被默认用于学校监督，或职位名称自动带来全量访问。

- [ ] **T-EVO-006：定义 Temporal/Commitment/Case/Workflow 最小切片**
  - Goal：用真实遗漏案例判断简单 Task 是否不足，并冻结时间精度、Case 和 Trigger 边界。
  - Inputs：LR-TIME-001、LR-WRK-001、E-EVO-009、E-EVO-010、A-023。
  - File scope：domain spec、state/temporal fixtures、合成 workflow prototype。
  - Depends on：五日任务日志中存在可复现承诺/转介/跟进缺口。
  - Expected output：最小状态机、时间反例、Trigger draft-only contract、no-go 结论也可接受。
  - Validation：`verify unit/contract --filter E-EVO-009,E-EVO-010`。
  - Rollback/recovery：不迁移 R1 Task/Event；原型可丢弃。
  - Stop condition：Case 退化为万能事件袋，或 Trigger 可绕过 BCG 自动写。

- [ ] **T-EVO-007：设计派生依赖失效与纠错传播**
  - Goal：事实/知识/身份/schema version 纠正或回滚后，使 AIInference、Memory、Profile、RAG、Artifact、Attention、Trigger、cache/backup 和 schema consumers 可定位并失效/重建。
  - Inputs：LR-EPI-001、LR-DER-001、LR-RES-001、LR-KNW-001、LR-EXT-001、E-EVO-005、E-EVO-007、E-EVO-011、E-EVO-014、E-EVO-019、E-EVO-020、E-EVO-021。
  - File scope：dependency metadata contract、synthetic propagation tests、lifecycle docs。
  - Depends on：T-EVO-001、T-EVO-002、T-EVO-004。
  - Expected output：可枚举 versioned dependency graph、consumer restrictions、stale/restricted/disabled 状态、重建/删除 receipt、故障恢复与 UI 解释/申诉。
  - Validation：`verify integration/recovery --filter E-EVO-005,E-EVO-007,E-EVO-011,E-EVO-014,E-EVO-019,E-EVO-020,E-EVO-021`。
  - Rollback/recovery：隔离数据集演练；失败时禁用派生读取。
  - Stop condition：主事实更正后仍无法枚举或阻止旧派生物使用。

- [ ] **T-EVO-008：运行四个 wedge 的 Net Burden 发现门**
  - Goal：用相同基线比较事件、沟通草稿、图片/手写 Capture、固定表单复用，只选择一个后续 release 候选。
  - Inputs：LR-VALUE-001、ACC-001、ACC-017、E-EVO-015、A-018、A-020、A-022、A-026。
  - File scope：`docs/04-计划与验证/**`、脱敏研究结果、prototype metrics；不修改 R1 gate。
  - Depends on：T-EVO-003、至少 5 日任务日志和目标教师原型测试。
  - Expected output：预注册的时间净值、错误非劣、wrong-person、backlog 上限/p95 age/清偿时间、onboarding/持续维护、隐私/安全/运维 hard guardrail，以及 go/change/stop。
  - Validation：研究协议在试验前冻结样本、周期、任务脚本、缺失值、阈值和决策人；保存匿名原始计时证据与可重算多维判定表，不生成可任意调权的单一总分。
  - Rollback/recovery：关闭/删除无净收益 prototype；清理研究数据。
  - Stop condition：只报告 AI 演示满意度，或忽略核对、纠错、通知和持续维护成本。
