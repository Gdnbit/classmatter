# 班事有谱 · 独立 Windows 桌面工作台

Windows x64，版本 0.1.0，Pre-alpha / synthetic only。不是浏览器快捷方式，也不是完整本地 Agent。

## 当前成绩与座位开发入口（D4）

默认`pnpm build`/`pnpm start`使用同一个原界面的D4开发增量，增加成绩表格、座位图及对话候选。只有存储协议升级，不是另一套工作台。完整工程证据与限制见[领域设计](../../docs/design/workbench-domain-packs.md)和[实施台账](../../docs/implementation-ledger.md)。

已有D3实例先关闭本次应用与API服务，保持数据库运行，在backend执行`uv run --frozen python local.py upgrade-classroom --profile workspace-chat-d3`。它先完整备份并隔离恢复核验，保留Owner、学生、聊天、文档与模型配置，再发布新描述；启动不隐式迁移。原D1/D2按下文先升级D3；全新目录仍用原`prepare-chat`，之后执行D4升级。不要对已有目录重新prepare、init或bootstrap。开发入口不设置密码。

完整D4本机checkpoint使用`backup`/`backup-check`及`--profile classroom-work-d4`，不能用D3备份漏掉成绩/座位后声称完整。启用后旧客户端不能连接新库；回滚需保留新旧checkpoint、核验整库恢复并说明升级后写入损失，或前进修复，不能仅revert后DROP表。兼容D3源码仍可显式`node scripts/runtime-build.cjs --profile workspace-chat-d3`构建，但只连接未升级的D3库。以下早期D3说明保留为演进记录，当前默认以本节为准。

## 本机开发直接使用（取代下文早期免密码登录流程）

默认 D3 桌面开发入口不设置用户密码，不生成隐藏密码，不显示登录、退出登录或重新验证身份。原工作区和聊天数据保留；刷新和完整重启直接恢复使用，空闲不触发登录过期。前端仅在本机连接实际失败时提供“重试连接”，不自动重放发送、创建、编辑或批准操作。

原有开发实例首次启动时，用旧开发标记核对同一工作区，停用旧密码和旧恢复码，删除旧隐藏密码文件，保留 Owner/workspace 标识和全部业务数据。新实例通过 `prepare-chat` 直接建立无密码本机工作区。内部连接标识继续服务 QG/BCG 的范围、预览和命令绑定，不是用户账号；数据库服务自身的内部连接凭据不属于用户密码。转换没有数据库结构迁移，不可用旧登录流程回滚已转换的身份。个人身份和旧 R1/D1 入口仅保留兼容测试，不是当前默认产品入口。

## 2026-11-08 聊天持久化与对话操作

原界面改造后，主导航为对话/总览/学生/工作，“…”展开数据与内容/视图；新对话在聊天组，当前未完成任务在事件区。设置从底部工作区右侧齿轮打开浮层；班级切换、兼容人工维护和模型管理均在此，不要求先建班才能聊天。已有会话隐藏欢迎区，输入框固定底部，无左右聊天头像。右下角可查看实际模型、选择最近启用模型或输入同服务商模型ID，经原预览确认后显式测试启用；更换服务商使用管理模型入口。没有预置假在线模型，不自动调用收费服务。

默认`pnpm build` / `pnpm start`现在使用显式`workspace-chat-d3`，仍是同一个原型界面和同一个自有本机数据库，开发免密码不变。普通聊天无需先建班，聊天列表/正文可跨刷新和应用重启恢复。需要班级数据时才查询或追问；AI准备班级/学期、学生、任务、文档的受控候选，用户在原预览确认后由原BCG保存。不是模型任意操作数据库。

全新克隆的开发实例，在`backend`执行`.venv/Scripts/python.exe local.py prepare-chat --profile conversation-d1 --pg-root '<PostgreSQL18安装目录>'`。它只在目录完全不存在时，复用原D1初始化与免密码开发身份，再执行同一套备份升级；不需要先临时打开D1应用或填写Owner表单。已有目录一律拒绝覆盖，部分准备失败时保留实例，按实际profile显式恢复升级，不重复初始化。

