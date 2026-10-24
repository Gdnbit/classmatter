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
