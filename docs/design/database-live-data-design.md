# 数据库与实时数据演进设计提案

日期：2026-10-23。检查基线：公开 main `3d8d750`。

状态：**design-proposal / post-R1-change-required**。这是对现有 ClassMatter 的专题补充，不是另一套 canonical SDD，不批准新增表、工具、外部服务、真实数据或正式 Gate。现行[架构](../specs/class-os-v1/architecture.md)、[ADR](../specs/class-os-v1/architecture-decision.md)和[冻结 R1](../specs/class-os-v1/release-1-manifest.md)仍为事实源。对象/字段/接口名称为候选，须在实现单元内完成契约和迁移评审。

## 1. 目标与不变量

目标不是“每页建一个表”，而是让会话、学生、记录和任务具有可解释的持久来源，不同页面复用同一份数据，重启、断线和重试时不丢失或重复执行。

- 复用 PostgreSQL、SQLAlchemy Core、Alembic、Psycopg、Pydantic AI 和现有 typed clients；不重选 Harness，不自研数据库/迁移/Agent loop。
- 所有业务读取经 Query Gateway（QG）；持久业务变更经 Business Command Gateway（BCG）；身份操作经 ISB。Agent 无数据库凭据、任意 SQL、DDL 或批准能力。
- 持久聊天、运行历史与业务事实分离；保存 AI 文本不等于确认其中的陈述，也不等于允许自动长期学习。
- 单 owner、当前班级/学期的既有 R1 不扩容。新增耐久聊天、工作专题、事件存储或记忆需独立后续 release/change；本提案不修改原 Requirement/Eval/Task/Gate。
- “真实数据链路”先用合成内容通过真实 API/事务/数据库验证，不引入真实师生信息，不依赖付费模型。
- 每个新增 store 都必须同时定义授权、来源、导出、保留、删除/限制、恢复和失效策略；不能仅以 INSERT 成功验收。

## 2. 当前实现：已拥有与缺少

现有数据库 head `0016`，`schema_inventory.py`登记22张表（含系统和审计表，不能称22个业务模块）。版本和实际清单以代码为准。

| 数据族 | 现有落点 | 现状与缺口 |
| --- | --- | --- |
| 身份/隔离 | workspace、owner_account、auth_session、恢复码与身份审计等 | 有单 owner/合成运行实现；workspace 是授权边界，不是“家长会准备”专题 |
| 班级/学生 | academic_term、school_class、student、enrollment、student_identifier | 可复用；当前仅一个 active 班/学期，不得直接取消唯一约束当作多班级交付 |
| 事实/任务 | record_revision、manual_task | 版本、更正、关联、状态和 due_at 已实现；等待别人是任务状态，不是对方已接手 |
| 写入证据 | command_proposal、approval_receipt、command_receipt、business_audit | 继续统一复用，不能以 SDK approval 或前端状态替代 |
| 模型/退出 | model_configuration、export_job | 配置不等于模型已启用；现有核心退出不含未来聊天等内容 |
| 聊天/运行 | Web ConversationStore；后端 ConversationMemory | 前端样例/内存；后端15分钟、10轮、最多32会话的临时历史；无耐久会话/运行日志/崩溃恢复 |
| 工作专题 | `apps/web/src/data/workspaces.ts` | 固定数组，不是数据库对象；变量名 persistentWorkspaces 不表示已持久化 |
| 注意力/总览 | DemoWorkStore；R1 work-projection、QG activity | R1部分真实投影；“可能遗漏”没有完整通知责任候选链，不可填假卡片 |
| 变更同步 | 本端 commit 后 reload、Agent SSE | 无耐久业务变更流、普通跨窗口实时同步或完整断线补读；不能把 Agent SSE 当全应用同步 |

代码证据：`backend/src/class_os/infrastructure/persistence/{database,schema_inventory,role_guards}.py`、`application/roster.py`、`infrastructure/{roster,activity,agent_memory}.py`、`apps/web/src/{App.tsx,runtime/R1App.tsx,store/ConversationStore.tsx,store/DemoWorkStore.tsx,data/workspaces.ts}`。

现有 QG/BCG 的 `store.atomic()`在事务内取得固定 business advisory lock；QG敏感读还追加耐久审计。**应用“只读查询”不是 PostgreSQL 整个事务 READ ONLY**。不能为了读性能把审计去掉，或将 QG 接到不能写审计的数据库角色后宣称兼容。