旧D1/D2实例须先停止本项目API和桌面，再在`backend`中显式执行`.venv/Scripts/python.exe local.py upgrade-chat --profile conversation-d1`（D2使用`workbench-d2`）。升级保留同根Owner、既有数据与开发身份，每步先完整checkpoint并隔离恢复校验，SQL提交后才发布新profile描述符；失败保留证据、支持向前恢复，不自动DROP/重建。**启动命令不做迁移**，不能把旧库直接声明为D3。`pnpm check:runtime:d3`只检查前置文件，不能代替API readiness或恢复验收。D1构建命令继续保留作兼容回归，不可用旧代码直接打开已升级新库。

原设置中的模型接入、连通性测试和启用流程继续使用。新实例默认不调用外部模型；本机明确测试启用后，D3会跨重启恢复同一配置和已确认传输，停用也会保留。Key本身不会触发启用。模型变化会提示重新确认，不能用合成回答冒充真实AI。原桌面已完成Gemini3.1 Flash-Lite多轮聊天、刷新/重启恢复及九类创建编辑候选的12轮真实合成调用样本；免费服务仍可能限流或超时。D3支持完整本机checkpoint及隔离恢复，包含文档与新聊天表；恢复实例不会继承模型启用记录，完整跨机退出/迁移仍不开放。详见[聊天设计和使用检查](../../docs/design/workspace-chat-and-actions.md)。下方2026-11-03等段落为历史实现记录，D1默认入口已被本节取代。

## 2026-11-03 单一工作台入口修正

用户界面不再要求选择“Demo / 真实工作台”。`pnpm build` / `pnpm start` 默认构建、启动连接本机 D1 的桌面入口。原冻结原型的 `WorkbenchFrame`、`SidebarFrame` 和桌面 chrome 与连接后端的控制器共享；数据由现有 QG 读取，业务变更仍经原 BCG 预览/批准/提交，身份变更仍经 ISB。当前绑定对话、总览、学生、事实、任务、设置；尚未绑定的原型功能不提供伪造数据或成功提示。此轮没有完成所有原型深层页面迁移，不能据此宣称整个原型已经接通。

用户随后明确要求本机开发暂不输入密码。因此默认 `pnpm start` 带可信 `--development-no-password` 开关，直接进入合成开发工作台。私有父进程为尚无Owner的实例创建随机开发身份，凭据仅以当前用户DPAPI保存为忽略的 `developer-identity.dpapi`，通过原ISB登录并在加载页面前安装原HttpOnly/SameSite Cookie；初始化仍经原BCG。不开公共免登录HTTP路由，不返回密码/token给renderer，不改变普通API认证、Agent工具或正式Gate。既有个人Owner且无开发凭据标记时拒绝接管，不重置密码或清空原库。重复启动使用同一开发身份与数据库，不重复初始化。此开发实例不作为真实数据或正式账号迁移准入。

开发会话退出/过期或Cookie丢失后，页面提供“进入本机开发”；设置中的“重新验证身份”也无需输入密码。只有明确开发启动的preload暴露这两个无调用方参数的固定动作；父进程复核发送窗口、主frame、同源和单请求状态，读取当前隔离session的Cookie，通过私有管道调用原ISB登录或reauthenticate。重新验证撤销旧会话、旋转当前Cookie；renderer仍用原session契约核对身份，失败/未知结果清理旧授权状态，不重放业务操作。没有后台自动续期、公共免认证路由、任意IPC/文件路径或业务命令。个人入口仍保持原密码/恢复流程；开发入口不展示无法使用的个人密码恢复操作。

不带该开发开关的兼容入口仍使用本人设置流程：应用内设置密码、保存一次性恢复码、重新验证身份、核对并批准原 Risk X 会话控制初始化，无需打开终端。它不是当前默认开发体验。`backend/desktop_setup.py` 是由桌面进程私有管道拥有的适配器；不监听 HTTP，不向业务页面或 Agent 暴露 bootstrap arming、密码、恢复码、身份 token 或通用 IPC。setup preload 只在独立本地设置窗口加载，严格限制资源/导航/发送者。错误、超时和丢失响应不自动重试写操作；恢复码未收到时使用原 ISB 恢复码重发流程，不能重建 Owner。

