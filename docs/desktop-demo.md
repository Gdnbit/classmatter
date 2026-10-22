# 桌面 Demo 宿主：设计、实施与验收

状态：2026-10-22，Windows x64 / 0.1.0，本机合成 Demo；不改变正式 R1 准入。

## 目标与决定

用户需要类似 Codex 的独立窗口，当前只启动前端 Demo，不创建数据库/owner。采用 Electron 45.0.0 + 官方 Electron Packager 20.3.0 + Playwright Core 1.64.1；这些版本由上游 registry 查询后固定在独立锁文件。Electron 是桌面宿主，不是 Agent Harness，现有 Pydantic AI 选型与领域模型不变。这里复用的是当前公开仓库 `apps/web`，不复制其他产品代码。

独立窗口加载 ASAR 内的 Vite Demo 产物，通过标准安全本地 `classmatter://app` 协议提供资源。它不加载远程网页、不依赖已有 8443 服务，也不捆绑 Python/PostgreSQL。相比 Web 默认入口，唯一编译模式差别是构建脚本强制 `VITE_CLASS_OS_DEMO=true`；输出隔离在桌面 staging 内，避免覆盖 Web 普通 R1 产物。

## 进程、资源与生命周期

Electron 主进程管理窗口/菜单；沙箱 renderer 仅渲染原有前端。没有 preload 或业务 IPC。主进程资源处理器限定 app host、GET/HEAD、已知 SPA 路由及平面 assets 白名单；真实路径必须仍位于 UI 根目录，缺失资源返回 404，不将 API 请求回退到 HTML。SPA 的 path/query、刷新、返回不需要改造成平行路由。

同一用户重复启动仅聚焦原窗口，最后窗口关闭退出，无托盘常驻、Vite server 或应用自建监听端口。独立 appData 目录避免与 Codex/其他应用混用。页面 Session partition 不持久化；不承诺底层 Electron 零缓存或本机可取证擦除。Demo 页面内存变更在刷新或重启后重置。

## 安全与业务边界

- sandbox、contextIsolation、webSecurity 开启；Node integration/webview/任意新窗口关闭；打包版禁用页面 DevTools。
- CSP 禁止远程脚本、网络连接、frame、worker、表单提交与 eval。现有 React 内联样式需要 style unsafe-inline；这不是任意脚本许可。
- session 拒绝权限请求、外网/localhost/文件 URL 访问及下载；不启动录音、文件解析、真实模型或真实数据路径。现有模拟按钮不应被宣传为生产能力。
- 没有从 renderer 直连数据库或宿主文件系统的新入口；Query Gateway、Business Command Gateway、Identity Security Boundary 不变。
- ASAR 是打包格式，不是加密、完整性签名或沙箱。此本机交付未实施代码签名、更新签名/回滚、安装器、完整 fuse 收紧与分发供应链验证，不适合当正式安装发行版。

官方依据：[Electron 安全清单](https://www.electronjs.org/docs/latest/tutorial/security)、[自定义协议](https://www.electronjs.org/docs/latest/api/protocol)、[Electron Packager](https://github.com/electron/packager)。后续需持续更新受支持 Electron，不能把本次固定版本当作永久安全背书。

## 追溯与范围

此变更属于新增表现层宿主交付（DESKTOP-DEMO），不是新的业务需求或正式任务完成声明。107 个 Requirement、147 个 Eval、94 个原子任务及 Gate 源行哈希不变；不将 synthetic 验证提升成真实用户或正式 R1 验收。映射现有 Conversation-first、Attention-first、One Data World/Multiple Views 的 UI 合同；不修改这些语义、mock store、原型样式或正式接口。

新增工程验收与测试映射：

| 验收 | 可执行证据 |
| --- | --- |
| 无浏览器/8443 服务依赖；打包版自己包含 UI | `tests/smoke.cjs --packaged` 校验本地 origin、打包标识、学生/工作页面 |
| 导航、详情刷新、返回正常 | 同一集成测试的 path/query 与历史导航 |
| renderer 无 Node/IPC 和宿主能力扩大 | 单测 + 集成测试检查沙箱、隔离、无 require/process/preload |
| API、任意文件、远程访问和弹窗不放行 | `tests/policy.test.cjs` + 集成测试 |
| 第二实例退出，最后窗口关闭后主进程退出 | 集成测试真实进程与窗口检查 |
| 现有 Web 契约和类型不漂移 | `apps/web` 的 typecheck（含 32 项测试）及普通 build |

`apps/desktop` 是可选交付层，代码和启动命令见[桌面 README](../apps/desktop/README.md)。独立 desktop 验证不取代后端、数据库或正式 Gate；统一检查入口新增可选 `desktop` suite（仅 Windows x64）。

本轮本机验收：6 项资源边界单测、开发/打包版 Electron 集成均通过；打包版额外验证 10 个现有页面入口和底部对话框发送，无 pageerror。原 Web 32 项 Node 测试、TypeScript 与普通生产构建通过；SDD self/eval-meta/gate-graph/task-graph/development/fixtures、文档 UTF-8/链接/空白检查通过。新增桌面工具链完整 `pnpm audit` 当次无已知漏洞报告（不是未来安全保证）。增加 Windows CI 步骤但本轮没有推送或运行远端 CI；没有执行完整后端/数据库回归，未改其代码与契约。集成测试截图与 JSON 只保留在本机忽略目录。

## 许可证、产物和已知限制

源码 Apache-2.0 / Gdnbit；Electron 保留自身 LICENSE 与 LICENSES.chromium.html；应用 ASAR 中包含自有 LICENSE/NOTICE、THIRD_PARTY_NOTICES 和实际 Web 生产闭包的通知/版本清单。开发打包工具不复制进应用。它补充原有 source-only 依赖清单，不将旧清单冒充完整桌面二进制 SBOM。正式公开二进制发布前仍需对 Electron/Chromium/FFmpeg、原生组件、打包链、签名及升级单独复核。

本机产物和证据在忽略目录，不上传截图/可执行文件，也不自动推送分支。回退只需退出新 Demo 并继续原 Web 入口；本变更未迁移或修改任何业务库，无需数据库回滚。

Future：生产桌面接入应复用原 API/Agent 服务，通过受控进程托管、认证握手、健康检查和退出清理连接；不能仅解禁网络/CSP 就宣布实现。文件选择/解析、可信上传、麦克风/ASR、本地工具/命令执行均需各自的能力接口、范围授权、取消/超时/审计和验收，不能暴露万能 IPC/shell，更不能绕过 BCG。
