# Synthetic Golden: Grade Metrics Shape

状态：synthetic-provisional；只固定结构和确定性，不固定学校口径。

```yaml
case_id: C-016
rule_version: synthetic-v1
student_ref: stu_demo_01
comparisons:
  - subject: mathematics
    from_exam: exam_demo_01
    to_exam: exam_demo_02
    from_score: 80
    to_score: 88
    delta_raw: 8
    sample_sufficient_for_persistent_trend: false
evidence:
  - score_demo_01@v1
  - score_demo_02@v1
warnings:
  - persistent trend requires more observations
```

不变量：数值由规则函数产生；证据可追；样本不足时不输出“持续进步”。
