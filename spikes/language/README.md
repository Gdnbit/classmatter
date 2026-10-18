# T-RSPK-001 Language Boundary Spike

状态：`development-accepted evidence`；spike 可删除，不能作为生产模块直接引用。

## 问题

比较两种后端边界：

1. React/TypeScript Web + Python 3.13/FastAPI 模块化单体；
2. React/TypeScript Web + Node 22/Fastify 单语言后端。

两端读取同一固定 seed fixture，实现相同的 `POST /v1/attention/list` 合成只读契约、严格字段校验、workspace not-found-safe 和三个 Attention bucket。没有数据库、认证、审计 store、模型或并发压测，因此结果只能用于边界选择，不是容量承诺。

## 固定候选

| 候选 | 直接依赖 | 锁定方式 |
|---|---|---|
| Python | FastAPI 0.141.1、Uvicorn 0.53.0、HTTPX 0.28.1；Python 3.13 | `python/pyproject.toml` + `python/uv.lock` |
| TypeScript | Fastify 5.12.5、Zod 4.6.5；Node 22 | `typescript/package.json` + `typescript/pnpm-lock.yaml` |

版本来自 2026-09-21 的 PyPI/npm registry 现场查询，并由 lockfile 固定。Pydantic AI 不在本任务内安装；其 adapter 属于 T-RSPK-002。

## 复现

```powershell
pwsh ./spikes/language/run.ps1
```

不重采 benchmark，只验证双方契约：

```powershell
pwsh ./spikes/language/run.ps1 -SkipBenchmark
```

## 同机结果

证据文件：`evidence/language-spike.latest.json`。观测主机为 Windows 11、Python 3.13.12、Node 22.20.0；每个候选 5 次冷启动、300 次串行 loopback 请求。

| 指标 | Python/FastAPI | TypeScript/Fastify |
|---|---:|---:|
| 响应 contract hash | `ee7277…21475` | 相同 |
| 冷启动中位数 | 837.832 ms | 569.689 ms |
| 进程树 RSS 中位数 | 51.246 MiB | 60.266 MiB |
| 请求 p50 | 14.697 ms | 14.600 ms |
| 请求 p95 | 24.932 ms | 16.544 ms |
| Spike source LOC（含测试） | 101 | 116 |
| 直接依赖 | 3 | 2 |
| lock 中依赖 | 24 | 50 |

Fastify 在本机冷启动和 p95 更好；Python RSS、源码量和 transitive dependency 数更小。两者都远低于 R1 交互预算，且此 benchmark 未包含 PostgreSQL、auth/audit 或 Agent，因此不能用这些毫秒差异决定产品效果。

## 架构解释与决定

接受 **TypeScript Web + Python backend**：

- 已选 Pydantic AI v2 的首个 AgentRuntimePort adapter 为 Python；采用 Node 后端要么更换 runtime，要么额外运行 Python Agent 进程，反而保留双语言并增加网络/部署边界；
- 文档解析、数据处理与未来 OCR/RAG 候选主要有 Python SDK，但继续通过 port 隔离；
- 前后端用版本化 OpenAPI/JSON Schema/stream event contract 隔离，避免手写重复类型；
- 当前吞吐极低，Fastify 的冷启动/p95 优势不足以抵消 Harness 与数据工具链切换成本；
- 后端仍是一个 Python 模块化单体，不因语言分离拆成微服务。

初始实现基线接受 Python 3.13、FastAPI 0.141.1、Pydantic 2.13.5、Uvicorn 0.53.0，必须使用 lockfile、adapter contract 和升级回归。若 T-RSPK-002 证明 Pydantic AI adapter 不可接受，可回退禁用 Agent或重新评估全 TypeScript/OpenAI Agents SDK；不得维持一个没有证据价值的 Python sidecar。

## 已知问题

- FastAPI 0.141.1 的 TestClient 依赖链在本机产生 HTTPX/AnyIO deprecation warning；不影响本次契约结果，但生产 test harness 应改用无弃用路径或在升级时解决，不能屏蔽警告假装不存在。
- Docker Desktop daemon 当前未运行；容器资源和恢复不是本任务证据，留给 T-RSPK-003。
- benchmark 仅是单机串行 loopback；不外推为生产 RPS、RTO 或硬件下限。
