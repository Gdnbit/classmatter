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

D1-13a最终PR #25在CI40101895174两平台成功后合并main80cbaf8：Windows非DB419/Web55/desktop23，Ubuntu非DB416+3跳过、实际PG/browser403+10跳过。669项hash及公开历史扫描通过；以上候选状态为历史过程，不表示该单元仍未验收。

## D1-13b：源端持久移交冻结（文件级计划）

下一目标不是再发一个preflight布尔值，而是建立真正导入所需的源端持久fence。一次源查询或PG进程锁不足以保护目标提交：源连接中断会释放锁。因此先经人工BCG明确冻结源，后续目标隔离导入→源退休→目标admission必须复用同一attempt，不自动恢复原源。此单元只交付源端冻结，目标导入/准入仍必须继续实现，不缩小Goal。

| 文件范围 | 计划内变化与验收 |
| --- | --- |
| 新`domain/source_transfer.py`、`infrastructure/source_transfer.py`及专项测试 | 封闭命令/固定元数据、同runtime/workspace/root绑定的DPAPI文件、排他原子发布及不可覆盖；复用已有文件锁，不把移交伪装成ClearMarker。缺失/损坏/异scope/硬链接/重启/发布故障拒绝，真实Windows DPAPI另验 |
| 新显式D1迁移及schema/role清单 | 为原control增加有限移交字段及none/pending约束，只允许现有runtime在BCG中写固定字段；默认R1仍0016/22表，不改旧迁移或用户实例 |
| 原Gateway/BusinessTransaction与conversation控制、独立SourceTransfer Gateway | 原ISB、近期认证、Risk.X批准、幂等、审计；文件先持久化再同事务保存SQL锚点/回执。普通D1 QG/BCG遇任一fence拒绝，仅同attempt的闭合移交操作可收口；不得让通用Gateway或嵌套调用借用豁免 |
| conversation出口及离线验证 | 新字段使用显式v3承载，旧v2校验保持原格式，不谎称旧包涵盖新控制状态；冻结源不能再导出或给SDK提供正文。backup仍含全部固定列且不可激活 |
| 源端真实PG/DPAPI/故障测试、原回归 | clear与seal竞争、未知/陈旧包、活动run、错误target、未经批准、审计/SQL/文件失败、幂等并发、文件丢失/损坏、缺文件但SQL已pending、旧SQL但文件已有fence、普通查询/写入/导出拒绝与原事实任务不变 |
| 原README/台账/本变更/PUBLIC_AUDIT/manifest | 实际证据、可追溯公开hash、独立审查与最终Windows/Ubuntu CI；正式107/147/94及Gate不变 |

目标坐标不是目标已建立或获准的证明；本单元只绑定坐标并冻结源，后续必须由目标ISB核验新Owner/空业务库、保留来源作者与恢复操作者差异、隔离旧run且不自动dispatch。source audit不能直接变成target可信audit。当前没有HTTP/UI/Agent入口，不能用此功能冻结真实现有实例。发生不确定结果时保留fence，不因超时、文件删除、源码revert或更换attempt解冻；已显式迁移的D1只能受控前滚/停用，不能破坏性降级。新身份/跨机可验证证明及撤销pending的受控协议仍待后续实现；没有这些条件时拒绝目标激活。

## D1-13b实际实现与候选证据

已实现封闭命令、固定DPAPI文件、0020原control的transfer_id/hash/at三字段、人工Risk.X批准及file-first SQL/audit收口。27表不变；只对显式D1新增这3列的runtime UPDATE，不给Agent增加工具或扩大原R1字段权限。共享Proposal仅补类型注解，原wire/R1命令解码器未增加seal。Gateway新增边界检查：普通R1 Store必须核对实际0016，D1 Store必须先验证注入restriction根与已有DB锚点，再判断file/SQL冻结；拒绝仍走原audit。专用豁免绑定store/owner/action/proposal，状态读取复用独立QG，不把查询塞进BCG。源无活动run、当前业务hash/未过期包和异target坐标才可seal；源清除与seal只有一个可提交。

两项独立真实PG发现已修复：仅相信构造参数profile会让默认r1对象读取被冻结的D1；只看空根中无file会绕过audit失败后file-only冻结。已补actual head/root-authority检查、普通读取及已有批准class.update提交拒绝，独立2项20.15秒通过。首轮测试另外发现状态查询挂错Gateway，以及测试误用姓名命令构造参数，均修正接线/fixture后重跑，不把失败当通过。

