# E-ARCH-002 候选规格：架构批准绑定当前源码

状态：candidate oracle contract。E-ARCH-002 在机器目录仍为 `catalogued`、`runner: null`；此处只规定 T-REVAL-012 的隔离合成验证，不是签发仪式、正式 executable-spec 或 `before_feature_task` 通过。

追溯：R-DEV-003、C-038、T-RGOV-006、T-REVAL-012、`architecture-confirmation.md` 与 `.ai/gates/signed-artifact-policy.yaml`。用户已确认 prototype/主仓库方向；security、architecture、operations 的应用外批准仍缺失。

## 输入与信任边界

- 候选制品必须先经已钉住 root 的 registry 与既有 DSSE/policy verifier 验签、角色 quorum、key usage、期限、撤回、target commit/release/definition bundle 检查。仓库内 `architecture-approval.example.yaml` 明确无效。
- 受信部署上下文固定仓库根与目标 commit；验证时必须核对 Git 顶层、HEAD 等于目标 commit，固定来源均已跟踪、整个 checkout 没有暂存/未暂存覆盖或未跟踪文件。请求、Agent、插件或制品自身不得决定待比对文件路径或 digest。当前实验通过隔离根参数注入，仅用于测试。
- 当前摘要清单：`docs/specs/class-os-v1/architecture.md` 原字节；`architecture-decision.md` 中 `## ADR-001` 至 `## ADR-007` 各节按 UTF-8/LF 节文本；`docs/00-项目总览/项目宪章与开发约束.md` 原字节；language、agent、self-host、signature 四份固定 spike evidence JSON 原字节。ADR-008+ 不混入 R1 批准范围。
- ADR-006B 仍未最终接受时必须拒绝；合成正向样本仅把隔离副本的状态设为 `accepted`，不能改变正式 ADR。

## Oracle

1. 正确签名且所有当前摘要逐项一致才可输出 `architecture-binding-valid`，但仍不授权 feature、真实数据或生产写入。
2. 任意一个 architecture、七个 ADR、四份 spike、constraints、definition bundle、commit 或 registry binding 漂移均拒绝；即使制品由测试密钥重新签名也不能绕过当前文件比较。
3. 少/多 ADR 或 spike 键、ADR 标题重复/缺失、ADR-006B 未最终接受、缺文件/错误编码必须 fail closed。
4. 不从 payload 读取路径，也不把验证结果写回 `.ai/gates`；真实批准者和 root/key 管理留在应用外。

后续正式 E-ARCH-002 仍需对准目标 commit 的受信 checkout、有效 root/registry、外部四角色批准、spike evidence 自身的新鲜度以及无请求可替换的部署组合做集成验证。当前候选不覆盖这些生产事实。
