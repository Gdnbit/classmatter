# Module Boundaries

2026-10-15 roster边界（原FR-CLS-001）：Term名称/起止日期为独立Term元数据，不借class.update任意嵌套更新。term.update闭合十字段、W2、active parent/Term版本/旧值复验；metadata只读经QG、持久化经BCG，模型不可批准/写入。日期更正不修改Enrollment有效期、历史Record/Task、Class/Student版本/主键，不构成Temporal触发或多学期切换；只补原R1编辑能力。

> 文档状态（2026-10-08）：现行规格/规划/规则；设计存在；实现/批准须另凭目标版本证据。项目完成度见 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md)；本标识不提升批准、测试或任务状态。

## 0. Physical Repository Mapping

| 逻辑层 | 物理位置 | 说明 |
|---|---|---|
| UI / Web adapter | `apps/web` | 冻结 UX baseline、view model、typed client；不拥有业务规则或正式事实 |
| HTTP / worker interfaces | `backend/src/class_os/interfaces`（ADR-006B 后创建） | 分别运行，进入相同 Query/Command/Identity boundaries |
| Application / Domain | `backend/src/class_os/application`、`backend/src/class_os/domain`（ADR-006B 后创建） | 模块化单体内的规则与用例所有权 |
| Infrastructure adapters | `backend/src/class_os/infrastructure`（ADR-006B 后创建） | DB/object/model/provider adapters，不反向污染 domain |
| Agent runtime adapter | `backend/src/class_os/interfaces/agent` + `infrastructure/agent_runtime`（ADR-006B 后创建） | Pydantic AI/Jev/AG-UI 类型只能停留在 adapter；Application 只见项目 DTO/port |
| Wire/tool contracts | `contracts` | versioned OpenAPI / JSON Schema / Tool-MCP schema |
| Deployment and operations | `infra` | compose/deploy/telemetry/backup，仍受部署 Gate |

物理目录不改变逻辑边界：API、worker、Agent 和未来 connector 不能各自实现一套权限或业务写路径。

## 1. Source Adapters

- `imports/excel`、`imports/csv`：读取字节和基础单元格，不决定学生匹配或成绩规则。
- `ui`、`rest`、`agent`、`mcp`：将外部请求转为 application command/query。
- `identity`、`model-provider`、`object-storage`：基础设施接口。
- Future `wechat/image/audio/form/calendar/connector`：只生成 ChannelEnvelope/CaptureDraft；不得决定实体归属、事实等级、权限或业务写入。
- `harness/ocr/asr/rag/renderer/workflow-runtime/solver`：Shared Capability ports；实现可替换且不持有 repository/BCG credential。
- Agent Tool 先经静态 capability metadata/allowlist；Jev 只能对候选能力做 typed 路由/判断，主模型只能生成 typed call/draft，二者都不得授权或 commit。

禁止：adapter 自己修正成绩、合并学生、应用座位或改变批准要求。
同样禁止 Channel、Memory、Knowledge、Workflow 和 Extension adapter 持久化业务事实、批准凭据或物理 Schema。

## 2. Parsing and Normalization

- 表头识别、空白/字符规范化、日期/数字安全解析；
- 源行号、工作表名、原值和警告保留；
- 生成 canonical import row，不直接生成 ORM entity；
- 文件资源和公式处理有上限与隔离。
- OCR/ASR/LLM 抽取必须保留 source span、processor/version 和置信信息，只产生 Draft/Candidate；置信度不能授予权限。
- Entity Resolution 生成候选、证据和冲突；同名、昵称、转发与低置信默认保持分离。

## 3. Canonical Domain Modules

