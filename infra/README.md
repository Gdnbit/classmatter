# Infrastructure

2026-10-15 当前head0016/22表/riskr1.3，替代下方历史0015“当前”快照；仅term.update白名单与runtime学期name/start/end三列授权。ready精确head并验证三列权限，backup-check仅当前同版本工具/配置/用户的隔离clone。旧0015包不是可直接恢复到0016的升级方案；无N/N-1/跨机/生产证明。用户已有实例未迁移/重启，operator应显式验证升级/前滚或匹配版本快照。

2026-10-15 同机恢复角色检查：原source dump和随机clone复验除内容/表/head外增加固定synthetic3角色critical ACL护栏，compose ready也复用；整表/列/PUBLIC跨域、高权/membership/危险DML/CREATE或audit session_digest泄露均拒绝，内置权限函数限定pg_catalog。应用代码只有只读检查，不GRANT/REVOKE/修用户实例。旧backup-check.v1/DPAPI/root/head/不切流不变；这不是完整权限矩阵、持续监控、异机/JSON/lifecycle恢复或正式发布准入。

2026-10-15 只读排障入口：`backend/local.py support` 复用原doctor，只输出无cookie的两个loopback健康结果及封闭operator版本/OS类别。坏响应/metadata不回显正文/exception；没有日志/配置/DB扫描、用户路径、凭据或自动上传。API不ready时exit1仍可给固定report；不证明服务端build版本、完整生产告警或支持拓扑，详见backend README与operator/support.v1契约。

2026-10-15 当前合成schema为head0015/22表，ready及checkpoint检查必须精确匹配；历史0013/0014增量不代表当前head。0015仅扩固定姓名更正命令白名单与runtime的student.name单列更新，旧checkpoint仍需匹配工具/原runtime，不声称跨版本/跨主机恢复、生产N/N-1或退役完成。部署升级必须由operator显式迁移、构建并重启，本轮只在隔离测试库验证。

2026-10-14：新增受限 Windows 合成 checkpoint 工具，见 [backend/local.py](../backend/local.py) 的 backup / backup-check 和 [说明](../backend/README.md)。复用原DPAPI及 PostgreSQL18工具，受保护文件只在Git忽略的自有runtime/backups；固定22表/head0013、同一导出快照与内容/计数核对，临时clone验证后删除，不切换原服务。不是容器生产拓扑/自动保留/新主机恢复/完整JSON退出/PITR/退役批准；真实数据仍禁止，老师无新增维护字段，operator当前手动演练不能被记成已自动化运维。

> 文档状态（2026-10-13）：已包含隔离合成 CI 的 PGDG 软件源资产；受支持生产部署、备份恢复和发布资产未完成。项目完成度见 [公开工程边界说明](../docs/ENGINEERING_OVERVIEW.md)；本标识不提升批准、测试或任务状态。

放置本地开发与受支持部署的 compose、观测、备份恢复和部署资产。当前没有批准生产拓扑；不得提交真实 secret、真实学生数据或默认公网暴露配置。

`ci/pgdg.sources` 只供 [.github/workflows/synthetic-ci.yml](../.github/workflows/synthetic-ci.yml) 的 Ubuntu 隔离测试安装固定 PostgreSQL 18.6；不是运行时数据库配置或正式部署。Windows 自有开发运行入口在 [backend/local.py](../backend/local.py)，操作说明见 [backend README](../backend/README.md)。不把合成 CI、spike Compose 或本机 DPAPI 凭据当成跨主机生产恢复方案。
