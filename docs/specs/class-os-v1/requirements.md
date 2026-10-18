# Requirements: ClassMatter v1

> 文档状态（2026-10-08）：现行规格/规划/规则；设计存在；实现/批准须另凭目标版本证据。项目完成度见 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md)；本标识不提升批准、测试或任务状态。

状态：`canonical-r1-requirement-source / review`
规格版本：0.3.1-open-world-integration
来源基线：经概括的定性需求与工程约束；原始研究不随公开候选分发。\
范围说明：本文件是 R1 machine applicability 的唯一 requirement universe，包含 107 个 `FR-*`/`NFR-*`。P0/P1/P2 是既有 v1 实施候选优先级，最终 release slice 待用户发现与架构确认。15 个 `LR-*` 位于独立 [长期演进需求](long-term-requirements.md)，全部不适用于 `class-os-r1`。

## 1. Goal

让中国初中班主任把分散在 Excel、聊天、纸笔、备忘录和个人记忆中的班级事实，转化为统一、可追溯、可迁移的数据与工作流；教师可直接操作结构化 UI，也可让 Agent 在严格工具、权限和批准边界内完成查询、草拟、分析与变更。

### Product Priority Invariant

`R-PROD-001` 是跨功能的第一排序原则：优先降低通知洪流、责任不清、无人承接、遗漏和事后追责形成的班主任被动责任风险。优先闭环必须让事项来源、必须动作、确认后的责任主体、期限、状态、交接/升级和完成证据可见；既不把组织责任静默派给班主任，也不免除法律、制度或明确授权职责。该原则强化 `E-VALUE-001` 的价值 oracle，不增加本文件的 107 个 R1 requirement，也不授权微信、自动 Capture、排班或多人协作进入 R1。

## 2. Inputs

- 教师在 UI 或 Agent 中输入的文字、表单、语音转写和确认；
- 学生、班级、学期、监护人等手工或批量导入数据；
- Excel/CSV 成绩、考勤和名单；
- 座位/宿舍布局、分配约束和教师调整；
- 日常事件、任务、作业、出勤、谈话和沟通记录；
- 系统配置、权限、学期口径、模型与工具策略。
- 后续经 release 批准的 ChannelEnvelope/CaptureDraft、Knowledge、Commitment、Case 和 Extension Proposal；它们不是 R1 输入，也不能因被解析而自动成为正式事实。

## 3. Outputs and Side Effects

- 学生中心档案与时间线；
- 班级今日视图、待办和关注项；
- 导入预览、错误清单和正式批次；
- 成绩统计、趋势和可解释关注提示；
- 座位、宿舍、分组、职务和值日方案；
- 报告、沟通和工作留痕草稿；
- 经批准的业务事实变更；
- PDF/Excel/CSV/JSON 等导出候选；
- 授权、批准、模型调用、导出和数据变更审计。

## 4. Priority Definition

- **P0**：安全/隐私/数据完整性或首个闭环不可缺少。
- **P1**：v1 完整价值的重要能力，可在首个切片后交付。
- **P2**：完整系统能力，取决于用户频率和试点结果。
- **Deferred**：需要真实样例、学校规则或单独授权。

以上优先级不表示 Release 适用性。Release 适用性只由对应 release manifest 与机器 gate 决定；长期要求不得用 P0/P1 绕过已冻结的 `class-os-r1`。

## 5. Functional Requirements

### 5.1 Workspace, identity and authorization

