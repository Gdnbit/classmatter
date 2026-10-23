# 实现与验收台账

更新时间：2026-10-23。基线：W1 `161a583`、W2-01 `9e97a08`，继续在 `codex/desktop-demo` 实施。此表是工程状态索引，不替代 canonical SDD、正式任务状态、签名或发布准入。

## 状态与顺序

状态分开记录：`implemented-synthetic`（已有合成工程实现）、`demo-only`（样例/内存交互）、`partial`、`pending-validation`、`deferred`。代码存在不等于正式 `implemented-green`。107项需求、147项Eval、94项原子任务不因本表变化。

1. W0：建立当前实现/证据/剩余项台账。
2. W1：冻结现有前端交互，逐页验收；先修布局、不可达入口、误导反馈与空态，再接业务。未来页面验收只验证导航/样例/明确未接入，不提升功能范围。
3. W2：最小真实桌面纵向切片，但数据仍为synthetic：进程托管→登录→班级/学生→事实记录→服务端预览/确认→BCG保存→Today/Timeline→退出重启读取。
4. W3：同一界面接入原有Agent查询/草稿和模型配置；真实供应商质量单独验证，密钥由用户在受信界面输入。
5. W4：补齐退出/恢复/运维，形成候选证据；先合成shadow，再作教师净负担研究和正式准入决定。
6. W5：依据真实任务证据选择通知责任闭环或其他下一切片；新release change，不偷渡进冻结R1。

W0已建立；W1当前已覆盖交互基线为`ready-for-binding`；W2-01已实现受控runtime入口，W2-02/03完成学生与注意力/工作页绑定，W2-04收口冻结R1的真实界面与故障矩阵（候选，须以对应PR的最终验收/CI为准）。完整Demo所有页面并不属于R1；W3真实Provider质量与W4/W5仍未完成。此结论不是“整个前端功能已完成”或正式R1 Gate晋级。

## 能力、代码与追溯

| 能力 | 状态 | 实现落点 | 追溯与剩余验收 |
| --- | --- | --- | --- |
| 桌面窗口/原生顶栏/菜单/沙箱 | implemented-synthetic | `apps/desktop/` | DESKTOP-DEMO及W2-01 runtime工程验收；非新增正式R1任务；安装器/签名/更新未完成 |
| 对话、历史、标题、搜索、输入草稿 | demo-only | `store/ConversationStore.tsx`、`shell/AppShell.tsx` | A05/A06/A11；当前内存会话，非持久工作历史 |
| 首页三类注意力/个人任务 | partial / W2-03 implemented-synthetic | `store/DemoWorkStore.tsx`；`runtime/R1App.tsx`、`runtime/work-projection.ts`、backend activity | T-RDOM-009/010/013、T-RWEB-004；E-TSK-001/E-EVT-004；真实全班注意力/任务筛选已接，通知责任候选仍未实现 |
| 学生列表、详情、搜索、空态 | partial / W2-02 implemented-synthetic | `shell/AppShell.tsx`；`runtime/R1App.tsx`、`runtime/student-directory.ts`、backend roster | T-RDOM-002—005/011、T-RWEB-002；E-ROS-001—004/E-ID-001—004；真实姓名/UUID搜索、详情、关联跟进已接；非整个冻结shell迁移 |
| 登录/会话/恢复码 | implemented-synthetic | backend identity、runtime identity | T-RPLT-013/014/018/019、T-RWEB-001；E-AUTH-009—018；新开发桌面已接既有R1登录；owner凭据不由Agent设置 |
| 事实/观察/更正/来源 | implemented-synthetic | backend activity、runtime forms | T-RDOM-006—008/012、T-RWEB-003；E-EVT/E-LEAVE/E-HWK；需在冻结桌面交互复验 |
| 预览/批准/提交/幂等/审计 | implemented-synthetic | backend QG/BCG/ISB、runtime command receipts | T-RPLT-007—009/015—018；E-CMD/E-AUD/E-AGT-015—025；不能复用Demo确认当服务端批准 |
| 班级/学期建立、切换、归档 | implemented-synthetic | backend roster、runtime term metadata | T-RWEB-006、T-RDOM-011；E-CLS-001；桌面接入需保留范围/版本与只读历史 |
| Agent loop/查询/任务及原文草稿 | implemented-synthetic | backend infrastructure agent、application agent_tool_contracts | T-RAGT-001—004；E-AGT-001/002/009—014；仅3个封闭查询/草稿工具，非通用本地执行 |
| 模型配置/测试/启停 | partial | runtime ModelConfiguration、backend model_control/provider/secrets | 现有模型契约/合成协议测试；Demo设置不连网；真实provider质量pending-validation |
| Conversation Memory | partial | backend agent_memory | 临时内存15分钟/10轮/32会话；无跨进程checkpoint/长期画像/持久偏好 |
| SSE状态与取消 | partial | backend HTTP agent、runtime R1App | 有事件与取消，答案完成后整段发出；逐token/replay/checkpoint未实现 |
| 核心退出包/同机checkpoint | partial | backend exit_package、operator_backup、local.py | T-REXP-001—003、T-ROPS-003/006；核心验证≠完整退出，lifecycle仍不完整 |
| 生命周期/跨机恢复/退役 | partial | schema inventory及退出/备份边界 | T-RLIFE-001—005、T-ROPS-001—007；权利/限制/删除/保留/admission账本、重放与退役证明待实现 |
| 学校通知/责任候选/接手闭环 | demo-only / discovery | shell ResponsibilityCandidate | R-PROD-001、LR-WRK/LR-COL；不自动判责，真实服务未实现，另行release决策 |
| 导入/成绩/生产排座/分组/值日/宿舍 | deferred | shell样例；完整v1任务定义 | T-IMP/T-GRD/T-SEA/T-ORG/T-DOR；明确非R1，座位交换Demo不是solver交付 |
| 报告/沟通/Office产物/外部MCP | deferred | shell样例；完整v1任务定义 | T-REP/T-EXP-002/T-MCP；无真实发送/生成服务 |
| Capture/ASR/RAG/Workflow/Extension/多角色 | deferred | 长期SDD、spikes | LR-*、T-EVO-001—008；各自需验证和新release，不开放万能IPC/JSON/DDL |
| 教师净减负/正式候选/真实试点 | pending-validation | R1 pilot profile与gate definitions | T-RREL-001—003；E-VALUE-001；没有代表性教师实证，不用合成测试代替 |

