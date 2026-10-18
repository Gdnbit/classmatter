# Release 1 Synthetic Fixtures

本目录全部由 `scripts/generate_synthetic_fixtures.py` 使用固定 seed `20260921` 生成，不含真实人物、联系方式、证件号或生产 secret。

- `canonical-r1.synthetic.json`：Workspace/Class/Term/Student/Identifier/Record/Task/Proposal/Approval/Audit 的最小合成集合；
- `workspace-isolation.synthetic.json`：跨 workspace 同名对象与拒绝预期；
- `student-identifier.synthetic.json`：多来源标识和冲突但不合并；
- `fact-events.synthetic.json`：事实、跟进任务和更正链；
- `proposal-approval.synthetic.json`：W2 proposal 与 session/client/nonce 绑定；
- `audit-failure.synthetic.json`：敏感读 audit 不可用时 fail closed。

禁止手工修改 JSON。更新工厂后运行：

```powershell
python ./scripts/generate_synthetic_fixtures.py generate
pwsh ./scripts/verify.ps1 -Suite fixtures
```

`fixtures` suite 会逐字节核对 tracked 文件并扫描手机号、邮箱、身份证号和常见 secret token 形状。该扫描是最低防线，不替代后续仓库/构建产物 secret 与 PII scanner。
