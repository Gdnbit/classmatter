import { useEffect, useRef, useState } from "react"
import { ApiError, type Session, type Classroom } from "./api"
import { d1Client, type History, type Listing, type Mode, type Preview, type Turn } from "./durable-conversation"
import { createQueryRefresh } from "./query-refresh"

const active = (turn?: Turn) => !!turn && ["queued", "running", "cancel_requested"].includes(turn.run.state)
const stateText = (turn?: Turn) => turn ? ({ queued: "输入已保存，尚未启动模型", running: "运行中，尚无已保存结果",
  cancel_requested: "已请求停止，尚不能认定取消成功", completed: "会话输出已保存 · 无业务写入",
  failed: "运行失败，不自动重跑", cancelled: "已取消，不自动重跑", interrupted: "运行中断，不自动重跑",
  unknown: "结果未知，不能据此认定模型未执行或未计费" }[turn.run.state]) : ""

type Props = {
  enabled: boolean; session: Session | null; classroom: Classroom | null; threadId: string
  readable: boolean; canWrite: boolean
  onSelect: (id: string) => void; onBusyChange: (value: boolean) => void
  onDraftChange: (value: boolean) => void; onError: (error: unknown) => void
}
export function useDurableConversation(props: Props) {
  const latest = useRef(props); latest.current = props
  const epoch = useRef(0), request = useRef<AbortController | null>(null), stream = useRef<AbortController | null>(null)
  const connectivity = useRef(0)
  const operation = useRef<symbol | null>(null)
  const running = useRef<{ threadId: string; requestId: string } | null>(null)
  const [history, setHistory] = useState<History | null>(null), [listing, setListing] = useState<Listing | null>(null)
  const [text, setText] = useState(""), [mode, setMode] = useState<Mode>("read"), [student, setStudent] = useState("")
  const [status, setStatus] = useState(""), [working, setWorking] = useState(false), [fresh, setFresh] = useState(false)
  const [inputReady, setInputReady] = useState(false)
  const [pending, setPending] = useState<{ preview: Preview; key: string; approval: string | null; attempted: boolean } | null>(null)
  const [title, setTitle] = useState("")
  const key = props.enabled && props.session && props.classroom
    ? `${props.session.subject.owner_id}/${props.session.subject.workspace_id}/${props.session.csrf_token}/${props.classroom.class_id}/${props.classroom.term_id}/${props.threadId}` : ""
  const api = () => {
    const p = latest.current
    if (!p.enabled || !p.session || !p.classroom) throw new Error("请先确认当前班级与身份。")
    return d1Client(p.session, p.classroom)
  }
  const report = (error: unknown) => {
    if (error instanceof ApiError && error.status === 428)
      error = new Error("近期身份验证已过期；本次在写入前被拒绝。未有先前送达未知时可取消预览，到设置重新验证身份再预览；已有未知请求须保留原键。")
    setStatus(error instanceof Error ? error.message : "未完成，请按原请求核对。")
    latest.current.onError(error)
  }
  useEffect(() => { latest.current.onBusyChange(working || !!pending) }, [working, pending])
  useEffect(() => { latest.current.onDraftChange(!!text.trim()) }, [text])
  useEffect(() => {
    const generation = ++epoch.current, connection = connectivity.current
    request.current?.abort(); stream.current?.abort(); running.current = null
    operation.current = null
    setHistory(null); setListing(null); setPending(null); setWorking(false); setFresh(false); setInputReady(false); setStatus(""); setTitle("")
    setText(""); setStudent("")
    if (!key) return
    const controller = new AbortController(); request.current = controller
    const client = api(), selected = latest.current.threadId
    Promise.all([client.list(controller.signal), selected ? client.history(selected, controller.signal) : Promise.resolve(null)])
      .then(([list, saved]) => {
        if (generation !== epoch.current || connection !== connectivity.current || !navigator.onLine || controller.signal.aborted) return
        setListing(list); setHistory(saved); setTitle(saved?.history.title || ""); setFresh(true); setInputReady(true)
        if (saved) { setStudent(saved.student_id || ""); setStatus(stateText(saved.turns.at(-1))) }
      }).catch(error => { if (generation === epoch.current && !controller.signal.aborted) report(error) })
    return () => { epoch.current++; controller.abort(); stream.current?.abort(); latest.current.onBusyChange(false); latest.current.onDraftChange(false) }
  }, [key])

  async function refresh(threadId = latest.current.threadId) {
    const generation = epoch.current, connection = connectivity.current, client = api()
    request.current?.abort()
    const controller = new AbortController(); request.current = controller; setFresh(false)
    try {
      const [list, saved] = await Promise.all([client.list(controller.signal), threadId ? client.history(threadId, controller.signal) : Promise.resolve(null)])
      if (generation !== epoch.current || connection !== connectivity.current || !navigator.onLine || controller.signal.aborted) return null
      setListing(list); setHistory(saved); setTitle(saved?.history.title || ""); setFresh(true); setInputReady(true)
      if (saved) setStatus(stateText(saved.turns.at(-1)))
      return saved
    } catch (error) {
      if (generation !== epoch.current || controller.signal.aborted) return null
      throw error
    }
  }
  const refreshRef = useRef(refresh); refreshRef.current = refresh
  const refreshIdle = useRef(false)
  refreshIdle.current = !working && !pending && title === (history?.history.title || "")
  const foreground = useRef<ReturnType<typeof createQueryRefresh> | null>(null)
  useEffect(() => {
    if (!key) return
    const controller = createQueryRefresh({
      read: async () => { await refreshRef.current() },
      invalidate: () => {
        connectivity.current++; request.current?.abort(); setFresh(false)
        setStatus("离线：当前可能是上次快照，恢复连接后重新核对。")
      },
      fail: report,
      available: () => navigator.onLine && document.visibilityState === "visible",
      idle: () => refreshIdle.current,
      now: () => performance.now(),
      schedule: (callback, delay) => window.setTimeout(callback, delay),
      cancel: timer => window.clearTimeout(timer as number),
    })
    foreground.current = controller
    const offline = () => controller.offline()
    const reload = () => controller.request()
    const visibility = () => document.visibilityState === "visible" ? controller.request() : controller.resume()
    window.addEventListener("offline", offline); window.addEventListener("online", reload); window.addEventListener("focus", reload)
    document.addEventListener("visibilitychange", visibility)
    return () => {
      controller.dispose(); if (foreground.current === controller) foreground.current = null
      window.removeEventListener("offline", offline); window.removeEventListener("online", reload); window.removeEventListener("focus", reload)
      document.removeEventListener("visibilitychange", visibility)
    }
  }, [key])
  useEffect(() => { foreground.current?.resume() })

  async function operate(action: (current: () => boolean) => Promise<void>) {
    if (operation.current) return
    const token = Symbol(); operation.current = token
    const generation = epoch.current
    setWorking(true); latest.current.onBusyChange(true)
    try { await action(() => generation === epoch.current) } catch (error) { if (generation === epoch.current) report(error) }
    finally { if (operation.current === token) operation.current = null; if (generation === epoch.current) setWorking(false) }
  }
  async function send(saved?: Turn) {
    const p = latest.current
    if (working || pending || !fresh || !navigator.onLine || !p.readable || !p.canWrite || !p.classroom || (!saved && (!text.trim() || active(history?.turns.at(-1))))) return
    const client = api(), generation = epoch.current, input = text.trim(), selected = p.threadId
    let threadId = selected
    await operate(async () => {
      const controller = new AbortController(); stream.current = controller
      const requestId = saved?.client_request_id || crypto.randomUUID()
      let target: typeof running.current = null
      try {
        if (!threadId) {
          threadId = crypto.randomUUID()
          await client.create(threadId, crypto.randomUUID(), mode === "read" ? student || null : null, controller.signal)
        }
        if (generation !== epoch.current || controller.signal.aborted) return
        target = { threadId, requestId }; running.current = target
        if (!saved) {
          const queued = await client.enqueue(threadId, requestId, input, mode, controller.signal)
          const state = await client.status(threadId, requestId, controller.signal)
          if (queued.status !== "committed" || !queued.receipt || queued.receipt.resource_id !== state.run_id) throw new Error("输入保存结果未知，请按原请求核对，不要重复发送。")
          if (generation !== epoch.current) return
          setText(""); setStatus("输入已保存，正在启动本次运行…")
          await refresh(threadId)
        }
        if (generation !== epoch.current || controller.signal.aborted || !navigator.onLine) return
        await client.start(threadId, requestId, controller.signal, kind => {
          if (generation === epoch.current) setStatus(kind.startsWith("tool.") ? "正在通过受控工具处理…" : "正在运行；以数据库核对结果为准…")
        })
      } catch (error) {
        if (generation === epoch.current) setStatus("运行或传输未完成，正在只读核对原请求；不会自动重跑。")
        if (!threadId) throw error
      } finally {
        if (stream.current === controller) stream.current = null
        if (running.current === target) running.current = null
        if (generation === epoch.current && threadId) {
          if (!selected) p.onSelect(threadId)
          const restored = await refresh(threadId)
          if (restored?.turns.some(turn => turn.client_request_id === requestId)) setText("")
        }
      }
    })
  }
  async function stop() {
    const controller = stream.current
    const target = running.current || (history && history.turns.at(-1) ? {
      threadId: history.history.thread_id, requestId: history.turns.at(-1)!.client_request_id } : null)
    if (!target) { controller?.abort(); setStatus("已停止等待；创建/保存结果仍需核对，不自动重跑。"); return }
    const generation = epoch.current, client = api()
    try {
      const current = await client.status(target.threadId, target.requestId)
      if (generation !== epoch.current) return
      if (["queued", "running"].includes(current.state)) await client.cancel(target.threadId, current)
      if (generation === epoch.current) setStatus("已请求停止，尚不能认定取消成功。")
    } catch (error) { if (generation === epoch.current) report(error) }
    finally { controller?.abort(); if (generation === epoch.current) void refresh(target.threadId).catch(report) }
  }
  async function control(action: "clear" | "archive") {
    if (!history || working || pending || !fresh || !latest.current.canWrite) return
    await operate(async current => {
      const proposal = await api().preview(history.history.thread_id, history.history.version, action)
      if (!current()) return
      setPending({ preview: proposal, key: crypto.randomUUID(), approval: null, attempted: false })
    })
  }
  async function commitControl() {
    if (!pending || working) return
    const current = pending, client = api(), generation = epoch.current
    await operate(async () => {
      let approval = current.approval
      if (current.preview.risk === "X" && !approval) {
        approval = await client.approve(current.preview)
        if (generation !== epoch.current) return
        setPending({ ...current, approval, attempted: false })
      }
      if (generation !== epoch.current) return
      setPending({ ...current, approval, attempted: true })
      try { await client.commit(current.preview, current.key, approval) }
      catch (error) {
        // Only the D1 pre-write recent-auth status permits cancellation.
        // Generic409 may follow durable file-first publication, not rollback.
        if (generation === epoch.current && !current.attempted && error instanceof ApiError && error.status === 428)
          setPending({ ...current, approval, attempted: false })
        throw error
      }
      if (generation !== epoch.current) return
      setPending(null); await refresh()
    })
  }
  return { history, listing, text, setText, mode, setMode, student, setStudent, title, setTitle, status, working, fresh, inputReady, pending,
    blocked: working || !!pending, active: active(history?.turns.at(-1)), isStreaming: !!stream.current,
    send: () => send(), startSaved: (turn: Turn) => send(turn), stop,
    refresh: () => operate(async () => { await refresh() }),
    select: (id: string) => { if (!working && !pending && !text.trim()) latest.current.onSelect(id) },
    moreThreads: () => operate(async current => {
      if (!listing?.next_offset) return
      const next = await api().list(undefined, { snapshot: listing.snapshot, offset: listing.next_offset })
      if (!current()) return
      if (next.snapshot !== listing.snapshot) throw new Error("会话列表已变化，请重新读取。")
      setListing({ ...next, data: [...listing.data, ...next.data] })
    }),
    moreHistory: () => operate(async current => {
      if (!history?.next_before) return
      const older = await api().history(history.history.thread_id, undefined, { version: history.history.version, before: history.next_before })
      if (!current()) return
      if (older.history.version !== history.history.version || older.student_id !== history.student_id) throw new Error("会话版本已变化，请重新读取。")
      setHistory({ ...history, next_before: older.next_before,
        history: { ...history.history, truncated: older.history.truncated, messages: [...older.history.messages, ...history.history.messages] },
        turns: [...older.turns, ...history.turns], results: [...older.results, ...history.results],
        message_attributions: [...older.message_attributions, ...history.message_attributions] })
    }),
    rename: () => operate(async current => {
      if (!history || pending || !latest.current.canWrite) return
      await api().rename(history.history.thread_id, crypto.randomUUID(), history.history.version, title.trim()); if (current()) await refresh()
    }),
    reconcile: () => operate(async current => {
      const turn = history?.turns.at(-1)
      if (!history || !turn || pending) return
      await api().reconcile(history.history.thread_id, turn.run); if (current()) await refresh()
    }),
    control, commitControl,
    dismissControl: () => { if (!working && pending && !pending.attempted) setPending(null) },
    checkControl: () => operate(async current => {
      if (!pending) return
      const state = await api().commandState(pending.preview, pending.key)
      if (!current()) return
      if (state.status === "committed") { setPending(null); await refresh() }
      else setStatus(state.status === "not_committed" ? "尚未查到提交；不代表在途请求已撤销，只能保留原预览/同键重试。" : "提交状态暂不可核对，请保留原请求。")
    }),
  }
}
export type DurableController = ReturnType<typeof useDurableConversation>