## W1 页面验收清单

| 页面/动线 | 必须达到 | 自动/人工证据 |
| --- | --- | --- |
| 首页→会话→候选→检查器 | 固定输入、会话隔离、清楚反馈；两步确认且仅Demo内存 | desktop acceptance A01—A11 |
| 学生→搜索→详情→栏目→对象对话→返回 | 姓名/学号搜索、无结果可清空、未知身份不回退、窄窗口按钮不竖排 | A12通过；本轮IAB截图已复验 |
| 工作→详情→完成→首页/学生/总览 | 同源任务/计数，责任待确认，不声称真实交接 | A02/A03 |
| 移动更多→各模块→设置→返回 | 菜单可见、设置可达、限高滚动/键盘退出/外点关闭 | A12/A17通过7入口、设置、键盘、焦点与外点；本轮IAB截图已复验 |
| 数据/名单/表格/文档/座位/宿舍/分组/Inbox/自动化/知识/报告 | 每页有标题、可达详情及明确样例边界；不伪造后台成功 | 原smoke + A13覆盖11个入口；A14通过名单/宿舍过滤和范围空态/分组确认/Inbox来源；非全部操作 |
| 设置所有栏目 | 栏目切换正确；未实现设置解释边界，不能用开关伪装已经启用 | A13通过9栏目说明弹层与焦点回归；模型表单仍不连网 |

## W2实施设计与停止条件

- 复用现有模块化后端和typed clients，不重新创建另一套领域服务；先设计UI绑定与宿主进程契约，再接已有API。
- 不直接解禁Demo网络/CSP；独立运行模式、固定受信服务origin、进程所有权、握手/认证、健康、关闭及故障恢复均要有封闭测试。
- 持久事实仍经QG/BCG/ISB；草稿与Memory不是事实源。断线/未知提交先查receipt，不自动重放。
- 首先只在隔离合成数据库验证。现有用户数据库不自动初始化/迁移；owner密码/恢复码由用户交互设置，不进日志/Git。
- 验收：新增事实/任务在同一桌面显示，重启后存在；错误scope、过期会话、版本冲突、重复点击、审计故障、未知提交分别可诊断；原实例无损。
- 数据模型/迁移、接口、权限或R1语义需变化时另列变更，不静默修改冻结task/hash。W2完成需源码、迁移/回退策略、合约、隔离PG、浏览器/桌面及故障证据齐全。

