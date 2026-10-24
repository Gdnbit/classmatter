# 实现与验收台账

更新时间：2026-10-24。当前已验收公开main为`21a7169`：D0/E1由PR #13—17收口，D1-00由PR #18收口；D1-10显式存储基础已由[PR #19](https://github.com/Gdnbit/classmatter/pull/19)及[两平台CI](https://github.com/Gdnbit/classmatter/actions/runs/40063379109)验收，Windows非DB340/Web55/desktop23，Ubuntu非DB338+2跳过、DB/browser341+6跳过。新Goal active；D1-11a快照核验在独立候选分支，持久会话/完整生命周期/UI还未交付。Owner仍由本人稍后设置，服务ready不等于个人验收。W3仍在Draft PR #10，真实Provider质量blocked；完整生命周期/跨机恢复尚未完成。早期提交号和候选状态保留为历史，不能覆盖本摘要。本表不替代canonical SDD、正式任务状态、签名或发布准入。

## 状态与顺序

状态分开记录：`implemented-synthetic`（已有合成工程实现）、`demo-only`（样例/内存交互）、`partial`、`pending-validation`、`deferred`。代码存在不等于正式 `implemented-green`。107项需求、147项Eval、94项原子任务不因本表变化。

1. W0：建立当前实现/证据/剩余项台账。
2. W1：冻结现有前端交互，逐页验收；先修布局、不可达入口、误导反馈与空态，再接业务。未来页面验收只验证导航/样例/明确未接入，不提升功能范围。
3. W2：最小真实桌面纵向切片，但数据仍为synthetic：进程托管→登录→班级/学生→事实记录→服务端预览/确认→BCG保存→Today/Timeline→退出重启读取。
4. W3：同一界面接入原有Agent查询/草稿和模型配置；真实供应商质量单独验证，密钥由用户在受信界面输入。
5. W4：补齐退出/恢复/运维，形成候选证据；先合成shadow，再作教师净负担研究和正式准入决定。
6. W5：依据真实任务证据选择通知责任闭环或其他下一切片；新release change，不偷渡进冻结R1。

