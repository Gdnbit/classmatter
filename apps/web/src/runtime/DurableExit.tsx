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
  return <section className="r1-card"><h2>导出工作记录</h2>
    <p>包含班级记录、任务和聊天，不包含模型密钥。导出文件不能直接用于恢复应用。</p>
    <button disabled={disabled || working || !!pending} onClick={() => void run(async current => {
      const preview = await client.exitPreview(crypto.randomUUID())
      if (current()) { setDownload(""); setPending({ preview, key: crypto.randomUUID(), approval: null, attempted: false }) }
    })}>预览导出</button>
    {download && <p><a href={download} download>下载工作记录（30分钟内有效）</a></p>}
    {pending && <R1Dialog titleId="d1-exit-title" busy={working} onDismiss={() => { if (!working && !pending.attempted) setPending(null) }}>
      <h2 id="d1-exit-title">确认导出工作记录</h2>
      <p>确认后生成下载文件。</p>
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
        if (current()) { setDownload(client.exitDownload(receipt.resource_id)); setPending(null); setNotice("已生成导出文件。") }
      })}>{pending.attempted ? "重试导出" : "确认导出"}</button>
      <button disabled={working} onClick={() => void run(async current => {
        const result = await client.commandState(pending.preview, pending.key)
        if (!current()) return
        if (result.status === "committed" && result.receipt) { setDownload(client.exitDownload(result.receipt.resource_id)); setPending(null) }
        else setNotice("暂时无法确认导出结果，请稍后核对。")
      })}>核对导出结果</button>
      {!pending.attempted && <button disabled={working} onClick={() => setPending(null)}>取消导出预览</button>}
      {notice && <p role="status">{notice}</p>}
    </R1Dialog>}
    {!pending && notice && <p role="status">{notice}</p>}
  </section>
}