## 版本与证据管理

各波次小提交；公开清单复核后提交本地开发分支。用户2026-10-23明确授权本阶段验收通过后同步GitHub；本次仅同步已审查源码与文档，不包含安装包、运行库、截图、密钥和证据原件。正式任务仍planned/Eval仍not-run时保留原状态，另用本台账记录工程事实；完成正式晋级需目标版本绑定和批准证据。

基线复核：后端非DB278通过/314未选入；task graph有效但正式implemented-green=0；147项Eval中82项executable-spec、65项catalogued。这些是本轮前置检查，不是W2/真实模型/生产验收。

W1第二轮：Web39项、类型、普通/Demo构建通过；桌面7项边界测试、原打包smoke及真实打包应用A01—A17通过，`pageErrors=[]`、`externalRequests=[]`。修复被回归捕获的表格view URL回落；测试使用已有`/students?view=table`，没有添加平行`/views`路由。Product Design截图流程帮助发现窄窗口两个问题，未改变冻结整体风格。

W1-B已完成定向工程验收：数据/表格/文档/报告的详情、返回/取消、工作表菜单及说明反馈；A15/A16通过。表格空白保持未录入，工作表内容和选中公式栏一致；没有实现真实解析/导入/导出。

W1-C已完成定向工程验收：A17覆盖移动更多7入口/外点、学生任务空态/返回、知识搜索无结果/恢复/关闭、自动化示例标记；无真实后台计划或模型引用。桌面最小窗、窄Web布局和关键交互已验证，全平台读屏器/多DPI验收单列，不把暂未覆盖项默认为通过。

### W2首个变更单元

W2-01已实施：新增desktop runtime supervisor/policy/main与单测，backend desktop operator/只读进程证明及测试，独立runtime构建/启动入口。原Demo main/policy不放宽。真实子进程、占用端口/错误proof/超时/退出和现有后端契约已验证；实际复用已有R1页面通过一次性SCRAM库的完整记录—任务—重启工程链路。此步骤不是冻结Demo全页面绑定或完整产品MVP完成。

1. 定义受控desktop runtime mode/进程契约，保留原离线Demo不放权；落点desktop main/policy/preload及隔离测试。启动/握手/退出/端口占用/服务崩溃各有确定结果，不接受renderer任意命令或URL。
2. 在Web表现层建立只绑定R1的状态/动作接口，复用runtime现有typed API、身份、receipt校验；不把MockDomainStore字段强行映射为真实座位/宿舍。落点App、shell及runtime表现层；StudentId使用后端UUID而非演示学号。
3. 首先接班级上下文、学生、事实记录和任务/Today/Timeline；未实现模块保留Future，不取回fixture填充真实视图。命令沿原服务端preview/approve/commit，不开放Agent写工具。
4. 验证依赖：后端合约/nonDB→隔离PG→浏览器真实接口→桌面进程生命周期→重启持久性/未知结果/故障回归。验证用合成临时实例；不初始化/迁移用户原实例。

其中第1项及既有R1页面的第3项纵向集成已形成合成工程证据；第2项全冻结shell绑定及第4项完整故障矩阵仍需继续，不把未实施项标绿。没有冻结计划要求为“前端完成”提前实现真实模型或新业务模块。

W2-01验证：后端非DB284项、完整隔离DB回归315项（包含真实浏览器与桌面）全部通过；Web39项及类型/普通与两种桌面构建通过；Node18项（原7+runtime11）通过。真实Electron/PG端到端涵盖私有批准/BCG提交、事实关联任务、重启后仍可查、fake只读来源/草稿不落库和强制退出清理。原型截图与测试结果只在忽略目录。原离线Demo17组回归复测通过；正式target-bound Eval/任务晋级、真实模型和用户研究不由上述工程测试替代。

新增读取接口仅`GET /health/desktop`，只在desktop operator opt-in装配中存在，不更改生成的业务契约。进程proof不授权用户/业务写入；测试临时owner不用于用户实例。其追溯复用T-RWEB-001—006、T-RDOM-006/009/010/012/013、T-RAGT-003，工程证据不提升正式任务或Eval状态。

`verify -Suite desktop`已纳入独立runtime资产构建（不启动服务/数据库）；真实PG/Electron测试仍在Windows本机DB suite中执行，当前远端CI只在Linux执行DB组，不能声称远端已经覆盖Windows持久化桌面。源代码开发入口不是完整安装包；默认用户runtime/owner/真实模型凭据仍须本人按文档配置，本轮未创建或修改。

