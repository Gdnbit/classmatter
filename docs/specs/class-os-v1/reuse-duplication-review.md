# Reuse and Duplication Review

> 文档状态（2026-10-08）：现行规格/规划/规则；设计存在；实现/批准须另凭目标版本证据。项目完成度见 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md)；本标识不提升批准、测试或任务状态。

| Logic/Module | Decision | Reason | Guardrail |
|---|---|---|---|
| student identity/matching | shared domain service | 所有导入和模块依赖同一身份 | property tests + manual conflict flow |
| authorization/context policy | shared service | UI/API/Agent/MCP 必须一致 | deny-by-default contract tests |
| audit event creation | shared application utility | 避免不同入口漏审计 | transaction integration tests |
| idempotency/version check | shared command infrastructure | 所有写入共性 | replay/concurrency tests |
| import parser interface | shared protocol, adapters local | Excel/CSV 差异大，canonical rows 相同 | adapter contract suite |
| grade calculations | shared pure domain functions | 口径一致且可版本化 | golden/property/metamorphic tests |
| seating/dorm assignment abstraction | share primitive, fork rules | 都有 Location/Slot/Assignment，业务约束不同 | 分开 module 与 eval，不用巨型通用服务 |
| report source citations | shared component | 所有生成内容需要溯源 | missing citation blocks finalize |
| sensitive field projection | shared policy engine | 跨输出/模型/日志一致 | field matrix tests |
| UI form glue | local duplication allowed | 低风险且领域差异明显 | 超过 3 次重复触发组件评审 |
| Agent Skill 文案 | per workflow | 流程和禁区不同 | 共享 metadata schema，不共享模糊大 Skill |
| Tool/MCP schemas | generate from one source | 防止内部/外部契约漂移 | schema snapshot and compatibility tests |
| external project code | avoid by default | 许可与架构不匹配 | ADR + license approval before use |
| signature envelope / crypto | reuse DSSE + in-toto/securesystemslib + cryptography | 自研 framing 和密码学实现增加审计面，且不产生产品差异 | exact lock、官方向量、ClassMatter policy 与 crypto validity 分离 |
| CI artifact provenance | reuse GitHub/Sigstore attestation when enabled | 已有 workflow/repository/commit provenance 语义 | 只证明构建来源，绝不替代 runtime role/admission authorization |