| 模块 | 拥有 | 对外能力 |
|---|---|---|
| identity-access | workspace、membership、AuthorizationSubject、AuthorityGrant/PolicySet | 唯一 authorize port、scope、field/purpose projection、break-glass |
| party-organization（post-R1） | person、organization、role binding、responsibility、availability、relationship、assignment | resolve refs、描述性 role/responsibility/handoff facts；不得 authorize，不拥有专业正文 |
| roster | class、term、student、guardian、enrollment | roster CRUD、match、merge proposal |
| records | event、attendance、homework、attachment ref | capture、correct、timeline query |
| tasks | task、follow-up、reminder | lifecycle、Today projection |
| grades | exam、subject、score、rule version、metric | import validate、calculate、explain evidence |
| seating | classroom layout、slot、constraint、plan、assignment | solve、validate、preview、apply |
| dormitory | dorm layout、bed、rule、assignment | validate、preview、move/swap |
| organization | position、group、duty、assignments | configure、assign、history |
| reporting | report/communication draft、source refs、version | compose、review、finalize |
| interchange | import batch、mapping、export job | stage、preview、commit、render |
| capabilities | tool definition、proposal、approval、invocation | policy、state machine、result envelope |
| audit | audit event、retention、integrity metadata | append、search、export-for-review |
| capture（post-R1） | channel envelope、capture session/draft、resolution candidate | deduplicate、normalize、review；所有中间态写经 BCG、读经 Query Gateway；不写 owning domain |
| knowledge（post-R1） | knowledge document/version、citation、supersession | 经 BCG publish/version、经 Query Gateway query；不覆盖 Domain Fact |
| work-orchestration（post-R1） | commitment、case coordination、workflow definition/instance、trigger | validate transitions；持久化经 BCG，读取经 Query Gateway |
| extension-governance（post-R1） | domain pack metadata、custom logical schema、proposal、promotion record | 经 BCG validate/propose/activate logical schema、经 Query Gateway 查询；无运行时 DDL |

## 4. Business Rules and Calculations

集中实现且可确定性测试：学生匹配、事件状态、出勤汇总、成绩口径、排名/趋势、座位/宿舍不变量、风险级别、批准 token 验证、敏感字段投影。

LLM 只用于意图理解、文本组织和解释；计算结果必须来自上述模块。

认识论分类、时间精度、来源权威、角色/责任/权限分离和 Net Burden 准入也是集中规则，不得分别复制到 UI、Agent prompt、Connector 或 renderer。

## 5. Validation and Audit

- schema validation：类型、格式、必填；
- domain validation：业务不变量和状态转换；
- policy validation：主体、资源、字段、目的和风险；
- concurrency validation：expected version 和 proposal hash；
- audit：记录决定与结果，不记录无关敏感正文。
- epistemic validation：Draft/Claim/Observation/Derived/Inference 不能静默晋升 Domain Fact；
- provenance validation：source/version/scope/validity 可定位且允许失效传播；
- extension validation：允许类型、端点、索引预算、权限、生命周期、导出、迁移和回滚完整；
- burden validation：产品 release gate 计入核对、纠错、Review debt 与运维，而非仅计算录入步骤。

## 6. Output Rendering

- 领域 DTO → UI ViewModel；
- 领域 DTO → Tool result envelope；
- versioned export model → Excel/PDF/CSV/JSON renderer；
- report facts + source refs → draft sections。

渲染层不得改变数字口径或遗漏需披露的警告。

## 7. Delivery and Export Adapters

- 本地下载、对象存储短期签名链接、打印；
- 未来消息通道必须作为独立 adapter，首版禁用实际外发；
- MCP 使用独立身份和允许列表；
- 所有 adapter 有契约测试和失败回执。
- Future Channel/Connector 的 inbound/outbound 分开授权；inbound 也必须声明目的、保留、身份映射、去重、删除传播和 cursor。

## 8. Trace Evidence

每个导入批次保留 `source_file_hash → sheet/row/cell → normalized row → validation result → target aggregate/version`。每个报告事实保留 `report_version → source entity/version`。每个 Command 保留 `request → proposal hash → approval → commit → audit`。

长期链路另保留：`channel event → envelope → capture session/draft → resolution decision → typed command → BCG receipt → domain aggregate/version`；`knowledge source/version → RAG chunk/index → citation`；`source correction/restriction/delete → derived dependency invalidation/rebuild proof`；`schema proposal → review/approval → logical schema version → migration/promotion/retirement evidence`。

## 9. 单一授权所有权与迁移

- controller、Query Gateway、Export、RAG、Tool/MCP 和 background worker 必须调用同一个 `identity-access.authorize` port；不得各自解释 RoleBinding 或维护第二套 Grant；
- `party-organization` 只返回已按调用方权限投影的角色/责任/关系事实，不能返回 allow/deny 决定；
- R1 `Membership.role` 与旧文档中的 `PolicyGrant` 迁移时，前者只形成 RoleBinding，后者映射为 `AuthorityGrant`；任何不确定映射进入人工 review，不创建宽权限默认值；
- 冲突、缺失、过期、未知 purpose、未知 field projection 全部 deny，并在 Query/Export/RAG 三条路径产生一致审计结果。