前置条件仍是已准备的自有合成数据库、运行中的 PostgreSQL、锁定依赖及正确构建。不会自动初始化/迁移/清空现有数据库，不会解除退出/转移限制或覆盖并发工作。旧 CLI 保留为操作兼容入口。独立离线样例仅供开发者回归，显式使用 `pnpm build:fixture` / `pnpm start:fixture`；下方旧记录中的 `pnpm start` 仅描述当时历史状态，当前命令以本段为准。

验收使用全新临时数据库，包含应用内初始化后进入共享原型布局，以及原有学生→事实→任务→聊天→刷新→重启读取→清除的实际 Electron/HTTP/PG 链路。测试密码与恢复码仅限临时合成实例；不读取、设置或截图用户的密码/恢复码。对正式 R1、Gate、真实数据、Agent 写权限和发行准入均无升级。

## 2026-11-02 真实运行入口退出包标识复验

实际Windows R1桌面测试发现原生保存对话框统一使用D1“合成证据退出包”标题，而该R1下载实际是`class-os.synthetic-core-exit.v1`。现由已验证的可信runtime profile选择标题：R1“合成核心退出包”、D1“合成证据退出包”，与各自已有默认文件名对应。没有从renderer、文件内容或任意URL猜测类型，也没有扩大下载路径/MIME/大小、保存位置、IPC、模型或业务权限；不增加用户操作。

原断言保持：真实Electron/HTTP/临时SCRAM PostgreSQL测试必须核对保存标题、下载完成、实际JSON协议及记录/任务数，并证明数据跨应用重启仍可读取。首轮1失败/7通过126.42秒是本缺陷的复现，不记通过；仅修标题分支后，R1/D1桌面及本机runtime组合8通过107.03秒，包含D1重启/来源恢复/clear后拒绝旧备份。自动测试选择临时保存路径，不代表人工原生对话框体验或正式发行已验收。测试使用全新一次性合成库，未操作用户实例或代设个人Owner。

在已合并Google原生适配的main4a6a92f上再次运行，同组合8通过109.48秒；桌面来源/下载/IPC/进程故障边界23项通过。前端生产样式、业务模型和数据库没有因此重构。

代码改动仅`runtime-main.cjs`一处条件标题；文档与准确公开哈希同单元更新。无新依赖、数据库迁移或Gate变更。回滚revert本修复，保留原失败与通过日志；不删除数据或放宽测试。完整Windows/Ubuntu CI仍按本独立PR最终head验证，不借用Provider PR的成绩。

## 使用

本机构建后双击 `out/ClassMatter-Demo-win32-x64/ClassMatter-Demo.exe`。请保留整个目录，不要只复制 exe；无需浏览器、Node、Python、8443 服务、数据库或模型配置。窗口右上角关闭即退出；重复启动聚焦已有窗口；“文件 → 关于班事有谱”说明功能边界。编辑菜单支持复制粘贴，视图菜单支持缩放和全屏。

顶部采用 44px 浅色一体化栏，左侧提供返回/前进、侧栏开关、文件/编辑/视图/帮助菜单；空白区域可拖动窗口，原生最小化/最大化/关闭控件保留。侧栏与顶栏同色，白色内容区圆角衔接。普通浏览器构建不显示这条桌面栏。

独立窗口复用已有侧栏、底部对话框、学生/工作/数据等演示页面和预览交互。数据与回答是合成或模拟的；修改仅当前演示会话有效，重新加载页面或退出后重置。不要输入真实个人信息、账号或密钥。文件/语音按钮并不表示已经实现文件解析、录音转写或模型工具执行；Demo 禁止网络、录音权限和下载导出，不自动启动后端。

这是未签名的本机解压运行版，不是已签名安装包或正式 Release。不要建议用户关闭 SmartScreen/杀毒或绕过组织策略。安装器、自动更新、签名、公网分发、完整二进制审查另行验收。

## 从源码运行与打包

真实模型专项可以在关闭当前桌面后手动复现。只适用于**尚无班级的独立合成D3实例**，先在原设置完成模型保存、检测及明确启用Gemini3.1 Flash-Lite，再构建D3。该脚本会真实调用已启用模型并创建合成班级、学生、任务和文档；不会替你登记Key、开通计费、重置或覆盖已有班级。不得用它对实际工作数据库做回归。已有班级会在发送前拒绝，默认`pnpm test`/CI不会运行真实模型。