最终source port/PG组合33通过96.32秒，含实际子进程硬退出、link后残留、clear/seal竞争、并发幂等、SQL/audit失败、文件丢失/损坏/部分SQL回滚和Windows实际DPAPI+PG。随后真实旧v2离线CLI与重算hash的v3冻结字段拒绝加入，port单文件16通过4.38秒。独立四文件组合76通过150.97秒发生于最后兼容用例加入前，不声称包含该新增用例。原clear/storage/backup/current-proof/R1Gateway回归96通过340.50秒，出口v2/v3真实PG组合43通过47.44秒；最终全非DB431通过4项宿主能力跳过、431 DB项未在该命令运行42.32秒。原始XML仅在忽略的test-results目录。

v3显式覆盖全部新control列，仅允许未冻结源导出；旧v2验证器、默认core-v1保留，旧v2不会冒充0020出口。所有新包仍固定不可激活。原0019 owned checkpoint精确head绑定，不自动升级。没有目标导入、源退休或admission；目标坐标仍需后续可信握手验证，不能因source receipt存在就释放目标。普通同源业务读写被有意阻断，不是假称已完成恢复或教师日常工作功能。

运维限制保留：pending重试仍需原artifact在30分钟有效期内、有效身份/批准；过期会保持冻结，后续必须增加受控诊断/前滚而非自动解除。initial link后硬退出可能留nlink2，源保持冻结，不自动删证据或生成新attempt。源码revert不能安全解冻或降级已迁移D1；当前没有对用户实例执行迁移/冻结。完整恢复与UI/SDK/文书Goal仍未完成，正式107/147/94与Gate不变。公开hash、扫描、独立最终字节审查与完整两平台CI须以最后head收口。

PR #26首轮CI40104849802：Windows成功；Ubuntu实际PG阶段1失败、419通过、11跳过。唯一失败为0015→0016非空升级fixture：当前Store新增的实际head检查正确拒绝在0015上种样本。修复仅在该测试内模拟严格限定0015的旧Store/Transaction，并明确验证当前QG拒绝0015；迁移后立即重建当前生产Store/Gateway，继续验证旧批准提交、精确ACL和原数据不变。没有放宽生产允许版本、修改历史迁移或删除安全断言。独立实际PG该升级测试1通过10.34秒；本机升级与source-transfer真实PG组合19通过84.95秒。真实hash及修复后两平台CI仍须按新head核验，不能拼用首轮Windows成绩。

D1-13b已由PR #26合并main72c14cc；最终head d3723cf的CI40106194706两平台成功：Windows非DB435/Web55/desktop23，Ubuntu非DB431+4跳过、真实PG/browser420+11跳过。实际合并后树与本机验收树一致，未触碰原工作区并发改动。

## D1-13c：隔离目标typed import（文件级计划）

在源持久冻结之后实际恢复到新Owner的空目标，但本单元不激活目标；源退休和目标admission仍为后续必做步骤。先只接受无active run的原生退出包，终态原样保存且不生成dispatch能力，不先建设通用run恢复或Actor框架。

| 文件范围 | 实施与验收 |
| --- | --- |
| `domain/target_import.py`、`application/target_import.py`、`infrastructure/target_import.py`及固定SQL store | 封闭命令、1MiB原生候选、当前源QG元数据证明、人工近期认证Risk.X批准、受保护目标pending证据先写，再同事务写固定实体/来源/回执/audit；SQL失败保留隔离证据，只可同attempt重试 |
| 原source transfer应用/store/边界及新显式迁移 | 源QG仅释放已提交seal的固定元数据，不释放正文或批准能力；目标普通QG/BCG/Agent读取/出口保持拒绝，错误根或文件丢失不绕过SQL pending；原r1/default0016不变 |
| 新固定import batch/entity provenance/source audit表及schema/role guards | 不伪造源Owner、不恢复登录/会话/批准。local作者外键记录实际导入人，原作者由固定批次及逐实体版本来源保留；在正式QG作者投影完成前绝不开放普通读取；源audit不插入目标可信business_audit |
| 显式v4出口/离线验证、原backup/integrity | 完整承载新固定集合，不扩大v1/v2/v3；native旧格式仍独立校验。新profile checkpoint包含全部新表且不可激活；清除限制不复活，来源不能在再次导出时静默丢失。多跳导入暂拒绝，不能以单跳证据宣称完整迁移 |
| 新纯格式/文件与两个真实PG数据库测试、原回归 | 新身份/空目标、严格scope与包hash/已提交源fence匹配、terminal-only、清除marker、原作者与restorer区别、审计/SQL/文件失败、并发幂等、源缺失/损坏/不匹配、普通读取/旧批准写入拒绝、原库保留、实际checkpoint与格式闭合 |
| 原README/台账/本变更/公开审查和manifest | 真实证据、独立对抗审查、677基线外新文件逐项来源/真实SHA及全Windows/Ubuntu CI；正式Requirement/Eval/Task/Gate无语义或状态改变 |

