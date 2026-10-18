# Release 1 Manifest: Minimal Event Loop

> 文档状态（2026-10-08）：现行规格/规划/规则；设计存在；实现/批准须另凭目标版本证据。项目完成度见 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md)；本标识不提升批准、测试或任务状态。

状态：`review`。这是当前唯一可进入实现准备的业务切片；完整 v1 需求仍是目标蓝图，不代表当前队列。

真实试点的唯一执行 profile 是 `release-1-pilot-profile.md`；完整 v1 的通用试点模板不得作为本 Release 输入。

## Goal

验证“记录一件学生事实 → 形成简单跟进 → 在 Student Timeline 与 Today 复用 → 随时完整退出”是否比现状净减负。

## Included

- 单 owner workspace，保留 `workspace_id` 隔离；不做邀请、多角色或 break-glass；
- 一个当前班级/学期；学生由受信 UI 手工建立；名单导入进入后续 release；
- 多来源 `StudentIdentifier` 和疑似重复提示；不合并学生；
- 事实型事件：表扬、迟到、缺勤、请假/销假、未交/补交、谈话事实；
- 简单跟进任务、Student Timeline、Today；Today 不含课务；
- 基本结构化 UI；手机页面内存恢复，不持久离线敏感草稿；
- 不提供录音、语音转写或音频上传入口；
- Agent 只读查询与 Draft，不提供任何 Agent/MCP approve 或业务写 Tool；
- owner 在直接 UI 中创建/更正事件；敏感事件按动态风险显示结构化确认；
- 业务审计、幂等、版本、最小核心 JSON 退出导出和 round-trip；
- 单一受支持试点部署、自检、备份恢复、升级回滚和退役。
- 运行时默认 `synthetic-only`；只有签名 gate artifact 生效后才能进入限定范围的 `approved-real-pilot`。

## Explicitly Excluded

- 外部 MCP listener；
- 多角色、邀请、break-glass；
- Student merge/undo；
- 附件和外部语音转写；
- 完整离线同步或 localStorage/IndexedDB 敏感草稿；
- 名单/成绩/其他文件导入；
- 监护人字段与联系方式；
- 所有录音、系统/浏览器/外部语音转写和音频存储；
- 出勤率、课次、课表、复杂作业状态或学生评价；
- 成绩、排座、宿舍、职务、分组、值日；
- 正式 AI 报告、家校外发、X 级发送基础设施；
- D4 健康、心理、家庭困难和处分材料；
- 公网开放的多租户 SaaS。
- 微信/ClawBot 或其他生产 Channel、图片/手写 Capture、Audio/Ambient/voiceprint；
- Knowledge/RAG、AI Inbox、Commitment/Case/Workflow、多人协作、Scheduling 和 Controlled Extension/Dynamic Schema。

## Requirement Applicability

逐 ID、不可使用“所有适用 P0”的机器清单见 `.ai/gates/release-1-requirements.yaml`。本 Release 的 included FR 是：

`FR-PLT-001/002/003/005/006/007`；`FR-CLS-001/002/003/007`；`FR-EVT-001/002/003/005/006`；`FR-TSK-001/002/004`；`FR-COM-002`；`FR-AGT-001—006/009/010`；`FR-EXP-001/003/004`。

其中 FR-EVT-003 在 R1 的含义是“来源类型可区分”，不是持久化推断能力：只保存 typed 事实和教师观察；AI 推断/建议限当前会话草稿，不进入任何 repository/schema、业务排序、Task/Today/Timeline/Profile/Attention 或 outbox。未来持久 AIInference 必须走独立 LR/E-EVO/release 准入。

Included NFR 必须逐项映射 Eval 和任务，不能由优先级自动推断。FR-IMP、Guardian、Student 360 全域聚合、附件、批量出勤、任务自动建议/提醒、成绩、组织、宿舍、报告、外发、外部 MCP 与办公格式全部 deferred；不得以“最小名单”“已有 P0”或“完整 v1 蓝图”为由带入 Release 1。

`long-term-requirements.md` 的 15 个 `LR-*` 是独立的长期 canonical/discovery source，全部对本 Release 标记 `applicable: false`；它们不属于 `.ai/gates/release-1-requirements.yaml` 声明的 `requirements.md` universe。`E-EVO-*` 与 `T-EVO-*` 不进入 R1 eval/task machine manifests；若未来启用，必须创建新的 release applicability/definition bundle，而不是修改 R1 状态文件。

## Exit Criteria

1. 数据处理角色、授权、保留/退役和单一部署责任获批；
2. `.ai/gates/release-1-evals.yaml` 中全部 required eval 已具备可执行规格、runner 和目标版本 `implemented-green` 证据；
3. 最小退出导出在任何真实写入前通过隔离 round-trip；
4. 目标用户任务中位步骤或时间降低 ≥30%，持续录入成本未抵消收益；责任压力样本中不得出现静默把责任不清事项派给班主任，遗漏/逾期不劣于现状，完成或交接/升级证据可检索；
5. 无越权、敏感日志、重复写、无法审计或不可恢复数据；
6. Agent 关闭时完整结构化闭环仍可用。

## Expansion Gate

只有 Release 1 价值和安全门通过，才从完整 v1 蓝图或 Discovery Track D1 中选择一个下一切片；不因“文档已经写了”或“长期 Ontology 已预留”自动进入开发。任何替换 R1 的 wedge 必须走 superseding change，不原地偷渡。
