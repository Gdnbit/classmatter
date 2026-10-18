# Quality and Operations Eval Cases

## Process and architecture gates

| eval_id | 条件 | 期望 | refs | auto | priority |
|---|---|---|---|---:|---:|
| E-SCOPE-001 | 扫描 v1 routes/tools/modules | 无招生、收费、人事、全校排课等超范围生产入口 | R-POS-002; Requirements Out of Scope | yes | P0 |
| E-SCOPE-002 | 将 Release 1 pilot profile 与 route/schema/Tool/worker/CLI/dependency 清单及 admission allowed_modules 比较 | 仅允许手工 roster、事实、任务、Today/Timeline、退出和只读/草稿 Agent；导入、排座、外发等 surface 不存在或固定拒绝 | R-POS-002; release-1-pilot-profile | yes | P0 |
| E-ARCH-001 | 扫描 Agent 注册和 ADR | 默认只有一个业务 Agent；新增 Agent 必须关联 accepted ADR 和质量 eval | R-AGT-005; FR-AGT-009 | yes | P0 |
| E-ARCH-002 | T-RPLT-001 或 feature gate 校验架构批准 | 当前 architecture/ADR/spike/constraints hash 必须与应用外签名 artifact 一致；example/过期/被篡改 artifact 固定拒绝 | R-DEV-003; architecture-confirmation | yes | P0 |
| E-DEV-001 | 在未配置个人机器状态的受支持干净环境执行仓库唯一验证入口 | 按文档一次完成依赖安装和验证；无未记录绝对路径、全局工具或本机 secret 依赖 | NFR-MNT-004; R-DEV-001/002 | yes | P0 |

## Reliability and failure injection

| eval_id | 条件 | 期望 | refs | auto | priority |
|---|---|---|---|---:|---:|
| E-OPS-001 | Command 响应丢失后重试 | 查询/复用 receipt，不重复写 | C-030/C-036; NFR-REL-001/002 | yes | P0 |
| E-OPS-002 | DB commit 前进程退出 | 无业务变更或可识别未提交事务 | NFR-REL-001 | yes | P0 |
| E-OPS-003 | DB commit 后响应前退出 | 重试返回已提交 receipt | NFR-REL-001/002 | yes | P0 |
| E-OPS-004 | outbox worker 重复投递 | 副作用幂等，attempt 可查 | ADR-005 | yes | P0 |
| E-OPS-005 | 每日备份生成 | 加密、校验、保留和告警正确 | R-OPS-001; NFR-REL-003 | yes | P0 |
| E-OPS-006 | 隔离环境恢复 Release 1 数据 | Class/Term/StudentIdentifier/Record/Task、关系、生命周期 ledger 与 audit 一致；不存在 R1 范围外附件要求 | C-035; NFR-REL-003 | partial | P0 |
| E-OPS-007 | 备份损坏/密钥缺失 | 演练失败并告警，不覆盖可用备份 | R-OPS-001 | partial | P0 |
| E-OPS-008 | 模型 provider 完全不可用 | 非 AI 基本功能可用，Agent 明确降级 | FR-PLT-005 | partial | P0 |

## Migration and compatibility

| eval_id | 条件 | 期望 | refs | auto | priority |
|---|---|---|---|---:|---:|
| E-MIG-001 | 空数据库执行全部迁移 | 成功达到目标 schema | NFR-REL-004 | yes | P0 |
| E-MIG-002 | 上一发布数据升级 | 数据不丢、约束成立 | NFR-REL-004 | yes | P0 |
| E-MIG-003 | 迁移中断 | 可安全重跑或按 runbook 前滚 | NFR-REL-004 | partial | P0 |
| E-MIG-004 | 旧 Web 与新 API 兼容窗口 | 兼容路径或明确阻止旧客户端写 | API compatibility | yes | P1 |
| E-MIG-005 | Tool schema snapshot 变化 | 向后兼容或要求新 version/ADR | NFR-MNT-001/003 | yes | P0 |

## Performance and capacity

| eval_id | 条件 | 期望 | refs | auto | priority |
|---|---|---|---|---:|---:|
| E-PERF-001 | 完整 v1 候选目标规模 Student 360 | Student 360 视图 p95 ≤2s；不作为 Release 1 花名册/时间线性能替代证据 | NFR-PERF-001 | yes | P1 |
| E-PERF-002 | 10k 行合成表导入预览 | ≤30s，内存受限，有进度/取消 | NFR-PERF-003 | yes | P1 |
| E-PERF-003 | Agent 长任务 | ≤2s 首反馈，阶段可见，可取消 | NFR-PERF-004 | partial | P1 |
| E-PERF-004 | 并发 5 个会话执行只读/草稿 | 无跨会话数据泄漏，SLO 达标 | NFR-PERF-002; R-AUTH-001 | yes | P1 |
| E-PERF-005 | 排座最坏候选规模 | 超时安全返回，不应用未经完整校验方案 | FR-SEA-003 | yes | P1 |
| E-PERF-006 | Release 1 目标规模下访问花名册、Today 与 Timeline | 在规定中档手机、常规家庭宽带和冷/热缓存矩阵中，关键只读交互 p95 ≤2s | NFR-PERF-002; A-002/A-013 | yes | P1 |
| E-PERF-007 | Release 1 目标规模下确认一次 W1/W2 写入 | 排除外部模型生成时间后，从最终确认到可验证 receipt 的 p95 ≤3s | NFR-PERF-002; A-002/A-013 | yes | P1 |

## Observability

| eval_id | 条件 | 期望 | refs | auto | priority |
|---|---|---|---|---:|---:|
| E-OBS-001 | 一次 Agent→Tool→Command 流程 | request_id 跨层关联，业务 audit 独立 | NFR-OBS-001 | yes | P0 |
| E-OBS-002 | Tool/模型失败 | metric、error code、trace 和用户状态一致 | NFR-OBS-001/002 | yes | P1 |
| E-OBS-003 | 触发 P0 告警 | 含 runbook/影响，不含学生 PII | NFR-OBS-003 | partial | P0 |
| E-OBS-004 | dashboard 维度检查 | 不按学生建立行为/风险指标 | NFR-OBS-002 | yes | P0 |

## Browser and platform

| eval_id | 条件 | 期望 | refs | auto | priority |
|---|---|---|---|---:|---:|
| E-WEB-001 | 支持矩阵内桌面浏览器 | 核心流程通过 | NFR-UX-002 | yes | P1 |
| E-WEB-002 | 支持矩阵内移动浏览器/PWA | 快速记录、查询、批准通过 | NFR-UX-001 | partial | P0 |
| E-WEB-003 | 网络切断/恢复 | 状态和数据新鲜度清晰，不重复写 | R-OPS-002 | yes | P0 |
| E-WEB-004 | 前后台切换/会话过期 | 敏感视图遮罩，草稿/认证行为符合设计 | FR-PLT-002; UX spec | partial | P1 |