- **FR-PLT-001 [P0]**：系统必须允许教师创建一个被授权的工作空间并按工作空间隔离数据；只有纳入多角色能力的后续 release 才允许通过邀请加入现有工作空间。（`rule_id`: R-POS-001, R-AUTH-001；`case_id`: C-001, C-034）
- **FR-PLT-002 [P0]**：系统必须提供安全登录、会话过期、退出其他设备和凭据恢复；恢复不得泄露班级是否存在。（`rule_id`: R-AUTH-001, R-PRV-001；`case_id`: C-034）
- **FR-PLT-003 [P0]**：所有 API、Tool 和导出必须同时校验用户、工作空间、班级、学期、动作和字段范围。（`rule_id`: R-AUTH-001；`case_id`: C-034）
- **FR-PLT-004 [P1]**：系统应支持教师、只读协作者和紧急管理员的最小角色集合；管理员 break-glass 访问必须说明原因并强化审计。（`rule_id`: R-AUTH-001, R-PRV-004；`assumption_id`: A-001）
- **FR-PLT-005 [P0]**：系统必须在模型不可用时保留当前 release 已启用的全部结构化核心能力；Release 1 至少包括登录、班级/学生维护、事实事件、任务、Today/Timeline、风险/批准、审计和退出导出。（`rule_id`: R-AGT-002, R-DATA-004；`case_id`: C-003）
- **FR-PLT-006 [P0]**：部署默认处于 `synthetic-only`。首次真实 scope 必须走两阶段 bootstrap：setup capability 的 scope 字段绑定发布/部署/owner/workspace，evidence 字段绑定 candidate、shadow/value 和 pilot-readiness 报告；它只能作为 Business Command Gateway 内唯一 `ScopeAllocationCommand` 的凭据，被原子消费后写无个人数据的 allocation ledger 并预留 class/term ID，不得创建业务实体。最终 `issued` admission artifact 绑定相同 workspace、allocation receipt、预留 ID、期限、模块和已验真证据；每次真实业务写重新验证。unknown pre-admission command、setup 重放/越权、example、或证据缺失/不匹配/过期/撤回均 fail closed，但保留退出导出。（`rule_id`: R-ADM-001, R-EXIT-001；`case_id`: C-058）
- **FR-PLT-007 [P0]**：R1 首次 bootstrap 必须生成只显示/导出一次的离线恢复码套件；恢复码只存哈希，经 Identity Security Boundary 兑换同会话短时恢复能力。恢复成功后轮换 owner 凭据、吊销全部旧会话与旧恢复码并生成新套件；无有效恢复码时应用不得提供绕过身份验证的恢复后门。（`rule_id`: R-AUTH-REC-001；`case_id`: C-059）

### 5.2 Class, academic term and roster

- **FR-CLS-001 [P0]**：教师必须能创建、编辑、归档班级及学年/学期，并明确当前工作上下文。（`rule_id`: R-POS-001, R-DATA-002；`case_id`: C-001）
- **FR-CLS-002 [P0]**：系统必须为每名学生生成不可变内部 `student_id`；外部标识使用带 authority、type、有效期和置信状态的 `StudentIdentifier`，显示姓名不得作为匹配键。（`rule_id`: R-DATA-001, R-STU-001, R-ID-001；`case_id`: C-007, C-011, C-049）
- **FR-CLS-003 [P0]**：教师必须能新增、编辑、停用和归档学生，历史记录不得因停用而丢失；转班只在多班级 release 中启用。（`rule_id`: R-DATA-001, R-DATA-002；`case_id`: C-008）
- **FR-CLS-004 [P0]**：学生详情必须聚合基本信息、当前与历史职务、座位、宿舍、成绩、出勤、作业、事件、沟通和任务。（`rule_id`: R-DATA-001；`case_id`: C-003, C-007）
- **FR-CLS-005 [P1]**：系统应支持多班、多学期切换和学期交接，但默认界面优先当前班级。（`rule_id`: R-POS-001, R-DATA-002；`assumption_id`: A-001）
- **FR-CLS-006 [P0]**：监护人姓名、关系和联系方式必须单独分级、遮罩显示并按目的访问。（`rule_id`: R-STU-002, R-PRV-001；`case_id`: C-013）
- **FR-CLS-007 [P1]**：Release 1 只提供疑似重复候选、证据和“保持分离”；不得执行学生合并。真正合并需逐引用迁移账本、拆分人工归属和独立规格后另行批准。（`rule_id`: R-STU-001, R-ID-001；`case_id`: C-011, C-012, C-049）

### 5.3 Import and data onboarding

