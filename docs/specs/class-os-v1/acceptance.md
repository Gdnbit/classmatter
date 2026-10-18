# Acceptance: ClassMatter v1

> 文档状态（2026-10-08）：现行规格/规划/规则；设计存在；实现/批准须另凭目标版本证据。项目完成度见 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md)；本标识不提升批准、测试或任务状态。

状态：`review`。本文件定义如何证明需求完成；具体 release slice 只验收其纳入的 P0/P1 条目，但安全和数据完整性门不得裁剪。

## 1. System Acceptance Scenarios

### AC-01 首次启用与隔离

Given 两个独立工作空间和不同教师，When 各自创建同名班级与学生，Then 两者在 UI/API/Tool/导出/搜索中均不可互见，越权请求不泄露资源是否存在。\
覆盖：FR-PLT-001—004、NFR-SEC-002；E-AUTH-001—004。

### AC-02 手机事件闭环

Given 当前班级和学生已存在，When 教师在目标手机记录一次迟到并创建跟进，Then 可在约 3 次核心交互内完成，学生时间线和 Today 同步出现，断网/重试不重复。\
覆盖：FR-EVT-001—003、FR-TSK-001—004、NFR-REL-001/002、NFR-UX-001。

### AC-03 名单/成绩导入

Given 用户确认的脱敏样例包含同名、重复、缺考和非法值，When 执行导入，Then 映射、匹配和错误逐行可见；未批准前正式数据无变化；提交后批次、来源和重算可追溯。\
覆盖：FR-IMP-001—006、FR-GRD-001—007。\
当前状态：blocked-by-sample。

### AC-04 成绩分析可信性

Given 至少两次口径已配置的考试，When 查看进退步和偏科，Then 结果由确定性函数生成并显示比较范围；样本不足时明确拒绝趋势结论；Agent 不能编造原因。\
覆盖：FR-GRD-003—006；E-GRD-001—008。

### AC-05 约束排座

Given 教室布局、学生和硬/软约束，When 生成方案，Then 硬约束零违反，评分分解可解释；不可行时不允许应用；可行方案显示差异并在批准后提交和审计。\
覆盖：FR-SEA-001—004；E-SEA-001—010。

### AC-06 宿舍交换

Given 两名已有床位的学生，When 发起交换，Then 唯一占用校验通过、预览准确、批准绑定当前版本、提交留史；并发变更使旧批准失效。\
覆盖：FR-DOR-001—004；E-DOR-001—006。

### AC-07 报告和沟通草稿

Given 一周结构化记录，When 生成周报或家长沟通，Then 事实有内部引用，推断/建议分区，高敏字段默认排除，输出保持草稿且无自动发送。\
覆盖：FR-REP-001—003、FR-COM-001—003；E-REP-001—008。

### AC-08 Agent 安全写入

Given Agent 提议 W2/X 操作，When 用户批准、拒绝、等待过期、数据被并发修改或恶意工具输出尝试改变权限，Then 只有范围、版本、主体和时效仍匹配的批准能提交；其余安全失败并审计。\
覆盖：FR-AGT-001—010；E-AGT-001—014。

### AC-09 导出与迁移

Given 教师选择班级、学期和字段，When 导出，Then 系统预览敏感字段和范围，生成版本化文件及校验信息；在隔离环境能重新导入核心数据。\
覆盖：FR-EXP-001—004；E-EXP-001—006。\
正式办公格式：blocked-by-sample。

### AC-10 恢复与降级

Given 模型不可用、服务重启、网络超时或主机损坏，When 执行相应演练，Then 非 AI 核心功能可用、Command 不重复、备份可恢复、故障和数据新鲜度对用户清晰。\
覆盖：FR-PLT-005、NFR-REL-001—004；E-OPS-001—008。

### AC-11 认识论与 Context 权威（non-R1 architecture）

Given Session/Memory/Knowledge 与最新领域记录冲突，或模型给出人物推断，When 系统查询、生成或尝试保存，Then Domain Fact 由 owning Domain 与 Query Gateway 决定；Observation/typed Claim/Derived/AIInference 状态、依赖、用途、有效期和限制可见；Memory/Knowledge 不覆盖事实；推断既不自动晋升，也不能侧路改变 Authority、纪律、风险分、Task/Attention 优先级、外发或长期画像。
覆盖：LR-EPI-001、LR-CTX-001、LR-KNW-001、LR-DER-001；E-EVO-003、E-EVO-006、E-EVO-007、E-EVO-019、E-EVO-020。

### AC-12 Capture 与实体解析无旁路（non-R1 architecture）

Given 任一未来微信/图片/文件/音频输入和同名歧义，When adapter/extractor 处理，Then 只请求 registry 中的 typed Command；显示 source/候选/冲突；没有 BCG receipt 时 Envelope、Draft、Resolution、Review、Workflow 和正式业务 store 均不变，所有读取经 Query Gateway。
覆盖：LR-CAP-001、LR-RES-001、LR-WRK-001；E-EVO-004、E-EVO-005、E-EVO-010。

### AC-13 Controlled Extension 可迁移可回滚（non-R1 architecture）

