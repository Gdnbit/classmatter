# 原界面剩余领域接入：合成开发增量

状态：2026-11-04 用户授权的后续开发设计，实施中。承接原Demo与当前QG/BCG/ISB，不是第二套产品或冻结R1扩容。正式Requirement/Eval/Task/Gate及真实数据准入保持原状态。

## 目标与验收

原文档、成绩表格、座位等页面逐项消费同一数据世界。开发入口免密码，已有班级、学生、记录、任务及聊天不因新增模块消失。每个动作都登记实际读写、预览、确认、刷新重开、拒绝/冲突及恢复证据；禁用或Future提示不计功能完成，mock成功不计验收。

实现顺序：文档持久化 → 成绩/考试及受控导入 → 座位布局/方案/手工交换 → 其余原型动作，按依赖独立PR。沿用原界面及公共展示组件，不复制另一套工作台。各模块可独立验收，但只有Goal承诺的清单实际完成且GitHub/CI收口才算整体完成。

## 唯一事实源和写入口

- 业务查询仍走QG；持久化业务变更仍由原BCG完成preview、批准、幂等commit和同事务audit。通过已有gateway扩展点注册闭集命令，不创建旁路HTTP写接口。
- ISB与本机开发会话只负责身份，不授予Agent写工具。数据库迁移只由受信operator执行；不运行Agent DDL或万能JSON patch。
- 工作文档是可编辑成果，不是学生Domain Fact、聊天Memory或Knowledge依据。保存AI文本不等于核验其主张；通知草稿不等于已发送。
- 查询、分页、编辑和导出均绑定workspace/class/term及稳定ID，姓名不作关联键。归档范围只读，跨范围ID、旧版本、未知结果都不猜测、不自动重放。

## D2存储增量与原实例演进

原R1/0016与D1/0026的已验收profile和历史migration保持不变。新增内部`workbench-d2`合成profile，先注册文档的固定表/列/命令和最小权限，再逐模块演进；它是存储协议版本，不是用户要选择的另一套工作台。

不把未知新表加入旧profile白名单，也不静默改变D1退出/恢复语义。现用实例的升级必须有明确operator动作：核验原profile/版本、停止本次服务并排空运行、创建并验证备份、检查source/import/retirement及restriction fences、串行迁移、验证ACL/表面/数据保留后才更新运行描述。失败时保留原描述及可恢复证据，不重建Owner、不清库、不回退到空实例。当前用户实例在此流程验收前不迁移。

新模块进入启用状态前，必须验证完整本机备份/恢复及不丢数据的导出。旧D1导出/transfer/retirement如果无法覆盖新数据，必须明确拒绝不完整包或另有显式完整新协议；不能漏掉新表后仍声称完整退出。已导入、转移、退役或受限实例的升级需单独验证，不放宽原限制以便启动。

## 文档领域

首个闭环保持原文档页面：新建/打开 → 编辑标题与正文 → 预览 → 保存 → 刷新/重开 → 历史版本 → 归档/恢复。复用已有事实/任务整理班级小结，再保存为独立工作文档，避免重复录入。

固定对象：文档head与不可变revision。head绑定文档ID、workspace、班级、学期、状态和当前版本；revision保留标题、plain-text/markdown正文、操作者、时间和操作类型。正文不是任意HTML执行环境；最多100000字符/400000 UTF-8字节，拒绝NUL、孤立代理项和非文本控制字符。Office/PDF等上传另经Capture候选解析，不将任意二进制当正文入库。

闭集动作：`document.create`、`document.revise`、`document.archive`、`document.restore`。版本必须为严格正整数，旧版本写入拒绝；归档内容保留且不可直接编辑，先恢复再修订。撤回历史版本通过追加新revision，不覆盖旧内容。草稿编辑不强迫老师重复填写事实更正字段，身份/时间/操作由系统记录。没有`document.delete`、任意路径、verified-fact或SQL字段。

验收必须包含正文字符/大小、同名不同ID、跨班级/学期、版本冲突、批准和幂等、审计失败回滚、归档只读、恢复版本递增、刷新重开、备份恢复、退出无遗漏及原页面浏览器测试。领域规则测试仅证明规则，不当作数据库/页面已接通。

## 成绩领域

复用已有FR-GRD-001—007设计语义，保持独立后续开发状态。固定对象是考试、科目/满分、学生考试结果和不可变更正。有效分数、缺考、免考、未录入、无效值分别建模；不用0/空字符串互相代替。分数采用有界精确十进制，拒绝NaN/Infinity、超满分、重复学生科目及跨范围关联。

先做原成绩表格的人工编辑/筛选/保存/统计及更正历史，再接文件导入候选。导入必须保留来源批次与字段映射，先验证后预览提交；同名歧义、无身份或无效行需明确处理，不猜学生、不静默跳过再声称全部导入。统计说明分母和排除状态，不生成学生人格/能力结论；查询与视图筛选不改变成绩。

