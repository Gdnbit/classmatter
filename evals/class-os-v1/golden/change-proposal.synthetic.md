# Synthetic Golden: Change Proposal Shape

状态：synthetic-provisional。

```yaml
proposal_id: prop_demo
proposal_hash: deterministic-hash-placeholder
command_type: seat.apply
actor_ref: user_demo
workspace_ref: workspace_demo
expected_versions:
  seating: 4
risk: W2
summary:
  affected_students: 2
changes:
  - resource: student/stu_demo_01/seat
    before: A1
    after: B2
  - resource: student/stu_demo_02/seat
    before: B2
    after: A1
warnings: []
reversible: true
approval:
  required: true
  expires_at: synthetic-time
```

不变量：对象、范围、前后值、风险、版本、可撤销性和批准有效期必须可见；批准绑定 proposal hash。
