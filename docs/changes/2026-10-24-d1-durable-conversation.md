# D1：耐久会话实施变更

日期：2026-10-24。状态：用户已确认合成开发方向；实施中，未验收。继承[数据库演进设计](../design/database-live-data-design.md)的D1，而非另建产品或替换Harness。冻结[R1](../specs/class-os-v1/release-1-manifest.md)、107/147/94定义与正式Gate不变；本文件的D1-*是后续开发追溯，不表示正式准入。只用合成数据，无Agent业务写工具、真实数据、自动付费或隐式迁移。

## 目标和验收

| 开发需求 | 必须证明 | 最小实施/验收单元 |
| --- | --- | --- |
| D1-01 | 会话列表、新建、改名、归档和打开来自当前授权数据库，刷新/进程重启后身份及内容稳定 | typed会话/消息模型、QG/BCG、真实Web/PG |
| D1-02 | 同一发送请求只保存一次输入且最多启动一次运行；相同键不同正文拒绝 | turn请求哈希/唯一约束、实际并发和回执丢失测试 |
| D1-03 | 输入先耐久保存，再调用原Pydantic AI；终态及可见输出写入/审计成功后才显示已保存 | 应用编排复用原SDK adapter；存储/审计故障不得假完成或自动付费重跑 |
| D1-04 | 完成/失败/取消/中断/未知与业务保存状态分开；旧worker不能覆盖新状态 | 固定run状态、版本/CAS、attempt fencing、有限lease和重启恢复测试 |
| D1-05 | 会话固定owner/workspace/class/term及可选student；旧会话/越scope拒绝，历史不恢复旧批准或旧授权 | 原ISB/QG/BCG复验，复合作用域外键和身份负向测试 |
| D1-06 | 用户可见历史可恢复，SDK上下文仍有界并按当前权限重建；历史AI文本非当前事实 | 不存raw SDK dump、隐藏推理、cookie、配置密钥、SQL或批准；每次工作查询仍新读QG |
| D1-07 | 新store进入受控schema/角色清单、同机备份核对及版本化退出；旧包能力不静默改变 | 显式迁移、旧新库/包兼容、失败回滚及真实重启/恢复测试 |
| D1-08 | 归档不冒称删除；明确清除/限制对历史正文、运行和上下文的作用，不能经恢复复活已限制内容 | 原事实/任务不受聊天清除影响；无真实数据准入前不任意设定真实保留期限 |
| D1-09 | 仍用原界面布局/底部输入；会话切换不丢未确认业务操作，不重复Teacher维护 | 真实浏览器/桌面、未知结果/取消/切scope/断线矩阵；操作步骤对照 |

## 最小架构和文件级顺序

1. 存储与生命周期：`domain/durable_conversation.py`封闭消息/发送意图/run规则；独立迁移revision、`schema_inventory`及角色guard；必要的backup/exit版本适配；合成数据库测试。不重写旧migration，不把一份万能JSON当所有对象。
2. 服务：固定Conversation handler挂在BCG，读取在QG；`infrastructure/durable_conversation.py`仅执行拥有者固定SQL。HTTP不得直接操作repository；模型只拿现有读/草稿能力。应用编排持有业务Gateway以保存交互证据，不把它交给LLM或Skill。
3. 接线：HTTP typed DTO/派生契约、runtime客户端、现有R1会话区的显式D1开发能力及真实UI测试。D1未接受前，默认R1 composition/migrate/readiness继续拒绝未知schema，不因Alembic出现新head隐式升级用户实例。
4. 工程交付：每单元独立review/PR、内容来源审核/真实SHA/public_guard/历史scan/docs及完整两平台CI；不能只靠内存测试或文档宣布耐久会话完成。

消息使用原始受控文本及明确origin；AI内容始终`assistant-unverified`。发送是保存本轮用户输入/请求运行的意图，不是批准消息描述的学生变更。第一切片不提供历史消息原地覆写、任意分叉、跨班搬移、附件/Office、长期画像、自动Skill或多Agent。