- **FR-IMP-001 [P0]**：系统必须将上传文件先保存为隔离的导入批次，不得在解析阶段写入正式业务表。（`rule_id`: R-IMP-001；`case_id`: C-006, C-012）
- **FR-IMP-002 [P0]**：导入必须支持工作表/表头识别、字段映射、类型转换、必填校验、重复检测和学生匹配。（`rule_id`: R-IMP-001, R-STU-001；`case_id`: C-011, C-012；`assumption_id`: A-004）
- **FR-IMP-003 [P0]**：预览必须列出新增、修改、无变化、跳过、冲突和错误数量，并能定位到源行。（`rule_id`: R-IMP-001；`case_id`: C-012）
- **FR-IMP-004 [P0]**：提交必须使用幂等键；默认全量事务，用户选择合法行部分导入时必须保存排除清单，并逐 aggregate 保存 before/after version、source row 和补偿资格。（`rule_id`: R-IMP-002, R-IMP-003, R-SAFE-003；`case_id`: C-012, C-030, C-052）
- **FR-IMP-005 [P1]**：系统应保存字段映射模板和来源指纹，但模板变化必须重新校验。（`rule_id`: R-IMP-001；`assumption_id`: A-004）
- **FR-IMP-006 [Deferred]**：生产适配器必须基于用户确认的脱敏样例和输出契约实现。（`rule_id`: R-DEV-004；`case_id`: C-039）

### 5.4 Daily events, attendance and homework

- **FR-EVT-001 [P0]**：教师必须能快速记录请假、销假、迟到、缺勤、表扬、违纪、谈话和经批准的自定义事实事件；Release 1 不接收 D4“特殊情况”或附件。（`rule_id`: R-EVT-001, R-UX-003, R-PRV-002；`case_id`: C-005, C-014）
- **FR-EVT-002 [P0]**：事件必须包含学生、发生时间、记录时间、类型、事实描述、来源、可见范围和记录者。（`rule_id`: R-EVT-001, R-DATA-003；`case_id`: C-014）
- **FR-EVT-003 [P0]**：系统必须区分客观事实、教师观察、AI 推断和建议。Release 1 只持久化 typed 事实与教师观察；AI 推断/建议只存在于当前会话草稿，关闭/过期即清除，不得写入 Record/Task/Today/Timeline/Profile/Attention、改变优先级或触发外发。（`rule_id`: R-DATA-003；`case_id`: C-009）
- **FR-EVT-004 [P1]**：事件应可关联附件、相关事件、任务和跟进结果；附件需经过类型、大小和恶意内容检查。（`rule_id`: R-EVT-002, R-PRV-001；`case_id`: C-015）
- **FR-EVT-005 [P1]**：Release 1 只按日期、学生、科目和事件类型汇总事实记录，不计算出勤率或唯一“当前状态”；任何统计可追溯到原记录。（`rule_id`: R-EVT-001, R-ATT-001, R-HWK-001；`case_id`: C-014, C-050）
- **FR-EVT-006 [P1]**：请假、延长、销假、返校和更正保存为关联事件；原因按最小必要展示，Release 1 不处理附件。（`rule_id`: R-EVT-001, R-LEAVE-001, R-PRV-001；`case_id`: C-014, C-050）
- **FR-EVT-007 [Deferred]**：批量出勤/作业和出勤率只有在课次、来源优先级、状态转换、补录与更正口径确认后才可实现。（`rule_id`: R-ATT-001, R-HWK-001, R-SAFE-002；`case_id`: C-050）

### 5.5 Tasks, follow-up and Today workspace

- **FR-TSK-001 [P0]**：教师必须能创建个人待办并关联学生、事件或班务对象。（`rule_id`: R-EVT-002；`case_id`: C-015）
- **FR-TSK-002 [P0]**：任务支持未开始、进行中、等待、完成、取消和逾期状态，以及截止时间和完成证据。（`rule_id`: R-EVT-002；`case_id`: C-015）
- **FR-TSK-003 [P1]**：系统可根据明确规则建议跟进任务，但创建自动任务前需让教师确认规则或单项草案。（`rule_id`: R-DATA-003, R-SAFE-001；`case_id`: C-015）
- **FR-TSK-004 [P0]**：Today 页面应聚合待办、事实型请假/缺勤/未交记录、近期跟进和快速记录入口。Release 1 不显示未建模的“当天课务”。（`rule_id`: R-UX-002, R-UX-003, R-ATT-001；`case_id`: C-005, C-050）
- **FR-TSK-005 [P1]**：提醒必须可关闭、稍后处理和追踪来源，不得使用无法解释的“风险学生”黑箱列表。（`rule_id`: R-DATA-003, R-GRD-003；`case_id`: C-009, C-018）

