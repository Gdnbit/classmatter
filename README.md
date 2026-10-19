# 班事有谱 · ClassMatter

**班里的事，记得住、跟得上、查得到。**

[English](README_EN.md) · [功能与边界](#当前能做什么) · [快速开始](#快速开始) · [工程设计](#工程设计) · [贡献与安全](#参与和安全)

> **已开源 · Pre-alpha · 仅限合成数据开发。** 这是可以在受支持的本机环境运行的工程原型，不是面向学校的生产系统。**请勿导入真实学生、家长或教师个人资料。**

## 为什么做这个项目？

班主任的日常工作并不只是填写表格：学生情况零散地出现在记录中，待跟进的事项容易被消息淹没，一件事处理到哪一步、依据是什么，也可能需要反复回忆。

**ClassMatter 希望成为班主任的「外置工作记忆」与事务跟进台。** 把班级里的事实、任务与处理过程组织起来，让重要事项不依赖一个人始终记在脑子里。

它聚焦的是**记录 → 跟进 → 回看 → 更正与审计**，而不是一次性做完整的教务 ERP 或用 AI 替代教师判断。

## 当前能做什么？

| 场景 | 当前实现 |
| --- | --- |
| 建立班级基础信息 | 本机单 owner 初始化、登录、班级与学生名单维护 |
| 记录班里的事 | 类型化业务事实，保留稳定身份与相关上下文 |
| 防止事情漏跟进 | Task、Today 待办入口，以及 Student Timeline 历史时间线 |
| 发现记录有误 | 更正预览、明确批准、版本与审计记录 |
| 用 AI 辅助整理 | 可替换的 Pydantic AI 组件支持查询与草稿；**不能自行批准或写入正式业务事实** |

例如，想弄清某项班务是否还有后续处理，可以从记录查看关联任务与进展，再通过时间线回顾处理过程。**这是已实现能力的设计路径，不是已验证的真实教师减负效果。**

### 一件事如何被处理？

`事实 / 记录 → 生成或关联待办 → Today 跟进 → Timeline 回看 → 必要时更正与审计`

AI 的回答、推测和草稿与正式事实分开；用户提出业务变更时，仍需经过服务端校验和相应的预览、批准流程。不能因为模型“说了”就直接修改记录。

## 工程设计

- **前端：** React 19、TypeScript、Vite、Tailwind CSS。
- **后端：** Python 3.13、FastAPI、PostgreSQL 18；领域规则、应用网关和基础设施适配器分层。
- **受控读写：** 业务查询使用 QG；业务修改经闭合命令、校验、预览/批准（按风险需要）、BCG 原子提交与事务审计；ISB 管理身份边界。
- **Agent 边界：** Pydantic AI / OpenAI-compatible adapter 可替换；只读查询、草稿与业务写入权限相互隔离。
- **公开安全边界：** 公开树由 [PUBLIC_MANIFEST.json](PUBLIC_MANIFEST.json) 的逐文件 SHA-256 白名单约束，并有 [CI](.github/workflows/synthetic-ci.yml) 检查秘密模式、文档、合约、前后端及隔离数据库/浏览器回归。

当前技术详情与边界参见 [工程与数据流说明](docs/ENGINEERING_OVERVIEW.md)。代码内部保留 `class_os`、`CLASS_OS_*` 等历史技术标识，以确保兼容，**不代表产品仍叫 Class OS**。

## 快速开始

目前正式支持的持久化本机入口依赖 **Windows + DPAPI**，并要求：

- PowerShell 7、Node.js 22–24、pnpm **11.19.0**
- Python **3.13**、uv **0.11.7**
- PostgreSQL **18.6** 的本机 binaries

先构建前端，再从后端目录启动：

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

在浏览器打开 **http://127.0.0.1:8000**。凭据和恢复码仅在本机交互终端妥善保存，**不要提交到 Git**；完成后可运行 `uv run --frozen python local.py stop`。

`init` 不覆盖已有实例，旧实例升级须显式执行迁移。不要把 `.local-runtime/` 直接复制到其他电脑。单独启动 Vite 并不是完整后端服务；`VITE_CLASS_OS_DEMO=true` 仅用于显式开启合成 mock 演示。

## 如何验证？

从仓库根目录执行：

```powershell
python scripts/public_guard.py --require-license
pwsh ./scripts/verify.ps1 -Suite docs
pwsh ./scripts/verify.ps1 -Suite web
pwsh ./scripts/verify.ps1 -Suite backend
pwsh ./scripts/verify.ps1 -Suite all -PostgresRoot '<PostgreSQL18安装目录>'
```

`all` 包含隔离的真实 PostgreSQL、浏览器及技术 spike 检查，需要对应依赖。GitHub Actions 的 Windows / Ubuntu 合成 CI 已在 [公开的运行记录](https://github.com/Gdnbit/classmatter/actions/runs/39185506327) 中通过；**工程测试通过不等于正式 R1 或真实数据准入**。

## 当前没有承诺的能力

- 尚未完成真实教师场景下的可用性和净减负验证。
- Capture、主动提醒、复杂排班、多角色协作、完整退出/跨机恢复仍有未实现或未验证部分。
- 未通过正式发布 Gate、真实模型质量与真实数据准入；不能用于生产部署、组织派责或免责判定。
- Linux CI 验证不意味着持久化本机安装已跨平台支持。

详细范围以 [正式规格](docs/specs/class-os-v1/release-1-manifest.md)、[工程说明](docs/ENGINEERING_OVERVIEW.md)及 [安全说明](SECURITY.md) 为准。

## 参与和安全

- [贡献指南](CONTRIBUTING.md) · [安全边界](SECURITY.md) · [公开审计摘要](docs/PUBLIC_AUDIT.md)
- [英文 README](README_EN.md) · [后端使用说明](backend/README.md) · [品牌与兼容矩阵](BRAND_MIGRATION_MATRIX.md)
- 代码自有部分以 [Apache-2.0](LICENSE) 开源，Copyright 2026 Gdnbit；第三方授权参见 [NOTICE](NOTICE) 与 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

此仓库是**独立导出的公开版**，没有继承原开发仓库的 Git 历史、私人访谈、个人截图、旧归档、运行凭据与数据。请不要把本机安装目录或未经审核的新素材直接推送到公开分支；新增或修改文件都必须重新审查并同步公开清单。