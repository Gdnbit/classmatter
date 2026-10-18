# T-REVAL-019 Signature Envelope Reduction Spike

状态：accepted for synthetic development；生产 authorization 仍固定为 `false`。

## 决策

删除候选 `CLASS-OS-SIGNATURE-V1` 自定义 framing。使用维护中的 `in-toto 3.1.0` / `securesystemslib 1.5.1` DSSE v1 envelope，`cryptography 50.0.1` Ed25519，以及 `rfc8785 0.1.4` canonical JSON。DSSE 先对原始 payload bytes 和 `payloadType` 验签，随后才严格解析 JSON、重现 JCS bytes 并执行 ClassMatter policy。

DSSE 只提供完整性和来源证明。角色、signer identity、key usage、有效期、撤回、全角色 quorum、registry generation/hash、artifact lifecycle 和 target commit 都是应用 policy；`keyid` 仅是未认证 lookup hint。相同 public key 或 signer 不得跨角色重复计数。

## 组件削减

| 候选 | 结论 | 原因 |
|---|---|---|
| 自定义 ClassMatter framing | 删除 | 标准 DSSE PAE 已解决 type/payload 无歧义绑定，自研字节协议只增加审计面 |
| JWS | 不采用 | 选项和算法协商面更大，当前不需要 Web token 生态 |
| Sigstore/GitHub Attestations | CI provenance 复用 | 适合构建/证据来源；不表达产品、隐私、试点范围或运行时授权 |
| 在线 key registry / signing service | 不引入 | R1 只需受保护的版本化 registry/root-pin 文件和本地 verifier |
| 每类 artifact 独立服务 | 不引入 | 一个 versioned payload family + schema/policy registry 足够 |
| PostgreSQL consumption ledger | 隔离合成事务已证明，生产接线未证明 | reusable/renewable artifact 永不“消费”；setup 与 scope allocation 的五表事务见下文，仍须 BCG integration test |

候选生产形态因此只需要：应用内 verifier library、应用外只读 registry/root pin，以及 one-time setup 的 PostgreSQL 唯一约束事务。当前 Spike 已额外实现一个 `classos-artifact://<store>/<filename>` 扁平 rooted local-store adapter：固定 scheme/authority、拒绝 traversal/symlink/reparse、限制单件大小、严格解析 UTF-8/duplicate-key envelope，以 opened-handle `fstat` 对照受控路径身份，然后复用同一 DSSE/policy verifier 返回 `VerifiedArtifactReference`。Windows 上用 `CreateFileW(FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS)` 打开原 candidate、查询同一句柄的 `FileAttributeTagInfo` 并核对最终句柄路径；真实 junction 与最终组件检查后替换的 synthetic mutation 均拒绝。这只证明受 ACL 保护、不可被非授权主体修改的本地 Windows 扁平 artifact root 的开发合同，不证明 UNC/SMB、任意文件系统驱动或生产 root/父目录 ACL 与轮换。identity-ledger 同时提供线程安全内存 fake 和 `PostgresIdentityLedger` adapter；后者以 artifact ID 主键与 nonce 唯一约束实现全局冲突仲裁。它不等同于 one-time setup consumption 或 workspace allocation 事务。GitHub/Sigstore 不进入运行时可用性路径。

## 证据边界

78 个通过、1 个按宿主 symlink 权限条件跳过的 synthetic/static tests 复现 DSSE PAE、RFC 8032 test 1、RFC 8785 canonicalization，并覆盖错误/inactive root、registry quorum/rotation、key status、篡改、NFC collision、self-reference、strict per-type schema、可信 context、嵌套 receipt/report 绑定、receipt owner/class/term scope、closed module set、reference type/digest/policy-role quorum、candidate/pilot gate identity 与 distinctness、重复 principal、usage、key/artifact revocation、expiry、registry rollback/chain、reference cycle、scope setup 约束、setup/admission shadow `go`、receipt 禁止业务内容、mutable state hash，以及 lifecycle fake 的幂等/冲突。concrete resolver 测试覆盖完整 scope-setup→两类 release-level gate + workspace-level shadow 成功链、受控 URI、路径穿越、大小/UTF-8/duplicate JSON、digest/signature/type、opened-handle identity、递归 cycle/depth/node、并发 session 以及 artifact-id/nonce collision。generic 引用闭包要求父制品签名绑定有序 ID/type/digest 与 catalog ID/URI/digest；catalog 经 DSSE 验证后只提供 ID→URI，目标仍独立验签。公共 admission 缺少完整闭包端口就拒绝，测试覆盖缺失/篡改/替换目录、同一 issued ID 的错误类型、错误摘要、撤销/过期和并发。另有 live PostgreSQL 18.6 drill 证明 12 路并发幂等、同 ID/异内容和同 nonce/异 ID 冲突、无半写、正常重启与 immediate-stop 后逐行恢复、错误旧 schema/trigger/rule/UNLOGGED/弱化 CHECK/deferrable/unvalidated constraint 拒绝、持锁超时与停机 fail closed；证据绑定 adapter、drill、测试、migration 和 portable runtime helper，并在 owned run directory 清理后原子写入。测试里的 Ed25519 seed 是公开/合成 test material，绝不是 production secret。