### 5.6 Exams and grades

- **FR-GRD-001 [P0]**：系统必须管理考试、科目、满分、考试日期、数据来源和适用班级/学期。（`rule_id`: R-GRD-002；`case_id`: C-016, C-017）
- **FR-GRD-002 [P0]**：成绩值必须区分有效分数、缺考、免考、未录入和无效数据，不得用同一数值代替。（`rule_id`: R-GRD-002；`case_id`: C-017）
- **FR-GRD-003 [P0]**：总分、均分、名次、并列、进退步和偏科必须由版本化确定性规则计算。（`rule_id`: R-GRD-001, R-GRD-002；`case_id`: C-016, C-017）
- **FR-GRD-004 [P0]**：任何趋势或异常说明必须显示比较考试、样本数量、计算口径和原始数值入口。（`rule_id`: R-GRD-003；`case_id`: C-018）
- **FR-GRD-005 [P0]**：数据不足时不得输出持续进步、持续退步或稳定偏科结论。（`rule_id`: R-GRD-003；`case_id`: C-018）
- **FR-GRD-006 [P1]**：教师可查看学生趋势、班级分布、科目对比和可筛选关注项，但这些视图不得构成自动评价标签。（`rule_id`: R-DATA-003, R-GRD-003；`case_id`: C-009, C-018）
- **FR-GRD-007 [P1]**：更正成绩必须保留原值、原因、操作者、来源批次和重算影响。（`rule_id`: R-SAFE-003, R-PRV-004；`case_id`: C-030, C-033）

### 5.7 Seating, groups, duties and positions

- **FR-SEA-001 [P1]**：教师必须能配置教室布局、不可用位置和座位属性，并支持拖拽手动调整。（`rule_id`: R-UX-002, R-DATA-002；`case_id`: C-019）
- **FR-SEA-002 [P1]**：排座必须支持硬约束与软目标；硬约束不可被评分抵消。（`rule_id`: R-SEA-001, R-SEA-002；`case_id`: C-019, C-020）
- **FR-SEA-003 [P1]**：系统必须生成多候选方案，显示约束满足、评分分解、冲突和不可行原因。（`rule_id`: R-SEA-001, R-SEA-002；`case_id`: C-019, C-020）
- **FR-SEA-004 [P1]**：应用前必须显示新旧 SeatMap、移动学生、影响范围与撤销期限；确认后才提交。（`rule_id`: R-SEA-003, R-SAFE-002；`case_id`: C-020）
- **FR-GRP-001 [P1]**：系统应支持分组、互助结对和值日安排，并保留有效期和历史。（`rule_id`: R-DATA-002；`case_id`: C-008）
- **FR-POS-001 [P1]**：教师必须能配置职务，允许多职务、任期、空缺和历史查询。（`rule_id`: R-POSN-001；`case_id`: C-022）
- **FR-POS-002 [P2]**：轮岗和推荐只能生成候选方案，不得以成绩或行为自动决定学生职务。（`rule_id`: R-DATA-003, R-REP-001；`case_id`: C-009）

### 5.8 Dormitory

- **FR-DOR-001 [P2]**：系统必须支持楼栋、楼层、房间、床位、不可用床位和寝室长配置。（`rule_id`: R-DOR-001, R-POSN-001；`case_id`: C-021, C-022；`assumption_id`: A-008）
- **FR-DOR-002 [P2]**：分配、移动和交换必须校验一人一有效床位、一床一人以及配置的额外规则。（`rule_id`: R-DOR-001；`case_id`: C-021）
- **FR-DOR-003 [P2]**：DormMap 差异预览必须显示学生、前后房间/床位、冲突、原因和生效时间。（`rule_id`: R-DOR-002, R-SAFE-002；`case_id`: C-021）
- **FR-DOR-004 [P2]**：提交后必须保留历史和可逆窗口；涉及学校正式宿管系统时仅生成待同步记录，除非有批准集成。（`rule_id`: R-DOR-002, R-SAFE-004；`case_id`: C-021；`assumption_id`: A-008）

### 5.9 Reports, evidence and family communication