固定run序列为queued/running/cancel_requested到completed/failed/cancelled/interrupted/unknown。取消请求不是取消成功；lease过期只说明本应用不再接受旧运行完成，不说明供应商没有计费。终态写失败保留可核对未知状态，不自动创建新attempt。历史source receipt只是当时来源，不当当前统计依据。

## 兼容、回滚和待证据

普通R1仍为head0016/原22表；D1需要明确的开发profile与迁移入口，旧二进制遇新格式必须拒绝，不stamp、不删除新表“回滚”。新store的导出/backup/限制语义未完成前，不启用其持久运行入口。具体新revision以实施时最新main为准，不提前占号。仅同机DPAPI checkpoint不等于跨机恢复，核心v1退出包不能冒称含会话。

用户已允许创建全新R1合成实例，Owner本人稍后设置；此授权不等于默许将该实例自动升级到D1。D1先用自有临时fixture验收，实际迁移/激活仍需显式操作。真实Provider价格/费用前置仍独立阻塞，不妨碍离线合成SDK/数据库/UI工程测试；此轮没有真实模型质量或教师净减负实证。

后续文书切片已选“班级工作小结，引用已有事实与任务”，取代此前纯主题班会提纲候选。先验证受控来源→可编辑草稿→人工保留/导出，不自动对外发送、不把观察改为事实、不判断学校责任；它不是D1本身或R1新增工具。

## D1-00：先行规则与默认迁移保护（实施中）

本单元只有`domain/durable_conversation.py`及单元测试、`persistence/database.py`及实际PG迁移回归。没有新表/持久repository/HTTP/UI/SDK接线，不能宣称D1-01—09已经完成。域对象不持有授权或执行能力；`SendIntent`精确哈希包括scope/thread、原文、既有read/draft/chat mode及task/record-note类型。同键不同payload拒绝，跨scope不能当重放；真实幂等/唯一键/并发仍须后续数据库单元证明。

`VisibleMessage`只允许user-original或assistant-unverified的有限纯文本，不接任意SDK对象、Tool/system消息。字符/字节校验不是秘密检测或事实核验；未来可信入口仍须执行数据分类及最小化，不能承诺能识别用户主动粘贴的所有秘密。尚无长期历史保存或模型上下文回放。

run规则固定queued/running/cancel_requested与五类终态；有版本前置、worker generation、有界lease、精确到期拒绝和中断恢复。排队取消不会dispatch；取消请求不假称已取消，也不接受迟到完成。规则返回新不可变值，必须由后续BCG适配器在同一事务内用数据库CAS和审计执行；仅调用纯函数不等于已保存、并发安全或Provider未计费。这里不重写SDK loop或引入新的Agent框架。

默认`migrate`显式目标0016，已知revision只接受0016祖先，不再升级任意未来Alembic head。当前原22表清单与权限不变；新profile入口仍未开放。实际一次性PG测试证明重复升级的固定目标、即使未来脚本已知也拒绝其revision且保留原marker，以及原0015非空库升级的记录/批准/列权限兼容。代码回滚只需revert本单元，无新schema或用户实例操作；新schema将来的回退不能因此简化成revert。

本地组合回归43通过13.69秒。独立对抗审查发现并修复两项纯规则缺陷：直接重建终态也必须校验lease边界；增加cancel_requested_at，终态不得早于取消请求，重复请求也不得倒退时钟。新增非法持久行和取消/迟到竞争测试，不修改原数据/权限。全套非DB、公开检查和两平台CI须按最终版本再次核验。

验收状态以该单元PR和真实测试日志为准；完整D1的存储/生命周期/出口/应用/UI验收继续待实施，不改变正式R1 Gate或把合成研究当已验证产品优先级。

## D1-10：显式存储profile基础（文件级计划）

新Goal按独立单元推进。本单元基于已合并D1-00的main，不修改其规则，也不把所有剩余能力塞入一次PR。