### W2-02：真实学生详情与跟进绑定（2026-10-23）

- 复用同一QG返回的学生、活动数据和现有BCG操作；新增纯表现层投影，不新增API、迁移、工具、权限或业务写入口。
- 姓名/内部UUID搜索支持去除首尾空格和大小写匹配；同名学生保持独立，停用身份保留历史，不把UUID伪称学号。无匹配时可清空，搜索变更清除旧详情，班级/会话变更清除搜索。
- 详情显示当前范围内记录与未结束跟进数；关联跟进进入现有工作页并保持学生筛选，可用原预览/确认动作处理。空身份返回空集合，不回退全班数据。教师观察没有晋升为人物事实。
- 成绩、文件和关系图谱明确未接入；没有把Demo字段或fixture填入真实详情，没有建立长期画像或把样例界面当作生产功能。
- 工程验收：新增2项投影测试（Web总41项并通过类型检查），18项桌面边界测试通过；真实Electron/一次性SCRAM PostgreSQL新增搜索无结果/恢复、UUID检索、两位学生详情隔离、跟进跳转/确认完成后摘要未结束计数归零，并保留记录/任务重启持久化与Agent草稿不落库验收，通过。截图/结果位于忽略的`apps/desktop/.build/evidence/runtime/`，人工检查桌面截图无溢出或样例冒充。
- 本轮追溯沿用T-RWEB-002/003/004、T-RDOM-002/006/009/010/012；没有调整Requirement/Eval/Task/Gate语义或正式状态。W2仍未整体完成，后续优先继续绑定注意力/工作主链与完整故障矩阵，其后再完成W3/W4；真实供应商质量、教师净负担、正式准入仍待验证。
- GitHub远端新增`a5e3156`研究文档已先合并并保留，Agent承接工作/Pi对照实验仍为Discovery/Future。同步不代表这些研究已实施或准许扩大R1。
- 本轮既有回归：backend非DB284项、真实浏览器/PG集成1项、真实桌面/PG集成1项、Web41项/类型/普通与Demo/runtime构建、Node18项通过。工程脚本81项在新增源文件加入Git索引后重跑通过（首次索引遗漏未记为通过）。公开内容和历史扫描仅有原4条已审查记录、0未解决；68份Markdown的引用/UTF-8/空白与冻结Task/Gate/Eval图检查通过。未重复运行上一轮完整315项DB suite，不把定向回归冒称全量。
- 原离线Demo smoke与打包应用A01—A17复测通过，`pageErrors=[]`、`externalRequests=[]`。首次因已有Demo占用单实例锁而退出；核实路径与窗口后正常关闭该Demo再重跑通过，不修改业务实例。浏览器预览构建恢复Demo模式，避免误把用户当前8443页面切成未配置的R1登录。

### W2-03：全班注意力与工作筛选边界（2026-10-23）

- 修正学生详情筛选意外影响全班首页/总览的缺陷：注意力和全班未结束计数始终来自当前授权班级/学期的完整活动快照；总览最近事实也来自同范围。工作页学生/状态筛选只是投影，不修改领域状态。
- 从全班注意力卡片进入任务时清除旧学生/状态筛选，确保目标可见；学生详情关联跟进保留明确学生范围但清除旧状态筛选。总览统计入口与其展示范围一致，不再用全班数字跳到残留的局部结果。
- 新增全部/未结束/等待别人/已结束筛选、当前/全班任务数量及清空空态；状态筛选与学生筛选取交集。完成/取消退出注意力但保留可查历史，等待状态不声称对方接手或自动转移责任。
- 新增`runtime/work-projection.ts`纯投影和2项测试；复用既有QG/BCG、预览确认和幂等/收据路径。不新增后端、Schema、工具、通知推断、调度或提醒机制。
- 追溯复用T-RWEB-004、T-RDOM-009/010/013与既有E-TSK/E-EVT；Requirement/Eval/Task/Gate定义及正式状态不变。W2其余冻结shell绑定/完整故障矩阵、W3真实provider质量、W4生命周期及用户研究仍待完成。
- 验收过程保留失败：桌面首轮测试仍假设全班任务返回学生页会保留某位学生详情，在新正确范围下找不到详情；测试明确重选学生后重跑通过。未修改产品去迁就旧筛选残留。最终验收结果在本节追加，不能把未执行的用例或上一轮DB全量算作本轮通过。
- 最终定向工程验收通过：Web43项/类型检查、普通与runtime构建；Node18项；真实浏览器/PG1项与真实Electron/PG1项；工程脚本81项；68份Markdown链接/UTF-8/空白检查、Task/Gate/Eval引用和定义hash检查。Electron新增覆盖空学生筛选不影响全班注意力/最近事实、卡片范围重置、等待转移、总览统计跳转、完成退出注意力及已结束历史。结果仍为`pageErrors=[]`、`externalRequests=[]`，忽略目录`apps/desktop/.build/evidence/runtime/04-work-filters.png`已人工复核布局。
- 本轮无后端/数据库迁移修改，未重跑完整315项DB或284项非DB套件；以上定向真实API/PG回归不等于正式发布准入、模型质量或真实教师净负担验收。原离线Demo行为未修改；浏览器预览仍恢复Demo构建。公开清单按最终字节更新，GitHub同步只包含审查后的源码/文档，不包含运行数据与截图。

