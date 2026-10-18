# Evals: ClassMatter v1

状态：规格级 eval catalog；最小 Release 1 由 T-REVAL-001—006 建立可执行 runner，完整 v1 的后续 runner 工作归入主工作包 T-FOUND-004。\
原则：eval 先于功能任务，业务 golden 不能为迎合实现而修改。

## Runner Contract

技术栈冻结后，仓库必须提供：

```text
verify docs
verify unit
verify contract
verify integration
verify e2e
verify security
verify performance
verify recovery
verify all
```

具体实现可映射到 `make verify-*`、`task verify-*` 或等价跨平台脚本，但 CI 与开发机使用同一入口。

## Case Format

- `eval_id`：稳定 ID；
- `case_id`：对应业务案例；
- `rule_refs` / `requirement_refs`：追溯；
- `input_fixture`：合成或已确认脱敏输入；
- `expected_output`：结构、不变量、错误码或 golden；
- `tolerance`：数值/文本允许变化；
- `auto_checkable`：yes/no/partial；
- `priority`：P0/P1/P2；
- `expected_red`：新实现前应失败，修复/实现后转绿。
- `spec_status`：`catalogued`（只有意图）或 `executable-spec`（fixture/setup/oracle/cleanup/runner 已定义）。Release 1 的唯一权威来源是 `.ai/gates/release-1-evals.yaml`；case 表仅为受校验投影。`implemented-green` 不是定义成熟度值，只能出现在独立 `.ai/gates/release-1-eval-state.yaml`，并且必须有绑定目标版本、commit、runner 与环境的签名证据。
- `owner` 与 `runner_mapping`：谁维护、由哪个 suite/命令执行。

## Suites

- `cases/core-domain.md`：学生、事件、导入、成绩、座位、宿舍、报告和导出；
- `cases/agent-and-security.md`：Tool、批准、注入、授权、隐私和 Command；
- `cases/quality-operations.md`：可靠性、性能、迁移、备份和降级；
- `cases/manual-ux.md`：真机、可访问性、确认理解和用户减负验证；
- `cases/audit-regressions.md`：对抗审计新增的治理、批准、风险、生命周期和可运维性回归；
- `cases/open-world-evolution.md`：长期语义、Capture/Memory/Knowledge、受控扩展、多角色与净负担边界；当前全部 non-R1；
- `cases/frontend-prototype-characterization.md`：冻结 prototype 的迁仓/工程清理回归清单；不属于当前 R1 required membership；
- `executable/release-1-p0.md`：Release 1 首批可执行规格，不以 catalog 数量代替可运行覆盖；
- `golden/`：经确认的业务输出和当前合成示例策略。

## Golden Output Policy

1. 用户/业务确认的样例是业务真值，不能为实现通过而修改。
2. 当前没有确认样例，所有现有 golden 仅标记 `synthetic-provisional`。
3. 真实样例须先脱敏、登记 source/case、确认，再复制为最小 fixture。
4. 规则变更时保留旧 golden、记录 superseded 和迁移影响。
5. Agent 自由文本不做整段字符串相等；校验事实引用、禁区、结构、分类、语言和人工评分 rubric。

## Coverage Gate

- P0 规则/需求：100% 有自动或明确人工 eval；
- W2/X Command：批准、拒绝、过期、重放、越权、并发变化、依赖失败全覆盖；
- 生产导入/导出：必须有用户确认样例；
- 发布不得存在失败的 P0/P1 eval 或未解释跳过。
- `.ai/pipeline-state.md` 分别报告 catalogued、executable-spec 和 implemented-green，不再把标题数量描述为已完成测试。
- `E-EVO-*` 默认不进入 `.ai/gates/release-1-evals.yaml`；只有新 release 经 change、executable spec、task mapping 和 definition approval 后才可升级为 required。