| 文件 | 修改和验收 |
| --- | --- |
| `backend/db/migrations/versions/0017_durable_conversation.py` | 新建四张有作用域外键的thread/turn/message/run表，有限列、状态、来源、幂等键和运行槽唯一约束；不建万能JSON、任意SDK缓存或自动执行表 |
| `persistence/schema_inventory.py` | 原r1清单/0016保持原样；另建明确conversation-d1清单/0017，未知profile和对象拒绝 |
| `persistence/database.py` | Database显式选择开发schema profile；普通调用仍停0016，不因新head升级R1；未来D1 revision不反向降级 |
| `persistence/role_guards.py` | 按精确profile核对表族，新表identity零访问、runtime有限列UPDATE，无DELETE/TRUNCATE/DDL；默认不宽松匹配所有新表 |
| `infrastructure/exit_package.py`、`tests/test_exit_read_limits.py` | 核心v1源读取/下载前明确拒绝非0016，避免新增store被漏导；原LIMIT上限/不得发布部分包的负向断言不削弱 |
| `backend/tests/test_durable_conversation_storage.py` | 隔离真实PG验证非空R1升级/重复执行/默认拒绝D1、跨scope外键、消息来源/大小、幂等键、单运行槽、时间边界、列权限；不使用用户实例 |
| 本变更单、实现台账、公开审计/manifest | 只记实际工程证据；新文件先审核来源再登记真实SHA；完整两平台CI和独立对抗审查 |

四表暂不向HTTP、模型或现有桌面composition开放；这不是耐久会话已可用。新schema只由显式profile的测试/受信迁移入口使用，默认R1 readiness/backup/exit仍拒绝它，防止核心v1包漏导聊天而假称完整。后续独立单元必须先补版本化备份/退出/恢复及清除一致性，再接QG/BCG和UI；不在当前用户新实例上尝试升级。SQL结构约束不代替应用鉴权、事务CAS、审计或数据分类，临时fixture写入不构成Agent写权限。

初轮新存储25项通过65.81秒；补核心退出拒绝、合法成员ID不能交叉配对和空白正文后，存储/既有inventory/0015非空升级组合37项通过94.04秒。全非DB338通过、2项宿主链接策略跳过。最后新增精确列清单/多余列权限拒绝后的重跑与完整CI待核验，不能复用早一版本成绩。独立审查未发现阻断基础单元的问题；特别保留限制：当前DDL不能独自保证cleared thread下所有正文已清除，也不阻止可信SQL重新置visible。下一生命周期单元须原子化实现并校验恢复不复活，不把DDL成绩当完成该语义。正式R1定义和Gate不变。

## 新Goal的工程完成条件

Goal状态active，按独立单元持续推进：D1-10存储基础→版本化生命周期/退出/备份/恢复→QG/BCG/ISB与真实会话UI/原SDK接线→班级工作小结纵向切片。每一单元实际验收、独立对抗复核、精确公开清单及两平台CI通过后再收口；所有相关代码/必要文档同步GitHub后才能标记工程完成。用户本人Owner设置、真实Provider配置/有效价格/费用授权及人工质量评估仍为外部待验证，不用测试Owner、fake模型或绿色CI冒充。

最终合成工程必须证明：刷新/业务与PG进程重启恢复相同内容和scope；重复发送/回执丢失不会重复运行；过期scope/撤权拒绝；取消/超时/迟到worker/终态保存故障不假成功；新store有受控退出/恢复及清除防复活；工作小结只引用当前QG事实/任务，观察/AI推断不晋升事实，产物可编辑且不自动发送。真实教师减负效果保持discovery，不以工程验收代替用户研究。

## D1-11a：显式profile快照核验（文件级计划）

D1-10已由PR #19在最终两平台CI40063379109通过后合并。恢复先拆出一个可运行、不可激活的checkpoint单元，随后实现备份外限制水位＋BCG清除，再做typed退出/新身份恢复；不是删去后续验收。