只在测试拥有的合成数据库及受信同机composition实施；没有HTTP/UI/CLI/Agent工具，不读取或复制外部凭据，不迁移用户实例。目标pending不是成功恢复或激活，不因超时、重启、删除证据、revert或改attempt解冻；回滚保留双方证据，停用profile或前滚。教师正常使用无新维护步骤；最终恢复入口及真实净减负仍待后续端到端验证。

## D1-13c实际实现与候选证据

已实现上述同机双身份、原生terminal-only包的隔离typed INSERT；固定batch/逐实体版本来源/source audit三表只授予runtime SELECT/INSERT，identity零访问，默认R1和Agent工具不变。原作者由batch与精确来源hash保存，local FK仅表示导入操作人；普通QG/BCG仍拒绝，不能把底层local字段直接展示成原作者。v4及owned checkpoint覆盖全部30表并验证来源；多跳输入明确拒绝。源QG只提供当前已提交freeze元数据，不提供正文/旧批准/离线激活凭据。

独立审查发现并修复：turn/message/run复合身份缺thread_id；Python bool可冒充版本及source audit必填event_id可为空；SQL写入后的CommandRejected可能被旧Gateway转换成已提交denied audit。现保留完整复合身份、严格类型/nullable规则，后置验证异常强制整笔SQL回滚。随后补同PG JSONB row-text口径的预展开预算，避免canonical包未超限、文件发布后读取预算却超限而留下不必要pending。没有放宽原读取上限或修改旧v2/v3验证规则。

候选实际证据：最后修复后新port/双PG完整组合56通过200.92秒，包含denied-proof→正常export/seal/import、旧CLI、PG预算边界、1800学生展开上限、后置真实restriction损坏及Windows DPAPI/PG。此前54通过190.07秒、52通过217.42秒为阶段历史；旧v3/v4 CLI独立兼容1通过2.34秒，PG预算临界1通过8.43秒，1800学生原生合法包展开超限在target文件发布前拒绝1通过37.47秒，后置真实restriction损坏与Windows DPAPI/PG另2通过25.09秒。原clear/source/exit/storage/backup/current-proof/0015升级七文件117通过465.02秒发生于最后audit兼容修复前，最终全量以新CI为准；最后全非DB465通过4项宿主能力跳过、453 DB项未在该命令执行46.88秒。首轮新fixture误调用BCG查询方法、audit故障未解除便断言业务拒绝，均只修测试接线/断言时点后重跑，不放宽生产边界。

独立真实PG关键回归3通过32.23秒，后置真实restriction故障与checkpoint/provenance篡改2通过34.78秒，PG预算临界与主正常导入2通过20.65秒；独立port32通过3.80秒发生于新增CLI用例之前。独立检查新增8文件为首方实现/合成测试，无外部来源或隐私材料。原始XML、临时DB与受保护文件仍仅在忽略的测试目录，最终真实manifest、历史scan和完整两平台CI待收口。

最后独立审查实证未seal源的proof查询被正常拒绝后留下新audit action，旧v3私有投影不认识该动作而使后续正常export失败。现仅新v4自有严格audit校验完整承载该动作，再以过滤后的私有旧动作投影复用旧core验证；对外v4与source audit不丢行，不修改v2/v3。未知动作仍拒绝，新增实际链与纯格式回归独立2通过16.53秒；之前685项hash校验须由修复后的真实字节重新核验，不能当最终通过。

