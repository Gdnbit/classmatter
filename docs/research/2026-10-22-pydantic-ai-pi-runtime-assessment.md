# Pydantic AI 与 Pi：Agent Runtime 选型及专业社区调研

> **研究记录**：2026-10-22；适用范围：ClassMatter 的 Agent Runtime Port 与未来可替换 Harness。
>
> **状态**：调研结论 / 候选方案（proposed for evaluation）；**没有批准迁移 Pi，没有替换当前实现，没有生产对比结果**。文中“有能力”是文档或作者描述；“适用”是结合 ClassMatter 架构做出的判断；“胜出”必须经过同条件实验。
>
> 数据源原则：官方文档说明功能、官方案例只证明所述采用事实，独立工程文章提供单一生产经验，Reddit/Hacker News 提供个体意见；不把热度、Star、引用、宣传数据当成独立性能评测。

## 1. 一句话结论

**对于现在的 ClassMatter，保持 Pydantic AI 为默认 Agent Runtime 更合理；Pi 是有价值的 TypeScript 备选，但缺少值得支付迁移与跨语言成本的实证收益。**

两者都能完成大模型调用、Agent loop、工具调用、模型/会话上下文组织、流式事件。差异在工程取向：

- **Pydantic AI**：Python、类型化工具与结构化输出、依赖注入、测试/评测/遥测以及服务端业务系统集成；
- **Pi**：TypeScript、极简可组合的 Agent 会话/工具/扩展生态，SDK 和 JSONL RPC，擅长交互式及高可定制 Agent 形态；
- **都不应该**成为 ClassMatter 的业务事实源、权限系统、法律/组织责任裁定者，或取代持久业务 Work Item 的生命周期。

框架改变通常不会天然提升同一模型的推理智力；业务准确率、Token、延迟、可维护性必须同基准测量。

## 2. ClassMatter 代码与既有技术决策（核对基准）

截至本次研究，公开仓库：

- Python 3.13 / FastAPI / PostgreSQL，React + TypeScript UI；
- backend/pyproject.toml 包含 **pydantic-ai-slim[openai]==2.53.0**（本次核对的仓库固定版本，**不代表上游最新版**）；
- [ADR-003](../specs/class-os-v1/architecture-decision.md) 要求单 Agent 起步、Agent 非业务关键路径、R1 仅查询/草稿、批准服务与 Runtime 分离；
- [ADR-006B](../specs/class-os-v1/architecture-decision.md) 已基于已有合成实验选择 Pydantic AI 作为首个 AgentRuntimePort adapter；禁止 Agent 直接访问正式业务写入口；
- [ADR-009/010](../specs/class-os-v1/architecture-decision.md) 约束 Context / Memory / Knowledge / Domain Fact 分离，Temporal 是底层语义，Workflow/Scheduling/Attention 属于可替换上层能力；
- [R1 manifest](../specs/class-os-v1/release-1-manifest.md) 排除 Agent/MCP 业务写、主动提醒、复杂 Workflow、外部 Channel、敏感数据及真实自动化。

以上是**当前设计与代码状态**；不意味着当前 R1 获得生产准入或真实模型质量验证。

## 3. 功能对照：避免把运行时、记忆与业务状态混为一谈

| 维度 | Pydantic AI | Pi | ClassMatter 的决策 |
|---|---|---|---|
| Agent loop / tool call | 支持，Python Agent 与 typed tools | 支持，SDK 会话与工具循环 | 通过自有 Runtime Port |
| 模型/Provider | 多家 Provider/兼容适配 | 模型服务/Provider 配置与扩展 | 独立锁模型与兼容用例 |
| 结构化输出 | Pydantic 校验与 typed dependency | Tool schema / 扩展结构化返回 | 由领域验证最终判断 |
| 会话上下文 | 消息历史、历史处理、Harness 能力 | 分支会话、压缩、上下文/资源加载 | 可缓存，但不是正式事实或权限 |
| 扩展 | Toolsets / Capabilities / Hooks / MCP | Extensions / Skills / SDK / RPC | 仅加载经过可信审查的能力 |
| 观测、评测 | OTel / Pydantic Evals 等完善生态 | 事件可观测，业务评测需自建/集成 | 共用 ClassMatter Eval schema |
| Durable run | 官方可与 Temporal、DBOS 等集成 | 存在外部生态与扩展，不能等同于 ClassMatter 业务事务 | 业务状态与调度由系统持有 |
| 与现有后端 | Python 直接嵌入 | Pi SDK 需 Node/Bun；Python 可用 JSONL RPC 子进程 | 默认 Pydantic，Pi 仅隔离实验 |
| 内置执行工具的权限 | 取决于配置/Tools | CLI/SDK 可带文件、Shell、扩展工具 | **禁止默认继承通用工具权限** |