Given Agent 请求新增未覆盖领域或 extension schema 回滚，When 提出、评审或降级 schema，Then 先复用 Ontology/Domain Pack；否则经 typed Command 形成 SchemaProposal，由 Extension Service/BCG 激活 logical schema；不存在 SQL/DDL/万能 JSON Tool；表单、validator、workflow、index、Tool schema、saved query、export 等消费者按版本失效/降级。
覆盖：LR-EXT-001、LR-KRN-001、LR-DER-001；E-EVO-011、E-EVO-012、E-EVO-021。

### AC-14 多角色最小披露（discovery）

Given 任课教师、年级主任、德育、心理老师、校医或宿管参与转介，When 请求读取、导出、RAG 检索或交接，Then Role/Responsibility/Membership 不自动带来 Authority；所有路径由 `identity-access` 的唯一 authorizer 一致裁决，只共享 purpose 所需协调信息，专业正文留在获准 compartment。
覆盖：LR-SEM-002、LR-COL-001；E-EVO-002、E-EVO-013、E-EVO-016、E-EVO-017、E-EVO-018。

### AC-15 Net Burden（discovery）

Given 一个新 Capture/Memory/Review/Reminder 原型，When 与现状执行相同真实任务，Then按试验前冻结的样本、周期、脚本、缺失值、阈值和决策人，分别判定时间净值、错误非劣、Review backlog/清偿时间、onboarding/持续维护；隐私、安全和运维为不可抵消的 hard guardrail。任一强门失败或没有净减负则得到 change/stop，而非扩大功能。
覆盖：LR-VALUE-001；E-EVO-015。

### AC-16 被动责任风险优先（product/release value gate）

Given 通知来源分散、责任主体不清、存在期限与后续催办的真实或合成事项，When 教师使用候选闭环识别、处理、交接或升级，Then 教师能回答“什么必须做、为何、由谁、何时、当前状态、交给了谁、证据在哪里”；系统不静默把责任不清事项派给班主任，不隐藏明确职责，遗漏/逾期不劣于现状，且新增维护成本计入 Net Burden。
覆盖：R-PROD-001、ACC-018；E-VALUE-001；C-075。R1 只强化价值 Gate，不因此增加微信、自动 Capture 或多人协作功能。

## 2. Quantitative Gates

| 指标 | 验证环境 | 通过线 |
|---|---|---:|
| 高价值任务步骤/时间缩减 | 至少 5 位目标用户或自愿参与的目标教师 5 次重复任务 | 中位缩减 ≥30% |
| 手机事件记录 | 至少 2 种目标手机尺寸 | 约 3 次核心交互；成功率 ≥95% |
| 只读性能 | 目标规模，常规网络，中档设备 | p95 ≤2s |
| 写入确认后性能 | 不含外部模型 | p95 ≤3s |
| Agent 首反馈 | 模型服务正常 | p95 ≤2s 有可见反馈 |
| 导入预览 | 10,000 行合成表；真实规模确认后修订 | ≤30s，有进度与取消 |
| 硬约束排座 | 所有 golden + property cases | 0 违反 |
| 幂等重放 | 每个 Command 10 次相同键重放 | 仅 1 次业务变更 |
| 关键确认理解 | 至少 5 位用户 | 100% 能复述对象、范围、后果 |
| 备份恢复 | 隔离环境演练 | 数据/附件/审计校验通过 |
| future wrong-person | 脱敏/合成 Capture 原型 | 正式误写 0；候选错误可发现/纠正 |
| future Review debt | 预注册早期周期 + 月度/学期维护观察 | backlog、p95 age 和清偿时间均不越过预注册上限；可暂停/过期/清空 |
| future 时间净值 | 现状与等价原型；onboarding 与持续维护分列 | 达到预注册的最小有意义改善，且缺失值不按有利方向填充 |
| future Net Burden hard guardrails | 同一预注册协议 | wrong-person/错误非劣；隐私、安全、可解释性、运维任一失败即 stop，不与时间加权抵消 |

## 3. Release Blocking Conditions

- 任意 P0/P1 缺陷；
- 未授权访问、敏感信息进入日志/模型/导出；
- 写入无幂等、无审计或旧批准仍能提交；
- 迁移不可验证、备份未恢复演练、回滚路径缺失；
- 使用未确认样例实现生产导入/输出；
- 用户不能正确理解高风险确认；
- 运行时/模型不可用导致非 AI 基本功能不可用。
- 对启用长期能力的 future release：出现第四写入口、Role→Authority 隐式扩大、AI Inference→Fact 自动晋升、万能 JSON/DDL、不可定位派生物或未通过 Net Burden 门。

## 4. Manual Acceptance Evidence

每次候选发布保存：测试版本、环境、数据集版本、参与者、任务脚本、录屏/截图位置（脱敏）、结果、问题、批准人和日期。不得只写“验收通过”。

## 5. 仓库可移植性回归（E-DEV-001 候选）

从目标提交的干净 Git 检出必须包含所有前端源码和所需配置；在不复制本机忽略目录、运行时数据库或密钥的情况下，按锁文件安装依赖并完成 TypeScript 检查及生产构建。本机含未跟踪/被忽略源码时通过的构建不算证据。正式 E-DEV-001 仍须在受支持的另一台干净环境验证唯一 `verify` 入口，此回归不能自行升级机器成熟度。
