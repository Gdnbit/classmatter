# Adversarial Audit Regression Catalog

本表是 eval 语义目录；Release 1 条目的 `spec_status` 必须逐 ID 投影自 `.ai/gates/release-1-evals.yaml`，该 immutable definition 是 R1 规格成熟度的唯一权威来源。T-REVAL-001 对投影做完全一致性检查；运行是否通过只由独立 run-state 与签名证据决定。

| eval_id | 条件 | 期望 | refs | auto | priority | spec_status |
|---|---|---|---|---:|---:|---|
| E-PRV-005 | 授权/学校许可失效 | 停止非必要处理，触发限制/退役流程 | R-PRV-005; C-040 | partial | P0 | catalogued |
| E-PRV-006 | 有权主体请求查阅/导出 | 验证身份和范围，输出可理解结果与证明 | R-PRV-005; C-040 | partial | P0 | catalogued |
| E-PRV-007 | 更正请求影响派生指标/报告 | 更正事实并使派生物 stale/重算，不抹除证据 | R-PRV-005/R-RET-001 | yes | P0 | catalogued |
| E-PRV-008 | 删除/限制请求 | 按生命周期矩阵执行并列出例外/到期 | R-RET-001/002; C-051 | partial | P0 | catalogued |
| E-PRV-009 | 外部处理器退出 | 撤销凭据、停止调用、验证删除/迁移并保留证明 | R-PRV-006 | partial | P0 | catalogued |
| E-PRV-010 | 去姓名叙事含可识别事件 | 外部投影被阻止/最小化 | R-PRV-006; C-046 | yes | P0 | catalogued |
| E-PRV-011 | D3/D4 自由文本请求外部模型 | 默认拒绝或本地路径，无 silent fallback | R-PRV-006 | yes | P0 | catalogued |
| E-PRV-012 | 供应商训练/保留/地域/分包任一未批准 | provider 不可启用处理 D2+ | R-PRV-006 | yes | P0 | catalogued |
| E-PRV-013 | 扫描 Release 1 Web、API、Tool、路由和依赖 | 不存在录音、音频上传、语音转写或音频持久化 surface | R-VOICE-001; C-047 | yes | P0 | executable-spec |
| E-PRV-014 | 尝试调用或配置任何语音/音频/转写入口 | route/tool/schema 不存在或固定拒绝；不得 silent fallback 到外部服务 | R-VOICE-001/R-PRV-006 | yes | P0 | executable-spec |
| E-AGT-015 | Agent/MCP 枚举或调用 approve | schema/catalog 不存在且拒绝 | R-SAFE-005; C-041 | yes | P0 | executable-spec |
| E-AGT-016 | 跨站请求 approve | CSRF/Origin/session binding 拒绝 | R-SAFE-005; C-042 | yes | P0 | executable-spec |
| E-AGT-017 | confirm 页面被 iframe/clickjacking | 安全头/策略阻止嵌入 | R-SAFE-005 | yes | P0 | executable-spec |
| E-AGT-018 | approval token 换设备/客户端使用 | client/session 不匹配拒绝 | R-SAFE-005; C-042 | yes | P0 | executable-spec |
| E-AGT-019 | X 操作重认证过期 | 拒绝并要求重新认证和预览 | R-SAFE-005 | yes | P0 | executable-spec |
| E-AGT-020 | 双击/后台页/拒绝后重放 approve | 最多消费一次，其余拒绝并审计 | R-SAFE-005 | yes | P0 | executable-spec |
| E-RISK-001 | 单人普通表扬 | 得到配置的静态最低风险 | R-RISK-001; C-043 | yes | P0 | executable-spec |
| E-RISK-002 | 违纪或谈话 D3 字段 | 至少 W2 | R-RISK-001 | yes | P0 | executable-spec |
| E-RISK-003 | 事件含附件或 D4 | R1 拒绝；未来只能升级风险 | R-RISK-001 | yes | P0 | executable-spec |
| E-RISK-004 | 批量普通事件 | affected count 使风险升级 | R-RISK-001 | yes | P0 | executable-spec |
| E-RISK-005 | 任意外发/不可逆删除 | X 且近期重认证 | R-RISK-001/R-SAFE-005 | yes | P0 | executable-spec |
| E-EXIT-001 | Release 1 任意时点退出 | 核心数据、可移植 lifecycle/right/restriction/delete/retention/admission ledger、manifest/checksum 完整 round-trip；已限制/删除数据不复活并产生退役证明 | R-EXIT-001; C-044 | partial | P0 | executable-spec |
| E-AUD-001 | D3 查询时 audit 持久层失败 | fail closed，不返回数据 | R-AUD-001; C-045 | yes | P0 | executable-spec |
| E-AUD-002 | 模型投影时 audit 失败 | 不调用 provider | R-AUD-001 | yes | P0 | executable-spec |
| E-AUD-003 | 敏感导出时 audit 失败 | 不创建/释放导出 | R-AUD-001 | yes | P0 | catalogued |
| E-AUD-004 | 无审计权限或审计查询审计 | 越权拒绝；合法查询产生二级 audit | R-AUD-001 | yes | P0 | catalogued |
| E-LOCAL-001 | 页面刷新/关闭 | D2+ 草稿不在持久存储残留 | R-LOCAL-001; C-048 | partial | P0 | executable-spec |
| E-LOCAL-002 | 登出/会话过期 | 内存草稿清除、下一用户不可见 | R-LOCAL-001 | partial | P0 | executable-spec |
| E-LOCAL-003 | 浏览器存储检查 | localStorage/IndexedDB/Cache 无 D2+ | R-LOCAL-001 | yes | P0 | executable-spec |
| E-LOCAL-004 | 共享浏览器新账号登录 | 看不到前用户表单内容 | R-LOCAL-001 | partial | P0 | executable-spec |
| E-LOCAL-005 | 断网提交失败 | 保留当前页面内存、明确未提交，不新建重复 key | R-LOCAL-001/R-OPS-002 | partial | P0 | catalogued |
| E-LOCAL-006 | 设备丢失威胁复核 | 无持久敏感草稿，服务端会话可撤销 | R-LOCAL-001 | no | P0 | catalogued |
| E-ID-001 | 一个学生多来源编号 | 标识共存并各有 authority/type | R-ID-001; C-049 | yes | P0 | executable-spec |
| E-ID-002 | 编号变更/过期 | 新旧有效期不混淆当前匹配 | R-ID-001 | yes | P0 | executable-spec |
| E-ID-003 | 不同学生编号复用/冲突 | 生成 duplicate/conflict candidate，不合并 | R-ID-001 | yes | P0 | executable-spec |
| E-ID-004 | 用户选择保持分离 | 后续导入不重复强推自动合并且保留决定 | R-ID-001 | yes | P1 | catalogued |
| E-ATT-001 | 同日请假、缺勤、返校和迟到 | 保留关联事实，显示待核对，不计算唯一状态 | R-ATT-001/R-LEAVE-001; C-050 | yes | P0 | executable-spec |
| E-LEAVE-001 | 跨日请假、延长、销假 | 事件链和时间范围可追，不覆盖原事件 | R-LEAVE-001 | yes | P0 | executable-spec |
| E-HWK-001 | 未交后补交再更正 | 保留全部事实/更正来源，不推导态度 | R-HWK-001 | yes | P0 | executable-spec |
| E-RET-001 | 停用学生 | UI 不称删除，历史按权限保留 | R-RET-001/002 | yes | P0 | executable-spec |
| E-RET-002 | 权利/删除请求跨业务、identity/session/recovery、approval/command receipt、outbox、model metadata、admission、telemetry/support、export/audit/backup | 实际 store inventory 无未分类位置；逐位置状态、owner 与例外可验证 | R-RET-001/002; C-051 | partial | P0 | executable-spec |
| E-RET-003 | 备份/退出包仍含已限制或删除数据，或 lifecycle ledger 缺失 | 恢复/导入前重放 restriction/delete tombstone；未结权利请求和 retention exception 保留 | R-RET-001/002/R-EXIT-001 | partial | P0 | catalogued |
| E-RET-004 | legal hold/必要审计/安全证明例外 | 不删除但明确依据、store、字段范围、owner、复核日和到期；无无限期空白例外 | R-RET-002 | partial | P0 | catalogued |
| E-TIME-001 | 旧关系 to==新关系 from | 半开区间无重叠/空档 | R-TIME-001; C-054 | yes | P0 | executable-spec |
| E-TIME-002 | 空结束/未来生效/回溯更正 | 查询与约束一致，变更版本化 | R-TIME-001 | yes | P1 | executable-spec |
| E-REP-009 | 引用记录存在但不支持因果句 | claim finalize 被拒绝/改为推断 | R-REP-003; C-053 | partial | P0 | catalogued |
| E-REP-010 | claim 数字与 source 不一致 | 一致性检查失败 | R-REP-003 | yes | P0 | catalogued |
| E-REP-011 | 一个 claim 混合事实和推断 | 拆分为 claim + inference/suggestion | R-REP-003 | partial | P1 | catalogued |
| E-REP-012 | source version 改变 | claim stale，需重建/复核 | R-REP-003 | yes | P1 | catalogued |
| E-IMP-011 | 导入逐变更 ledger | 每个 aggregate 有 source/before/after | R-IMP-003; C-052 | yes | P0 | catalogued |
| E-IMP-012 | 导入后人工修改再补偿 | 冲突项不自动覆盖，进入 reconcile | R-IMP-003 | yes | P0 | catalogued |
| E-IMP-013 | 部分导入补偿 | 只补偿本 commit 且无后续变更项 | R-IMP-003 | yes | P0 | catalogued |
| E-IMP-014 | 后续实体引用导入对象 | 不破坏引用，转人工处理 | R-IMP-003 | yes | P0 | catalogued |
| E-IMP-015 | 重放补偿 | 幂等，仅一次反向变更 | R-IMP-003/R-SAFE-003 | yes | P0 | catalogued |
| E-OPS-009 | 干净主机安装+doctor | 文档化流程完成且自检全绿 | R-OPS-003; C-056 | partial | P0 | executable-spec |
| E-OPS-010 | 上一支持版本升级/失败回滚 | 数据完整、应用可恢复 | R-OPS-003 | partial | P0 | catalogued |
| E-OPS-011 | 主机丢失重建 | 在批准 RTO/RPO 内恢复并校验 | R-OPS-003 | partial | P0 | executable-spec |
| E-OPS-012 | 磁盘低位/证书临期 | 提前告警和安全退化，不降级明文 | R-OPS-003; C-057 | partial | P0 | catalogued |
| E-OPS-013 | support bundle | 无 PII/secret，含必要版本与错误信息 | R-OPS-003 | yes | P0 | catalogued |
| E-OPS-014 | uninstall/retire | 退出导出、撤销、清除/例外证明完整 | R-OPS-003/R-EXIT-001 | partial | P0 | catalogued |
| E-VALUE-001 | 记录首次建班、40—60 人手工花名册、既有系统核对/重复录入、连续 5 日维护/支持与复用节省；加入通知发现、责任不清、期限、交接/升级、遗漏/逾期、最后时刻私信催办和证据检索样本 | 输出一次性 setup、持续成本、节省、中位/区间和批准摊销周期；分别报告责任发现/澄清耗时、遗漏/逾期率、临时催办、证据检索和主观责任压力。总成本不低于节省、责任风险/错误变差或责任不清事项被静默派给班主任时 stop/change | R-PROD-001; R-VALUE-001; C-055; C-075 | no | P0 | executable-spec |
| E-TASK-001 | Release 1 task lint | 每项 1—3 日、单产物/写模块、有限 eval、独立回退 | R-DEV-005; C-055 | partial | P0 | catalogued |
| E-ADM-001 | synthetic-only 部署接收业务写 | 非合成 workspace 写入固定拒绝并审计 | R-ADM-001; C-058 | yes | P0 | executable-spec |
| E-ADM-002 | 准入 artifact 签名/发布 hash/部署/用户/班级/学期任一不匹配 | fail closed，不创建业务事实 | R-ADM-001 | yes | P0 | executable-spec |
| E-ADM-003 | 准入 artifact 到期或被撤回 | 下一次写立即拒绝；受控退出导出仍可用 | R-ADM-001/R-EXIT-001 | yes | P0 | executable-spec |
| E-ADM-004 | 应用进程尝试签发/延长准入 | 无能力或拒绝，记录安全事件 | R-ADM-001 | yes | P0 | executable-spec |
| E-ADM-005 | synthetic fixture 被误投 real workspace | fixture provenance 校验拒绝或隔离 | R-ADM-001/R-PRV-003 | yes | P0 | executable-spec |
| E-ADM-006 | 填满仓库 example 并用受信测试 key 正确签名，或复制其 fingerprint 到外部 | verifier 仍因 example type/status/fingerprint/artifact_id/仓库来源拒绝；只有唯一 issued artifact 可准入 | R-ADM-001; FR-PLT-006 | yes | P0 | executable-spec |
| E-ADM-007 | 使用合法 setup capability 创建 Student、事实、任务或任意个人数据，或尝试启用业务写 | 固定拒绝；setup 只能预分配空 class/term ID 并产生 allocation receipt；capability 单次消费 | R-ADM-001; FR-PLT-006 | yes | P0 | executable-spec |
| E-ADM-008 | 重放/跨部署使用 setup capability，或 final admission 未绑定 allocation receipt、candidate、shadow/value、pilot-readiness 签名报告 | verifier 校验完整 payload、签名、角色/quorum、release/commit/environment、scope、期限与撤回状态；任一不匹配拒绝且不创建业务数据 | R-ADM-001; FR-PLT-006/NFR-PRV-005 | yes | P0 | executable-spec |
| E-ADM-009 | 在 final admission 前发送未知 command，或通过任一 adapter 以 setup capability 创建 Class/Term/Student/Record/Task；跨 workspace 使用 capability/receipt | BCG 仅接受 `ScopeAllocationCommand` 且只写 workspace-bound ScopeAllocation ledger；unknown type/field、任何业务 aggregate 写和 workspace 不匹配固定拒绝；consume 与 ledger 写原子 | R-ADM-001/R-SAFE-005; FR-PLT-006/FR-AGT-003 | yes | P0 | executable-spec |
| E-GATE-001 | required eval 使用未知 `required_before` 值，或 runner 改变阶段选择器 | schema/mutation gate 固定失败，不产生 authorization | R-DEV-001/002 | yes | P0 | catalogued |
| E-GATE-002 | 删除/缩小 selector；混写 definition/state/evidence；改 canonical 字节向量、NFC collision、role/quorum/key usage/revocation、artifact lifecycle/consume 规则；task machine mapping 相对 source row 缺失/多余；旧 registry generation、同代异 hash、断 previous hash、过期、未排空写入即切换，或重放旧 artifact | canonical hash/signature/vector/mapping/lifecycle 校验失败，authorization 固定 false；不得出现自引用 hash、可复用报告被消费或一次性 setup 未消费；成熟签名方案比较/删减 ADR 缺失不得越过 T-REVAL-019 | R-DEV-001/002 | yes | P0 | catalogued |
| E-AUTH-009 | 空部署首次 owner bootstrap | 只允许一次、短时 bootstrap secret；成功后失效并审计 | R-AUTH-001 | yes | P0 | executable-spec |
| E-AUTH-010 | 已有 owner 时重放 bootstrap | 固定拒绝，不创建第二 owner | R-AUTH-001 | yes | P0 | executable-spec |
| E-AUTH-011 | 请求凭据恢复 | 响应不泄露账号是否存在，token 单次/短时/哈希存储 | R-AUTH-001/R-PRV-001 | yes | P0 | executable-spec |
| E-AUTH-012 | 恢复成功 | 轮换凭据并吊销全部旧会话/恢复 token | R-AUTH-001 | yes | P0 | executable-spec |
| E-AUTH-013 | 恢复 token 过期/重放/篡改 | 固定拒绝并限速/审计 | R-AUTH-001 | yes | P0 | executable-spec |
| E-AUTH-014 | 自托管 owner 丢失凭据且无在线通道 | 经离线双人恢复 runbook 产生短时恢复能力，不直接改业务表 | R-AUTH-001/R-OPS-003 | partial | P0 | catalogued |
| E-AUTH-015 | 未持有恢复码或仅能发起未认证恢复请求 | 响应不枚举 owner，不能取得恢复 token/session | R-AUTH-REC-001; C-059 | yes | P0 | executable-spec |
| E-AUTH-016 | 使用未消费离线恢复码并在同一客户端完成恢复 | 只获得短时受限恢复 session；成功后凭据轮换、全部旧会话/旧码吊销并只显示一次新套件 | R-AUTH-REC-001; FR-PLT-007 | yes | P0 | executable-spec |
| E-AUTH-017 | 恢复码重放、暴力尝试、跨客户端兑换，或扫描日志/支持包 | 固定拒绝/限速；无明文码泄露；安全审计不含码值 | R-AUTH-REC-001; NFR-SEC-004/006 | yes | P0 | executable-spec |
| E-AUTH-018 | REST/controller/worker/测试代码直接写 owner、credential、recovery 或 session store | 架构边界测试失败或运行时拒绝；只有 Identity Security Boundary 可写 | R-AUTH-REC-001/R-DEV-003 | yes | P0 | executable-spec |
| E-AGT-021 | 直接 REST 调用 W2 commit 无 approval receipt | 固定拒绝，无业务写 | R-SAFE-005/R-RISK-001 | yes | P0 | executable-spec |
| E-AGT-022 | 内部 service/test adapter 绕过 Command Gateway | 架构边界测试失败或运行时拒绝 | R-SAFE-005/R-DEV-003 | yes | P0 | executable-spec |
| E-AGT-023 | 客户端伪报较低风险 | 服务端按 canonical payload 升级，W2 receipt 必需 | R-RISK-001 | yes | P0 | executable-spec |
| E-AGT-024 | 已消费 receipt 用于不同 command/资源版本 | 固定拒绝并审计 | R-SAFE-005 | yes | P0 | executable-spec |
| E-AGT-025 | REST/controller/worker/repository/test/future CLI 任一路径绕过 Business Command Gateway；worker 直接写 job-state/attempt/receipt 或业务 store | 架构 scanner/mutation runner 失败或运行时固定拒绝；W1/W2 均有统一分类、风险、幂等、批准与审计证据 | R-SAFE-005/R-DEV-003; FR-AGT-003 | yes | P0 | executable-spec |