该 spike 不签发真实 artifact、不生成生产 root、不批准 real data，也不把“验签成功”升级为 release authorization。正式签发/撤回仪式仍属于 `T-RGOV-005`。T-REVAL-020 follow-on 已把 reference-verifier port 接到受控本地 artifact store、digest 和既有 DSSE/policy verifier；父 artifact 仍只消费包含 canonical payload、type、lifecycle、digest、registry 和 roles 的 `VerifiedArtifactReference`。generic closure 的目录是签名 locator，不提供目标类型、摘要或授权；它的引用由父 payload 钉住，端口只在受信应用组合中注入，不能由请求或插件替换。gate report 明确定义为 release/environment 级（不伪造 workspace 字段），candidate 与 pilot 槽位分别绑定 `before_release_candidate` / `before_pilot_readiness` 且不得复用同一 report。PostgreSQL identity ledger 已证明 artifact ID/nonce 的 durable uniqueness；Windows 扁平本地 artifact root 的 synthetic native final-component no-follow 已证明。新增的 `scope_allocation.py` 隔离合成演练证明 setup consumption、allocation、ledger、audit、receipt payload 五表在一个 PostgreSQL 事务中提交或回滚；精确 schema contract、受限 writer、幂等/冲突、并发、篡改重试拒绝、重启和停库行为均有测试。`TrustedAllocationContext` 仍是测试注入的受信端口值，`VerifiedArtifactReference`/registry 也由 fixture 构造；它们没有证明生产 BCG 主体认证、DSSE 实际解析接线、签名回执或 adapter 旁路隔离。owner IDs 在 consumption/allocation/receipt 中属于最小身份范围元数据，不是学生业务事实；不得笼统宣称五表“无个人数据”。生产 root/父目录 ACL、轮换与部署自检仍待证明。

## 运行

```powershell
pwsh ./spikes/signature-envelope/run.ps1
```

显式重跑隔离的 live PostgreSQL identity-ledger drill：

```powershell
uv run --project ./spikes/signature-envelope python ./spikes/signature-envelope/postgres_ledger_drill.py `
  --pg-root <local-path> `
  --runtime-root <local-path>
```

显式重跑隔离的 scope-allocation 五表事务演练（只用合成数据）：

```powershell
uv run --project ./spikes/signature-envelope python ./spikes/signature-envelope/scope_allocation_drill.py `
  --pg-root <local-path> `
  --runtime-root <local-path>
```

仅在评审迁移结构发生有意变化时加 `--refresh-schema-contract`；通常运行不得刷新精确 schema 基线。

只有在有意升级定义或锁定依赖时刷新证据：

```powershell
pwsh ./spikes/signature-envelope/run.ps1 -RefreshEvidence
```

## E-ARCH-002 当前源码绑定候选

`architecture_binding.py` 在现有 DSSE/registry/policy 验证后，逐项比对当前 architecture、ADR-001—007、四份 spike evidence 和约束文件的摘要。它要求受信 checkout 的 Git HEAD 与制品 target commit 完全相同、固定来源均已跟踪且整个工作树无覆盖或未跟踪文件；ADR-006B 未最终 `accepted` 时拒绝。合成签名与变异测试见 `tests/test_architecture_binding.py` 和 [候选规格](../../evals/class-os-v1/candidates/architecture-approval-binding.synthetic.md)。此组合尚未接入 machine gate，未签发真实 architecture approval，也不能把 E-ARCH-002 或 `before_feature_task` 宣称为 green；当前正式 ADR-006B 仍未最终批准。

## 来源

- [DSSE specification](https://github.com/secure-systems-lab/dsse)
- [in-toto DSSE Envelope](https://in-toto.readthedocs.io/en/latest/model.html#dsse-envelope)
- [RFC 8032](https://www.rfc-editor.org/rfc/rfc8032.html#section-7.1)
- [RFC 8785](https://www.rfc-editor.org/rfc/rfc8785.html)
- [GitHub Artifact Attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations)
