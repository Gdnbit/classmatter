# 班事有谱 · ClassMatter 文档

- [Logo 资产登记](../assets/brand/README.md)：用户指定的带字标识与独立图形原件、哈希及本地留档边界；图片未随源码公开，不代表应用图标已替换。

## 数据库与真实数据接入（2026-10-23 · 设计提案）

- [真实数据闭环执行目标与验收台账](design/live-data-delivery-acceptance.md)：Goal必交范围、U0—U3依赖、11项验收指标与证据要求；D1—D3单独后续变更，不自动扩R1。
- [数据库与实时数据演进设计](design/database-live-data-design.md)：保留PostgreSQL；核对22表与Mock/R1差距；耐久会话/运行、工作专题、注意力投影、Agent读写边界、提交后同步、迁移与退出的分阶段设计。候选对象和DB验收条目不是正式Requirement/Eval，不批准建表、Agent写入或扩大R1。

## Agent 自主推进与 Runtime 调研（2026-10-22 · Discovery / Future）

- [从教师 Todo 到 Agent 承接工作：事项生命周期、记忆所有权与人机协作 Attention](product/agent-owned-work-and-attention.md)：视频启发的抽象、ClassMatter-owned Work Item、等待/检查/证据、班务模拟与安全边界。
- [Pydantic AI vs Pi：官方能力、专业社区/生产案例与选型判断](research/2026-10-22-pydantic-ai-pi-runtime-assessment.md)：默认继续采用 Pydantic AI，Pi 仅为隔离评测候选；证据与来源分级。
- [Agent Runtime / 持续工作研究测试计划](research/2026-10-22-agent-runtime-and-work-evaluation-plan.md)：合成场景、对照合同、硬性安全门槛、Net Burden、渐进验证。

以上均为研究文档，**不是 R1 新功能、已通过的 Eval/Gate、真实学生数据处理许可或 Runtime 迁移批准**。

## 业务场景与安全协同（2026-10-21 · Discovery / Future）

- [班务与异常事件场景图谱](product/scenario-catalog.md)：20 个虚构情境，覆盖日常事实、家校沟通、失联/请假、寄宿、冲突、心理困扰、突发事故和交班；区分 R1 能力与长期业务假设。
- [学生安全与履职协同流程](product/student-safety-and-duty-workflows.md)：发现—处置—上报—接收确认—复访—关闭，证据边界、协作责任、失败模式、隐私护栏及合成验收脚本；**非法律或医疗建议**。

这两份文档不包含具体个人/学校/学生资料，不代表学校授权或真实用户验收。R1 manifest、107 个规格需求、Eval/Task/Gate 均不因此扩张。

- [法律、案例、规章与校规的效力核验和规则追溯](product/legal-evidence-and-rule-hierarchy.md)：Discovery / Future，含已核对的官方规范、来源元数据与上线拒绝门。
- [工程边界与代码地图](ENGINEERING_OVERVIEW.md)
- [实现与验收台账：波次、页面、代码、追溯与剩余项](implementation-ledger.md)
- [独立 PC Demo：设计与验收](desktop-demo.md) · [运行与打包](../apps/desktop/README.md)
- [前端 Demo 定向修复、范围与验收](frontend-demo-acceptance.md)
- [发行审查状态](OPEN_SOURCE_READINESS.md)
- [公开安全审计](PUBLIC_AUDIT.md)
- [R1 范围](specs/class-os-v1/release-1-manifest.md)
- [架构](specs/class-os-v1/architecture.md)
- [需求](specs/class-os-v1/requirements.md)
- [任务](specs/class-os-v1/release-1-atomic-tasks.md)

必要的 canonical SDD、契约、eval 和机器 Gate 保留。内部研究与操作日志不在此发行范围；指向其技术讨论的链接统一改为工程边界说明，不伪装成原始证据或代表性用户研究。历史技术目录名与冻结任务表保留兼容意义，见根命名矩阵。