**版本限定**：官方“最新”文档可能描述仓库现有固定版尚未启用或未验证的特性；能力进入 ClassMatter 前必须与目标锁定版本和依赖安全审核逐项核验。不能把 Pydantic AI Harness 的所有功能当成当前已安装的能力，也不能把 Pi 的扩展生态当成默认业务能力。

### Pi 集成候选

方案 A：**独立受限 Pi RPC 子进程** → Python AgentRuntimePort adapter → 既有 ClassMatter Query Gateway。Pi 官方 RPC 为基于 stdin/stdout 的 JSONL 控制和事件流，适合跨语言与进程隔离。

方案 B：**TypeScript Agent Worker 嵌入 Pi SDK** → 通过可信内部接口调用 ClassMatter 业务工具。可控性更高，但增加部署、进程管理、身份传递和跨语言契约维护。

这两个选项都只作为**受限合成研究实验**，暂不将 Pi 引入正式 API/运行时部署。Pi 的扩展运行在同一 OS 权限下，能够访问提示、工具、凭据与 Session，不能未经白名单与源码审计加载第三方扩展。

### 非目标

- 不通过 Fork Pi 把班级业务与其内部实现深度耦合；
- 不因 Pi 的编码/文件操作能力而向班主任产品开放 Bash、文件全盘、任意网络/SQL；
- 不把 Pi SessionManager / Pydantic 会话持久化当成 ClassMatter 的正式业务数据库；
- 不因为框架有持久执行支持，就直接实现新的跨 Release Workflow；
- 不为“可替换”维持两套永远在线、重复构建的正式 Agent 服务。

## 4. 专业社区和生产反馈：按证据层级看

### A. 官方生产案例：采用证据，存在选择偏差

