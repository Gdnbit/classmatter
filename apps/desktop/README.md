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