## 3. 数据库与存储选型

建议：**PostgreSQL继续作为唯一正式数据主库，沿用当前18.x受支持基线和精确依赖锁；本次不升级版本。** 关系约束和可审计事务比供应商是否有“Agent”标签重要。

| 方案 | 适配判断 | 本项目选择 |
| --- | --- | --- |
| 现有 PostgreSQL + SQLAlchemy Core/Alembic/Psycopg | 已有角色隔离、事务、迁移、恢复和真实测试资产；适合结构化事实与并发修改 | 保留，不重建另一套数据访问层 |
| SQLite主库 | 单机打包轻；经应用服务器也能服务多个客户端，并非“不能多用户” | 不替换：需要重新验证迁移、权限、事务及恢复；目前没有足以抵消改造成本的证据 |
| PostgreSQL与SQLite双主写 | 增加同步、冲突、删除和退出一致性问题 | 不采用；桌面壳不需要第二个业务事实源 |
| 独立文档库/图数据库 | 特定查询可能有价值，但目前主要对象关系可用关系表表达 | 暂不引入；人物关系图不等于必须图数据库 |
| 独立向量库/搜索服务/Redis | 可作后续可重建索引或缓存，不适合替代业务主库 | 先不增加运维组件，按测量证据单独评估 |
| 文件/对象存储 | 未来大文件不宜当作聊天 JSON 一直塞进主表 | DB保存受控元数据/哈希/版本，文件由私有本地卷 adapter 承载；云对象存储另行准入 |