```powershell
$env:CLASSMATTER_RUN_LIVE_CHAT_ACCEPTANCE = '1'
node tests/live-chat-acceptance.cjs
Remove-Item Env:CLASSMATTER_RUN_LIVE_CHAT_ACCEPTANCE
```

真实调用结果写入被Git忽略的`test-results/live-chat-acceptance.json`；原UI确认、数据库回读、上下文和完整重启都有断言，失败不自动重复模型轮次。该脚本不替代无费用的固定fixture/故障矩阵和正式发布验收。

要求 Windows x64、Node 22.20 或受支持的 24.x、pnpm 11.19.0。先在 `apps/web` 执行 `pnpm install --frozen-lockfile`，再在本目录执行：

```powershell
pnpm install --frozen-lockfile
pnpm test
pnpm build
pnpm start
```

生成独立可执行目录并验证：

```powershell
pnpm package
pnpm test:desktop -- --packaged
```

也可直接用 `node tests/smoke.cjs --packaged` 运行打包版测试。测试前关闭已打开的 ClassMatter Demo（单实例锁是正常行为），不要并发跑开发版/打包版测试。集成测试覆盖真实 Electron，不下载 Playwright 浏览器。`pnpm start` 是开发启动，仍需本机 Node；打包 exe 不需要。

定向前端验收运行 `node tests/acceptance.cjs`，也已加入仓库 `scripts/verify.ps1 -Suite desktop`。包括准确预览、确认后仅应用演示内存、会话隔离、同源任务状态、弹层/焦点、输入法、附件与模拟反馈；详见[修复和验收记录](../../docs/frontend-demo-acceptance.md)。本演示只接受明确两名合成学生的交换请求，例如“交换合成学生01和合成学生02的座位，先给我预览”，其他请求不会套用固定座位样例。

Electron 的安装脚本由 `pnpm-workspace.yaml` 精确允许；若机器全局禁止安装脚本，检查本机策略，明确允许后运行上游 `node node_modules/electron/install.js`，不要为所有依赖打开脚本执行。首次安装/打包需访问 Electron 官方发行资源，运行不需要网络；不要把机器代理地址写进源码。

## 代码地图与边界

| 文件 | 职责 |
| --- | --- |
| `main.cjs` | Electron 窗口、菜单、单实例、关闭生命周期、权限/网络隔离 |
| `policy.cjs` | `classmatter://app` 协议、本地资源白名单、SPA 路由回退、CSP |
| `scripts/build.cjs` | 显式 Demo 构建、契约漂移检查、隔离 staging，不修改 Web 默认构建 |
| `scripts/package.cjs` | 上游 Electron Packager，Windows x64 ASAR 目录包与 exe 摘要 |
| `scripts/notices.cjs` | 收集实际安装的 Web 生产依赖及其通知，缺失时阻断构建 |
| `tests/` | 资源边界单测与真实桌面进程集成测试 |

`.build/`、`out/` 和测试截图不进入 Git；源码、测试、锁文件和设计说明可同步。Electron 使用独立 `ClassMatter-Demo` 用户配置目录，业务页面使用内存 session partition；Chromium 自身仍可能留下日志/缓存等基础文件，不承诺零磁盘痕迹。preload 仅暴露四类固定原生菜单请求，主进程复核发送窗口/主 frame/本地 URL；没有通用 IPC、任意文件访问、shell、DDL、Agent 执行、数据库连接或凭据存储入口。

详情与未来生产接入边界见[桌面宿主演进说明](../../docs/desktop-demo.md)。

## 合成持久化开发入口（W2-01，非发行版）

2026-11-03启动故障边界：自有API的进程证明与readiness请求各有最长500毫秒的完整交换期限，且共享原30秒总启动预算。持续缓慢返回字节不能延长期限；总期限使用单调时钟，不随系统时间调整。超过期限不打开业务窗口，只清理本次子进程；既有端口监听者、PG和数据不被停止或修复。进程停止仍有独立最长5秒等待，这不是“30秒内完成所有清理”的承诺。默认不重试业务命令、不重放模型请求。`runtime-service.test.cjs`使用真实本机TCP/HTTP子进程验证慢证明、慢readiness及被占用端口；正常R1/D1原生回归另行验证。