1. **MindsDB**：Pydantic 官方案例记载，该团队从 LangChain 迁至 Pydantic AI，主要为了更可控的中间状态、验证输出及普通 Python 工程师可维护性。其“10x”是团队自述的综合收益，**并非跨框架独立统一基准**。[原始案例](https://pydantic.dev/case-studies/mindsdb)（2025-01）。
2. **Qualio**：Pydantic 官方案例称，该受监管软件团队将 Pydantic Evals 接入部署门禁，维护约 160 个测试用例和 300 项评估，并从复杂多 Agent 结构收敛至更少的高层工具。说明可审计评估实践有现实采用，但**不能把其合规场景无条件外推到未成年人数据**。[原始案例](https://pydantic.dev/case-studies/qualio)（2026-07）。

### B. 相对独立的生产复盘：单一团队经验

3. **Codify**《Lessons learned from a year of running Pydantic AI in production》报告其长期运维经验，肯定类型化工具合同、OpenTelemetry、分层 Context，并强调 **framework should not become the product**。其用户规模与成效属于文章作者自报，不能作为 ClassMatter 的收益预测。[原文](https://codify.ch/en/post/a-year-of-pydantic-ai-in-production)（2026-09）。

### C. HN / Reddit：个体开发者反馈，不是社区共识投票

4. **Hacker News**：有开发者赞赏 Pydantic AI 在控制与抽象之间的平衡、结构化验证和依赖注入；样本是公开评论，不代表全体资深工程师。[讨论](https://news.ycombinator.com/item?id=43468435)（2025-03）。
5. **Reddit r/LLMDevs**：有开发者表示此前在复杂流程中与 LangChain/Flowise/n8n 抽象发生摩擦，而 Pydantic AI 更直接；该帖本身也在征集大规模生产经验，不能据此认定“工业级规模已被普遍证实”。[讨论](https://www.reddit.com/r/LLMDevs/comments/1iih8az/pydantic_ai/)。
6. **Reddit 同框架试验**：个别反馈指出部分“OpenAI-compatible”端点并不完整实现官方接口，导致 Pydantic AI 的结构化输出/模型适配容易失败。这是**值得转成兼容性 Eval 的具体风险**，不是所有兼容模型都会失败的结论。[讨论](https://www.reddit.com/r/LLMDevs/comments/1kqfaf4/i_have_written_the_same_ai_agent_in_9_different/)。
7. **反面体验**：有开发者表示 Pydantic AI 源码/抽象对其阅读习惯并不简单，说明易用性取决于团队经验。[讨论](https://www.reddit.com/r/LLMDevs/comments/1iqawjz/am_i_the_only_one_that_thinks_pydanticai_code_is/)。

### 综合判断

- 有明确的**生产采用证据**，并非仅用于 Demo；
- 类型化工具与明确控制流在专业讨论中反复获得正面反馈；
- 升级、Provider 兼容性、前端事件流、断线恢复、权限和业务持久化仍需要系统工程；
- 未找到足够强的**同业务、同模型、同工具、同评测**证据，证明 Pi 全面优于 Pydantic AI，或反之；
- 不采纳动态 Star 数、贡献人数、营销式“十倍”作为 Runtime 切换判据。

## 5. 设计建议：ClassMatter 持有长期状态，Runtime 仅按需推理

~~~text
ClassMatter Web / Today / Timeline / AI Inbox（未来）
          │
   Auth / Context Policy
          │
   Query Gateway / Domain Fact ─── PostgreSQL / Evidence / Memory Policy
          │
   AgentRuntimePort（稳定契约，最小权限）
          ├── Pydantic AI adapter（现有）
          └── Pi adapter（仅合成实验候选）
          │
    typed result / proposed action
          │
    ClassMatter validator / preview / BCG（仅经未来 release 授权）
          │
    Work Item / Trigger / Audit / Attention（Discovery / Future）
~~~

会话历史的处理可委托 Framework，但业务 Context 的**来源/权限/有效期/组装策略由 ClassMatter 负责**。业务状态机、事件与事务 Outbox 不因更换框架丢失，且 Agent 不需要全天常驻思考。

RAG/Wiki 提供 Knowledge，向量相似度或全文搜索是检索手段，并不能天然建立业务事实权威；Tool 输出仍当作数据，防止 prompt injection 将外部文本变成指令。

对应产品研究：[Agent 承接可执行工作](../product/agent-owned-work-and-attention.md)。

## 6. 决策与何时重新评估

**建议保留现状**：ClassMatter 默认 Pydantic AI，并先盘点已用功能/有无重复开发官方能力；不实施 Pi 迁移。

重新评估条件（任一项有可测收益时）：

- 现有 Pydantic AI 在真实目标模型兼容、事件流、长任务/取消、成本或自定义 Hooks 上出现实质阻碍；
- 未来确实需要 Pi 的交互式 Agent/扩展体验，且是 ClassMatter 真实用户高频需求；
- 同一隔离数据集和模型/工具/上下文策略下，Pi 能显著改善正确率、维护成本或运行可靠性，且没有增加隐私和安全风险；
- 异语言运行时的部署、升级、监控和恢复成本被证明可接受。

变更门槛是**实验 → 证据 → ADR → 目标 release applicability → Eval / Task / Gate**。不得通过这份研究文件偷渡功能。

详细实验设计：[Agent Runtime 和持续工作研究验收计划](2026-10-22-agent-runtime-and-work-evaluation-plan.md)。

## 7. 上游官方资料（2026-10-22 查阅）

- [Pydantic AI overview](https://pydantic.dev/docs/ai/overview/)：typed agent、Provider、工具与 Harness 总览。
- [Pydantic Capabilities](https://pydantic.dev/docs/ai/capabilities/overview/)：可组合的工具、Hooks、指令和模型设置。
- [Pydantic Durable Execution](https://pydantic.dev/docs/ai/capabilities/durable_execution/overview/)：受支持的持久执行引擎；官方明确 **durability ≠ conversation storage**。
- [Pydantic Evals](https://pydantic.dev/docs/ai/evals/)：输出、工具轨迹与评测。
- [Pydantic Production](https://pydantic.dev/docs/ai/production/)：生产部署、审查与可观测性。
- [Pi: How Pi Works](https://pi.dev/docs/latest/how-pi-works)：会话树、Agent loop、工具与信任。
- [Pi SDK](https://pi.dev/docs/latest/sdk)：可嵌入 Node/Bun 的接口、会话与资源管理。
- [Pi RPC](https://pi.dev/docs/latest/rpc)：跨语言 JSONL 子进程。
- [Pi Extensions](https://pi.dev/docs/latest/extensions)：扩展和权限风险；第三方扩展必须审核。

**后续重新核对**：上游文档是可变的，版本或接口升级必须重新验证；本文件不承诺以上全部特性在 ClassMatter 锁定版本已存在或已被调用。