## 座位领域

复用FR-SEA-001—004。固定对象是有版本的教室布局、可用/不可用位置、候选方案和已提交分配。位置和学生均用稳定ID，验证同班/同学期、重复分配、越界、不可用座位、未分配学生和过期方案。

先接原座位图/双选交换/拖拽手工调整的预览与提交，再做可替换solver的多候选及硬约束验证。硬约束不可由评分抵消；不根据成绩自动推断健康、行为或安排理由。教师显式给出的约束才参与求解，不引入敏感画像。展示新旧分配及受影响学生；撤销追加新版本，不删除历史。导出/打印与当前布局/版本一致，失败不伪造已保存或已应用。

## 页面动作台账

| 原页面/动作 | 当前工程状态 | 后续验收单元 |
|---|---|---|
| 对话、学生、事实、任务 | 已有合成持久化；原界面逐项共享 | 继续回归，不重复造底层 |
| 数据与内容/文档/小结保存/版本 | 领域/BCG/QG/版本库、HTTP/typed client及本机快照验证已有；原UI/实例升级与完整退出未完成 | D2-DOC |
| 成绩表格/考试/统计/更正/导入 | 原型仍为样例，未完成 | D2-GRD、D2-IMPORT |
| 座位布局/交换/拖拽/方案/打印 | 原型仍为样例，未完成 | D2-SEA |
| 名单事务/批量改动 | 手工单条已有；批量未完成 | D2-ROSTER |
| 宿舍/分组/职务/值日 | 领域规则/生产写入未完成 | D2-ORG，逐动作细化 |
| AI Inbox/Capture/文件与语音 | 采集/候选转正式数据链路未完成 | D2-CAPTURE |
| 工作专题/自动化/知识/报告 | 部分研究/小结已有；完整页面未完成 | 独立闭环逐项细化 |

这张表是未完成清单，不是把Future当交付。子单元开始时把上述大项展开为实际按钮/深层页面及测试证据；未经实际验证的提醒规则、自动画像、外发及调度不默认启用。

## D2-DOC 存储子单元

`domain/documents.py`提供闭集四动作与CAS；`application/documents.py`复用原BusinessGateway，不提供Agent工具；`infrastructure/documents.py`只在显式workbench-d2/0027工作，沿用原身份租约、事务锁、保护根及transfer/import限制。当前文档适配器只承载文档操作，不冒充整个D1服务可直接运行在D2。读取列表/历史暂取最多201项供后续HTTP适配器作截断或分页，不能直接当完整集合。

0027为新增迁移，不修改0016/0026。文档head只允许runtime改status/version/updated_at，revision只允许SELECT/INSERT；D2角色检查同时保留全部D1列级权限检查。固定FK绑定Owner、班级学期和当前revision；四命令均为W2，必须原BCG预览、批准及幂等提交。归档/恢复追加正文快照，历史不覆盖。

本机checkpoint新增独立D2种类，完整登记两张新表并检查历史连续性、状态转换、正文边界、当前版本和时间。真实pg_dump/pg_restore临时克隆比较完整库存哈希与当前restriction；明确activation_allowed=false、complete_exit=false，不作为可移植退出或导入授权。旧D1服务/备份遇到新表或新head明确拒绝，不生成遗漏文档的成功包。

这只是存储子单元。HTTP typed contracts、原文档编辑器、同一实例显式升级及完整退出尚需后续实现验收；未对用户运行实例迁移，也未改变开发入口或个人认证。

## D2-DOC HTTP/客户端子单元

显式document_business/document_query必须与同一ISB及store装配，缺任意一项拒绝；默认R1/D1 composition不启用该模块。原app增加可选文档router，不新增旁路写引擎或Agent工具。`document-commands`路由仅适配原BCG四命令与批准/拒绝/提交/回执；领域存储、批准及同事务审计仍在原gateway执行。旧R1请求与wire schema不变。

文档列表/版本历史采用50项元数据页，scope/snapshot/next_offset显式返回；路径包含闭集snapshot与offset，不开放任意查询参数。后续页遇到集合变化返回409，不默默拼接两个快照；历史页不批量返回正文，按稳定document_id/version单独读取不可变正文。当前和历史正文均标记working-draft，不是事实或已发送材料。200项截断的内部前置查询不作为HTTP全集接口。

正文请求仅在模块显式启用且路径为文档preview时采用640KiB上限，覆盖100000字符被JSON转义后的体积；身份、原命令、批准等仍为原8KiB。保留重复JSON字段、NaN/Infinity、同源、Cookie、CSRF与审计失败拒绝。导出11个固定文档schema，原有schema保持字节不变；前端复用既有Ajv构建时生成模式，保持严格additionalProperties和disjoint command literals，不在浏览器编译任意schema。