- **FR-REP-001 [P1]**：教师应能按日期、学生、事件类型和任务状态生成日报、周报、月报和工作留痕草稿。（`rule_id`: R-REP-001；`case_id`: C-023）
- **FR-REP-002 [P1]**：报告使用 claim-level 事实卡；单一命题、数值、日期、来源实体与版本绑定，建议、推断和待确认内容独立分区；只有 block 级引用不得 finalize。（`rule_id`: R-REP-002, R-REP-003, R-DATA-003；`case_id`: C-023, C-053）
- **FR-REP-003 [P1]**：教师可编辑、接受或删除草稿段落；正式归档必须记录最终编辑者和来源版本。（`rule_id`: R-REP-001, R-PRV-004；`case_id`: C-023）
- **FR-COM-001 [P1]**：系统可生成家长群通知、个别沟通提纲、评语和沟通摘要草稿。（`rule_id`: R-REP-001, R-COM-001；`case_id`: C-024；`assumption_id`: A-009）
- **FR-COM-002 [P0]**：v1 不得自动外发真实消息；复制或未来发送操作必须有敏感字段检查和明确确认。（`rule_id`: R-COM-001, R-PRV-001；`case_id`: C-024）
- **FR-COM-003 [P1]**：沟通记录必须区分“草稿、已复制、人工确认已发送、发送失败”，不得把生成视为已发送。（`rule_id`: R-DATA-003, R-PRV-004；`case_id`: C-024）

### 5.10 Agent capability layer

- **FR-AGT-001 [P0]**：Agent 必须通过版本化 Tool schema 访问业务能力，不能直接访问数据库或对象存储凭据。（`rule_id`: R-AGT-002, R-AGT-003；`case_id`: C-025, C-026）
- **FR-AGT-002 [P0]**：每个 Skill 必须声明目的、所需权限、读取数据、步骤、输出、禁区、确认点和失败回退。（`rule_id`: R-AGT-001；`case_id`: C-025）
- **FR-AGT-003 [P0]**：所有学生/班级业务 Command adapter（UI、REST、内部服务、worker、Agent Tool 与未来 CLI）必须调用同一 Business Command Gateway 和版本化风险评估器；动作、对象、数据等级、人数、外发、可逆性和授权上下文只能使静态最低风险升级。Identity Security Command 是显式独立边界，不得被实现成未分类例外。（`rule_id`: R-SAFE-001, R-RISK-001, R-UX-004, R-AUTH-REC-001；`case_id`: C-004, C-028, C-043, C-059）
- **FR-AGT-004 [P0]**：所有 W2/X 业务 Command adapter 必须经过同一个 draft/validate/preview/approve/commit/audit 服务端状态机；commit endpoint 只接受已验证且尚未消费的批准凭据。approve endpoint 永不注册为 Agent、Skill 或 MCP Tool；identity bootstrap/recovery 不进入 W2 流，但必须通过 Identity Security Boundary。（`rule_id`: R-SAFE-001, R-SAFE-002, R-SAFE-003, R-SAFE-005, R-AUTH-REC-001；`case_id`: C-029, C-030, C-041, C-059）
- **FR-AGT-005 [P0]**：服务器可证明的批准属性限于允许 Origin、CSRF nonce、主体、认证会话、客户端绑定、proposal hash、资源版本、范围、时效和单次消费；不得把 Page Visibility 或普通点击事件声称为人类存在证明。X 级操作需近期重认证或经批准的 WebAuthn/二次验证。（`rule_id`: R-SAFE-002, R-SAFE-003, R-SAFE-005；`case_id`: C-029, C-030, C-042）
- **FR-AGT-006 [P0]**：Agent 回答必须能引用调用结果，工具失败时不得编造成功；用户可查看关键调用和业务审计。（`rule_id`: R-AGT-002, R-PRV-004；`case_id`: C-025, C-033）
- **FR-AGT-007 [P1]**：内置 Agent 优先使用进程内/服务内 Function Tool，外部 Agent 只通过允许列表 MCP Tool。（`rule_id`: R-AGT-004；`case_id`: C-025）
- **FR-AGT-008 [P1]**：MCP 服务必须支持工具过滤、最小权限、调用审计、速率限制和可撤销授权。（`rule_id`: R-AGT-004, R-PRV-004；`case_id`: C-033）
- **FR-AGT-009 [P0]**：v1 默认单业务 Agent；引入多 Agent 必须有隔离、质量或成本 eval 证据。（`rule_id`: R-AGT-005；`case_id`: C-027）
- **FR-AGT-010 [P0]**：Prompt injection 或工具输出中的指令不得提升权限、改变批准策略或访问未授权数据。（`rule_id`: R-AUTH-001, R-AGT-002；`case_id`: C-026, C-034）

