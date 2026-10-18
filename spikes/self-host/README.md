# T-RSPK-003 Self-host and Recovery Spike

状态：进行中；仅使用 synthetic data。`compose.yaml` 是候选拓扑，不是生产部署清单。

## Static validation

```powershell
pwsh ./spikes/self-host/run.ps1
$env:CLASS_OS_POSTGRES_PASSWORD = 'synthetic-config-validation-only'
docker compose -f ./spikes/self-host/compose.yaml config --quiet
Remove-Item Env:CLASS_OS_POSTGRES_PASSWORD
```

## Live portable PostgreSQL drill

Docker Desktop 4.77.0 在本机因遗留 `dockerInference` socket reparse point（Windows error 1920）启动失败；没有执行 factory reset，也没有删除 Docker 镜像/卷。为了区分宿主工具故障与架构可行性，本次使用 PostgreSQL 官方 Windows 下载页所链接的 EDB 18.6 x64 portable binaries，在 `.local-runtime/` 隔离目录执行真实演练：

```powershell
pwsh ./spikes/self-host/run.ps1 -Live -WriteEvidence
```

归档来源：`https://sbp.enterprisedb.com/getfile.jsp?fileid=1260566`；SHA-256 `1df55002afe95b945d934c078b13e82c1603fa546731e511d068aa983b4ead28`。PostgreSQL Windows binary 无法在本机的中文仓库路径下可靠初始化 cluster，因此解压后的二进制和可变数据均使用仓库同级 ASCII-only `class-os-local-runtime/`；下载归档仍位于 Git 忽略的 `.local-runtime/`。脚本会验证边界，结束时只清理 `class-os-local-runtime/self-host-spike/` 内的临时 cluster/backup/log；不会触及共享数据库。

演练包括 init/start、schema/合成 seed、重启持久性、`pg_dump -Fc`、数据库完全停止时 fail closed、第二个独立 cluster 的 `pg_restore` 与逐字节 JSON 投影相等。它不包含 API/Web/object store/TLS/auth/并发负载，因此资源数和时间不是生产容量或 RTO 承诺。