### W2-04：冻结R1界面与故障矩阵收口（2026-10-23）

基线为公开修复PR #8合并后的`3e0b388`；独立分支/PR，不吸收未审查的并发文件。原工作树的新鲜度补丁保留不动，按语义重新应用并验证；默认离线Demo与本次真实R1模式仍分离，不能拿前者的内存成功代替后者的回执。

| R1入口/功能 | 真实绑定与代码路径 | 受影响验收 |
| --- | --- | --- |
| 登录、恢复码、会话撤销 | `runtime/identity.ts`、R1App登录/设置 → ISB | `backend/tests/test_web.py`真实登录/恢复码/撤销/丢失响应与旧会话迟到；不保存凭据到业务缓存 |
| 班级/学期建立、显式切换、元数据、更名/归档 | R1App → typed roster/metadata → QG/BCG | 真实Web建立/更正；`test_activity_gateway.py`归档保留历史且拒绝新写；归档需原批准 |
| 学生、来源标识、重复候选、停用 | R1App、`student-directory.ts` → QG/BCG | 同名/UUID/空态/更正、学生隔离、重复候选不合并、停用仍可查 |
| 事实/教师观察及更正、来源历史 | R1App RecordCard/表单 → QG/BCG | Web来源/时间/更正/历史、关联任务与桌面重启；不持久化AI推断 |
| Today、Timeline、工作筛选/状态 | R1App、`work-projection.ts` → activity QG/BCG | 全班/学生范围、等待/完成/取消、来源回查；无通知派责/自动交接 |
| 可信预览/批准/幂等/回执核对 | R1App命令控制 → `CommandPreview.tsx`纯表现组件 → 原BCG/ISB | 绑定错误/丢失响应/明确拒绝；边界测试覆盖批准过期、scope、版本、重复键及审计回滚 |
| 审计与核心退出导出 | R1App设置 → 原审计QG/退出命令与下载 | Web批准/JSON下载/内容校验；桌面下载采用测试自有临时目标，不改变生产保存路径策略；完整生命周期退出仍属W4 |
| Agent关闭及只读/草稿 | 原runtime client → Pydantic AI及既有3工具 | 无模型时结构化闭环可用；fake仅证明集成/协议，不是W3真实质量 |

新增恢复语义：原子采用成功的当前scope查询快照；读取中或失败后不生成新的领域预览。失败保留上次快照并持续标记“当前列表尚未刷新”，关闭普通错误提示不能解除保护。首次无快照也不能误开放建班。查询失败不回显原始正文；成功重新读取后才恢复编辑。Provider配置自身版本/撤销机制不与班级读取故障耦合，仍受原控制器校验。

已验证的提交回执与查询刷新分开：收据已绑定则保持“已保存”证据；之后读取失败不能倒推回滚、重新新建或静默重放。未知提交继续只核对原proposal/幂等键，既有直接身份恢复与拒绝路径不变。`CommandPreview`不持有API客户端、身份或第二份批准/事实状态；拆分不改变DOM入口和确认行为。