当前仍无源退休、目标admission、正式作者读取投影、跨机可信握手、多跳导入或耐久UI/SDK/工作小结。不能以pending receipt或checkpoint完整性宣称恢复完成；所有这些后续目标保留。没有自动迁移用户实例，原R1App并发17+/3-改动未触碰，正式107/147/94与Gate不变。教师日常新增维护步骤为零，恢复入口和真实净减负研究未验收。已显式迁移的D1不能revert后破坏性降级，异常时保留双方fence与来源文件，停用未激活profile或受控前滚。

## D1-13d：已提交目标证明与源退役（文件级计划）

基线为PR #27实际合并main29e2cce；其CI40162167299两平台成功：Windows非DB469/Web55/desktop23，Ubuntu非DB464+5平台跳过、真实PG/browser441+12跳过。685个真实hash及独立审查已收口。以下是新的依赖单元，不把13c的pending导入改称完整恢复。

| 文件 | 范围与验收 |
| --- | --- |
| `domain/source_retirement.py`、原`application/target_import.py`及`infrastructure/target_import_store.py` | 固定已提交目标DTO：实际目标fence、import receipt、root与完整pending快照hash；只经当前ISB授权的QG读取元数据，不释放正文，不接受离线dict替代，不允许未提交或被篡改的数据 |
| `application/source_retirement.py`、`infrastructure/source_retirement.py`及`source_retirement_store.py` | 人工近期认证Risk.X退役命令；受信同机composition持有临时目标QG身份，不存储凭据。实际已提交源seal和当前目标stage完全匹配后先写固定DPAPI退役证明，再复用现有proposal/receipt/audit事务；回滚保留证明、同attempt重试，普通源读写永不自动恢复 |
| 显式`0022`迁移、原schema/control/source边界 | 只扩闭合命令枚举，不新增业务表、任意DDL入口或新的business写入口；默认R1仍0016/22。新增退役文件单独存在也必须冻结，错误根、缺失/损坏证据、旧批准不得绕过。退役查询以当前文件+源seal+已提交命令/回执核验，file-only不是已提交退役 |
| 新纯/文件/真实双PG测试和原回归 | 真实导入→目标QG证明→批准退役→重启构造→回执/退役证明重读；未提交/篡改目标、撤销身份、错误hash/attempt/根、陈旧认证、SQL/audit失败、并发重试、实际DPAPI及子进程硬退出；所有普通源/目标入口继续拒绝，无模型调用 |
| README/台账/本变更、公开审查与manifest | 已完成/未完成证据及来源审查、逐文件真实SHA、固定扫描/文档/两平台CI、独立对抗审查。正式Requirement/Eval/Task/Gate无变化；回滚停用未激活profile或受控前滚，不删除证明、不解冻、不破坏性降级 |

目标准入、修改后的来源校验/作者投影、UI/SDK和文书仍是同一完整Goal的后续必做内容。当前v4只能验证未修改pending内容，因此准入必须与可演进的固定来源语义一起交付，不能先开放再补校验。退役文件是备份外单调证据，与原seal一样不复制为可重放离线授权；owned checkpoint仍只证明SQL完整性、不可激活。教师正常使用新增维护步骤为零，本轮尚无用户恢复入口或真实净负担证据。

## D1-13d实际实现与候选证据

已按计划实现固定目标stage DTO/QG和人工源退役BCG，显式0022只扩两项command/risk约束，仍30表且ACL不变。固定退役文件先发布，原proposal/receipt/audit事务收口；没有第二套写入口、万能业务模型、正文复制或Agent工具。退役证明读必须匹配当前源seal、文件和已提交回执；目标始终pending。默认R1仍0016/22，v4投影结构与旧离线验证器不变，`source_revision=0021`明确仅指固定投影基线，实际live Store独立要求0022，不把包字段当Schema或准入权威。

首轮新组合27通过114.07秒。独立审查指出退役文件保留、source seal文件及SQL部分回滚后，专用seal入口仍可能重开handoff；已在seal校验最前拒绝任何退役证据，补实际旧artifact重新seal拒绝。还禁止为已提交退役创建新proposal，只能重放原receipt；普通source-staging proof在任何退役证据存在时拒绝，内部退役同attempt重试/证明路径仍需完整源/目标/文件/回执核验，没有对外或Agent开关。旧nonce与响应丢失不得制造第二份退休。

