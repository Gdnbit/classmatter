# T-RSPK-002 Agent Read/Draft Boundary Spike

状态：read/draft 开发基线；2026-10-07 补运行中事件消费；仅 synthetic evaluation，不是生产 Agent 模块。

该 spike 验证项目自有 `AgentRuntimePort`、Pydantic AI 2.53.0 adapter、确定性 fake、静态 capability filter、Query Gateway/Draft Builder、项目自有实时事件 envelope 与审计最小投影。初始开发基线为2.46.0；本候选已进行同主版本安全修复，详见 [依赖变更](../../docs/DEPENDENCY_REMEDIATION.md)。所有 Tool 仅为只读或未提交草稿；没有 Business Command Gateway、数据库提交、任意 SQL/URL/file/shell 或 Agent approval。

## 运行

```powershell
pwsh ./spikes/agent-read-draft/run.ps1
```

仅在依赖或 corpus 发生有意变化时刷新证据：

```powershell
pwsh ./spikes/agent-read-draft/run.ps1 -RefreshEvidence
```

## 路由对照的证据边界

`corpus/chinese-routing.synthetic.jsonl` 包含 320 条固定模板合成中文表达，覆盖 answer/read/draft/clarify、假设讨论、伪造批准和 prompt injection。`routing_eval.py` 可读取三种候选各自的 JSONL predictions 并计算准确率、wrong route、missed tool 和写意图误判。

本机没有 TypeSafe 或主模型 provider credential，因此当前证据明确把三个语义组标为 `not-run`，不伪造 Jev 或主模型质量、延迟、token 和成本指标。确定性 capability filter 的测试只能证明危险 Tool 不可见，不能证明语义理解。基于“无校准证据不启用”的规则，当前结论为 **R1 默认关闭 Jev**；以后取得合成/研究授权标注集和 provider 凭据后，可在不改变 Runtime port 的情况下补跑。

## AG-UI 结论边界

依赖中固定 `ag-ui-protocol` 1.0.0，并证明项目 port 不导入 AG-UI/Pydantic 类型。R1 前端只依赖 ClassMatter 自有、带 cursor 的最小事件 envelope。Pydantic AI 的 AG-UI adapter 可留作 wire adapter 候选，但当前事件集合很小，尚无证据表明直接采用完整协议能降低复杂度，因此不把 AG-UI 固化为 Kernel 或前端领域契约。

## 运行中事件（2026-10-07）

`run(request)` 仍返回完整 RuntimeResult；`stream(request)` 沿同一实现消费 run/tool/draft/message/terminal 事件，不另写 Agent loop：

```python
from contextlib import aclosing

async with aclosing(runtime.stream(request)) as events:
    async for event in events:
        render(event)  # consumer owns transport/rendering; use no business writes here
```

调用者必须使用 `aclosing` 或在断开时显式 `aclose`；否则 Python async generator 不能保证消费者提前 break 就立即停止 producer。关闭/取消会传播到上游并等待清理；从未迭代的 stream 不启动 Agent。每个 runtime instance 最多一个 active run，重复启动拒绝，不取消原运行；完成后可复用。共享 gateway 的诊断 calls 不是审计来源，每轮独立记录 Tool 调用。

每运行最多 128 事件（含一个 terminal）、32 KiB 单事件、256 KiB 总序列化 envelope 字节，预留 failure 位置；stream queue 最多 129 项（含内部结束标记）。过量输出停止，不静默丢弃中间事件或报成功；终态后不能再发事件，snapshot/consumer payload 与内部缓冲隔离。timeout 必须有限且在 (0,60] 秒；Pydantic 限整次 upstream run，fake 限每个 Tool 等待（最多两个，非总响应 SLA）。这些是隔离 spike 固定上限，生产策略须按 contract/性能门确定。

READ 未获得 QG source refs 不释放答案。当前 `message.delta` 是上游完成后的整段答案，带 source_refs；**不是 token streaming**。首反馈和 Tool 状态已可在运行中取得，但尚无 HTTP/SSE endpoint、真实浏览器 E2E、断线 replay、跨进程 checkpoint 或消息历史存储；不宣称 RV-03 全部关闭。

验证覆盖首次事件早于上游完成、运行中 Tool、显式关闭/等待消费者取消、超时清理、无来源答案拒绝、事件数/字节上限、单实例并发、共享网关审计隔离、组合 read+draft 描述不串用。零生产写、无新增依赖；见[公开工程边界说明](../../docs/ENGINEERING_OVERVIEW.md)。

## 隔离 ASGI transport（2026-10-07）

`transport.create_app` 复用锁定环境已有 Starlette 1.6.0 `StreamingResponse`，提供合成 loopback-only POST `/spike/events`。fixture bearer、固定 Origin/Host/client、合成 workspace 和 server-owned IDs 只验证传输边界，不替代正式 Identity/authorization/session/CSRF。请求不能提交任意 Tool、workspace、run ID 或 timeout；服务端固定 route→read/draft allowlist。

最多 4 个活动 stream；请求总量 16 KiB、文本 8,000 字符、接收 1 秒。输入错误不回显；SSE 带 no-store、nosniff 和禁代理缓冲 header。ASGI 2.3 disconnect、2.4 socket send failure 和任务取消均显式关闭迭代器并等待上游清理。拒绝 Last-Event-ID 和 query，不能自动重放/重启；这是每轮临时流，不是 conversation/history/checkpoint。

ASGI 阶段通过真实 send/receive 握手证明首事件早于上游完成，不使用 TestClient 完成后缓冲冒充实时流；后续 TCP/browser 证据见下节。没有正式 Web 接线、生产身份、代理配置、send-side deadline、跨进程并发限制或部署准入。传输层仅输出整段 grounded answer，不新增 token streaming。见[公开工程边界说明](../../docs/ENGINEERING_OVERVIEW.md)。

### TCP/browser follow-on 验证结果

上述 ASGI 阶段限制现已部分补齐：`browser_fixture.py` + `browser/` 提供**隔离合成**同源测试页，复用 Uvicorn 0.53.0（仅 dev）与 eventsource-parser 4.1.1（MIT；不自研 SSE parser）。每次进程生成临时 capability，不放 URL/日志/证据，不用 CDN；fixture status 只返回合成运行计数/审计 outcome，无业务正文。生产身份/部署、正式 `apps/web`、代理缓冲、send-side deadline、多进程限额、重连/历史仍未完成。

```powershell
# 本目录运行；先安装与验证固定依赖
pwsh ./run.ps1
uv run python browser_fixture.py --port 8766
# 打开输出的 loopback /spike 地址，点击“运行固定验收”；结束后 Ctrl+C
```

`run.ps1` 会先 frozen 安装独立 browser 依赖，执行 Node envelope/UTF-8/限额测试，再执行 Python/临时 TCP server 测试；后者自行停止服务器。`tests/test_live_tcp.py` 不等于浏览器 UI 测试，实际浏览器点击结果另见[公开工程边界说明](../../docs/ENGINEERING_OVERVIEW.md)。Edge 和内置浏览器均观察到 8/8，源于 FunctionModel 合成替身，不是模型质量或完整业务验收。