- `infrastructure/operator_backup.py`：显式选择r1或conversation-d1，复用原快照/DPAPI/原子发布/临时clone清理；D1使用独立包格式、head/表清单和profile绑定。旧v1结构/默认调用语义不变。D1结果只证明snapshot完整性，固定activation_allowed=false，不提供恢复激活或模型调度。
- `infrastructure/conversation_integrity.py`：固定关系/来源/清除一致性检查；孤立turn、终态/可见消息不符、cleared正文残留或归档中的active run拒绝。它不证明限制水位新鲜，也不阻止可信SQL绕过应用层。
- `tests/test_conversation_backup.py`：真实dump/clone对比包含26表；source/已存在备份不变；跨profile、坏元数据/ACL/不一致内容拒绝；active run仍无恢复激活；fixture codec不冒称加密，Windows实际DPAPI另验。
- 变更单/台账/公开审计和manifest：只登记实际来源和结果；独立审查、历史scan、完整两平台CI。

重要限制：旧快照可能含清除前正文，不能声称物理抹除。仅把tombstone也放在同一备份里不能防回滚复活；下一单元需要备份之外的当前限制证明，缺失/损坏/无法确认新鲜度时拒绝激活。这个checkpoint API既不释放正文，也不启动服务/导入业务/接受任何激活标志；正式恢复仍未交付。用户实例和R1默认不变。

本单元初轮16项通过58.84秒，增加clone ACL变宽拒绝后17项通过68.86秒；既有R1 backup/recovery组合35通过、1项宿主链接策略跳过113.61秒。最后补“检查清除前旧快照后当前受限库不变”的实际对比，最终重跑和完整CI仍待收口。独立审查未发现本范围阻断问题；关系检查依赖已登记FK/UNIQUE/CHECK，并非任意DDL篡改指纹验证。清除处理器也不能为通过checkpoint而提前假报interrupted/cancelled。

PR #20 已以最终 head ce0a2c7、两平台 CI 40064737955 验收，合并 main 71b6a41：Windows 非 DB341/Web55/desktop23；Ubuntu 非 DB339+2跳过、真实PG/browser356+7跳过。以上“待收口”为历史过程，不代表当前仍在等待该轮CI；仍不允许D1恢复激活。

## D1-11b1：备份外限制记录适配器（文件级计划）

后续验收补记：PR #22最终68cfc37经CI40078603025两平台成功合并为main91a47a1；Windows非DB385/Web55/desktop23，Ubuntu非DB382+3跳过、实际PG/browser356+7跳过。独立审查657真实hash及专项42通过2宿主链接跳过均核验。它只完成适配器，以下集成是新单元。

## D1-11b2：数据库锚点和BCG清除（文件级计划）

目标：真实受控清除和读取拒绝闭环；不是恢复激活或完整耐久聊天UI。

- 新建`0018_conversation_control.py`：D1专用有限control锚点，authority/owner不可更新、epoch/hash有限更新，无DELETE/DDL；只在D1登记两种命令与独立人工高风险策略。原R1 schema/default/risk表不变。
- `schema_inventory.py`、`role_guards.py`、原存储/备份测试：D1显式0018/27表；拒绝未知列/权限。旧0017 D1开发快照不自动升级/激活；R1/v1退出备份保持原样。
- 新`domain/conversation_control.py`、`application/conversation_control.py`、`infrastructure/conversation_control.py`：封闭初始化/清除命令和有界历史DTO；复用原BCG预览、批准、回执、ISB认证租约和业务锁；近期认证在锁后重新检查。外部标记先行，数据库原子清正文/通用标题、fence活动run、锚点、回执与审计。文件ahead保留，只允许同一待清除线程/版本重试，QG读正文前要求精确对齐。
- `application/roster.py`、`infrastructure/roster.py`：提取默认行为不变的固定解码/策略/用途/事务工厂扩展点；R1闭合解码器与HTTP契约不增加命令。不得把新BCG注入Agent。
- 新`tests/test_conversation_control.py`：合成真实PG与受保护临时文件，验证清除、重试/并发、scope/近期认证/批准、文件/审计失败、旧DB锚点拒绝读取、活动run真实终态与旧worker CAS拒绝、事实/任务不变；R1负向回归。
- 只更新现有变更单/台账/审计/真实manifest；独立对抗审查、公开/历史scan/docs及完整两平台CI。正式107/147/94与Gate不变。

