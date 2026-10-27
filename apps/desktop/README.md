# 班事有谱 · 独立 Windows 桌面 Demo

此交付是现有前端 Demo 的独立 PC 宿主，不是浏览器快捷方式，也不是完整本地 Agent。Windows x64，版本 0.1.0，Pre-alpha / synthetic only。

## 使用

本机构建后双击 `out/ClassMatter-Demo-win32-x64/ClassMatter-Demo.exe`。请保留整个目录，不要只复制 exe；无需浏览器、Node、Python、8443 服务、数据库或模型配置。窗口右上角关闭即退出；重复启动聚焦已有窗口；“文件 → 关于班事有谱”说明功能边界。编辑菜单支持复制粘贴，视图菜单支持缩放和全屏。

顶部采用 44px 浅色一体化栏，左侧提供返回/前进、侧栏开关、文件/编辑/视图/帮助菜单；空白区域可拖动窗口，原生最小化/最大化/关闭控件保留。侧栏与顶栏同色，白色内容区圆角衔接。普通浏览器构建不显示这条桌面栏。

独立窗口复用已有侧栏、底部对话框、学生/工作/数据等演示页面和预览交互。数据与回答是合成或模拟的；修改仅当前演示会话有效，重新加载页面或退出后重置。不要输入真实个人信息、账号或密钥。文件/语音按钮并不表示已经实现文件解析、录音转写或模型工具执行；Demo 禁止网络、录音权限和下载导出，不自动启动后端。

这是未签名的本机解压运行版，不是已签名安装包或正式 Release。不要建议用户关闭 SmartScreen/杀毒或绕过组织策略。安装器、自动更新、签名、公网分发、完整二进制审查另行验收。

## 从源码运行与打包

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

`check:runtime`只读检查，JSON仅输出固定步骤码及布尔结果，不读取/输出密码或恢复码，不启动服务、不写文件。退出0只表示文件前置条件齐备，**不表示PG已启动、Owner已建立或服务ready**；退出2表示需处理`next_steps`。`open:runtime`先构建当前源码再执行同一检查，随后复用原自有API进程握手/readiness；无失败回退Demo、自动安装、建库、迁移、设置Owner或旧请求重放。

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