### 5.11 Export, migration and lifecycle

- **FR-EXP-001 [P0]**：在任何真实数据可持续写入前，教师必须能导出 Workspace、班级、学期、学生/标识、事件、任务，以及可移植的 rights-request、restriction/delete tombstone、retention exception 和 admission/revocation ledger，为带 manifest、schema version、checksum 的格式；隔离 round-trip 必须证明不会复活已限制/删除数据并能产生退役证明。（`rule_id`: R-DATA-004, R-EXIT-001；`case_id`: C-010, C-044）
- **FR-EXP-002 [P1]**：座位、宿舍、成绩与报告应支持适合打印/办公的输出；格式在样例确认前保持草案。（`rule_id`: R-DATA-004, R-DEV-004；`case_id`: C-010, C-039）
- **FR-EXP-003 [P0]**：导出必须预览范围、敏感字段、文件格式和接收目的，并记录审计。（`rule_id`: R-PRV-001, R-PRV-004；`case_id`: C-033）
- **FR-EXP-004 [P1]**：归档、转班、毕业和权利请求按逐类生命周期矩阵处理；策略未批准前 UI 只能称“停用/归档”，不得声称删除；完成状态必须说明备份、审计和法定例外。（`rule_id`: R-DATA-002, R-SAFE-004, R-RET-001, R-RET-002；`case_id`: C-040, C-051）

## 6. Non-Functional Requirements

### 6.1 Security and privacy

- **NFR-SEC-001 [P0]**：传输必须加密；敏感数据静态加密或使用等效受控存储；密钥不得写入仓库。（`rule_id`: R-PRV-001）
- **NFR-SEC-002 [P0]**：授权必须在服务端执行，默认拒绝；前端隐藏按钮不能作为安全控制。（`rule_id`: R-AUTH-001；`case_id`: C-034）
- **NFR-SEC-003 [P0]**：上传文件需限制类型、大小、解压资源、公式/宏风险、路径穿越和恶意内容。（`rule_id`: R-PRV-001；`case_id`: C-012）
- **NFR-SEC-004 [P0]**：模型、MCP、日志和 tracing 使用前必须经过字段最小化与脱敏。（`rule_id`: R-PRV-001, R-PRV-002；`case_id`: C-013, C-031）
- **NFR-SEC-005 [P0]**：任何 fixture、截图和错误报告不得包含真实学生数据。（`rule_id`: R-PRV-003；`case_id`: C-032）
- **NFR-SEC-006 [P0]**：敏感读取、导出、模型调用、批准和写入形成不可由普通用户篡改的审计链。（`rule_id`: R-PRV-004；`case_id`: C-033）
- **NFR-PRV-001 [P0]**：真实数据前必须有批准的数据处理角色与授权链，覆盖目的、依据、告知/授权、撤回、查阅、更正、导出、删除、投诉和退役。（`rule_id`: R-PRV-005；`case_id`: C-040）
- **NFR-PRV-002 [P0]**：模型、语音、存储、监控等外部处理器逐项登记地域、训练、保留、分包、删除、事件和退出条件；未批准默认禁用。（`rule_id`: R-PRV-006；`case_id`: C-046, C-047）
- **NFR-PRV-003 [P0]**：Release 1 的 D2/D3/D4 学生详情、Timeline、事件列表、模型投影和敏感导出均在数据释放前取得耐久审计回执；审计不可用时 fail closed，审计查询本身受最小权限和审计。（`rule_id`: R-AUD-001；`case_id`: C-045）
- **NFR-PRV-004 [P0]**：每个实际 store 都有创建目的、真值位置、期限、归档/删除触发、备份传播、审计例外、删除证明和 owner；inventory 至少覆盖业务实体、identity/session/recovery、approval/command receipt、outbox、Agent/model metadata、admission/revocation、audit/telemetry/support bundle、export 与 backup。（`rule_id`: R-RET-001, R-RET-002；`case_id`: C-051）
- **NFR-PRV-005 [P0]**：真实数据准入状态必须在运行时强制执行并可审计；应用不得签发 setup/admission，只能验证。setup 仅能在 BCG 内对绑定 workspace 原子生成无 PII allocation ledger/receipt，不能创建业务实体；receipt 和最终 artifact 必须绑定 target commit/environment、耐久 ledger proof 与经 verifier 验真的 candidate、shadow/value、pilot-readiness 报告。撤回、到期、重放、unknown command 或证据链不匹配后所有业务写 fail closed。（`rule_id`: R-ADM-001；`case_id`: C-058）

