# Release 1 Pilot Profile

> 文档状态（2026-10-08）：现行规格/规划/规则；设计存在；实现/批准须另凭目标版本证据。项目完成度见 [公开工程边界说明](../../ENGINEERING_OVERVIEW.md)；本标识不提升批准、测试或任务状态。

状态：`review`。这是 Release 1 唯一可被 T-RREL-002/003 引用的试点范围定义；`docs/07-实施与测试/发布验收与试点计划.md` 仅是完整 v1 的未来模板。

## 允许范围

- 1 位 owner、1 个部署、1 个当前班级、1 个当前学期；
- owner 经受信 Web UI 手工建立班级、学期和学生；
- 记录已发生的表扬、迟到、缺勤、请假/销假、未交/补交、谈话事实；
- 简单任务、Today、Student Timeline；
- Agent 只读查询和内存草稿，模型不可用时结构化功能保持可用；
- 版本化 machine exit package、备份、隔离恢复、升级回滚和退役演练；
- `synthetic-only` shadow 后，只有外部签名 admission artifact 的精确 scope 可进入 `approved-real-pilot`。

## 禁止范围

- 任何 CSV/Excel/文件/第三方名单或成绩导入；
- 排座、宿舍、成绩、监护人、附件、音频、语音/转写；
- 批量业务写、merge、hard delete、X 级动作；
- 消息外发、报告外发、外部 MCP listener、Agent/MCP 写 Tool 或 approve；
- 未在 admission artifact 中列出的用户、班级、学期、模块或时间窗口。

禁止项不得只依赖 UI 隐藏：route、OpenAPI/schema、Tool catalog、worker/CLI 注册和依赖扫描都必须证明 surface 不存在或固定拒绝。

## 阶段

1. 合成 shadow：使用确定性 fixture；不录入真实学生信息；产出含 setup/维护成本的 go/change/stop 决策。
2. 候选与 readiness 验收：在目标 commit 完成 candidate、最终 store inventory、退出/恢复/退役和全部 required eval；verifier 产生外部可验的 candidate、shadow/value 与 pilot-readiness gate reports。
3. 空 scope 预分配：批准者在应用外签发一次性短时 setup capability；scope 字段绑定 release/deployment/owner/workspace，evidence 字段绑定第 2 步 candidate/pilot-readiness/shadow-value 报告。应用只允许 BCG 内的 `ScopeAllocationCommand` 原子消费它，写无 PII 的 allocation ledger 并预留 class/term ID；此时不存在 Class/Term/Student 业务实体，其他 pre-admission command 全拒绝。receipt 绑定 workspace、target commit/environment、setup ID、预留 ID 和耐久 ledger proof。
4. 最终准入签发：批准者在应用外核验 allocation receipt 和第 2 步全部 gate reports，签发只覆盖相同 workspace、预留 class/term、本 profile、目标版本和期限的最终 admission artifact。应用 verifier 必须验证 report/receipt 的签名、内容 hash、release、commit、environment、ledger 与未撤回状态，不能只比较任意字符串 hash。
5. 最小真实试点：在最终 artifact 生效后，owner 才可手工建立学生花名册；每次写重新验证 artifact 与证据链；每日检查审计、失败、重复、投入和退出能力。
6. 到期/撤回：立即停业务写；执行受控退出并保留批准的审计/例外证明。

不存在“只读导入”或“先小批量导入”的过渡例外。若手工建班净成本不可接受，应 `change/stop`，不能借此开启导入。

## Go / Change / Stop

- Go：目标版本全部 required eval green，governance/admission/ops 证据有效，且包含启动成本的净减负成立。
- Change：仍局限于本 profile 内改变交互或任务拆分，重新签发受限 artifact。
- Stop：任一越权、未审计释放、不可恢复写、范围外 surface、恢复接管风险或净收益为负。
