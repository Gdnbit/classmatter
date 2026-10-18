# Resource Review

> 文档状态（2026-10-08）：现行规格/规划/规则；设计存在；实现/批准须另凭目标版本证据。项目完成度见 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md)；本标识不提升批准、测试或任务状态。

| Resource | Source | Purpose | License/Rights | Commercial Use | Decision |
|---|---|---|---|---|---|
| eventsource-parser | https://github.com/rexxars/eventsource-parser | 成熟 SSE 分帧；Web 只加封闭 envelope 校验 | MIT（既有 spike 与安装包 LICENSE） | allowed with notice/SBOM | 4.1.1 精确锁定，复用已验证 spike 版本；不自研流协议 parser |
| Playwright Test | https://github.com/microsoft/playwright | 实际浏览器 against disposable PostgreSQL E2E；不 mock API | Apache-2.0（安装包 LICENSE） | allowed with notice/SBOM | 1.64.0 dev-only 精确锁定；Windows 使用现有 Edge，Linux 需安装匹配 Chromium；不引入运行时产品依赖 |
| rfc8785 | https://github.com/trailofbits/rfc8785.py | 成熟 RFC 8785 canonical JSON；既有签名 spike 复用到固定 proposal hash | Apache-2.0（0.1.4 installed metadata/classifier；同 spike 锁版本） | allowed with notice/SBOM | 0.1.4 synthetic-development；只做规范化，不自建 hash framing 或授权机制 |
| Gibbon | https://github.com/GibbonEdu/core | 参考学生中心、权限、报告 | GPL-3.0 | 有义务 | ideas-only；不复制源码 |
| Frappe Education | https://github.com/frappe/education | 参考教育实体和后台流程 | 选型时重核 | unknown | ideas-only |
| RosarioSIS | https://www.rosariosis.org/ | 参考 SIS 数据域 | GPLv2 自述 | 有义务 | ideas-only |
| Project-X | https://github.com/Dalian-No-5-Middle-School-I-T-C/Project-X | 参考考试与分析流程 | GPL-3.0 | 有义务 | ideas-only；不合并源码 |
| open_fuckseats | https://github.com/laosan577622/open_fuckseats | 排座算法与约束参考 | GPL-3.0 + 自定义例外 | risky/unknown | avoid code until legal review |
| class-teacher-skills | https://github.com/PIGU-PPPgu/class-teacher-skills | 班务场景与 Skill 参考 | MIT（访问时） | likely allowed | concepts; copy only with notice/review |
| education-agent-skills | https://github.com/GarethManning/education-agent-skills | Skill 组织与教学法参考 | CC BY-SA 4.0 | conditional | ideas/citations only |
| Pydantic AI v2 | https://github.com/pydantic/pydantic-ai | Agent runtime adapter | MIT（T-RSPK-002 SBOM/installed metadata） | allowed with notice/SBOM | 当前候选2.53.0安全维护pin；历史2.46.0为初始spike接受基线；经AgentRuntimePort，回归与未完成项见依赖修复/公开审计，不自动晋升 |
| TypeSafe SDK / Jev | https://typesafe.ai/；https://pydantic.dev/docs/ai/models/typesafe/ | optional typed routing | MIT（typesafe-sdk 0.7.0 installed metadata） | allowed with notice/SBOM；service terms/provider admission separate | SDK adapter 可安装但 R1 默认关闭；无校准 provider run，不得声称质量收益 |
| FastAPI / Uvicorn | https://github.com/fastapi/fastapi；https://github.com/encode/uvicorn | Python API runtime | MIT / BSD-3-Clause（T-RSPK-001 registry/lock evidence） | allowed with notice/SBOM | FastAPI 0.141.1、Uvicorn 0.53.0 accepted-for-development；升级须 contract/性能回归 |
| Fastify / Zod | https://github.com/fastify/fastify；https://github.com/colinhacks/zod | 单语言后端对照 | MIT / MIT（T-RSPK-001 registry/lock evidence） | allowed | backend rejected-for-current-baseline；保留 spike 对照，不进入生产依赖 |
| PostgreSQL | https://www.postgresql.org/；Windows binary 由官方页链接至 EDB | canonical transactional store | PostgreSQL License；18.6 portable archive SHA-256 见 T-RSPK-003 evidence | allowed with notice/operations controls | PostgreSQL 18 accepted-for-development；生产镜像 digest、补丁升级/回滚与 clean-host doctor 留给 T-ROPS/T-REVAL-022 |
| Psycopg 3 | https://www.psycopg.org/psycopg3/；https://github.com/psycopg/psycopg | Python PostgreSQL adapter | LGPL-3.0-only（官方 metadata；2026-09-22 复核） | allowed with LGPL obligations/SBOM | 3.3.6 accepted-for-development；官方测试覆盖 Python 3.13、PostgreSQL 18、Windows；仅作为 infra adapter，不泄漏到 domain port |
| SQLAlchemy Core / Alembic | [Core](https://docs.sqlalchemy.org/en/20/core/) / [migration cookbook](https://alembic.sqlalchemy.org/en/latest/cookbook.html) | PostgreSQL connection/transaction 与发布迁移；不自建框架 | MIT：[SQLAlchemy LICENSE](https://github.com/sqlalchemy/sqlalchemy/blob/rel_2_0_54/LICENSE)、[Alembic LICENSE](https://github.com/sqlalchemy/alembic/blob/rel_1_20_0/LICENSE)，2026-10-08 核查 | allowed with notice/SBOM | 2.0.54 / 1.20.0 synthetic-development；精确锁定；真实部署/签名准入不自动通过 |
| pwdlib / Argon2 | [official API](https://frankie567.github.io/pwdlib/reference/pwdlib/) / [package](https://pypi.org/project/pwdlib/) | 本地密码/离线恢复码的成熟哈希实现，不是完整身份系统 | [MIT（pwdlib v0.3.1 LICENSE）](https://github.com/frankie567/pwdlib/blob/v0.3.1/LICENSE)；Argon2 依赖许可随锁包 metadata 核查 | library reuse | 0.3.1 synthetic-development；明确只是哈希组件，ISB/session/recovery/审计仍由应用用例编排和测试 |
| OpenAI Agents SDK | https://github.com/openai/openai-agents-python | runtime 对照/回退 | MIT（2026-09-20 复核） | allowed with notice/SBOM | comparison fallback；0.x 需精确锁版本 |
| AG-UI Protocol | https://github.com/ag-ui-protocol/ag-ui | Agent UI wire protocol candidate | MIT（ag-ui-protocol 1.0.0 installed metadata） | allowed with notice/SBOM | adapter-only candidate；R1 前端使用 ClassMatter 自有 event envelope，不把 AG-UI 类型固化进 Kernel |
| Microsoft Agent Framework | https://github.com/microsoft/agent-framework | workflow/runtime alternative | MIT（2026-09-20 复核） | allowed with notice/SBOM | defer until durable workflow need |
| LangGraph | https://github.com/langchain-ai/langgraph | durable workflow alternative | MIT（2026-09-20 复核） | allowed with notice/SBOM | defer；引入前复核 security advisories |
| Pi | https://github.com/earendil-works/pi | coding harness/reference | MIT（2026-09-20 复核） | allowed with notice/SBOM | development/reference only；not business runtime |
| DeepSeek Harness | https://github.com/deepseek-ai/deepseek-harness | experimental harness reference | MIT（2026-09-20 复核） | license permits；status blocks production | avoid production：developer preview/未安全审计 |
| Docling | https://github.com/docling-project/docling | unified document parsing candidate | MIT（2026-09-20 复核） | allowed with notice/SBOM | preferred synthetic benchmark baseline；经 `DocumentProcessingPort`，不把 DoclingDocument 变成 domain model |
| MinerU | https://github.com/opendatalab/MinerU | complex Chinese PDF/OFD/image parsing comparison | MinerU Open Source License（Apache-2.0 + additional terms） | conditional；attribution/scale thresholds | comparison only until benchmark、resource、license obligations approved |
| Apache Tika | https://github.com/apache/tika | broad format detection/metadata/text fallback | Apache-2.0 | allowed with notice/SBOM | optional fallback；只有覆盖证据需要时引入 JVM 栈 |
| LibreOffice | https://github.com/LibreOffice/core | legacy Office conversion/rendering worker | MPL-2.0 | allowed with obligations | isolated converter candidate；never execute macros/external links |
| libarchive | https://github.com/libarchive/libarchive | archive inspection and extraction | New BSD | allowed with notice/SBOM | preferred archive backend candidate；ClassMatter adds quotas/path policy |
| 图标/字体/模板 | 尚未选择 | UI 与导出 | unknown | unknown | do not use until inventoried |
| 真实学生数据 | 用户/学校 | 验证业务 | 受隐私、授权和学校制度约束 | not a licensable asset | prohibited until approval and de-identification |

任何 `unknown` 或 `risky` 资源不得进入生产依赖。依赖锁定后必须生成 SBOM，并记录版本、哈希、许可、维护状态和替代方案。
