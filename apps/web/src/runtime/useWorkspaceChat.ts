import { useEffect, useLayoutEffect, useRef, useState } from "react"
import type { Session } from "./api"
import { workspaceChatClient, type ChatHistory, type ChatListing, type ChatPreview, type ChatTurn } from "./workspace-chat"
import { createQueryRefresh } from "./query-refresh"
import { getModelStatus, type ModelStatus } from "./model-configuration"

type Props = { enabled: boolean; session: Session | null; threadId: string; canInteract: boolean; refreshSignal: unknown;
  onSelect: (id: string) => void; onSaved: (id: string) => void; onBusy: (busy: boolean) => void; onDraft: (dirty: boolean) => void; onError: (error: unknown) => void; onPreview: (preview: ChatPreview) => void }
const active = (turn?: ChatTurn) => !!turn && (turn.state === "queued" || turn.state === "running")
export function useWorkspaceChat(props: Props) {
  const latest = useRef(props); latest.current = props
  const epoch = useRef(0), operation = useRef(false), selected = useRef(props.threadId)
  const reader = useRef<AbortController | null>(null), stream = useRef<AbortController | null>(null)
  const [history, setHistory] = useState<ChatHistory | null>(null), [listing, setListing] = useState<ChatListing | null>(null)
  const [text, setText] = useState(""), [working, setWorking] = useState(false), [fresh, setFresh] = useState(false), [status, setStatus] = useState("")
  const [pendingSend, setPendingSend] = useState<{thread: string; request: string; text: string} | null>(null)
  const [model, setModel] = useState<ModelStatus | null>(null)
  const identity = props.enabled && props.session ? `${props.session.subject.owner_id}/${props.session.subject.workspace_id}/${props.session.csrf_token}` : ""
  const scopeRef = useRef(identity); scopeRef.current = identity
  const [readyScope, setReadyScope] = useState("")
  const client = () => { if (!latest.current.session || !latest.current.enabled) throw new Error("请先连接当前身份"); return workspaceChatClient(latest.current.session) }
  function report(error: unknown) { setStatus(error instanceof Error ? error.message : "操作未完成"); latest.current.onError(error) }
  async function refresh(thread = selected.current) {
    if (!identity) return null
    const generation = epoch.current, key = scopeRef.current, controller = new AbortController()
    reader.current?.abort(); reader.current = controller; setFresh(false)
    try {
      const api = client()
      const session = latest.current.session
      if (!session) return null
      const [list, saved, modelStatus] = await Promise.all([api.listing(controller.signal), thread ? api.history(thread, controller.signal) : Promise.resolve(null), getModelStatus(session, controller.signal)])
      if (controller.signal.aborted || generation !== epoch.current || !navigator.onLine) return null
      setListing(list); setHistory(saved); setModel(modelStatus); setFresh(true); setReadyScope(key)
      return saved
    } catch (error) { if (controller.signal.aborted || generation !== epoch.current) return null; throw error }
  }
  const refreshRef = useRef(refresh); refreshRef.current = refresh
  useEffect(() => { latest.current.onBusy(working) }, [working])
  useEffect(() => { latest.current.onDraft(!!text.trim()) }, [text, identity])
  useLayoutEffect(() => {
    epoch.current++; reader.current?.abort(); stream.current?.abort(); operation.current = false
    selected.current = props.threadId
    setText(""); setHistory(null); setListing(null); setPendingSend(null); setModel(null); setWorking(false); setFresh(false); setStatus("")
    if (identity) void refreshRef.current(props.threadId).catch(report)
    return () => { epoch.current++; reader.current?.abort(); stream.current?.abort(); latest.current.onBusy(false); latest.current.onDraft(false) }
  }, [identity])
  useLayoutEffect(() => {
    if (!identity || selected.current === props.threadId) return
    epoch.current++; reader.current?.abort(); stream.current?.abort(); operation.current = false
    selected.current = props.threadId; setText(""); setHistory(null); setPendingSend(null); setWorking(false); setFresh(false); setStatus("")
    void refreshRef.current(props.threadId).catch(report)
  }, [props.threadId, identity])
  const idle = useRef(false); idle.current = !working && !pendingSend
  const foreground = useRef<ReturnType<typeof createQueryRefresh> | null>(null)
  useEffect(() => {
    if (!identity) return
    const controller = createQueryRefresh({ read: async () => { await refreshRef.current() },
      invalidate: () => { reader.current?.abort(); setFresh(false); setStatus("连接已断开，恢复后请刷新对话。") },
      fail: report, available: () => navigator.onLine && document.visibilityState === "visible", idle: () => idle.current,
      now: () => performance.now(), schedule: (callback, delay) => window.setTimeout(callback, delay), cancel: timer => window.clearTimeout(timer as number) })
    foreground.current = controller
    const offline = () => controller.offline(), reload = () => controller.request()
    const visibility = () => document.visibilityState === "visible" ? controller.request() : controller.resume()
    window.addEventListener("offline", offline); window.addEventListener("online", reload); window.addEventListener("focus", reload); document.addEventListener("visibilitychange", visibility)
    return () => { controller.dispose(); foreground.current = null; window.removeEventListener("offline", offline); window.removeEventListener("online", reload); window.removeEventListener("focus", reload); document.removeEventListener("visibilitychange", visibility) }
  }, [identity])
  useEffect(() => { foreground.current?.request() }, [props.refreshSignal])
  useEffect(() => { foreground.current?.resume() })
  async function operate(action: (generation: number) => Promise<void>) {
    if (operation.current) return
    operation.current = true; const generation = epoch.current; setWorking(true)
    try { await action(generation) } catch (error) { if (generation === epoch.current) report(error) }
    finally { if (generation === epoch.current) { operation.current = false; setWorking(false) } }
  }
  const freshScope = fresh && readyScope === identity
  const last = history?.turns.at(-1)
  async function runSaved(thread: string, turn: ChatTurn, generation: number) {
    const controller = new AbortController(); stream.current = controller
    try {
      await client().start(thread, turn.request_id, controller.signal, kind => {
        if (generation === epoch.current) setStatus(kind.startsWith("tool.") ? "正在整理…" : "正在回复…")
      })
    } catch (error) {
      if (generation === epoch.current && !controller.signal.aborted) setStatus("连接中断，请刷新对话查看结果。")
    } finally { if (stream.current === controller) stream.current = null }
  }
  async function send() {
    if (!props.canInteract || model?.mode === "stale" || !freshScope || working || operation.current || pendingSend || active(last) || !navigator.onLine || !text.trim() || history?.thread.status && history.thread.status !== "active") return
    const target = { thread: selected.current || crypto.randomUUID(), request: crypto.randomUUID(), text }
    await operate(async generation => {
      setPendingSend(target); selected.current = target.thread
      let savedInput = false
      try {
        const result = await client().send(target.thread, target.request, target.text)
        if (generation !== epoch.current) return
        if (result.turn.request_id !== target.request || result.turn.user_text !== target.text) throw new Error("输入保存响应不匹配")
        savedInput = true; setPendingSend(null); setText(current => current === target.text ? "" : current)
        latest.current.onSaved(target.thread); await refreshRef.current(target.thread)
        if (generation === epoch.current && navigator.onLine) await runSaved(target.thread, result.turn, generation)
      } catch (error) {
        if (generation === epoch.current) setStatus("暂时无法确认发送结果，请先刷新对话。")
        throw error
      } finally {
        if (generation === epoch.current) {
          const restored = await refreshRef.current(target.thread).catch(error => { report(error); return null })
          if (generation !== epoch.current) return
          if (restored?.turns.some(row => row.request_id === target.request && row.user_text === target.text)) {
            if (!savedInput) { setPendingSend(null); setText(current => current === target.text ? "" : current) }
            savedInput = true
          }
          if (savedInput) latest.current.onSaved(target.thread)
          if (restored?.turns.find(row => row.request_id === target.request)?.state === "completed") setStatus("")
        }
      }
    })
  }
  async function stop() {
    const target = history?.turns.at(-1), thread = selected.current
    if (!target || !active(target) || !thread) return
    const generation = epoch.current, api = client()
    try {
      const saved = await api.history(thread), current = saved.turns.find(row => row.request_id === target.request_id)
      if (generation !== epoch.current) return
      if (!current) throw new Error("原运行未找到，未取消其他运行")
      if (active(current)) await api.cancel(thread, current)
      if (generation !== epoch.current) return
      stream.current?.abort(); setStatus(active(current) ? "已停止回复。" : "回复已结束。")
      await refreshRef.current(thread)
    }
    catch (error) { if (generation === epoch.current) report(error) }
  }
  return { history, listing, model, text, setText, working, fresh: freshScope, status, pendingSend, send, lastActive: active(last),
    canSend: props.canInteract && model?.mode !== "stale" && freshScope && !working && !pendingSend && !active(last) && (!history || history.thread.status === "active") && navigator.onLine,
    stop, refresh: () => void refreshRef.current().catch(report),
    select: (thread: string) => { if (!working && !text.trim() && !pendingSend) latest.current.onSelect(thread) },
    newChat: () => { if (!working && !text.trim() && !pendingSend) { epoch.current++; reader.current?.abort(); selected.current = ""; setHistory(null); setFresh(false); setStatus(""); latest.current.onSelect(""); void refreshRef.current("").catch(report) } },
    recoverSend: () => operate(async generation => {
      if (!pendingSend) return
      // Explicit human recovery reuses the original UUID and bytes. It can
      // restore an unsaved input, but never starts or retries a model run.
      const restored = await client().send(pendingSend.thread, pendingSend.request, pendingSend.text)
      if (generation !== epoch.current) return
      if (restored.turn.request_id !== pendingSend.request || restored.turn.user_text !== pendingSend.text) throw new Error("原输入恢复响应不匹配")
      const saved = await refreshRef.current(pendingSend.thread)
      if (generation !== epoch.current) return
      const turn = saved?.turns.find(row => row.request_id === pendingSend.request)
      if (turn && turn.user_text === pendingSend.text) { setPendingSend(null); setText(current => current === pendingSend.text ? "" : current); latest.current.onSaved(pendingSend.thread); setStatus("消息已保存，可以继续回复。") }
    }),
    startQueued: (turn: ChatTurn) => operate(async generation => { if (props.canInteract && freshScope && turn.state === "queued" && history?.thread.status === "active") { await runSaved(history.thread.thread_id, turn, generation); await refreshRef.current() } }),
    preview: (turn: ChatTurn) => operate(async generation => { if (props.canInteract && freshScope && history?.thread.status === "active" && turn.candidate && !turn.action_receipt) {
      const value = await client().preview(history.thread.thread_id, turn); if (generation === epoch.current) latest.current.onPreview(value) } }),
    control: (action: "archive" | "clear") => operate(async generation => { if (!props.canInteract || !freshScope || !history || active(last)) return
      await client().control(history.thread.thread_id, history.thread.version, action); if (generation === epoch.current) await refreshRef.current() }),
    moreThreads: () => operate(async generation => { if (!listing?.next_offset) return; const next = await client().listing(undefined, listing.next_offset)
      if (generation === epoch.current) setListing({ ...next, data: [...new Map([...listing.data, ...next.data].map(row => [row.thread_id, row])).values()] }) }),
    moreHistory: () => operate(async generation => { if (!history?.next_before) return; const next = await client().history(history.thread.thread_id, undefined, history.next_before)
      if (generation !== epoch.current) return
      if (next.thread.version !== history.thread.version) throw new Error("会话已变化，请重新读取，未拼接旧版本")
      setHistory({ ...next, turns: [...next.turns, ...history.turns] }) }),
  }
}
export type WorkspaceChatController = ReturnType<typeof useWorkspaceChat>