| 故障族 | 工程证据落点与断言 |
| --- | --- |
| 初始/部分并行读取失败、恢复、提交后读取失败 | 新Web注入503验证旧快照标记、无新preview/commit、正文canary不显示、可信保存仍成立；恢复后同一任务只出现一次 |
| 提交响应丢失、错误回执、重复点击/重试 | 既有真实Web故障 + `test_command_status.py`/`test_roster_gateway.py`；一条业务记录/一个有效回执，先核对原键 |
| 版本冲突、过期/拒绝/错误scope、审计故障 | roster/activity/status隔离PG测试；拒绝、事务回滚、不释放未审计结果，不能用UI隐藏代替服务端校验 |
| 会话失效、scope切换、迟到响应 | 真实Web身份轮换/撤销、旧响应；`test_agent_memory_expiry.py`；不能污染新scope或释放过期结果 |
| 端口占用、错误proof、API死亡、父进程强退、重启 | Node监督器测试及真实Electron/PG链路；只停止自有进程，不附着/自动重放；原用户数据库不动 |
| 取消、Agent-off、退出导出 | 既有协议/取消回归与直接UI闭环；核心JSON可下载不代表完整跨机/退役；真实native对话框的人机体验不由测试替代 |

测试自有下载目标只在Electron测试进程设置，验证生产download策略/保存选项和实际JSON字节，不向生产renderer暴露任意路径能力。截图/原始日志/退出JSON留在忽略目录，不进公开清单。完整安装器、签名更新、跨机恢复/生命周期账本、所有Demo未来模块、真实模型质量和用户净减负仍不属于本单元。

本单元复用T-RWEB-001—006、T-RDOM-002/006—013及既有E-CMD/E-AGT/E-LOCAL/E-WEB/E-AUD追溯，不修改Requirement/Task/Eval/Gate定义或正式状态。最终本地结果与两平台CI必须逐项记录在PR；未全绿前不标W2完成、不进入W3。回滚为revert本PR；无新增迁移或数据重写。

本地定向结果：Web43项/类型/构建通过；真实浏览器与Electron/PG2项通过；roster/activity/status/memory-expiry隔离PG30项通过。首轮新测试未等待重新读取完成便断言可编辑而失败，修正等待实际按钮状态后完整重跑通过，不将失败计为通过。其余公开检查和远端完整CI以PR证据为准；未重复本机全315项DB回归。

PR #9首轮Ubuntu完整CI在320px最新来源可见性断言失败（其余309项DB通过、5项平台跳过），Windows通过；没有合并或跳过失败。修复viewport尺寸变化触发scroll早于ResizeObserver时误取消跟随最新回复的问题，保留主动上滚阅读历史时不抢回位置。最终状态以修复后的两平台完整CI为准。

### W4-01：同机checkpoint发现与中断保护（2026-10-23）

本单元从已合并PR #9后的main建立独立分支；不依赖W3真实Provider付费评测，不改Pydantic AI、业务模型、权限或正式Gate。教师的实际价值是故障后无需另记备份UUID，操作员可在数据库停止时找到可检查的同机checkpoint，避免把损坏/未写完的文件当作恢复凭据；教师平时无新增维护步骤。

- `backend/local.py backup-list` → `operator_backup.SyntheticBackup.catalog()`：只读、闭合UUID元数据；有效元数据不等于已成功恢复，所有条目均明确`restore_verified=false`。损坏/绑定不匹配/不兼容条目拒绝；原始名称、行内容、凭据和错误细节不输出。
- checkpoint先写加密临时文件、flush/fsync，再以原子exclusive hard link发布。已有checkpoint绝不覆盖；写入/同步/发布故障保留上一有效备份。主机骤停遗留pending文件只计数，不自动删除/导入；不支持hard link的文件系统拒绝，无不安全降级。
- 清单限制128目录项/候选文件合计64MiB/单包原32MiB，超限不返回部分成功。目录或checkpoint symlink/junction保留拒绝边界；无任意路径、SQL、DDL、自动修复或新HTTP/Agent能力。
- 验收：真实临时PG snapshot/隔离恢复及源库存量不变；实际Windows DPAPI+SCRAM CLI在stop后发现、start后check；同步/发布失败及UUID碰撞不产生可见半包且不覆盖；坏包、链接和清单上限拒绝。符号链接创建受宿主策略限制时明确skip，不当作通过。
- 复用T-ROPS-003/006及E-OPS-005/006/007既有目标，仅形成合成工程证据，不将完整任务/正式Eval标绿。不覆盖retention、生命周期ledger重放、跨机迁移或退出完整性；这些仍待实施。回滚为revert本PR，无数据库迁移；旧checkpoint格式保持兼容。

具体本地结果与完整Windows/Ubuntu CI按PR记录，远端全绿前不合并。使用方法及限制见[backend README](../backend/README.md)。