### 6.2 Reliability and consistency

- **NFR-REL-001 [P0]**：所有 Command 和导入提交具备幂等键、乐观并发/版本检查与事务边界。（`rule_id`: R-SAFE-003；`case_id`: C-030, C-036）
- **NFR-REL-002 [P0]**：客户端在超时后显示“未知/待确认”状态，不得自动宣称失败或成功；重查状态后再重试。（`rule_id`: R-OPS-002；`case_id`: C-036）
- **NFR-REL-003 [P0]**：每日自动备份并按计划做恢复演练；RPO/RTO 在部署确认后冻结。（`rule_id`: R-OPS-001；`case_id`: C-035）
- **NFR-REL-004 [P1]**：系统升级必须包含数据库迁移 dry-run、版本兼容窗口和回滚/前滚策略。（`rule_id`: R-OPS-001）
- **NFR-REL-005 [P0]**：所有有效时间关系采用半开区间 `[valid_from, valid_to)`，空结束表示无穷；边界切换、未来生效和回溯更正行为一致。（`rule_id`: R-TIME-001；`case_id`: C-054）

### 6.3 Performance and scale

- **NFR-PERF-001 [P1]**：目标规模暂定单班 60 人、5 学年、200 次考试、每生每年 2,000 条事件；需在用户研究后调整。（`assumption_id`: A-001）
- **NFR-PERF-002 [P1]**：在目标规模、常规家庭宽带和中档手机上，关键只读交互 p95 ≤2 秒，写入确认后 p95 ≤3 秒，不含外部模型生成。（`assumption_id`: A-002, A-013）
- **NFR-PERF-003 [P1]**：10,000 行表格解析与预览目标在 30 秒内完成并提供进度/取消；具体规模由样例修订。（`assumption_id`: A-004）
- **NFR-PERF-004 [P1]**：Agent 首个可见反馈目标 ≤2 秒；长任务必须流式显示阶段和可取消状态。（`rule_id`: R-UX-001）

### 6.4 Usability and accessibility

- **NFR-UX-001 [P0]**：手机关键路径支持单手、清晰焦点和足够触控目标；事件记录目标约 3 次核心交互。（`rule_id`: R-UX-003；`case_id`: C-005）
- **NFR-UX-002 [P1]**：桌面批量页面支持键盘、复制粘贴、筛选和错误定位。（`rule_id`: R-UX-003；`case_id`: C-006）
- **NFR-UX-003 [P0]**：确认卡使用人类可读业务语言，不能只显示 JSON、工具名或数据库 ID。（`rule_id`: R-UX-004, R-SAFE-002；`case_id`: C-020, C-029）
- **NFR-UX-004 [P1]**：关键路径目标达到 WCAG 2.2 AA 的适用要求，包含键盘、焦点、对比度、错误提示和屏幕阅读器标签。（`rule_id`: R-UX-002）
- **NFR-UX-005 [P0]**：Release 1 不在 localStorage/IndexedDB 持久化 D2+ 离线草稿；只允许页面内存恢复，登出、会话过期或关闭即清除。（`rule_id`: R-LOCAL-001；`case_id`: C-048）
- **NFR-UX-006 [P0]**：Release 1 不提供录音、语音转写或音频上传入口；无法证明为本地离线处理的“系统转写”一律视为外部处理器并保持禁用。（`rule_id`: R-VOICE-001, R-PRV-006；`case_id`: C-047）