独立审查另指出跨DB反序锁：已提交目标的新import preview现先本地检查batch/非空再拒绝，不重新获取源锁；真实并发duplicate-target-preview与source-retirement均收口，普通目标仍拒绝。现有5秒lock/statement timeout保留，不宣称分布式原子性或无死锁。目标file-only、来源/源audit被篡改、目标身份撤销、陈旧认证、未知attempt/hash、audit或SQLfinish失败、并发幂等、退休证据丢失/损坏/目录/缺回执均有实际负向；新端口有真实子进程硬退出、nlink2拒绝和Windows DPAPI测试。

最后source-proof加固后的新纯/文件/双PG组合35通过249.00秒，含实际双端DPAPI+PG、完整导入→目标证明→批准退役→回执重放→重建Store读取→实际pg_dump/pg_restore checkpoint不可激活。之前35通过255.21秒及source/target四文件73通过527.26秒发生于最后加固前，仅为阶段回归；两项锁/本地先拒绝和file-only/reseal定向3通过37.58秒。全非DB480通过4项宿主能力跳过、473 DB未执行49.18秒也先于最后source-proof加固，最终当前head全量以独立两平台CI为准。

独立真实PG：file-only/reseal、audit回滚和完整重开/checkpoint3通过36.58秒；锁并发、SQLfinish回滚及缺失/损坏proof6通过89.32秒，均为最后加固前证据；最后加固后完整链/audit回滚重试2通过44.69秒。纯规则/文件/硬退出/DPAPI独立15通过4.25秒。独立当前无新增阻断；仍需最终692项真实hash复核、固定files/history scan、docs与完整Windows/Ubuntu CI。原始XML/数据库/受保护文件仅存忽略目录，不上传运行日志或凭据。

公开guard/license、固定8.30.1 files/history扫描4项已审查且0未解决、root81及docs74/图/合成scope/契约检查已实际通过；最后文档改动后须重算hash并重查。Requirement/Eval/Task/Gate仍107/147/94/green0；原R1App并发17+/3-未触碰，用户实例未升级，原Logo哈希一致且本地忽略。回滚保留全部fence/checkpoint，只停用未激活profile或前滚，不删除文件、自动解冻或降级0022。整个Goal仍须完成目标准入与可修改作者来源、耐久UI/SDK和事实引用工作小结；Owner本人设置及真实Provider条件没有被合成测试代替。

## D1-13e：目标准入、可修改来源与作者读取（文件级计划）

基线main668ed15，PR #28最终CI40164342955两平台成功：Windows非DB484/Web55/desktop23，Ubuntu非DB478+6跳过、真实PG/browser460+13跳过614.94秒；692项真实hash独立核验。前一单元已验收源退役，目标仍pending；以下必须完成完整修改链，不以只读激活或仅预检查替代。

| 文件范围 | 必须实现的范围和证据 |
| --- | --- |
| 新`domain/recovery_admission.py`、`conversation_exit_v5.py`与原当前出口/候选适配器 | 固定每kind不可变字段/可修改字段、真实复合键、源版本及来源集合hash；原record revisions/terminal turns/runs完整hash，可见消息正文hash、清除后NULL和限制marker例外。本地新修订与原作者区分；只存hash，不复制baseline正文或建设万能JSON |
| 新显式0023迁移、schema/role guards及固定SQL store | 两张固定append-only表保存准入锚点和原导入创建/正文指纹，runtime仅SELECT/INSERT，默认R1仍0016/22。已有import/source audit不改写；原业务持久变更仍经BCG，不增加Agent写权限或运行时DDL |
| 新application/受保护admission文件/store及原target/source边界 | 近期认证Risk.X人工批准；实际已提交源retirement与当前target stage完全匹配，再文件先行、SQL来源集合/锚点/receipt/audit同事务。文件、当前root/Owner/authority、stage/retirement receipt/hash、origin集合任一缺失/不符均拒绝；SQL失败保持pending，只可同attempt重试。准入后可独立于源在线运行，但不能上传dict替代初次live证明 |
| 作者感知QG/历史投影 | 原始revision作者仍源Owner，新本地revision作者为实际本地Owner；可变实体保留创建来源、后续修改者归本地；assistant-unverified不能归为老师事实。含正文的旧无归因读取不得静默释放导入数据；普通Roster/context不伪造人物身份，不创建源Owner账号 |
| 原checkpoint、当前v5出口与CLI校验 | v5独立承载可修改来源与准入集合，不放宽旧v4。原生修改/clear后实际pg_dump/pg_restore与v5继续校验；v4 pending snapshot hash维持历史projection以读取既有retirement证明。多跳未实现时既拒绝import，也在再次seal前拒绝，避免先冻结再发现无法导入 |
| 新纯格式/端口/双PG测试及原回归 | 实际退役→准入→原生更名/事实修订/任务修改→QG归因→clear→重建Store→checkpoint/pg_restore→v5；audit/SQL/文件失败、旧DB回滚、origin新增/缺失/篡改、visible正文替换、旧terminal run修改、跨Owner/root/过期认证、重放/并发、原默认R1不隐式升级 |
| README/台账/本变更/公开审查/manifest | 最终字节审查、真实SHA、固定历史scan、docs、独立对抗审查与完整两平台CI；正式107需求/147eval/94task及Gate不变。当前用户实例/原脏改动/Logo原图不动 |