SQLite WAL支持读写并行，但仍只有一个 writer，且WAL要求访问进程同宿主；这是部署约束，不是否定SQLite能力。[SQLite官方说明](https://www.sqlite.org/wal.html)。本方案不声称做过本项目PG/SQLite等价业务负载性能比较。

桌面初期继续“Electron → 固定可信本地API → 同机PG”；不让renderer连接数据库。当前开发runtime依赖源码、Windows DPAPI和显式准备的PG，不是完整安装包。后续需单独交付数据库打包/启动/升级/故障提示。远程API部署可以复用领域层，但当前`Database`只允许loopback、合成库名和固定角色；改成远程并非换URL即可完成，需新的部署/凭据/TLS/准入适配与测试。禁止把PG数据目录或DPAPI目录当作跨机同步文件夹。

## 4. 存储分区与权威性

| 分区 | 保存什么 | 不能成为 |
| --- | --- | --- |
| 业务事实 | Student/Enrollment、Record修订、Task及来源 | 聊天推断、全文检索结果 |
| 交互历史 | 用户可见消息、会话标题、轮次、运行状态/工具结果摘要 | 业务确认、审批、授予职责的凭证 |
| 模型上下文 | 按当前权限重建的有界历史、必要来源、可选派生snapshot | 所有历史无条件重放、永久授权 |
| 变更与运行证据 | 业务receipt、审计、提交后的invalidation、运行计量 | 可自由执行的SQL/可回放批准token |
| Future偏好/Knowledge | 经确认的偏好、版本化文档和引用 | Domain Fact、组织权限或法规结论 |
| 文件与派生索引 | 受控字节对象、重建索引、渲染草稿 | 第二套正式业务数据 |

优先同一数据库中的逻辑模块/表所有权，不为每族立即建独立服务或物理库。身份仍用ISB及现有角色隔离。密码、恢复码、会话cookie、API key、DSN、私有批准句柄及隐藏推理不进入聊天正文、通用JSON、事件推送或模型上下文。

同一个受支持deployment使用同一正式主库，按workspace/class/term关联和隔离；不按每个学生/学期建一张表或一份数据库。未来托管PG只是部署选项，不因此引入可被前端/Agent直接调用的通用数据库写API。

## 5. 下一阶段候选关系模型

以下不是待一次性建齐的表清单。先实现有价值的垂直切片，再按阶段创建必要实体。新键使用应用生成UUID；时间用UTC timestamptz，日期用date，界面显示时转本地时区；名称、手机号、学号都不作全局身份主键。

### 5.1 复用领域，不重新定义“学生/事实/任务”

- 保留Student/Record/Task主键、版本、修订历史和现有来源，不把演示学号或字符串ID强塞为正式UUID。
- 复合外键优先带`workspace_id`；班级关联同时带class/term，防止合法ID被跨scope拼接。权限仍在应用层校验，外键不代替授权。
- 学生统计取各record_id的最新修订，不把修订条数误算为事实数；总数在数据库对完整授权集合计算，不能用分页结果长度代替。
- “需要处理”“等待”“逾期”是同一Task集合的规则化视图；不另建三份任务表。逾期按due_at与查询时刻计算，不维护容易过期的永久overdue布尔值。

### 5.2 工作专题，与安全Workspace区分

候选`work_collection`：`workspace_id, collection_id, owner_id, name, description, status, version, created_at, updated_at`，加当前阶段明确的class/term绑定。它只组织资料，不授予权限，不自动切班或接手职责。

关联先使用明确的`collection_task`、`collection_thread`等带外键的关系表，唯一键含workspace、collection和目标ID。不要用`entity_type + 任意entity_id + JSON`作为无约束万能关联表。是否确需多对多、跨专题复用是产品假设；第一切片可先只关联会话与任务，不提前关联所有未来对象。

### 5.3 耐久会话和运行：五个候选实体

| 对象 | 核心字段/约束 | 用户价值 |
| --- | --- | --- |
| conversation_thread | workspace/thread/owner、class/term绑定、title、status、version、最后可见消息时间；所有关联在同scope | 侧栏会话可恢复，不依赖页面内存 |
| conversation_turn | workspace/thread/turn、单调thread内序号、client_request_id、request_hash、创建时刻 | 双击/重连不重复创建同一次发送；序号不靠时间猜 |
| conversation_message | thread/turn/message、ordinal、role、content_origin、已验证text/parts、status、created_at | 保存用户可见内容；AI文本保持未验证属性 |
| agent_run | turn/run、attempt、state、mode/tool-policy-version、provider配置版本引用、开始/结束、lease、usage nullable、错误枚举 | 重启后知道完成/失败/中断，而非永远显示“处理中” |
| agent_run_item | run/item、seq、closed item_type、状态、工具名/版本、来源ref/摘要、业务receipt引用（若未来允许） | 展示工具执行和来源；不是任意SDK对象垃圾桶 |

共同约束：作用域内复合PK/FK、turn请求键唯一、`(thread_id,ordinal)`与`(run_id,seq)`唯一且带workspace、同thread最多一个占用运行槽（固定partial unique条件为queued/running/cancel_requested，不把now()放进索引predicate）、状态转移CAS。SDK provider ID只作元数据，不能当业务主键。

第一阶段不提供历史消息原地修改、任意分叉或跨班级搬移；若后续开放编辑，必须追加版本并明确旧运行是否失效，不能覆写已引用来源。会话改名、归档、消息保存也要有typed Command及审计；“点击发送”可作为该交互命令的用户意图，不意味着用户批准了消息中描述的业务变更。

运行状态建议`queued → running → completed/failed/cancelled/interrupted/unknown`，取消请求先进入`cancel_requested`等待实际确认。终态竞争由版本/CAS解决；取消和断线不等于供应商没有计费。重启后以有界lease识别遗留运行并标中断/待核对，通过合法状态变更释放唯一运行槽；旧worker凭已失效generation/fencing token不得再写完成结果。lease过期不能直接绕过唯一约束，也不自动重跑模型或执行历史工具。用户明确重新执行才创建新attempt，并保留前后关联。

消息持久化的BCG handler由受信应用编排调用，不交给LLM一个“保存任意消息/运行”的工具。终态发布必须在结果记录与审计成功后；中途delta属于临时展示，不能冒称已耐久保存。若终态写入失败，显示“结果尚未保存/需核对”，不静默重复付费调用。

### 5.4 注意力与学生总览

- `needs_action`、`waiting`、`closed`取自既有Task状态；“等待别人”不证明对方已接收。
- 先接真实逾期/重复标识候选并说明具体原因；逾期与“可能存在未知责任”不是同一语义，不为了填满栏目制造推断。
- 未来通知责任候选应有独立来源、处理版本、人工决策/拒绝/更正状态和范围；在该模型和release获准前，不注册对应写命令或Tool。
- 首页、工作页、专题和学生详情复用同一QG投影；派生统计带`as_of, scope, source_refs, rule_version`，不是另一个可编辑事实表。
- 这里的“投影”首先是受控查询DTO，不要求新建SQL VIEW；当前relation surface会拒绝未登记view，不能绕过清单创建。

### 5.5 其他长期族

Person/Organization/RoleBinding/Relationship/Group/Assignment、Claim/Evidence、Calendar/Commitment/Case、Knowledge/Artifact/Capture仍按长期canonical模块所有权扩展。Student不自动重命名为Person，不重写现有ID；学校角色不自动成为AuthorityGrant。第一批不建立所有长期表，不建设图数据库、万能Fact或万能Workflow。

## 6. Agent读取与写入的实际接口

### 6.1 读：领域语言 + 可核对来源

现在只复用三个封闭Tool：attention_list、task_draft、record_note_draft。后续若增加`student.get_summary`、`task.list`、`conversation.list`等，仅为候选命名；每个Tool必须先有typed DTO、用途、scope、返回上限、分页和来源测试。scope从当前认证上下文取得，不能由模型随意更改workspace/班/学期。

查询返回最小字段、`as_of`、版本/规则标识及耐久query receipt。模型需要更新信息时重新经QG查询；聊天历史只作上下文，不作当前统计依据。不存在`execute_sql`、任意表名、任意filter表达式、全库MCP、数据库URL或自由图查询工具。

现有`work_snapshot`会先读取完整activity（含记录正文）再计算计数/来源hash；长期数据增长后应改用专用受限SQL聚合/分页。索引、来源hash算法和结果完整性必须一起测试；改变source proof算法应显式版本化，不能静默沿用旧规则版本。

### 6.2 写：提议与提交分开

```text
Agent产生受限草稿
→ 可信UI核对对象/来源/字段
→ 原BCG schema/domain/risk/version校验
→ server preview → 必要approve → commit
→ 业务变更 + command receipt + audit (+ 后续change event)原子提交
→ QG重新读取 → 各页更新
```

当前R1的Agent没有直接业务写Tool，本提案不改变这一点。未来如单独批准低风险模型动作，也必须有特定purpose/command allowlist、受限授权、撤回、幂等和Eval；不能由“模型有能力”推导“模型获得权限”。Agent-readable不要求Agent拥有PG只读账号；经QG同样可以可靠读取并完成审计。

### 6.3 会话、SDK与长期记忆

Pydantic AI继续拥有loop和消息类型。ClassMatter拥有thread ID、授权、存储、来源和生命周期。优先复用当前锁版本的消息序列化/验证边界，不pickle，不用SDK内部任意对象作为稳定业务schema。

持久显示历史与模型history分开：显示可分页；模型只取当前许可的有界窗口，重建系统提示和Tool白名单，校验已失效来源，不重放旧approval/credential/未结束副作用。若缓存SDK消息，必须带sdk/schema/model配置版本，字段allowlist及字节上限；不兼容时丢弃派生缓存、从受控记录重建或要求新会话，不修改原消息。

官方将会话保存、运行checkpoint、跨会话Memory与durable execution区分；这支持我们的职责划分，但**不能证明当前锁定2.53.0具有最新文档的Conversation/StepPersistence等全部API**。具体适配先做锁版本兼容测试，不为了存聊天直接升级Harness或引入durable engine。[Pydantic AI Persistence](https://pydantic.dev/docs/ai/core-concepts/persistence/)。

## 7. JSONB、约束、索引与检索

- 身份键、scope、状态、版本、时间和高频筛选字段使用typed列、外键、CHECK/UNIQUE；不用一个JSONB保存整套业务世界。
- JSONB限于版本化、判别式、有限大小的message parts/工具摘要/已批准扩展元数据，先拒绝重复key、未知字段/类型和不合法值再入库。审批hash继续按现有canonical规则计算，不能依赖JSONB保留原始字节或key顺序；JSONB会折叠重复key。[PostgreSQL JSON类型](https://www.postgresql.org/docs/18/datatype-json.html)。
- 既有record采用修订追加；Task用expected_version CAS；删除/归档语义按各实体定义，不通用ON DELETE CASCADE清空所有历史。
- 候选索引：Task按workspace/class/term/status/due_at/task_id；记录按scope/student/record/version与时间查询；thread按workspace/owner/updated_at/thread_id；message按workspace/thread/ordinal；run按workspace/thread/state；变更按workspace/revision。先查现有索引，避免重复；以真实合成查询计划和数据规模决定新增。
- 列表采用稳定复合游标，排序含唯一ID；不靠OFFSET无限翻页，不用本页条数冒充总量。每个接口必须固定条数/文本/字节上限，不能一个活动查询无限加载全年记录和全部消息。
- 初期姓名/标题用受控精确/前缀/有限子串查询；通配符转义，不自动合并同名学生。中文分词、全文召回/排序要有本项目corpus再决定，不宣称PG默认配置已解决中文语义检索。[全文检索官方说明](https://www.postgresql.org/docs/18/textsearch-intro.html)。
- 向量索引若未来引入，是可删除重建的派生层，带原始对象版本与scope；原文更正/删除/权限撤回须使索引失效。向量相似不能确认事实或授予访问。

## 8. 实时同步：先真实，再及时，再可靠推送

### 8.1 不加新表即可先完成的绑定

沿用现有R1 API与typed clients，移植已确定交互，不把整个MockDomainStore接成数据库ORM。commit后核对receipt，再统一invalidate并经QG刷新所有相关视图；focus/visibility恢复和断网重连重新校验。没有网络时保留最后授权快照并显式标旧；禁写条件沿用queryFresh及服务端版本校验。禁止失败后回落fixture或静默创建空白新工作区。

自动刷新合并重复请求、后台暂停、有限退避；不能每个组件各自高频轮询，导致审计膨胀和锁竞争。刷新频率、数据量和延迟目标必须实测，不在本文编造SLO。

deadline经过时不一定有数据库写入；应用前台需在下一到期点或有界周期经QG重新评估，不能只等待change_event。关闭/离线时不承诺提醒送达；后台提醒与Scheduling仍需另行设计。

### 8.2 多个HTTP请求不是同一快照

现有global advisory lock使一个QG调用内的受控查询与审计串行；UI的多请求Promise.all不保证它们来自同一提交点。若需要同一页精确一致，新增**QG组合投影**或版本校验重读，不在UI拼出伪事务。

组合查询应在同一个受控事务内取得事实、计数和snapshot标识并耐久审计；允许审计写，不设成SQL READ ONLY。第一阶段保留现有READ COMMITTED与business lock，阻止受控写路径在组合查询中交错，不另改隔离级别。脱离该锁后，READ COMMITTED下多条SELECT可能可见不同提交，不能仅因“同连接”声称快照一致。[PostgreSQL隔离级别](https://www.postgresql.org/docs/18/transaction-iso.html)。

若未来缩锁并采用REPEATABLE READ，须在首条查询/取锁前设置；但取advisory lock的SELECT本身可能先建立快照再等待锁，解锁后时钟不代表该快照包含刚提交的最新数据。必须单独设计一致性与新鲜度的revision/重读策略，不能机械更换隔离级别。审计或冲突失败不释放结果，重试有界且不触发模型/业务写。

保留现有identity lease和business lock顺序；未来缩小锁粒度需要独立并发/死锁/撤销测试。当前NullPool还承担session advisory lock退出时关闭物理连接的安全语义，不能为吞吐直接替换成共享池。

### 8.3 需要耐久变更订阅时的最小候选

新增候选`workspace_change_clock(workspace_id, revision)`与`change_event(workspace_id, revision, event_id, actor/source_ref, aggregate_type/id/version, scope, created_at)`。事件只含受控引用/失效信息，不含师生正文、密钥或完整命令payload。两表不承载新的业务事实，不是完整Event Sourcing。

BCG在业务事务内按固定锁顺序更新workspace clock行、写业务/receipt/audit/change_event；clock行锁保持至提交，保证该workspace消费者的revision不会越过尚未提交的较早业务变化。已提交幂等重试只返回原收据，不产生第二个事件。

**禁止把BIGSERIAL/nextval最大值或客户端时钟当提交水位**：事务A先取小ID后晚提交，事务B大ID先提交会造成补读跳过A；sequence回滚也不归还号码。event_id可用UUID，消费者cursor绑定持久revision而非任意ID。[PostgreSQL sequence/事务语义](https://www.postgresql.org/docs/18/transaction-iso.html)。

后端订阅适配器通过QG重新鉴权、按允许scope分页读取change_event，向UI发送SSE invalidation；UI按scope/revision去重，再经QG取正式快照。重连用有界cursor补读，事件已按保留策略裁剪或scope改变则明确resync，重取快照；不得猜“没有变化”。多设备各有cursor，不能一个全局processed=true使另一设备漏消息。

跨scope的写事务/批量变更应原子分配一致revision；当前方案的workspace串行点适合首阶段规模，高吞吐/多角色需按实测另行设计，不能承诺无限伸缩。订阅是读取既有变化，不因读取自身写审计而递归产生新的业务invalidation；heartbeat与临时token delta也不逐条写业务变更日志。

### 8.4 NOTIFY只负责唤醒，不负责可靠性

可选PG LISTEN/NOTIFY作为后端进程的低延迟唤醒，不直接给renderer数据库连接。业务和change_event提交后，**另一个短事务best-effort NOTIFY**；通知失败不回滚已提交业务，由数据库补读/有界轮询兜底。这样不把通知队列满与业务commit可用性耦合。

不能依赖离线客户端收到NOTIFY；新监听先提交LISTEN，再做快照/补读，之后处理通知与重复。通知通道对数据库用户可见，所以只发无敏感意义的wake标记，不放学生/会话内容或权限令牌。当前NullPool不是常驻listener，实现时使用受控、可关闭的专用监听连接，重新连接后重新LISTEN。[NOTIFY](https://www.postgresql.org/docs/18/sql-notify.html)、[LISTEN](https://www.postgresql.org/docs/18/sql-listen.html)。

若后续有外部发送/文件发布等可靠副作用，再按已规划outbox引入单独delivery attempt/receipt和重试策略；不能把所有客户端消费、模型运行、业务审计混成一张万能event表。此阶段不引入Kafka、Redis或完整workflow引擎。

## 9. 授权与数据边界

- 当前三种DB登录角色：migrator、identity、runtime；Agent和renderer无角色/密码。QG由应用校验purpose/scope/身份，并在释放内容前确认审计。
- 当前并未因此拥有完整RLS：`rolbypassrls=false`不等于每表启用policy。未来多owner/学校场景可评估RLS作为纵深防御，owner/superuser bypass、FORCE、WITH CHECK和连接context重置必须验证；RLS不能替代应用鉴权、字段最小化和审计。[PG RLS](https://www.postgresql.org/docs/18/ddl-rowsecurity.html)。
- 新的chat/run表权限和append/终态update列需明确登记。不得给runtime整库DELETE、CREATE或任意表owner权以图省事；生命周期删除需独立命令和狭窄权限设计。
- SSE每次释放受限信息前重验身份/scope，撤销或切班立即停止旧订阅并清空不再可见投影；不长时间持有身份锁阻止注销。
- UI选择、工作专题、搜索结果和历史消息只描述上下文，不能给模型扩大班级范围、人物关系或组织权限。

## 10. 迁移、退出与恢复是新增表的前置

当前`schema_inventory`、`role_guards`、`operator_backup.HEAD`、8个core集合与退出验证器都是闭合实现。增加新表后若不一起更新，可能使启动/备份拒绝，或让导出遗漏新数据；这不是实现细节，必须进入验收。

每个新增持久实体需要同一变更单交付：

1. 独立的下一迁移revision（实施时按最新分支分配，不预占0017）、字段约束/索引和最小GRANT；不重写0001—0016。
2. `schema_inventory`、角色guard、迁移后的完整性/未知对象拒绝测试、备份head/packet兼容策略同步；不放宽为“任何表都允许”。
3. 新数据纳入退出profile、版本化schema和引用图；旧v1仍保持原core-only语义，不因文件存在就声称包含聊天。必要时新增v2 reader/writer兼容矩阵，不原地改变v1字段/hash语义。
4. 定义消息/运行/专题/事件的保留与删除/限制、审计、索引失效、恢复重放。保留期需按用途确认，不在提案中随意写永久或固定天数；缺治理决定时保持synthetic，不获真实数据准入。
5. 旧库→新库迁移、并发升级拒绝、重复执行、磁盘满/审计/commit故障、应用与schema不兼容、恢复旧包和新包分别验证。

回滚先关闭新功能/停写，使用兼容版本或已验证快照/前滚修复；不能删新表假装回滚且丢失聊天。新格式/新状态旧二进制不能读时须明确拒绝，不自动stamp或create_all修复。

跨机恢复是另一个完整闭环：在隔离新实例重建身份与凭据、校验包/引用、按批准映射保留来源actor、重放限制/删除/准入策略并核对计数/hash后才允许切换。旧session/approval/key不迁移为有效授权，旧未完成run/outbox默认隔离，不在新机自动继续执行。PG checkpoint同机DPAPI绑定和核心JSON复制核对不能替代这个流程。

## 11. 分阶段实施与追溯

| 阶段 | 范围与成果 | 可复用追溯 | 边界 |
| --- | --- | --- | --- |
| D0：真实业务页面绑定 | 同一套Student/Record/Task驱动首页/工作/学生/统计；提交后统一刷新、离线旧快照、scope隔离 | T-RWEB-002—004、T-RDOM-009/010/013；E-TSK/E-EVT/E-CMD/E-AUD既有目标 | 不新增表/Agent权限；不能声称所有Demo模块实现 |
| D1：下一版本耐久会话 | thread/turn/message/run/items与可信UI历史恢复，重启有明确终态 | 参考T-RAGT-001—004边界；新增需求/Eval/task须另建release/change | 超出R1短期Memory；必须先补生命周期/退出/迁移设计 |
| D2：工作专题与关联 | 已验证需要的专题、会话/任务关联及派生统计 | 沿长期Ontology/ADR-008—010原则，尚无本单元正式ID | 不把安全workspace重定义，不做所有对象万能关联 |
| D3：可靠业务变更流 | clock/change_event、SSE补读、跨窗口一致与恢复 | 参考现有outbox/审计/可恢复性原则；新增契约/故障Eval另建 | 轮询/收据刷新先行，未测量前不增加消息平台 |
| Future | 通知责任、长期偏好/知识/Artifact、关系/多角色、向量检索、扩展 | 现有长期需求/后续独立release | 不是R1承诺，不因本设计提前建表/授权 |

顺序不是先造完D1—D3数据库再接UI：D0首先交付真实端到端闭环；随后每个阶段都按“需求/验收→domain/契约→必要迁移→QG/BCG→UI→故障测试→review”推进。D1/D2是否交换由实际教师操作证据决定，优先级是工程建议，不是validated user requirement。

D0首单元落点：沿`apps/web/src/runtime/{api.ts,work-projection.ts,student-directory.ts,R1App.tsx}`与现有identity/command-receipt clients提取必要表现接口，将已确认主界面上的学生/任务/统计逐页绑定；保留布局和交互，不为了清洁重写prototype。不能仅另开简化R1页面就宣布完整Demo已接通，也不能把MockDomainStore直接当repository。新增统一刷新只调用已存在API，不增加模型网络权限；未来模块用明确未接入状态，不给fixture兜底。

验收落在`apps/web/tests/runtime.mjs`、`backend/tests/test_web.py`、`apps/desktop/tests/runtime-integration.cjs`及现有gateway测试。先用测试自有一次性PG证明；用户可运行实例另有显式初始化/owner交互与进程自检，不自动迁移当前机器的旧数据或替用户设密码。该单元的成功是“一个真实闭环”，不是本提案所有候选表已交付。

## 12. 验收矩阵（设计要求，尚非执行成绩）

下列`DB-*`只为本提案定位验收条目，不是正式Eval或Gate ID。

| 编号 | 场景 | 必须证明 |
| --- | --- | --- |
| DB-01 | 学生→记录→任务→首页/学生/总览→重启 | 真实API/PG、同一scope/版本、一份事实多视图；无mock fallback |
| DB-02 | 同请求重复发送/两窗口同时更改 | 一次turn/一次业务提交；不同payload复用key拒绝，旧expected_version冲突可解释 |
| DB-03 | 会话恢复与权限变化 | 历史可读但来源不当当前事实；跨owner/班/学期拒绝，旧订阅不泄露，SDK上下文无凭据 |
| DB-04 | Provider超时/取消/进程崩溃/终态写失败 | 保留输入及明确状态，usage未知为null；不假完成、不自动付费重跑、不重复业务写 |
| DB-05 | A早分配ID晚提交，B晚分配早提交 | revision补读不漏A；rollback/幂等无假事件，NOTIFY丢失仍能恢复 |
| DB-06 | 刷新中断/乱序/事件裁剪/切scope | 旧快照显式标注、无错误写/假数据；过期cursor full resync；同一组合投影一致 |
| DB-07 | 时间经过deadline但没有数据库写入 | 到期视图按时钟重新评估，不依赖change_event才显示逾期，不自动推导责任 |
| DB-08 | 非法JSON/未知Tool/超限输出/越权SQL意图 | typed拒绝、有限资源、无新DB权限/DDL，审计失败不释放内容 |
| DB-09 | 新旧schema/退出包/备份/恢复 | 所有新store有归属及导出；旧包能力明确，限制/删除不复活，源库不被试验覆盖 |
| DB-10 | 数据量/搜索/后台多窗口 | 稳定分页、总数独立计算、索引EXPLAIN；无无限读/轮询/审计膨胀，不编造性能结论 |
| DB-11 | Agent-off与合成模式 | 直接UI全链可用，fake模型标签清楚；合成内容走真实持久化，不引入真实师生或费用 |
| DB-12 | 教师净负担 | 对照完成步骤/主动录入/修订/等待/恢复成本；不要求手记UUID/重复维护三个列表 |

可执行基线：复用现有真实Web/PG/Electron、gateway、identity、exit和backup测试；新增chat/stream故障注入只允许固定合成数据。性能与教师价值暂未运行；不以文档、框架能力或合成测试升级正式Gate。

## 13. 风险与待决事项

| 问题 | 当前处理 | 进入实现前需要 |
| --- | --- | --- |
| 长期聊天保存涉及R1认识论/保留边界 | 仅后续release提案 | 明确保留/删除、来源及AI文本权威标记、新退出profile |
| PG桌面运维负担 | 复用现有同机开发profile，不声称已打包 | 首次安装/owner设置/升级失败/异常退出恢复的可操作原型 |
| global lock与全量activity增长 | 保留安全语义，先量测 | 合成长期数据查询计划、审计负载；必要时独立缩锁/投影设计 |
| 消息、run和业务receipt关联复杂 | run状态与业务提交状态分开 | 断线/取消/未知结果UI验收，不能把“模型完成”当“业务已保存” |
| 工作专题真实频率/跨专题复用 | 明确为hypothesis | 教师典型任务对照，不预建所有关系表 |
| 最新SDK文档与锁版本不一致 | 不升级、不复制未经验证API | 以2.53.0兼容测试验证序列化/恢复；新特性单独选型 |
| 多人/多学校/RLS | 只留正确scope/身份引用 | 独立授权模型、连接隔离、负向测试和新release |

本轮仅交付设计与源码核验，没有数据库迁移、索引基准、实际跨机恢复、真实Provider或用户研究结果。保留PG不等于所有后续设计已接受；可先按现有R1权限推进D0，不把本提案全部内容塞入第一实施单元。

## 14. 官方资料与来源边界

资料于2026-10-23访问，只据公开技术语义制定候选方案；没有引入外部源代码或依赖，没有把上游文档当作本项目验收证据。

- [PG18事务隔离](https://www.postgresql.org/docs/18/transaction-iso.html)：快照、sequence与并发设计依据。
- [PG18 JSON类型](https://www.postgresql.org/docs/18/datatype-json.html)：typed列/JSONB职责及canonical字节边界。
- [PG18 RLS](https://www.postgresql.org/docs/18/ddl-rowsecurity.html)：纵深防御及owner bypass限制。
- [PG18 LISTEN](https://www.postgresql.org/docs/18/sql-listen.html)、[NOTIFY](https://www.postgresql.org/docs/18/sql-notify.html)：监听竞态、提交与通知语义。
- [SQLite WAL](https://www.sqlite.org/wal.html)：单机打包替代与部署约束。
- [Pydantic AI Persistence](https://pydantic.dev/docs/ai/core-concepts/persistence/)：会话、运行和Memory职责划分；不是锁版本API保证。
- [PG18全文检索](https://www.postgresql.org/docs/18/textsearch-intro.html)：搜索方案与语言配置须实际验证。
