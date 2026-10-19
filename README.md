# 班事有谱 · ClassMatter

班里的事，记得住、跟得上、查得到。

帮助班主任整理学生事实、跟进班务、追踪未闭环事项，保留可核查的处理记录。当前是 **Pre-alpha · Synthetic development only**，不是生产产品，不允许处理真实学生资料。

## 可运行的范围

本机 owner 初始化和登录 → 班级/名单 → 类型化事实与跟进任务 → Today / Student Timeline → 更正预览与明确批准 → 版本与审计。Agent 使用可替换的 Pydantic AI 运行组件，只能查询和提出草稿，不能批准或直接提交业务写入。模型可选，离线合成测试不依赖真实供应商。

这里的个人事项分流不是组织派责或免责证明。观察、AI 推断、候选和正式事实不混用。Capture、主动提醒、复杂排班、多角色协作与完整生命周期不因公开整理而自动实现；真实模型效果和教师净减负仍待验证。

## 安装与运行

Windows、PowerShell 7、Node 22—24、pnpm **11.19.0**、Python **3.13**、uv **0.11.7**、PostgreSQL **18.6** binaries。本机持久入口依赖 Windows DPAPI；Linux CI 仅验证隔离合成测试，不代表跨平台生产部署。

```powershell
cd apps/web
pnpm install --frozen-lockfile
pnpm typecheck
pnpm build
cd ../../backend
uv sync --frozen
uv run --frozen python local.py init --pg-root '<PostgreSQL18安装目录>'
uv run --frozen python local.py start
uv run --frozen python local.py bootstrap
uv run --frozen python local.py serve
```

打开 <http://127.0.0.1:8000>。密码、恢复码本人在交互终端保管，不写入 Git。停止服务后运行 `uv run --frozen python local.py stop`。初始化不覆盖现有目录；升级须显式 migrate，禁止直接修改旧迁移。不要复制 `.local-runtime/` 到另一台电脑作为凭据迁移方式。

单独 Vite 不是完整服务。`VITE_CLASS_OS_DEMO=true` 显式开启 mock 原型；演示数据不证明持久业务能力。

## 验证

```powershell
pwsh ./scripts/verify.ps1 -Suite docs
pwsh ./scripts/verify.ps1 -Suite web
pwsh ./scripts/verify.ps1 -Suite backend
pwsh ./scripts/verify.ps1 -Suite all -PostgresRoot '<PostgreSQL18安装目录>'
python scripts/public_guard.py
```

`all` 包含真实隔离 PostgreSQL、浏览器及技术 spike，需要相关依赖。正式 release、真实数据准入与安全 target-bound Eval 仍由 `.ai/gates/` 控制；工程测试通过不能把它们改绿。

## 导航与发行限制

- [工程、数据流与代码地图](docs/ENGINEERING_OVERVIEW.md)
- [正式规格](docs/specs/class-os-v1/release-1-manifest.md) / [原子任务](docs/specs/class-os-v1/release-1-atomic-tasks.md)
- [后端](backend/README.md) / [英文介绍](README_EN.md)
- [候选审查状态](docs/OPEN_SOURCE_READINESS.md) / [安全说明](SECURITY.md)
- [命名兼容矩阵](BRAND_MIGRATION_MATRIX.md) / [第三方声明](THIRD_PARTY_NOTICES.md)

自有部分按 [Apache-2.0](LICENSE) 授权，Copyright 2026 Gdnbit，见 [NOTICE](NOTICE)；第三方保留各自许可。Owner 已确认自有源码及导入原型的再分发权，这不是独立法律清查证明。

本仓库是独立的 **Private 开源候选仓库**，已推送一个不继承原项目历史的初始提交；首次 Windows 与 Ubuntu GitHub Actions 均已通过，但**尚未公开、尚无 GitHub Release**。合成开发测试通过不代表正式 R1、生产部署或真实学生资料准入。不要直接压缩整个工作目录：安装后的依赖、测试截图和运行资料都不是公开范围。公开源码以 `PUBLIC_MANIFEST.json` 为准。不携带原访谈、私人指令、截图、商业策略、运行库和旧提交历史；未经检查的材料不在公开范围内。