### Explicit model transport for the owned desktop service

2026-11-03：桌面开发入口可将操作者显式许可的模型端点及可选本机代理传入自有后端。先准备已有合成实例、启动PG并由本人设置Owner，再在本目录构建和启动：

```powershell
pnpm build:runtime
node scripts/runtime-launch.cjs --model-api-base-url https://generativelanguage.googleapis.com/v1beta/openai/ --model-api-proxy http://127.0.0.1:7890
```

独立D1实例使用：

```powershell
pnpm build:runtime:d1
node scripts/runtime-launch.cjs --profile conversation-d1 --model-api-base-url https://generativelanguage.googleapis.com/v1beta/openai/ --model-api-proxy http://127.0.0.1:7890
```

代理可省略；示例不启动代理、不改变系统设置。端点最多4个、参数逐个重复，只允许无凭据/查询/片段的HTTPS或127.0.0.1开发HTTP；代理只接受规范`http://127.0.0.1:PORT`。UI中保存的base URL必须与许可值精确一致，包括末尾斜杠。启动参数不接受Key、模型自动选择或自动启用；诊断Key不会导入。此处仅提供通道许可，仍需本人登录，经原BCG预览/批准/提交保存配置、显式合成连接测试并启用。没有通过连接测试不能直接启用，默认仍离线。

可信本机快捷方式可以保留这些非秘密参数，修改后须正常退出并重新启动；第二实例仅聚焦原窗口，不更新运行中权限。不带参数重开，已保存配置仍在，通道许可恢复关闭。不新增renderer接口、IPC、runtime-source字段或存储Schema，不自动初始化/迁移数据库。只支持现有合成开发入口，不等于免安装发行或真实Provider质量验收。

`test_desktop_model_network.py`及`runtime-model-network.cjs`使用一次性自有PG/Owner与假Key，验证实际Electron→自有Python→原BCG/QG、未测试启用被拒绝、重启后网络默认关闭，以及零模型测试/启用/调用审计；不调用外部API。保留原桌面关闭、下载、进程证明及D1回归断言。

### D1 独立入口候选（2026-10-27，整单元验收仍在进行）

只有显式 `pnpm build:runtime:d1`、`pnpm check:runtime:d1`、`pnpm open:runtime:d1` 选择新D1根和数据库；旧命令仍R1，`pnpm start`仍离线Demo。D1默认端口8001、独立用户配置目录与session partition，不停止或接管占用8000的服务。先由操作者按后端README在全新授权根完成D1初始化、本人Owner设置、原Risk.X control初始化并启动PG。不得迁移已有R1、复制DPAPI或手改运行描述以绕过检查。

`runtime-source.json` v2闭合绑定源码根、D1根、固定profile及服务端口；无效描述在单实例握手前拒绝，不能激活旧窗口。仍使用原进程HMAC/同源限制、sandbox、4种菜单IPC，关闭只停止本次API，不停止PG或自动重放运行。开发测试可在自有临时root/隔离端口验证真实Electron/API/PG进程重启，不因此授权真实数据或用户凭据。

原UI现在候选接入列表/深链/来源/草稿/状态/取消/归档/清除；答案只从已保存QG历史读取，流仅展示进度，刷新不调用模型。设置中D1导出使用受控v6证据包，全工作区范围、本人批准、同键收据、当前限制重验；原生保存位置由用户选择，固定JSON路径/MIME/大小限制不变，不支持任意下载。原生保存对话框人工操作仍待验证。附件、语音、长期记忆与工作小结未因这次接线变成已完成。

`backend/tests/test_durable_desktop.py`已在一次性Windows自有fixture验证原UI建班/学生/事实/任务、模型查询来源、刷新、正常退出、PG进程重启、新Electron恢复同回执、草稿未执行、清除和强退API清理，以及旧checkpoint拒绝/新checkpoint验证。最终源码仍需重跑和完整CI；不冒充整个Goal或正式Gate。