初始化是人工批准的BCG操作，要求无旧锚点且无会话；不得由QG缺失文件自动重建。文件写成但数据库回滚时，只能重试同authority的空初始证据。普通clear不假称Provider已取消：lease未到使用unknown、lease已到使用interrupted，queued才可直接cancelled。源旧备份仍不可激活；本单元不恢复身份/业务包，不实现SDK RAM清理或对外发消息。用户实例不迁移。回滚不得删除或倒退已存在的限制文件；新schema只能受控forward-fix或停用profile，不能破坏性downgrade。

## D1-11b1历史详情（以下未交付结论为当时范围）

目标是为后续BCG清除提供不随PostgreSQL快照回滚的受控限制证据，而不是新增业务写入口或宣称清除已交付。先独立验收文件原子性和封闭协议，再接BCG/数据库锚点，避免同时改变身份、写入和恢复边界。

| 文件 | 本单元范围和验收 |
| --- | --- |
| `infrastructure/conversation_restrictions.py` | 固定文件名/可信根目录、workspace/authority/root绑定、有限清除标记、DPAPI；互斥文件锁、期望head比较、临时文件fsync与原子替换；只允许初建和追加，不支持删除/降水位/导入/任意JSON |
| `backend/tests/test_conversation_restrictions.py` | 合成临时目录：重开、陈旧head、单步未完成识别、多步/缺失/损坏/异scope拒绝、并发进程、写入前后故障、链接/大小/未知字段；Windows实际DPAPI与跨平台fixture codec分别验证 |
| 本变更单、实现台账、PUBLIC_AUDIT/manifest | 更新明确未交付边界，实际hash/测试/审查与两平台CI；无正式Requirement/Eval/Task/Gate变化 |

此适配器没有HTTP/CLI/Agent入口，不启动模型、不释放正文，不访问或修改用户实例/数据库。head是待数据库锚点保存和比对的值，不是授权凭据。初始化只能由未来受信composition在已验证全新D1存储上调用；不得在已有锚点而文件遗失时自动重建。单步超前只供后续同一已批准clear的恢复判断，不能自动宣称提交成功或允许读取。

文件锁只序列化本适配器的跨进程操作；BCG仍须现有业务锁、身份/作用域校验、版本CAS、批准/幂等回执和事务审计。先持久化限制标记、后提交数据库；后者失败时保留标记并拒绝历史读取，不能撤回限制来换取可用性。读取、上下文准备与最终答复放行都需要后续明确接线。整个主机文件系统及数据库同时恶意回滚无法靠同机文件证明新鲜度；离线旧包也不能自证没有后续清除。缺少当前证明就不激活，不承诺物理擦除或可信硬件/远端防回滚。旧R1默认、0017表结构、原备份结构、SDK和正式Gate不变。

本机专项最终42通过、2项宿主symlink限制跳过3.79秒（包含实际Windows DPAPI、两个进程同一head只能一个推进、子进程持锁硬退出后证据不变与锁释放、replace前/后故障）；最终全非DB381通过4跳过、363 DB项未在该轮运行31.32秒。root81、docs73/UTF8/链接、公开license检查、固定scanner8.30.1文件及历史4已审查0未解决，107/147/94与formalgreen0保持不变；完整两平台CI仍待最终head验收。独立对抗审查未发现本端口范围阻断；其独立运行41通过2跳过发生于最后一个硬退出用例加入前，不冒称该用例已被独立重跑。生成的XML和受保护文件仅在忽略的合成临时目录，不公开。

明确保留两项运维约束：初次排他link后若硬退出导致临时硬链接未清理，读取会因nlink不为1而安全拒绝；本单元不提供自动修复或重置authority，后续集成须增加受控诊断/修复。4096条为硬容量上限，达到后明确拒绝追加；不得自动裁剪既有限制或更换authority。只验证内核锁释放不能声称所有崩溃都能自动恢复，更不能宣称物理断电耐久性。正式BCG清除/数据库锚点/防业务恢复复活尚未实现。

