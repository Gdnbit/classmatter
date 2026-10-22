# 实现与验收台账

更新时间：2026-10-22。基线：`e6a5bdd`，本轮继续在 `codex/desktop-demo` 实施。此表是工程状态索引，不替代 canonical SDD、正式任务状态、签名或发布准入。

## 状态与顺序

状态分开记录：`implemented-synthetic`（已有合成工程实现）、`demo-only`（样例/内存交互）、`partial`、`pending-validation`、`deferred`。代码存在不等于正式 `implemented-green`。107项需求、147项Eval、94项原子任务不因本表变化。

1. W0：建立当前实现/证据/剩余项台账。
2. W1：冻结现有前端交互，逐页验收；先修布局、不可达入口、误导反馈与空态，再接业务。未来页面验收只验证导航/样例/明确未接入，不提升功能范围。
3. W2：最小真实桌面纵向切片，但数据仍为synthetic：进程托管→登录→班级/学生→事实记录→服务端预览/确认→BCG保存→Today/Timeline→退出重启读取。
4. W3：同一界面接入原有Agent查询/草稿和模型配置；真实供应商质量单独验证，密钥由用户在受信界面输入。
5. W4：补齐退出/恢复/运维，形成候选证据；先合成shadow，再作教师净负担研究和正式准入决定。
6. W5：依据真实任务证据选择通知责任闭环或其他下一切片；新release change，不偷渡进冻结R1。

W0已建立；W1当前已覆盖交互基线为`ready-for-binding`，允许准备W2绑定已有R1能力；未来模块仍只是样例，完整逐按钮/全支持矩阵验收待完成；W2—W5未完成。此结论不是“整个前端功能已完成”或正式R1 Gate晋级。

## 能力、代码与追溯

| 能力 | 状态 | 实现落点 | 追溯与剩余验收 |
| --- | --- | --- | --- |
| 桌面窗口/原生顶栏/菜单/沙箱 | implemented-synthetic | `apps/desktop/` | DESKTOP-DEMO工程验收；非新增R1任务；安装器/签名/更新未完成 |
| 对话、历史、标题、搜索、输入草稿 | demo-only | `store/ConversationStore.tsx`、`shell/AppShell.tsx` | A05/A06/A11；当前内存会话，非持久工作历史 |
| 首页三类注意力/个人任务 | partial | `store/DemoWorkStore.tsx`；`runtime/R1App.tsx`、backend activity | T-RDOM-009/010/013、T-RWEB-004；E-TSK-001/E-EVT-004；Demo与真实视图仍分离 |
| 学生列表、详情、搜索、空态 | partial | `shell/AppShell.tsx`；`runtime/R1App.tsx`、backend roster | T-RDOM-002—005/011、T-RWEB-002；E-ROS-001—004/E-ID-001—004；待统一冻结UX与API |
| 登录/会话/恢复码 | implemented-synthetic | backend identity、runtime identity | T-RPLT-013/014/018/019、T-RWEB-001；E-AUTH-009—018；桌面尚未接入，owner凭据不由Agent设置 |
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

各波次小提交；公开清单复核后提交本地开发分支，未经新的明确决定不推送公开仓库。运行库、截图、密钥和证据原件留在忽略目录。正式任务仍planned/Eval仍not-run时保留原状态，另用本台账记录工程事实；完成正式晋级需目标版本绑定和批准证据。

基线复核：后端非DB278通过/314未选入；task graph有效但正式implemented-green=0；147项Eval中82项executable-spec、65项catalogued。这些是本轮前置检查，不是W2/真实模型/生产验收。

W1第二轮：Web39项、类型、普通/Demo构建通过；桌面7项边界测试、原打包smoke及真实打包应用A01—A17通过，`pageErrors=[]`、`externalRequests=[]`。修复被回归捕获的表格view URL回落；测试使用已有`/students?view=table`，没有添加平行`/views`路由。Product Design截图流程帮助发现窄窗口两个问题，未改变冻结整体风格。

W1-B已完成定向工程验收：数据/表格/文档/报告的详情、返回/取消、工作表菜单及说明反馈；A15/A16通过。表格空白保持未录入，工作表内容和选中公式栏一致；没有实现真实解析/导入/导出。

W1-C已完成定向工程验收：A17覆盖移动更多7入口/外点、学生任务空态/返回、知识搜索无结果/恢复/关闭、自动化示例标记；无真实后台计划或模型引用。桌面最小窗、窄Web布局和关键交互已验证，全平台读屏器/多DPI验收单列，不把暂未覆盖项默认为通过。

### W2首个变更单元（未实施）

1. 定义受控desktop runtime mode/进程契约，保留原离线Demo不放权；落点desktop main/policy/preload及隔离测试。启动/握手/退出/端口占用/服务崩溃各有确定结果，不接受renderer任意命令或URL。
2. 在Web表现层建立只绑定R1的状态/动作接口，复用runtime现有typed API、身份、receipt校验；不把MockDomainStore字段强行映射为真实座位/宿舍。落点App、shell及runtime表现层；StudentId使用后端UUID而非演示学号。
3. 首先接班级上下文、学生、事实记录和任务/Today/Timeline；未实现模块保留Future，不取回fixture填充真实视图。命令沿原服务端preview/approve/commit，不开放Agent写工具。
4. 验证依赖：后端合约/nonDB→隔离PG→浏览器真实接口→桌面进程生命周期→重启持久性/未知结果/故障回归。验证用合成临时实例；不初始化/迁移用户原实例。

这是一份下一变更的执行设计，不把未实施的连接/启动/持久化标绿；没有冻结计划要求为“前端完成”提前实现真实模型或新业务模块。
