# Golden Outputs

当前状态：`synthetic-provisional`。

这里暂不存放用户业务真值，因为尚未收到并确认脱敏输入输出样例。实现团队可以用合成数据建立结构和不变量测试，但不得把字段顺序、表名、排名口径、报告措辞或版式宣称为最终契约。

## Promotion Process

1. 原始样例进入 `handoff/raw/examples/`；
2. 登记 `source-inventory.md` 并完成脱敏；
3. 规范化到 `handoff/normalized/examples.normalized/`；
4. 更新 `examples.catalog.md`、rulebook 和 output-contract；
5. 用户在 `.ai/confirmation/sample-io-confirmation.md` 明确确认；
6. 复制最小必要 golden，并记录 case/rule/schema version；
7. CI 锁定哈希，变更走规格更新。

## Provisional Golden Shapes

- `grade-metrics.synthetic.md`：成绩计算的结构和不变量；
- `change-proposal.synthetic.md`：高风险写入预览结构；
- 排座的正式 golden 在软约束权重确认后创建。