本单元回滚为revert其代码/测试/必要说明，没有迁移或用户实例变更。已经生成的限制证据必须保留，不通过删除文件、重建authority或回退水位来“恢复可用”；未来任何使用该格式的集成均须先证明与数据库锚点一致。当前尚无该类消费者，不提升任何正式Gate。

最终提交前已整合独立Logo登记PR #21的新main dc69e7a，两处公开审计/manifest插入冲突逐项保留两单元内容并重算最终字节SHA；root81、docs74及原public_guard再次通过，没有覆盖并发业务代码。原桌面工作区R1App的17增/3删保持原样；已运行的用户合成实例仍停原R1基线，ready不等于Owner设置完成。本单元未触碰该实例。

## D1-11b2实际实现与候选证据

已实现计划内锚点、近期认证/人工批准清除及只读历史适配器，均未向现有HTTP/CLI/Agent/UI注册。共享Proposal的类型注解补充D1值类型，但原R1解码器、风险表与wire契约保持闭合；默认Gateway用途/策略提取为等价扩展点，旧R1仍不接受新命令。初始化要求无历史，不要求老师维护UUID或限制文件；未来启用流程仍需单独验证净负担，不宣称现有UI已提供该能力。

真实临时PostgreSQL专项最终24通过92.32秒，包含实际Windows DPAPI+PG组合、文件损坏拒读、初始化/清除审批、审计/SQL/文件回执故障、run UPDATE为0行拒绝假成功、幂等并发、近期认证在不同阶段过期、错误scope、pending不可用于另一线程、事实/任务字节不变、unknown/interrupted/cancelled真实边界及旧worker CAS为0行。完整历史按最后50个完整turn截取（最多100消息），固定ordinal和user→assistant顺序；同时间戳逆UUID/51turn边界已实测。全非DB最终382通过4宿主跳过、386 DB项未在该轮执行39.55秒。原Gateway/事实任务/回执/查询/模型控制、D1存储与实际checkpoint组合87通过243.46秒；最终全平台CI仍须按PR head核验，不用这些局部成绩冒充完整验收。原始XML/运行态均忽略，不公开。

两项对抗发现已修复并有真实PG回归：不能依赖消息时间/随机UUID排序；即使文件与anchor对齐，也须核对该thread已有ClearMarker与SQL cleared/version/cleared_at，部分旧正文回填亦拒读。SQL fence/正文/标题/锚点/回执/批准消费/审计全部在原BCG事务，外部标记保留于回滚之外。所有关键UPDATE检查预期行数，不能把0行写入当成功。

追溯变化明确限定为本post-R1开发变更及新工程测试；没有新增/更改正式Requirement、147 Eval、94 Task或Gate结果。旧D1 profile从0017演进至明确0018/27表；checkpoint必须包含control表，缺少owner锚点的会话快照拒绝。备份fixture通过真实BCG初始化锚点，不用直接SQL假冒业务操作；原R1/v1出口与默认22表不变。未知/旧D1包仍不激活，已有0017历史不被自动生成外部证明，也不由QG初始化“修复”。

剩余边界：尚无SDK上下文/迟到输出放行接线、跨机新身份typed恢复、业务包导入或真实耐久聊天UI。QG限制校验只证明当前受控读取事务，不代替未来SDK终态输出前复核。完整主机回滚、硬链接残留的受控修复、容量演进仍需后续单元；不假称物理删除、Provider取消或全生命周期完成。用户Owner/真实Provider外部条件不改变，Goal保持未完成。

独立审计最终重跑24/24通过78.97秒，无剩余阻断发现；root81、docs74/UTF8/本地链接与public_guard/license通过，107/147/94及formalgreen0不变。公开安全和CI需以最终提交再次核验，PR记录承载最终远端结果，不将本地/独立成绩外推为完整发布准入。