先实现固定语义与新format，再迁移及store/边界/QG，最后完整故障验收；这些是同一依赖PR，未闭环不合并。最大包/集合预算在文件发布前检查，超限不放宽原边界；退出校验不等于离线恢复或多跳授权。回滚只能停用未激活profile或受控前滚，保留两端全部证据，不自动解冻/清文件/破坏性降级。教师正常工作无新增来源维护步骤；真实恢复UI、耐久发送/SDK和工作小结仍在完整Goal后续，合成结果不代替Owner/Provider/真实净负担验收。

### D1-13e 候选实施与独立审查记录

已实施固定准入/作者感知QG和v5，复用既有BCG/ISB、receipt和audit；没有Agent写工具、用户实例升级或新HTTP/UI入口。新两表仅允许runtime SELECT/INSERT。源Owner保留为固定来源元数据而非新增本地账号；原revision与新本地revision分别归因，assistant仍未核实。v5原生修改/clear后可校验，不把原创建者改成restorer，也不保留baseline正文副本。

独立审查捕获并修复：仅凭新Gateway名字但实际使用旧未归因事务的组合旁路、已准入批次和源audit集合未完全绑定、原始commit-audit缺失仍可证明提交，以及源退休后才发现准入容量不足。现在要求实际AdmissionTransaction；受保护witness绑定完整batch/source-audit/origin摘要；seal/stage/retire/admit各证明要求原始payload/receipt/commit-audit，准入后仍核验本地stage和admit原提交证据。目标QG在源退役前模拟固定准入扩展的canonical与PG JSONB预算，UUID/hash长度固定、时间采用最长微秒宽度，模拟不发布为authority。当前容量失败测试注入预算拒绝，证明调用位置和不发布退役；不是实测接近1MiB膨胀样本。

本机初轮规则及完整准入/3回滚组合30通过70.53秒；随后规则/故障矩阵48通过254.11秒，当前规则/文件端口43通过5.66秒（含真实Windows DPAPI及硬退出）。最新非DB523通过/4跳过/496未选59.04秒，契约检查通过。非空0022升级/存储/准入并发组合50通过404.64秒；此前控制/退出/checkpoint/封存/暂存/退役完整组合112通过775.72秒。升级测试首次Alembic配置错误已按既有固定script_location模式修正，未放宽生产检查。最终审查另发现stage proof helper只比声明hash而未比payload本体；现同时按固定canonical JSONB核验，并补stage-payload篡改拒绝，须按最终head再验，不能用早期计数冒充最后字节全量。

独立临时PG负向14通过210.18秒；实际admission→更名/事实修订/任务更新→归因→clear→真实PG重启→checkpoint/pg_restore/v5及回滚隔离5通过113.92秒；规则/端口43通过10.29秒。公开审查702项SHA全部匹配、10个新文件为first-party；例外/正式Gate/R1/CI未改。固定8.30.1 files/history扫描4项已审查0未解决，root81及docs74/图/合成scope通过。原始XML/受保护文件/数据库留在忽略目录；最终两平台CI及最后字节复核仍待，不据本段宣称已合并或整个Goal完成。
