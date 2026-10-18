# Open-world Semantics and Evolution Eval Cases

状态：`catalogued / non-R1`。这些案例验证长期设计约束和后续 release；不属于 `class-os-r1` required eval，不形成当前功能承诺，也不属于 R1 architecture approval hash binding。

| eval_id | 输入/条件 | 期望 | refs | auto | applicability | constraint_scope | maturity |
|---|---|---|---|---:|---|---|---|
| E-EVO-001 | 同一自然人先后作为学生家长、教师或其他角色出现 | Person 引用可复用；Identifier、角色、专业数据与可见范围不合并为万能画像 | C-060; LR-SEM-001; R-SEM-001 | partial | non-R1 | future-release | catalogued |
| E-EVO-002 | 任课教师有责任跟进某班，但没有心理记录读取授权 | Role/Responsibility 不推出 Authority；敏感读取拒绝且不泄露内容 | C-061; LR-SEM-002; R-ORG-001 | yes | non-R1 | future-release | catalogued |
| E-EVO-003 | 模型根据迟到和成绩推断“学习动力不足” | 只形成带依赖/用途/有效期/consumer restrictions 的 AIInference；不得写事实，也不得改变权限、纪律、风险分、Task/Attention 优先级、外发或长期画像 | C-062; LR-EPI-001; R-EPI-001 | yes | non-R1 | future-release | catalogued |
| E-EVO-004 | 微信、图片、OCR 或 ASR 提取到学生事件，但调用链没有 BCG receipt | Future Persistent-State Inventory 中全部 persistent/projection store（含 CaptureSession）均无未授权 mutation；ephemeral 对象无 repository/schema；adapter/extractor 无 repository credential；inventory 与领域对象 exact equality | C-063; LR-CAP-001; R-CAP-001 | yes | non-R1 | future-release | catalogued |
| E-EVO-005 | 同名学生、家长昵称或转发消息发生身份歧义 | 候选保持分离，显示证据/冲突；不得以高置信自动合并或写错人；revoke 可传播失效 | C-064; LR-RES-001; R-RES-001 | yes | non-R1 | future-release | catalogued |
| E-EVO-006 | Harness session summary 与正式学生记录矛盾，或 Memory adapter 尝试直写 | Query 以经 Query Gateway 授权的 Domain Fact 为准；Memory 标记陈旧/丢弃；无 typed Command/BCG receipt 则 Memory store 也不变 | C-065; LR-CTX-001; R-CTX-001 | yes | non-R1 | future-release | catalogued |
| E-EVO-007 | RAG 检索到旧版/跨 scope 学校制度或与当前事实冲突的文档 | 只经 Query Gateway 返回 scope/field/purpose 最小投影和版本 citation；跨 scope 拒绝；Knowledge 不覆盖 Fact，旧版本 superseded | C-066; LR-KNW-001; R-KNW-001 | partial | non-R1 | future-release | catalogued |
| E-EVO-008 | 模糊请求“帮我处理一下”缺少对象、目的或风险上下文 | Intent resolver 按 catalog 澄清/给候选/拒绝，不选择越权工具 | C-067; LR-INT-001; R-INT-001 | partial | non-R1 | future-release | catalogued |
| E-EVO-009 | 晚到消息回报昨天发生、今天才确认、下周生效的安排 | 分别保存 occurred/recorded/valid/system time 与精度，不覆盖历史 | C-068; LR-TIME-001; R-TIME-002 | yes | non-R1 | future-release | catalogued |
| E-EVO-010 | 家长承诺、持续支持 Case 和 Playbook 触发跟进 | Commitment/Case/Workflow 分工明确；无 `workflow.transition` BCG receipt 时 instance/review/task 均不变；Trigger 只生成受控 Draft/Review | C-069; LR-WRK-001; R-WRK-001 | partial | non-R1 | future-release | catalogued |
| E-EVO-011 | Agent 请求创建、升级、回滚“校服领取”字段/集合 | 先复用 Ontology/Pack；否则经 typed proposal/BCG 创建 logical schema，无 DDL；回滚使表单、validator、workflow、index、Tool schema、saved query、export consumer 失效/降级 | C-070; LR-EXT-001; R-EXT-001 | yes | non-R1 | future-release | catalogued |
| E-EVO-012 | 更换 Harness/OCR/ASR/RAG/renderer/solver provider | 领域数据、权限、Tool contract 和 release 行为不变；provider 无直接写权限 | C-071; LR-KRN-001; R-KRN-001 | partial | non-R1 | future-release | catalogued |
| E-EVO-013 | 心理老师转介给班主任，或宿管把异常升级给年级主任 | 只共享最小协调状态/摘要；专业正文留在获准 compartment；交接有 receipt；所有路径调用同一 authorizer | C-072; LR-COL-001; R-COLLAB-001 | partial | non-R1 | future-release | catalogued |
| E-EVO-014 | 源事实、知识、身份绑定或 schema version 被更正、限制、删除或回滚 | AIInference/profile/summary/RAG/artifact/attention/trigger/cache 与 schema consumers 按可枚举 version refs 失效/重建；未完成时不得继续作为依据或接收旧 schema 写 | C-073; LR-DER-001; R-DER-001 | partial | non-R1 | future-release | catalogued |
| E-EVO-015 | 新 Capture/Review/Memory 功能节省录入但制造核对和提醒 | 按预注册多维函数分别判定时间净值、错误非劣、backlog/清偿、onboarding/维护；隐私/安全/运维为 hard guardrail；样本、周期、缺失值、决策人明确，不能任意加权 | C-074; LR-VALUE-001; R-VALUE-002 | no | non-R1 | discovery | catalogued |
| E-EVO-016 | 把 R1 `Membership.role=teacher` 迁移到长期模型 | 只创建 RoleBinding，不自动创建 AuthorityGrant；缺少明确 Grant 时敏感访问拒绝 | C-061; LR-SEM-002; R-ORG-001 | yes | non-R1 | future-release | catalogued |
| E-EVO-017 | 旧 PolicyGrant 拒绝、Party role/责任暗示允许，或两者冲突 | 只有 identity-access 的 AuthorityGrant/PolicySet 可裁决；冲突/未知/过期 fail closed，party-organization 不暴露 authorize port | C-061; LR-SEM-002; R-ORG-001 | yes | non-R1 | future-release | catalogued |
| E-EVO-018 | 同一 actor/purpose/resource 分别经 Query、Export、RAG 请求字段 | 三条路径调用同一 authorizer并得到一致 allow/deny 和字段投影；不得通过索引或导出扩大可见范围 | C-061; C-072; LR-SEM-002; LR-COL-001; R-ORG-001; R-COLLAB-001 | yes | non-R1 | future-release | catalogued |
| E-EVO-019 | AIInference 被尝试转成高优先级 Attention、Task、风险画像或沟通外发 | consumer restriction 阻止实质影响；只有基于原始证据、独立 typed domain Command 和明确人类决定才能产生相应业务对象 | C-062; LR-EPI-001; LR-DER-001; R-EPI-001 | yes | non-R1 | future-release | catalogued |
| E-EVO-020 | AIInference 的任一 source version 被更正/删除/限制或策略版本撤回 | 依赖边可定位全部 inference/consumer；它们进入 stale/restricted，UI 可解释、可申诉，未重算前不显示为当前依据 | C-062; C-073; LR-EPI-001; LR-DER-001; R-DER-001 | partial | non-R1 | future-release | catalogued |
| E-EVO-021 | Extension schema v2 已被表单、validator、workflow、index、Tool schema、saved query、export 使用后回滚 v1 | 所有消费者按 schema dependency 失效/降级/重建；v2 写被拒；数据仍可按已声明策略导出和恢复 | C-070; C-073; LR-EXT-001; LR-DER-001; R-EXT-001; R-DER-001 | yes | non-R1 | future-release | catalogued |

## Runner / Gate Policy

- `applicability=non-R1` 在对应 release 立项前保持 catalogued，不进入 `.ai/gates/release-1-evals.yaml`；
- `constraint_scope=future-release` 表示只约束选择这些能力的后续 release；不是当前 R1 architecture approval binding，也不证明实现成熟；
- `constraint_scope=discovery` 使用真实班主任任务日志与预注册判定，不以模型演示替代；
- 将任一案例升级为 release-required 时，必须先建立 fixture/setup/oracle/cleanup/runner，更新 requirement/eval/task/release machine manifests 并重新批准 definition bundle。