PR #23最终de409a3已由CI40081114526两平台验收合并为main b177567：Windows非DB386/Web55/desktop23；Ubuntu非DB383+3跳过、实际PG/browser378+8跳过。下个单元不得重写其迁移或把候选历史当当前状态。

## D1-12：版本化出口闭环（文件级计划）

目标是让8类core和5类conversation/control集合实际可受控导出、下载、离线校验，为随后typed导入与新身份恢复提供完整输入；不是把可读包冒充可激活恢复。本单元不缩减完整Goal。

- 新`domain/conversation_exit.py`：封闭v2格式、13类固定集合、字段/关系/来源/时间/限制证据校验、有界字节与记录数；复用现有core校验而不放宽v1。身份/批准/SDK对象和运行权限明确不迁移，run仅为源证据，checksum不是来源认证或当前准入。
- 新`infrastructure/conversation_exit.py`、`application/conversation_exit.py`：复用原ISB/BCG批准/幂等/audit和QG；预览哈希只含稳定业务快照及当前限制证据，不因自身audit变化失效。集合读取前做有限列的字节/数量预检，禁止越权读取audit的session_digest。下载前重新核对当前限制head，清除/损坏/未收口时拒绝释放旧包；任一步失败不保存部分包或假回执。
- 新`0019_conversation_exit.py`及现有D1 profile/store/version测试：只在显式D1中允许独立高风险export命令、两条audit action、v2 export_job；不增表或角色权限，不修改原迁移/默认R1。D1明确0019/27表，v1仍仅0016。
- `domain/roster.py`仅补充共享Proposal类型，`application/conversation_control.py`提取等价近期认证检查，`infrastructure/conversation_control.py`增加固定事务工厂便于复用；不向HTTP/CLI业务执行器/Agent开放导出命令。
- `backend/verify_exit.py`：显式profile选择，默认v1；v2只做离线完整性/源快照对比，拒绝require-complete，永不导入/激活。不能自动把格式变化当来源可信或迁移成功。
- 新纯格式/真实PG/离线进程测试：包含AI回复未验证来源、活动run证据不得续跑、清除后旧artifact拒读、新artifact只含受限正文、scope/角色、审批/幂等/时效/审计故障、缺失/多余/关联错误/过大/乱码包、原v1回归；然后独立审计、真实manifest、历史scan/docs及最终两平台CI。

恢复仍必须独立实现：新Owner/空目标、明确来源和当前限制证明、source author与target restorer分离、原audit仅源证据、所有INSERT经BCG、active run隔离且不自动dispatch。无法证明当前限制新鲜度的离线旧包不可激活；整机回滚/物理删除不作虚假承诺。源码回滚不能降级已显式迁移的D1数据库；停用profile/forward-fix且保留限制文件。当前用户实例、正式107/147/94与Gate不变。

## D1-12实际实现与候选证据

上述13集合出口、BCG生成/QG下载及离线显式v2检查已实现。所有新源/测试/迁移为首方内容，fixture仅合成；无新依赖、公开例外或用户实例变更。复用既有退出/运维目标作为工程追溯，不新增或改写正式Requirement/Eval/Task/Gate语义或结果。日常教师操作为零；未来入口预计一次预览批准/下载，不要求老师再录入已有信息，真实净负担尚待入口原型验证。

实际PG测试发现未发布迁移草稿误选同表CHECK名称，已改为仅替换0018的风险约束，增加0018→0019对其余payload/权限约束定义逐项保持的回归。原R1拒绝未知命令时暴露activity属性访问异常，`application/activity.py`增加原9种活动命令的精确类型白名单，未知命令先拒绝，不改变任何原准入类型。artifact过期测试需保持ISB会话活跃才能真正到达30分钟出口失效检查，已用原QG读维持而非放宽会话策略。

独立对抗审查发现marker只向前核对thread，未反向检查孤立marker；现按D1不删除thread的既有语义要求每条marker引用已导出thread，并加入重算两层hash后仍拒绝的负向用例。初轮独立纯格式+PG42通过48.62秒；修复后独立纯格式32通过0.33秒。最终本机新旧v1/v2/CLI/活动领域组合125通过、1项平台跳过57.39秒；全非DB414通过4项宿主能力跳过、397项DB未在该命令执行35.89秒。前一条旧版回归因漏传`--pg-root`产生2个fixture错误，不计为通过；此处125组合已带真实PG参数重跑。