W0已建立；W1当前已覆盖交互基线为`ready-for-binding`；W2已按[PR #9最终CI](https://github.com/Gdnbit/classmatter/actions/runs/39921094043)收口冻结R1真实界面与故障矩阵，W4-01按[PR #11最终CI](https://github.com/Gdnbit/classmatter/actions/runs/39941521068)通过后合并。完整Demo所有页面并不属于R1；W3真实Provider质量与完整W4/W5仍未完成。此结论不是“整个前端功能已完成”或正式R1 Gate晋级。

当前下一阶段（用户2026-10-24确认）：先交付真实桌面明确入口/只读检查与操作验收；再按独立post-R1变更推进D1耐久会话；W3只推进不需凭据/费用的工程准备；随后纵向验证“班级工作小结，引用已有事实与任务”。用户另明确允许创建全新本机合成实例，Owner本人稍后设置；本机操作结果不应写入公开配置/凭据。新能力仍不获得真实数据或Agent业务写权限，不因计划确认改正式Gate。

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

### W4-02：离线退出包复制核对（候选）

教师问题：更换设备/交付备份前，操作员不应仅凭“文件能打开”判断资料复制完整。复用原`verify_exit.py`和固定`validate_package`，新增`--compare-with`，一次命令分别核对文件字节、规范包及核心数据摘要；正常使用无额外业务录入。两份均合法但不同返回2（包括仅格式变化），坏包返回1，完全一致返回0。不是来源认证或恢复授权，不导入/写入数据库。

验收覆盖真实BCG批准/QG下载包→复制→离线核对，比较前后事实/任务/收据/导出/审计数量及文件字节不变；格式、元数据和核心内容差异分开报告。坏包、重复字段、NaN/Infinity、编码/深度/尺寸、缺失、目录/特殊文件/叶子链接拒绝，错误不回显原文/路径。新增文件打开约束不改变退出包wire schema、BCG授权或导出行为；父目录链接不在本机只读operator的隔离保证内。

复用T-REXP-001—003、T-ROPS-006和既有退出完整性目标，不修改正式Eval/Task/Gate语义或状态；`--require-complete`继续拒绝。Windows/Linux各自通过不证明实际两台机器的导入恢复。跨机业务写入、身份重新配置、生命周期账本和退役证明仍待实施。独立PR记录最终测试/CI，回滚为revert，无迁移；首轮Windows目录异常测试断言过窄已修正，不当作生产成功。详细操作见backend README。

### 数据库与真实接入：设计准备（design-proposal，未实施）

2026-10-23在main `3d8d750`上核对现有22表、QG/BCG/ISB、界面Store与刷新链。新增[专题设计提案](design/database-live-data-design.md)，建议保留PostgreSQL/SQLAlchemy Core/Alembic/Psycopg；先绑定真实学生/记录/任务投影，再以单独后续change处理耐久聊天、运行、工作专题和可靠变更订阅。本文没有执行迁移、增加Tool、启用Provider或替换当前Demo。

设计把会话消息与正式事实分开、明确工作专题不是授权workspace，补齐并发幂等/终态、分页计数、跨页快照、提交水位、deadline无写变化及备份退出升级条件。D0复用既有T-RWEB-002—004/T-RDOM-009/010/013；D1—D3与DB-*为后续候选，不是新正式Task/Eval，原107/147/94定义和Gate状态不变。设计和官方资料核验不等于真实性能、模型质量或教师净负担验收；先前W4-02实际通过与合并证据见[PR #12](https://github.com/Gdnbit/classmatter/pull/12)。

### D0 Goal：真实数据闭环执行与验收（2026-10-23，进行中）

用户已明确授权持续推进及验收后GitHub同步。见[执行目标与验收台账](design/live-data-delivery-acceptance.md)：U0固定范围，U1恢复刷新，U2主界面真实绑定，U3综合验收/公开交付。11项LD验收索引不是正式Eval；目前未标通过。D1—D3不作为偷偷扩大R1的手段，无真实数据/付费Provider/Agent业务写入权限变更。设计原提交`b8bf32a`的81脚本测试、71份Markdown检查、公开guard及历史扫描为前轮设计证据，不等于本Goal完成。

### D0-U1：前台恢复与断网重读（候选，未整体验收）

基线为设计PR #13在两平台完整CI通过后的main `5fcc2e2`。教师返回应用或恢复网络时不必手动重复刷新；复用现有QG `reload()`与BCG/ISB边界，不新增API、表、Store或Agent权限，不将原Demo改成真实业务模式。

- `runtime/query-refresh.ts`合并focus/visibility/online事件，250ms合并窗、自动读取启动间隔至少5秒；只在可见、联网、空闲时执行。失败不自主循环重试，没有周期轮询；新事件/显式重读可恢复。卸载注销事件和timer。
- `R1App.tsx`保留最近成功快照和既有generation校验；断网立即标旧，跨断网代次的旧成功响应不能因后来online而重新标fresh。表单、待确认proposal、busy提交/核对、恢复码、审计、设置和Agent运行期间延后自动重读；不自动批准、提交、切身份或调用模型。
- `tests/query-refresh.mjs`覆盖事件风暴、执行前空闲重检、断网/隐藏、无重叠、失败无轮询、卸载迟到错误。`tests/runtime.mjs`走实际QG/PG，只有交付延迟/故障注入，不stub成功业务；验证表单保留、重连、跨offline/online迟到响应，以及待确认/Agent交付期间无额外API请求。普通恢复窗口统计所有非GET/HEAD请求为0，不只统计command POST。
- 已有本地真实Web/PG两轮分别1通过（87.37秒；加入连接代次后92.06秒）；真实Electron/API/PG重启链1通过（43.14秒），监督器18通过，Web49单测/类型/build通过。后续补充待确认/Agent交付断言后须重新跑最终Web链；最终结果、审查和远端CI以独立PR为准，不拿前轮测试覆盖新增断言。
- 独立只读对抗审查未发现已证实P1/P2缺陷，同时指出idle布尔单测不等于真实批准/Agent竞态覆盖，以及最初只计command POST不足以证明零其他写入；已补真实断言/全非GET计数，仍不宣称覆盖所有身份轮换窗口。

审计进一步发现350ms观察可能被5秒冷却掩盖，不能证明交互保护确实工作。已把表单、待确认、Agent交付的真实浏览器观察延长到5250ms并保持交互未结束；fixture总体子进程上限100→130秒只容纳新增场景等待，所有业务/响应断言仍保留。加强前第三轮Web/PG1通过93.50秒只作历史记录；加强后的最终运行必须另取证据。真实gateway30项通过79.07秒，覆盖既有版本/幂等/授权/审计/Memory到期，不表示已经穷尽前端所有身份竞态。

加强后最终真实Web/PG链1通过99.04秒，忽略日志`test-results/live-data-refresh-web.xml`；合成上下游真实业务成功、故障/交付延迟受测试控制，外部请求仍为空。后端全非DB301通过、2个宿主链接能力跳过、315个DB项未在该命令执行，日志`test-results/live-data-refresh-nondb.xml`；定向gateway与桌面日志分别为`live-data-refresh-gateways.xml`/`live-data-refresh-desktop.xml`。独立复审确认冷却掩盖已修复、未发现新的已证实实现缺陷；远端完整两平台CI通过之前不标本单元最终验收，不标Goal完成。

当前前台持续停留、无任何事件时不会自动更新到期投影；LD-08与主界面真实绑定U2、综合验收U3仍待完成。不以本单元宣布全部页面、耐久聊天、工作专题或跨窗口推送已完成。回滚为revert独立PR，无schema/data迁移；原用户工作树修改不动。

U1最终远端验收：[PR #14](https://github.com/Gdnbit/classmatter/pull/14)在[完整CI39979232478](https://github.com/Gdnbit/classmatter/actions/runs/39979232478)的Windows/Ubuntu均成功后合并为main `ee44bfe`；Ubuntu实际310个DB/browser通过、5个平台跳过，非DB301通过、2个平台跳过。此处只收口U1，不提升正式Gate或整个Goal。

### D0-U2：真实主界面导航与同源投影（2026-10-24，候选）

从已验收main `ee44bfe`建立独立`codex/live-data-navigation`。目标是当前非Demo主入口中的真实页面可刷新/返回，列表、表格、详情和工作筛选不切到MockStore；不是把全部未来原型生产化。教师无需重复选取已有页面来核对同一事实，导航本身不新增业务录入、批准、模型或后台业务动作。

| 当前页面 | 实际数据/操作路径 | U2新增或保留的明确边界 |
| --- | --- | --- |
| 对话首页/三类注意力 | 原roster/activity QG及既有Agent客户端 | 需要处理/等待按原Task投影；可能遗漏仍无通知责任候选。聊天显式临时，不承诺刷新/重启恢复 |
| 总览 | 原学生/记录/任务授权快照及原统计投影 | 不额外维护统计副本或把AI推断写成事实 |
| 学生列表/表格/详情/时间线/跟进/记录 | `StudentDirectory`与原typed QG/BCG | 一个学生身份/一份记录修订/一项任务，多种表现；更正不增加记录数，停用保留历史。成绩/文件/关系不填样例 |
| 工作/筛选/任务详情 | 原activity及BCG命令 | 路径保存闭合filter和UUID；详情按当前activity解析，跨窗口更正后重读采用新版本，不保留旧对象作为事实 |
| 设置/审计/核心退出 | 原ISB、QG、BCG与配置控制器 | 不把UI导航变成身份、批准或恢复授权；原型未来模块与核心导出完整性限制不变 |
| 数据/专题/自动化等未来页面 | 仅固定页面壳GET | 明确未接入，不加载MockStore，也不创建Store/Schema/Task |

实现文件：`runtime/navigation.ts`闭合路由提示、`useRuntimeNavigation.ts`轻量原生History接线、`StudentDirectory.tsx`/`student-directory.ts`纯表现/计数、局部`student-directory.css`及R1App接线。URL/history不保存姓名、搜索词、正文、草稿、CSRF、供应商配置或批准。`history.state`不读取，挂载/恢复时规范化清除；交互期间只排队最新导航，不弹跳或增长历史；可信身份清理优先清除旧选择/排队。URL不包含旧class/term授权，不承诺刷新恢复历史scope；未知UUID显示缺失，不回落他人。

源码核验发现原`mount_web`只有`/`且middleware全拒query，真实deep-link刷新将404/400。因此新增有限UI壳GET路径，始终返回同一固定index文件，不拼文件路径或catch-all吞掉API/asset错误。只在Web mounted时允许学生view/tab和工作UUID/filter闭合参数；API/health/assets、重复字段、未知字段/值、超长输入和非GET仍拒绝。无业务API、Tool、数据库或权限变化。

验收文件：新`tests/runtime-navigation-browser.mjs`与`backend/tests/test_web_navigation.py`，原Web回归和桌面runtime链。合成内容经原UI预览/提交→实际PG，再验证表格/详情tabs/工作深链刷新、Back/Forward、未提交表单与待确认proposal延后导航、未知对象/Future/伪造history、注销后不释放事实；第二窗口经原BCG更正任务后，第一窗口focus重读及编辑表单须采用新标题。测试末尾另直接只读核对2学生、1记录的2修订、1项waiting/version3任务。截图/原始日志留忽略目录，不作为公开数据导出。

失败保留：最初HTTP缺深链；早期断言未等待提交后重读/排队导航；恢复dashboard不含学生ID却误期望隐式旧选择；Playwright便捷单页context不能再建共享页；桌面“视图”与原生菜单同名。分别补受限壳路由、等待真实完成、明确重选、显式共享context及侧栏范围定位，没有改产品去自动猜对象或删业务断言。独立审查发现并修复detail丢table view与规范URL未清history.state，补真实work/多窗口证据；U3身份/Agent导航/未知提交矩阵仍不可从本单元外推。

当前已验证Web54单测/类型/build、HTTP拒绝边界、真实聚焦链及Electron链的定向运行；加入最终数据库数量断言后，组合Web/PG/Electron仍在重跑，最终日志/计数及两平台CI按独立PR记录，不提前标U2或Goal完成。回滚为revert该独立PR，无schema/data迁移。LD-08持续到期刷新和U3完整故障矩阵仍待实施。

最终本地组合：`uv run --frozen pytest tests/test_web_navigation.py tests/test_web.py tests/test_desktop_runtime.py -q --pg-root <owned-PG18.6> --junitxml=../test-results/live-navigation-final.xml` 4通过150.32秒（含最终数据库数量/版本断言、规范history清理及detail表格刷新）。全非DB302通过、2项宿主链接能力跳过、316项DB未在该命令执行；Web54/类型/build、桌面边界18通过。独立审查发现的两项导航问题均修复，并补真实work/多窗口及桌面深链证据；未提升跨scope恢复、Agent/身份/未知提交完整矩阵。截图实查320px表格只在自身区域横向滚动，页面无横向溢出。公开审查、最终清单及远端完整两平台CI仍须以该单元PR的实际结果收口。

U2最终交付：[PR #15](https://github.com/Gdnbit/classmatter/pull/15)，提交`3b321696`，在[完整CI39999026807](https://github.com/Gdnbit/classmatter/actions/runs/39999026807)两平台成功及独立审查后合并main `5244047`。实际远端日志：Windows非DB304/Web54/desktop18；Ubuntu非DB302+2平台跳过、DB/browser311+5平台跳过。两平台公开guard、8.30.1历史扫描（4已审查、0未解决）、验证器81、文档72及图检查通过；643清单哈希独立复算零差异，例外元数据不变。不是完整Goal通过。

### U3：时钟重读与综合故障验收（2026-10-24，实施中）

基线main `5244047`；沿T-RWEB-002—004及原E-CMD/E-AUD/E-WEB/E-LOCAL，LD索引仅是本轮工程证据，不修改正式Requirement/Eval/Task/Gate。教师价值：不额外点击刷新即可看到既有任务跨到期变化，不因切页/未知回执重复操作；新增教师维护步骤为零。

文件级范围：`query-refresh.ts`依据既有QG `activity.as_of/due_at/overdue/status`计算下次到期重读；`R1App.tsx`一次性可见窗口定时失效仍交U1控制器，沿原session/generation与idle保护。已结束、已逾期、无截止不定时；最短5秒、最长浏览器安全上限，避免零延迟循环和timer溢出。隐藏/断网清timer，返前台由原事件合并重读；失败停止自动尝试。客户端墙钟不判定逾期、不改状态，不是定时任务、提醒或可靠推送系统；后台无实时保证，响应传输及交互延后有滞后，多API仍非原子快照。

验收增加`runtime-deadline-browser.mjs`/`test_web_deadline.py`：原BCG合成种子3项未来截止，真实服务器单调时钟跨到期，错误浏览器墙钟，表单延后、受控503交付、隐藏事件和可见空闲重读；无Agent adapter、外部请求及业务POST，最终PG三任务version1。隐藏由受控浏览器visibility事件验证接线，不冒称操作系统物理最小化。`runtime.mjs`加强未知提交Back/Forward后只GET原proposal/key、零额外preview/approve/commit，及Agent延迟交付期间Back/Forward不重读、不新增历史。`runtime-navigation-browser.mjs`增加实际旧200/撤销后401交付跨登录代次，以及原班归档→新空班后旧scope不回填；不手改React state或放开单active约束。

首次加强组合3通过、1失败：新会话测试错误地把“未选择学生的授权班级时间线”期望为空；随后聚焦复现定位，改为交付前后同源内容一致，新增真实换班空时间线强断言，而非修改产品隐藏合法事实。最终组合、完整CI和公开清单仍待执行。回滚为独立PR revert，无schema/data迁移，不影响原工作区用户脏改动。D1聊天耐久、D2专题、D3可靠变更流及真实Provider/用户研究仍未获得本轮实现或质量证据。

最终本地证据：Web/PG/Electron `tests/test_web_navigation.py tests/test_web.py tests/test_web_deadline.py tests/test_desktop_runtime.py` 5通过227.16秒；其中主链含实际停止Agent再交付迟到响应，答案/草稿未采纳、零额外POST及单次排队导航。Web55/类型/build、desktop18、非DB302+2宿主链接跳过（318项DB的最终收集数以后续CI为准；该非DB运行时为317项DB未执行）通过。U2基线另完整本机DB316通过957.39秒，不冒充新增U3全DB。失败保留：会话timeline错误预期、清理未等待交付而掩盖原异常、同名新建按钮需侧栏定位、新建班不自动替换教师当前归档选择需明确select；均修测试同步/合法动线，没有删安全断言或改变产品授权。

独立审查要求补足真正PG业务重启：`test_local_runtime.py::test_owned_business_entities_survive_actual_pg_process_restart`在新临时SCRAM/DPAPI运行时经BCG写学生/事实/关联任务，关闭全部连接再stop/start自有PG，新建ISB/QG和数据库对象核对原实体ID/version/count、关联及完整投影；不是仅检查数据库元数据。local-runtime文件6项通过31.50秒，随后固定合成时钟的最终单项仍须核验。此证据只证明同机自有实例重启，不升级跨机迁移/容灾/恢复准入。README空白行导致docs首次拒绝，清理后72Markdown/引用/UTF8及图检查通过；正式107需求/147eval/94任务与green0不变。U3公开guard/历史扫描/精确清单、独立PR及完整两平台CI必须按实际结果收口。

最终PG业务重启单项（固定合成时钟版本）1通过9.93秒。该补充缺口已由实际测试消除，不再把此前的metadata smoke当成业务持久性证明。最终公开CI/提交/合并收口证据记录在本单元独立PR验收评论；其成功之前本Goal不宣告完成。

## 下一阶段 E1：真实桌面入口（2026-10-24，候选）

基线main `d9400c1`。新增`apps/desktop/runtime-check.cjs`只读固定路径/描述/profile检查，输出闭合布尔和步骤码；不读取受保护凭据正文、不写文件/启动服务，不将前置文件齐备冒充Owner/服务ready。`runtime-launch.cjs`拒绝缺条件、旧checkout及测试fixture描述；`open:runtime`构建当前源码后走原自有API握手/readiness，原Demo入口不变。新增4项测试覆盖空目录不变、正常元数据不等于就绪、跨checkout/fixture拒绝、坏/过大配置和受保护文件缺失；desktop22通过。真实隔离Electron/API/PG链1通过40.44秒，原持久化/故障断言保留。

独立审查指出隔离Electron测试不直接覆盖新launcher拒绝入口；补真实Node子进程启动临时checkout的launcher，验证缺条件/坏JSON/fixture描述退出2、无路径/原文回显、不加载Electron或生成cluster。最终desktop23项通过；真实正常入口另已构建/打开并由原握手与API readiness核验（不外推Owner已创建）。

用户明确授权全新合成实例，Owner本人稍后设置；本人使用链因此仍pending-owner，不能用测试账号冒充其验收。测试集不依赖/覆盖这个实例。文书下一切片选择“班级工作小结，引用已有事实与任务”；不是新增学校授权/自动责任判断。此单元无数据库Schema/API/角色权限/模型调用改变，沿原T-RWEB与desktop工程追溯。公开清单/安全扫描及本PR两平台CI待核验，回滚revert代码不删除已创建的合成实例或凭据。

E1收口：[PR #17](https://github.com/Gdnbit/classmatter/pull/17)已在[完整CI](https://github.com/Gdnbit/classmatter/actions/runs/40058146095)两平台成功后合并为`e95863a`；Windows非DB304/Web55/desktop23，Ubuntu非DB302+2平台跳过、DB/browser312+6平台跳过。Owner待本人设置仍未改变，不把工程CI替代个人链验收。

## D1-00：耐久会话前置规则（2026-10-24，候选）

按[独立变更单](changes/2026-10-24-d1-durable-conversation.md)推进后续D1-01—09，不修改正式Requirement/Eval/Task/Gate。先实现有限消息origin、含全部既有请求字段的scope绑定哈希、闭合run状态与版本/generation/lease规则；默认迁移明确停在冻结0016，拒绝未来schema。无新表、API、权限、SDK工具或前端接线。域单元和实际隔离PG兼容测试属于工程前置，不证明聊天已持久化或DB CAS并发安全。下一单元必须把受控store、生命周期/退出/恢复与QG/BCG一起交付，不能先向用户启用一份无出口的聊天存储。

D1-00已由[PR #18](https://github.com/Gdnbit/classmatter/pull/18)及[最终两平台CI](https://github.com/Gdnbit/classmatter/actions/runs/40059582389)验收合并为main `eae4ca4`：Windows非DB339/Web55/desktop23，Ubuntu非DB337+2跳过、DB/browser313+6跳过。旧候选文字/先前提交号为阶段历史，不代替本收口证据。

## D1-10：显式存储profile基础（2026-10-24，候选）

用户已明确建立新Goal，持续到D1/恢复/文书工程验收和GitHub同步；外部Owner/真实Provider条件单列。当前独立分支新迁移0017仅由`conversation-d1` profile明确选择，增加thread/turn/message/run四张受控表、enrollment完整scope FK、发送键/ordinal/运行槽唯一约束、来源/正文/状态时间规则与精确列ACL。默认R1仍0016/22表；旧核心v1退出在源读取或下载前拒绝新schema，原backup拒绝未知表。不开放HTTP/UI/SDK或用户实例，不据表存在声称聊天已耐久可用。继承D1-01—09的工程追溯，正式107/147/94及Gate不变。

新存储首轮25通过，补充后与原inventory/非空旧版升级组合37通过94.04秒；非DB338通过+2宿主跳过。精确列清单最后加固后的最终重跑、安全检查/完整CI和独立PR待收口。已明确下一生命周期单元必须补原子清除、防恢复复活、版本化出口/备份/恢复；当前DDL不承担这些应用语义。回滚只能停止未启用的开发profile/兼容前滚或已验证快照；本轮没有迁移用户实例，不能删表假装无损降级。

D1-10最终收口见PR #19上述CI，局部最终新存储29通过77.79秒、原退出/数据库/恢复权限44通过117.87秒；精确652项公开清单和独立复审通过。没有HTTP/UI/SDK或用户实例激活。

## D1-11a：不可激活的D1 checkpoint（2026-10-24，候选）

复用`operator_backup.py`原有快照/DPAPI/原子发布/随机临时clone/finally清理，增加显式conversation-d1独立包格式及26表inventory，r1/v1默认结构/语义保持。`conversation_integrity.py`对固定聚合关系校验，无任意SQL/SDK对象/Agent调用。D1返回snapshot_integrity_verified且固定activation_allowed=false；metadata、源码关系、ACL或hash不符拒绝，不能借check导入业务、启动服务或激活run。

首轮新单元16通过，增加clone ACL故障后17通过68.86秒；旧R1备份/恢复组合35通过+1宿主跳过113.61秒，最终补旧快照与当前受限源库对比后的重跑/公开检查/完整CI待收口。独立审查无范围内阻断问题，明确不证明限制水位新鲜、完整DDL指纹或正式恢复。后续继续备份外限制水位、受控BCG清除、typed退出/新身份BCG恢复；不以本单元缩小Goal。回滚revert代码；用户实例未迁移，已存在checkpoint不删除。
