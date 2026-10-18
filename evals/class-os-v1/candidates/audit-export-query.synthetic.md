# E-AUD-003/004 合成候选规格：导出故障与审计查询

状态：candidate oracle contract；两项在 `.ai/gates/release-1-evals.yaml` 中仍为 `catalogued`、`runner: null`。本文件不构成正式 executable-spec 批准，也不改变 Release Gate。

## 追溯与范围

| Eval | 需求/规则/用例 | 待证性质 |
|---|---|---|
| E-AUD-003 | FR-EXP-003、NFR-SEC-006、NFR-PRV-003、R-AUD-001、C-033/C-045 | D2/D3 学生敏感导出在耐久审计故障下不产生可用产物、不释放字节/下载能力 |
| E-AUD-004 | NFR-SEC-006、NFR-PRV-003、R-AUTH-001/R-AUD-001、C-033/C-045 | 审计查询只允许有明确 scope/action 权限的主体；合法查询的读取本身有先于响应的独立耐久审计回执 |

## E-AUD-003：敏感导出审计故障

- Fixture：组合 `audit-failure.synthetic.json` 与 `workspace-isolation.synthetic.json`，构造固定合成 workspace/学生、D2 与 D3 双 canary 的导出正文、规范化字节数和 SHA-256；无真实学生数据。故障注入只作用于耐久审计持久层。
- 入口：受控导出 API、worker 生成/发布路径、下载/释放路径；可见路由和实际注册 handler 清单必须精确闭包，不能靠测试替身自报。其他已注册入口也纳入矩阵。
- 序列：每个注册入口先在独立合成前置状态下做正常 audit 可用的正向对照，证明其受审计路径可达；再分别在导出登记前、产物发布前和下载释放前注入 audit 不可用；每种故障后等待 worker/清理完成，再读取真实对象存储与发布索引。正向对照必须隔离清理，不污染故障计数。
- Oracle：正向对照的产物对象与下载 egress 必须与 fixture 正文摘要、字节数相同，审计回执绑定 request/export ID 与正文摘要，独立观察的审计提交严格先于产物发布、链接激活和下载释放。故障得到固定安全错误；响应/日志/trace 无导出正文或 token；独立存储/索引/egress 观察均为零，产物与下载摘要为空，清理后不存在 canary、对象或链接。API/worker 的正常业务写必须经过 BCG，下载只读，所有入口均无直接 repository 写。登记阶段故障不写；发布/释放阶段可保留一条无业务正文的失败 job/attempt 元数据，且须经 BCG；下载入口不写。故障本身只留无业务内容的最低安全信号，正常路径信号同样不得含业务内容。
- 负例：提前落盘产物、先发布链接再审计、下载放行、清理失败、日志泄露、worker 绕过均失败。
- 清理：撤销合成链接、清除隔离对象和 job，复核零可用产物。生产 runner 必须独立观测对象存储、索引、下载 egress、worker 和 audit receipt。

## E-AUD-004：审计查询二级审计

- Fixture：两个合成 workspace 均有审计事件。按 case 隔离同一 owner/工作区的单条 grant/session：无 grant、跨 workspace、grant 过期/撤销、session 过期/撤销、错误 action、错误 grant ID（另有有效 grant）、session 主体错配、grant 主体错配、未知 session ID、有效。另有非 owner 但获有效 grant 的正向对照。测试变体仅用于组织请求，不传入被测查询业务入口；入口只能基于 actor/session/action/workspace/grant 与受信时钟判断。
- 入口：审计查询 UI API、REST 和可注册的其他 Query Gateway 入口；可见路由与受信运行时 handler 清单必须精确闭包。
- Oracle：每个入口执行上述十四类隔离请求。拒绝请求仅得到固定错误，不暴露目标存在性或内容，零 provider/业务写；owner 与非 owner 的有效 grantee 均须先取得耐久 `audit.query` 回执再释放最小投影。回执绑定 request ID、查询 scope hash、actor/workspace、时间和结果数，独立审计存储与响应 egress 观测必须证明提交序号严格先于释放序号；不含被查询审计内容，也不触发无限自审计递归。审计故障时合法查询 fail closed，不返回审计正文。
- 负例：仅靠 UI 隐藏、使用目标 workspace 自报授权、查询成功但无二级 receipt、先返回后审计、审计故障仍返回、二级审计携带正文均失败。
- 清理：合法二级审计 receipt 必须先耐久，再由隔离测试 namespace 整体销毁；销毁后独立确认 namespace、合成事件、查询回执、缓存投影均为零。真实实现的授权、审计回执与响应顺序由受信 adapter 独立观测。

## 待确认项

- 导出 job 的非敏感失败元数据保留期、三阶段故障的真实对象生命周期和安全错误码需在正式 export schema/worker 设计时冻结。
- 审计查询的 R1 最小授权角色、查询字段投影和耐久回执结构需由 identity/audit 设计核准；当前合成 oracle 不给普通班主任新增审计查询权限。
- 上述不确定性阻止 machine maturity 或 implemented-green 升级；合成 runner 只检验候选边界及已知绕过。