当前无新API/Tool、导入、激活或worker接线。下载前限制proof必须与当前源一致，但不能撤回已下载副本，也不物理擦除export_job旧字节。1MiB/每集合10000行硬上限超限拒绝而非部分导出；未提供大规模分片/裁剪。源码revert不能无损降级已迁移D1，保留文件/停用profile或前滚。后续完整恢复和耐久UI仍未完成，不能因此宣布Goal通过。最终公开哈希、历史扫描、完整两平台CI及PR按实际证据收口。

D1-12最终由PR #24在两平台CI40083796925通过后合并main e8fb126：Windows非DB418/Web55/desktop23，Ubuntu非DB415+3跳过、实际PG/browser388+9跳过。独立复算668项hash；源工作树与验收main内容一致。以上候选文字为阶段历史。

## D1-13a：恢复快照当前限制核对（文件级计划）

目标：恢复准备不能把清除前旧checkpoint的结构完整，当成当前限制仍兼容；不以本单元替代新身份typed导入和后续耐久UI目标。

- `operator_backup.py`复用原临时clone/精确inventory/ACL/清理，新增显式`check_current_restrictions`，仅D1可用。受信operator绑定本runtime根目录及workspace，从源DB锚点与备份外文件读取当前证明；恢复clone必须具有同一head及一致清除关系，检查后再读源证明，变化/缺失/pending/损坏拒绝。不输出正文，不返回激活授权，不接受调用者提供的proof或路径。
- `conversation_integrity.py`新增固定anchor/marker/thread双向关系核对，供源/clone复用；不修改R1规则、QG/BCG或既有check输出，不读凭据或更改业务行。
- 新`test_conversation_backup_restrictions.py`走真实PG/原BCG清除/实际pg_restore，证明旧包拒绝、新包匹配、部分回滚/孤立标记/缺文件/检查期间推进/还原失败均不假成功，源库与原包保留且临时clone清理；Windows实际DPAPI另测。
- 更新原README/台账/本变更与公开审查/真实manifest；复用既有退出与运维目标，仅增加post-R1工程证据，不改正式Requirement/Eval/Task/Gate。最终独立审查、扫描、完整两平台CI后交付独立PR。

该结果只表示检查时点兼容，检查结束后可立即变旧；绝不是持久恢复凭据。后续真正导入仍需受控新身份、来源证明、目标授权、提交时新鲜度和跨源目标故障协议；一次读proof再目标commit存在竞态，不能复用本布尔值绕过。无用户实例升级、业务写入或新store，回滚revert代码即可，不删除任何已有备份或限制文件。

实际实现保持原`check`返回值和语义，显式新方法增加源/clone/源三阶段核对。最终专项17通过100.91秒，含真实BCG清除、实际pg_restore、Windows DPAPI、缺失/损坏/pending/异根/异workspace/proof字典拒绝、检查期间clear、恢复失败/最终证据损坏后的clone清理，以及源库/原包保留。新旧backup回归26通过1项平台跳过125.85秒；全非DB415通过4项宿主能力跳过、当时412项DB未执行46.90秒（随后另加1个DB用例，最终收集数以CI为准）。日志仅存忽略的test-results，不公开。

独立首轮14通过81.47秒，指出篡改clone会先被旧inventory检查拒绝，证据不能归因于新关系检查；已补实际生成inventory自洽但marker关系错误的坏包，并明确断言旧check通过/新check拒绝，独立关键用例1通过15.02秒。无剩余实现阻断发现；不将独立首轮成绩冒称最后3个新增用例已全量独立重跑。公开清单、扫描、完整两平台CI仍按最终head收口。教师正常工作新增操作为零；该operator开发能力尚无UI，不声称已经完成用户净负担验收、新身份恢复或耐久会话链路。