### 6.5 Observability and cost

- **NFR-OBS-001 [P0]**：技术日志、Agent trace 和业务审计分离，均使用关联 `request_id`，但不重复存储敏感正文。（`rule_id`: R-PRV-004；`case_id`: C-033）
- **NFR-OBS-002 [P1]**：监控成功率、延迟、错误类型、批准/拒绝、撤销、模型 token/成本和工具失败，不建立学生个人行为画像。（`rule_id`: R-PRV-001）
- **NFR-OBS-003 [P1]**：告警必须关联 runbook、负责人和用户影响；不得把学生姓名放入告警渠道。（`rule_id`: R-PRV-001, R-OPS-001）

### 6.6 Portability and maintainability

- **NFR-MNT-001 [P0]**：领域模型、规则和 Tool schema 不依赖具体 LLM 或 Agent runtime。（`rule_id`: R-AGT-002, R-DATA-004）
- **NFR-MNT-002 [P0]**：模块写入权唯一，公共规则集中测试；不得在 UI、API 和 Agent adapter 复制业务判断。（`rule_id`: R-DEV-003）
- **NFR-MNT-003 [P1]**：数据库、文件存储、模型、邮件/消息和 MCP 通过 adapter 接口替换。（`rule_id`: R-DATA-004, R-AGT-004）
- **NFR-MNT-004 [P0]**：仓库提供单一验证入口和可重复本地环境；构建不得依赖未记录的个人机器状态。（`rule_id`: R-DEV-001, R-DEV-002）
- **NFR-OPS-001 [P0]**：真实试点只支持一个经批准的部署拓扑，并给出 OS/CPU/RAM/磁盘、网络边界和不支持项。（`rule_id`: R-OPS-003；`case_id`: C-056）
- **NFR-OPS-002 [P0]**：提供可重复安装、自检、升级、回滚、备份恢复、证书处理、支持包和卸载/退役流程。（`rule_id`: R-OPS-003；`case_id`: C-056, C-057）
- **NFR-OPS-003 [P0]**：磁盘、证书、备份、数据库、队列和安全补丁有提前告警、责任人和安全退化策略。（`rule_id`: R-OPS-003；`case_id`: C-057；`assumption_id`: A-016）
- **NFR-OPS-004 [P0]**：发布前批准安全补丁 SLA、支持版本窗口、恢复责任与停止服务条件。（`rule_id`: R-OPS-003；`assumption_id`: A-016）

## 7. Long-term Evolution Requirements

长期、非 R1 的 `LR-*` 已迁入独立 canonical source：[Long-term Evolution Requirements](long-term-requirements.md)。这样 `.ai/gates/release-1-requirements.yaml` 对本文件 107 个 `FR-*`/`NFR-*` 继续保持“每个需求恰好一次”的完备性；15 个 `LR-*` 由长期追溯链独立覆盖，全部对 `class-os-r1` 为 `applicable: false`。任何 LR 进入实现，必须创建 superseding release change 并建立该 release 的 machine applicability manifest，不能修改或绕过当前 R1 selector。

## 8. Out of Scope for v1

- 全校招生、收费、人事、教务排课和财务；
- 自动心理/健康诊断、纪律裁决和学生标签；
- 学生或家长端完整门户；
- 未经确认的真实微信/短信/邮件自动发送；
- 通用代码执行、任意 SQL、任意远程 MCP 或插件市场；
- 为概念展示而建立多 Agent 组织；
- 视频监控、人脸识别、学生设备控制。
- 微信/ClawBot 生产 Channel、图片/手写批量 Capture、Audio/Ambient/voiceprint、自动外发、全校 Scheduling、自治 Schema/Workflow 和图数据库；当前仅允许合成/彻底脱敏 Discovery spike 或架构预留。

## 9. Open Questions

开放项保持未验证状态：A-003（学校允许使用）、A-004（真实表格）、A-008（宿舍职责）、A-009（外发边界）、A-010（模型数据流）在对应生产功能开始前是强阻断项；A-018—026 继续是 Discovery 假设，不因第 7 节建立长期语义而转成已验证产品优先级。内部研究台账不分发，公开候选的工程边界见 [说明](../../ENGINEERING_OVERVIEW.md)。
