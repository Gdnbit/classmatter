import { useEffect, useRef, useState } from "react"
import { ApiError, type Classroom, type Session } from "./api"
import { d1Client, type ExitPreview } from "./durable-conversation"
import { R1Dialog } from "./R1Dialog"

// Human-only v6 evidence exit, not an import, activation or Agent capability.
export function DurableExit({ session, classroom, disabled, onBusyChange, onError }: {
  session: Session; classroom: Classroom; disabled: boolean
  onBusyChange: (busy: boolean) => void; onError: (error: unknown) => void
}) {
  const generation = useRef(0), locked = useRef(false)
  const [working, setWorking] = useState(false), [download, setDownload] = useState("")
  const [notice, setNotice] = useState("")
  const [pending, setPending] = useState<{ preview: ExitPreview; key: string; approval: string | null; attempted: boolean } | null>(null)
  const key = `${session.subject.owner_id}/${session.subject.workspace_id}/${session.csrf_token}/${classroom.class_id}/${classroom.term_id}`
  const client = d1Client(session, classroom)
  useEffect(() => {
    generation.current++; setPending(null); setDownload(""); setNotice(""); setWorking(false); locked.current = false
    return () => { generation.current++; onBusyChange(false) }
  }, [key])
  useEffect(() => { onBusyChange(working || !!pending) }, [working, pending, onBusyChange])
  async function run(action: (current: () => boolean) => Promise<void>) {
    if (locked.current) return
    locked.current = true; setWorking(true); onBusyChange(true)
    const started = generation.current
    try { await action(() => started === generation.current) }
    catch (error) { if (started === generation.current) onError(error instanceof ApiError && error.status === 428
      ? new Error("近期身份验证已过期；本次在写入前被拒绝。未有先前送达未知时可取消预览，重新验证后再预览；已有未知请求须保留原键。") : error) }
    finally { if (started === generation.current) { locked.current = false; setWorking(false) } }
  }
  return <section className="r1-card"><h2>耐久会话退出导出</h2>
    <p>生成当前工作区全部班级、学期的合成 v6 证据包：含核心事实、任务、会话、历史来源及恢复限制，不含密码、登录凭据或模型密钥。需要最近 5 分钟验证的身份。</p>
    <p className="r1-muted">不是数据库备份、恢复准入或可直接激活的跨机实例；旧包不能绕过后续清除或退役限制。恢复仍使用受控流程。</p>
    <button disabled={disabled || working || !!pending} onClick={() => void run(async current => {
      const preview = await client.exitPreview(crypto.randomUUID())
      if (current()) { setDownload(""); setPending({ preview, key: crypto.randomUUID(), approval: null, attempted: false }) }
    })}>生成耐久会话退出预览</button>
    {download && <p><a href={download} download>下载已批准的合成 v6 证据包（30分钟内）</a></p>}
    {pending && <R1Dialog titleId="d1-exit-title" busy={working} onDismiss={() => { if (!working && !pending.attempted) setPending(null) }}>
      <h2 id="d1-exit-title">确认导出合成 v6 证据包</h2>
      <p>风险 X · 由本人批准；不自动发送到外部，不授予恢复或模型运行权限。</p>
      <pre>{JSON.stringify(pending.preview.payload, null, 2)}</pre><p>预览摘要：{pending.preview.payload_hash}</p>
      <button disabled={working} onClick={() => void run(async current => {
        const original = pending
        let approval = original.approval
        if (!approval) {
          approval = await client.approve(original.preview)
          if (!current()) return
          setPending({ ...original, approval, attempted: false })
        }
        if (!current()) return
        setPending({ ...original, approval, attempted: true })
        let receipt
        try { receipt = await client.commit(original.preview, original.key, approval) }
        catch (error) {
          if (current() && !original.attempted && error instanceof ApiError && error.status === 428)
            setPending({ ...original, approval, attempted: false })
          throw error
        }
        if (current()) { setDownload(client.exitDownload(receipt.resource_id)); setPending(null); setNotice("已核对原提交回执；仅生成证据包，不代表恢复验收。") }
      })}>{pending.attempted ? "使用原预览与同键重试导出" : "明确批准并生成证据包"}</button>
      <button disabled={working} onClick={() => void run(async current => {
        const result = await client.commandState(pending.preview, pending.key)
        if (!current()) return
        if (result.status === "committed" && result.receipt) { setDownload(client.exitDownload(result.receipt.resource_id)); setPending(null) }
        else setNotice("未核对到已提交回执；不代表在途请求已撤销，保留原预览与请求键。")
      })}>核对原导出结果</button>
      {!pending.attempted && <button disabled={working} onClick={() => setPending(null)}>取消导出预览</button>}
      {notice && <p role="status">{notice}</p>}
    </R1Dialog>}
    {!pending && notice && <p role="status">{notice}</p>}
  </section>
}