`runtime/documents.ts`为固定typed client，不接mock、不缓存业务数据，不自动保存/批准/重试。响应限制1MiB、严格UTF-8/日期/身份与班级学期/文档/版本/分页/来源权威核对；丢失提交结果后只由调用方显式GET原请求回执，未知结果不重放。原文档页面与运行实例尚未装配，客户端单测不能当作UI验收。

## D2-DOC 与原领域共用同一服务

`application/workbench.py`显式组合文档策略与既有ConversationWorkerGateway/ConversationInteractionQuery；`infrastructure/workbench.py`将原AdmissionTransaction与文档固定SQL组合，仍使用同一个BCG事务、ISB、store和数据库。没有另建写入引擎、Owner或班级。仅允许原生、未转移/导入/退役的已初始化D2；文件先落地而SQL尚未提交的旧fence也必须拒绝所有普通读取。

原D1对话完整性验证使用闭集旧审计协议。D2先用`domain/workbench_audit.py`验证全部审计：仅三个新增文档读取动作归文档分区，共用BCG的命令审计仍保留在原分区；重复ID、未知动作、跨范围、伪造写回执或未来时间拒绝。原D1校验器原样验证其分区，原native结果commit校验继续执行；这只是私有对话组件证明，不能作为完整D2退出包。公共旧exit/transfer/import/retirement路径均拒绝，新的完整退出仍未交付，不默默遗漏文档。

`interfaces/http/workbench.py`通过固定装配复用原durable HTTP/SSE与Pydantic AI loop，额外挂文档路由。新capabilities显式声明workbench-d2、synthetic-only、文档协议及complete_exit=false，不冒充旧D1 capabilities。审计v2包含文档动作，保留R1/D1 wire schema；对话活动/历史继续使用已验收的既有协议。结果捕获器和typed历史阅读器仅新增一个显式、完整证据校验的D2类型，不使用isinstance放行任意子类，不向模型注册新业务写工具。

这仍是受测服务装配，尚非本机默认启动。运行描述、同实例备份/升级/恢复及原前端页面还未接入；不得据此迁移用户库、创建另一套空工作空间或宣称整个原型完成。现有D1组件验证的包/行数上限仍有效，不把合成开发通过当长期生产容量结论。

## D2-DOC 同实例升级与运行入口

`workbench_upgrade.py`是受信本机operator，不是HTTP、identity pipe或Agent工具。D2复用D1同一默认目录、数据库名、Owner和受保护控制，不允许初始化空D2、通用migrate或重新bootstrap。显式`backend/local.py upgrade-workbench --profile conversation-d1`只适用于已初始化、原生且无运行服务/其他数据库客户端/在途run/转移导入退役fence的合成实例；升级不会自动关闭用户窗口、杀连接或停止其他实例。现阶段不得自动执行到用户实例；原页面、完整退出和桌面协议仍有前置依赖。

顺序是：持有协调、身份、业务会话锁→原D1结构/权限/保护头核验→完整pg_dump与临时克隆pg_restore核验→DPAPI密封升级凭据→同一事务迁移0027并复核原业务库存→原描述只替换profile值并原子发布。保留原描述的编码与换行，不替换数据库/目录。既有Owner、班级、学生、任务、消息、模型配置及身份不复制到新世界。凭据仅包含固定范围标识和哈希，不含密码、正文或dump。

DDL或验收失败在提交前回滚，原D1仍可用；已核验备份与失败凭据保留。重试会重新核验当前库存并归档旧凭据，不恢复旧会话或删除备份。SQL提交后配置发布失败，重试必须验证原描述哈希、既有升级凭据、Owner/范围、保护头及旧业务库存，才允许向前完成发布；不得以旧D1代码降级读取0027。成功后再次调用只验证当前证据并返回，不重复迁移。升级凭据损坏/缺失、额外连接、源fence或不一致均拒绝；失败不输出连接凭据或原始数据库异常。

`workbench_local_runtime.py`显式装配同一QG/BCG/ISB/Pydantic AI及原SSE，启动/就绪必须核验D2结构、列级权限、文档历史完整性和升级凭据。NativeSetup对明确D2只复用既有开发身份，不创建Owner/control；原免密码开发入口及重新验证仍走原ISB，普通个人身份不会被开发模式接管。`serve --profile workbench-d2`是operator级显式服务入口，并未切换桌面默认profile或前端协议；备份/检查选择完整D2库存，依然complete_exit=false、activation_allowed=false。

验收需覆盖原班级/学生/已完成消息保留、同一Owner、免密码进入和会话旋转、实际HTTP发现/文档列表、损坏凭据拒绝、已连接应用拒绝、迁移回滚、提交后发布失败续接、幂等重入及旧D1回归。Windows DPAPI/真实PG本机测试与现有双平台CI覆盖范围分别记录，不把Linux跳过的Windows测试算通过。完整D2可移植退出、迁移激活和原编辑器仍未交付；回滚方式是启用前撤回代码，启用后停止服务保留原库/受检checkpoint交operator处理，禁止DROP文档表或篡改迁移head。