2026-10-24：D0真实页面/恢复已在[PR #16](https://github.com/Gdnbit/classmatter/pull/16)验收；这不等于本README上方离线Demo自动变成真实实例。`pnpm start`仍打开离线Demo；真实持久化入口为以下命令，依赖本机Windows/Python/PG，不是免安装发行包：

```powershell
pnpm check:runtime
pnpm open:runtime
```

`check:runtime`只读检查，JSON仅输出固定步骤码及布尔结果，不读取/输出密码或恢复码，不启动服务、不写文件。退出0只表示文件前置条件齐备，**不表示PG已启动、Owner已建立或服务ready**；退出2表示需处理`next_steps`。两种profile都要求实际运行入口及其四个模块（runtime-service、runtime-policy、model-network、preload）齐备，缺失时返回`build`待办，并在加载Electron前拒绝；存在文件不等于已验证全部依赖或内容完整性。`open:runtime`先构建当前源码再执行同一检查，随后复用原自有API进程握手/readiness；无失败回退Demo、自动安装、建库、迁移、设置Owner或旧请求重放。

| next_steps | 本机操作者动作 |
| --- | --- |
| windows | 当前持久化开发profile仅支持Windows；不要绕过DPAPI |
| backend | 在backend执行`uv sync --frozen`，确认固定desktop.py入口存在 |
| electron | 在apps/desktop执行`pnpm install --frozen-lockfile` |
| build / source | `pnpm build:runtime`；移动checkout或测试fixture描述必须重建，不能手改路径冒充用户实例 |
| database_configuration / protected_credentials | 尚无完整自有实例或配置不符；先确认是否全新目录，按backend README显式初始化。已有实例不得重建或复制DPAPI；缺文件先诊断，不用init修复 |

准备好数据库后，在backend显式执行`uv run --frozen python local.py start`。首次Owner由本人在受信终端执行`uv run --frozen python local.py bootstrap`，设置密码并离线保存一次性恢复码；不要把密码/恢复码发给Agent或写入命令行、日志、Git。此后返回桌面登录，完成“班级→学生→事实→预览确认→任务→关闭重开核对”。只使用合成内容。应用关闭仅停止自有API，不停止PG。

原离线Demo命令和快捷方式不变。另有独立的开发入口，复用已有R1业务页面、API和PostgreSQL，不是把Demo内存当数据库，也不表示全部冻结页面已迁移。

先按[后端运行说明](../../backend/README.md)准备本机自有合成runtime、启动PostgreSQL并由本人交互bootstrap owner；不要重建已有实例。同步冻结依赖后，在本目录执行：

```powershell
pnpm build:runtime
pnpm start:runtime
```

桌面以固定自有Python入口启动API，使用每次启动的新密钥和随机challenge验证服务进程，再检查数据库/身份/业务Gateway readiness；不连接占用8000端口的旧服务。不启动/初始化/迁移/停止PostgreSQL，不创建owner、不重放失败写入。关闭桌面会停止自有API；父进程强退时空stdin管道EOF触发API退出。服务崩溃关闭窗口，不自动重连或重启。

runtime构建在`.build/runtime/`，与`.build/app/`离线Demo及普通Web dist分开。生成的`runtime-source.json`只包含本机源码与合成runtime路径，不入Git，不能跨机复制。此入口依赖源码、Python虚拟环境、当前用户DPAPI和已启动的PG；不支持packaged分发，不是安装包/完整离线后端捆绑。

renderer只访问已验证的固定loopback同源，preload仍只有4类菜单请求；没有通用IPC、shell、DB或DDL。仅已批准JSON核心退出包的既有API路径、正确MIME和1—16MiB大小允许打开原生保存对话框；保存位置由用户选择，其他下载拒绝。保存对话框完整手工体验尚待验证。模型默认仍是确定性fake，真实供应商质量没有验收。

工程验证：`pnpm test`当前包含原7项Demo边界及11项runtime监督/策略测试；`backend/tests/test_desktop_runtime.py`在临时SCRAM库和真实Electron中验证建班/学生/事实/关联任务、重启持久化、只读Agent来源/未提交草稿及父进程强退清理，既有用户runtime不变。Windows执行：

```powershell
# backend
uv run --frozen pytest -q tests/test_desktop_runtime.py --pg-root '<PG18目录>'
```

测试若8000已被占用会明确skip，不杀已有服务；缺桌面依赖会失败，不假报通过。此测试自动创建的owner仅属于一次性合成库，不代替本人设置真实使用凭据。完整状态见[实现台账](../../docs/implementation-ledger.md)。
