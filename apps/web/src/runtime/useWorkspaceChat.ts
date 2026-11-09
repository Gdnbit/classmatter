import { useEffect, useLayoutEffect, useRef, useState } from "react"
import { ApiError, type Session } from "./api"
import { workspaceChatClient, type ChatHistory, type ChatListing, type ChatPreview, type ChatTurn } from "./workspace-chat"
import { createQueryRefresh } from "./query-refresh"
import { getModelStatus, type ModelStatus } from "./model-configuration"

type Props = { enabled: boolean; session: Session | null; threadId: string; canInteract: boolean; refreshSignal: unknown;
  onSelect: (id: string) => void; onSaved: (id: string) => void; onBusy: (busy: boolean) => void; onDraft: (dirty: boolean) => void; onError: (error: unknown) => void; onPreview: (preview: ChatPreview) => void }
const active = (turn?: ChatTurn) => !!turn && (turn.state === "queued" || turn.state === "running")
type LocalThread = { text: string; editVersion: number; busy: boolean; saving: boolean; status: string; pending: {thread: string; request: string; text: string; editVersion: number} | null; stream: AbortController | null }
function clearSentDraft(state: LocalThread, sent: { text: string; editVersion: number }) {
  if (state.text === sent.text && state.editVersion === sent.editVersion) { state.text = ""; state.editVersion++ }
}
export function useWorkspaceChat(props: Props) {
  const latest = useRef(props); latest.current = props
  const epoch = useRef(0), view = useRef(0), selected = useRef(props.threadId)
  const reader = useRef<AbortController | null>(null), threads = useRef(new Map<string, LocalThread>())
  const listingRead = useRef(0), listingLoading = useRef(false)
  const [, redraw] = useState(0)
  const changed = () => redraw(value => value + 1)
  function local(thread = selected.current) {
    let state = threads.current.get(thread)
    if (!state) { state = { text: "", editVersion: 0, busy: false, saving: false, status: "", pending: null, stream: null }; threads.current.set(thread, state) }
    return state
  }
  const [history, setHistory] = useState<ChatHistory | null>(null), [listing, setListing] = useState<ChatListing | null>(null)
  const [fresh, setFresh] = useState(false)
  const [model, setModel] = useState<ModelStatus | null>(null)
  const identity = props.enabled && props.session ? `${props.session.subject.owner_id}/${props.session.subject.workspace_id}/${props.session.csrf_token}` : ""
  const scopeRef = useRef(identity); scopeRef.current = identity
  const [readyScope, setReadyScope] = useState("")
  const client = () => { if (!latest.current.session || !latest.current.enabled) throw new Error("请先连接当前身份"); return workspaceChatClient(latest.current.session) }
  function report(error: unknown, thread = selected.current) {
    local(thread).status = error instanceof Error ? error.message : "操作未完成"; changed()
    if (thread === selected.current || error instanceof ApiError && error.status === 401) latest.current.onError(error)
  }
  async function refreshListing() {
    const generation = epoch.current, serial = ++listingRead.current, api = client()
    const list = await api.listing()
    if (generation === epoch.current && serial === listingRead.current) { setListing(list); return list }
  }
  async function refresh(thread = selected.current) {
    if (!identity) return null
    const generation = epoch.current, currentView = ++view.current, serial = ++listingRead.current, key = scopeRef.current, controller = new AbortController()
    reader.current?.abort(); reader.current = controller; setFresh(false)
    try {
      const api = client()
      const session = latest.current.session
      if (!session) return null
      const [list, saved, modelStatus] = await Promise.all([api.listing(controller.signal), thread && !local(thread).saving ? api.history(thread, controller.signal) : Promise.resolve(null), getModelStatus(session, controller.signal)])
      if (controller.signal.aborted || generation !== epoch.current || currentView !== view.current || thread !== selected.current || !navigator.onLine) return null
      if (serial === listingRead.current) setListing(list)
      setHistory(saved); setModel(modelStatus); setFresh(!local(thread).saving); setReadyScope(key)
      return saved
    } catch (error) { if (controller.signal.aborted || generation !== epoch.current) return null; throw error }
  }
  const refreshRef = useRef(refresh); refreshRef.current = refresh
  async function loadView(thread: string) {
    // Navigation needs one target history, not another listing/model fan-out.
    if (!model || !listing || readyScope !== identity) {
      try { return await refreshRef.current(thread) }
      catch (error) { report(error, thread); return null }
    }
    const generation = epoch.current, currentView = ++view.current, controller = new AbortController()
    reader.current?.abort(); reader.current = controller
    try {
      const saved = thread && !local(thread).saving ? await client().history(thread, controller.signal) : null
      if (controller.signal.aborted || generation !== epoch.current || currentView !== view.current || thread !== selected.current || !navigator.onLine) return null
      setHistory(saved); setFresh(!local(thread).saving)
      if (saved?.turns.length && !active(saved.turns.at(-1)) && !local(thread).pending) { local(thread).status = ""; changed() }
      return saved
    } catch (error) { if (!controller.signal.aborted && generation === epoch.current) report(error, thread); return null }
  }
  async function refreshAfter(thread: string, generation: number) {
    if (generation !== epoch.current) return null
    return thread === selected.current ? refreshRef.current(thread) : (await refreshListing(), null)
  }
  const state = local(), { text, busy: working, status, pending: pendingSend } = state
  const anyWorking = [...threads.current.values()].some(item => item.busy)
  const anyDraft = [...threads.current.values()].some(item => !!item.text.trim() || !!item.pending)
  useEffect(() => { latest.current.onBusy(anyWorking) }, [anyWorking, identity])
  useEffect(() => { latest.current.onDraft(anyDraft) }, [anyDraft, identity])
  useLayoutEffect(() => {
    epoch.current++; view.current++; reader.current?.abort()
    for (const item of threads.current.values()) item.stream?.abort()
    threads.current.clear(); listingRead.current++; listingLoading.current = false
    selected.current = props.threadId
    setHistory(null); setListing(null); setModel(null); setFresh(false); changed()
    if (identity) void refreshRef.current(props.threadId).catch(report)
    return () => { epoch.current++; view.current++; reader.current?.abort(); for (const item of threads.current.values()) item.stream?.abort(); latest.current.onBusy(false); latest.current.onDraft(false) }
  }, [identity])
  useLayoutEffect(() => {
    if (!identity || selected.current === props.threadId) return
    view.current++; reader.current?.abort()
    selected.current = props.threadId; setHistory(null); setFresh(false); changed()
    const timer = window.setTimeout(() => void loadView(props.threadId), 100)
    return () => window.clearTimeout(timer)
  }, [props.threadId, identity])
  const idle = useRef(false); idle.current = !working && !pendingSend
  const foreground = useRef<ReturnType<typeof createQueryRefresh> | null>(null)
  useEffect(() => {
    if (!identity) return
    const controller = createQueryRefresh({ read: async () => { await refreshRef.current() },
      invalidate: () => { view.current++; reader.current?.abort(); setFresh(false); local().status = "连接已断开，恢复后请刷新对话。"; changed() },
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
  async function operate(action: (generation: number, thread: string, api: ReturnType<typeof workspaceChatClient>, state: LocalThread) => Promise<void>, thread = selected.current) {
    const state = local(thread)
    if (state.busy) return
    const generation = epoch.current, api = client(); state.busy = true; changed()
    try { await action(generation, thread, api, state) } catch (error) { if (generation === epoch.current) report(error, thread) }
    finally { if (generation === epoch.current) { state.busy = false; changed() } }
  }
  const freshScope = fresh && readyScope === identity
  const last = history?.turns.at(-1)
  async function runSaved(thread: string, turn: ChatTurn, generation: number, api: ReturnType<typeof workspaceChatClient>) {
    const state = local(thread), controller = new AbortController(); state.stream = controller
    try {
      await api.start(thread, turn.request_id, controller.signal, kind => {
        if (generation === epoch.current) { state.status = kind.startsWith("tool.") ? "正在整理…" : "正在回复…"; changed() }
      })
    } catch (error) {
      if (generation === epoch.current && !controller.signal.aborted) {
        if (error instanceof ApiError && error.status === 401) report(error, thread)
        else { state.status = "连接中断，请刷新对话查看结果。"; changed() }
      }
    } finally { if (state.stream === controller) state.stream = null }
  }
  async function send(continuation?: string) {
    const message = continuation ?? text
    if (!props.canInteract || model?.mode === "stale" || !freshScope || local().busy || pendingSend || active(last) || !navigator.onLine || !message.trim() || history?.thread.status && history.thread.status !== "active") return
    const target = { thread: selected.current || crypto.randomUUID(), request: crypto.randomUUID(), text: message, editVersion: continuation === undefined ? local().editVersion : -1 }
    if (!selected.current) {
      local(target.thread).text = text; local(target.thread).editVersion = target.editVersion
      local("").text = ""; local("").editVersion++
      selected.current = target.thread; view.current++; reader.current?.abort(); setHistory(null); setFresh(false)
    }
    await operate(async (generation, thread, api, state) => {
      state.pending = target; state.saving = true; state.status = "正在发送…"; changed()
      if (!props.threadId) latest.current.onSaved(target.thread)
      let savedInput = false
      try {
        const result = await api.send(target.thread, target.request, target.text)
        if (generation !== epoch.current) return
        if (result.turn.request_id !== target.request || result.turn.user_text !== target.text) throw new Error("输入保存响应不匹配")
        savedInput = true; state.pending = null; state.saving = false
        clearSentDraft(state, target)
        changed(); await refreshAfter(thread, generation)
        if (generation === epoch.current && navigator.onLine) await runSaved(thread, result.turn, generation, api)
      } catch (error) {
        if (generation === epoch.current) { state.status = "暂时无法确认发送结果，请先刷新对话。"; changed() }
        throw error
      } finally {
        if (generation === epoch.current) {
          state.saving = false
          const wasCurrent = thread === selected.current
          const restored = await (wasCurrent ? refreshRef.current(thread) : api.history(thread)).catch(error => { if (generation === epoch.current) report(error, thread); return null })
          if (generation !== epoch.current) return
          if (restored?.turns.some(row => row.request_id === target.request && row.user_text === target.text)) {
            if (!savedInput) { state.pending = null; clearSentDraft(state, target) }
            savedInput = true
          }
          if (restored?.turns.find(row => row.request_id === target.request)?.state === "completed") state.status = ""
          changed(); if (!wasCurrent) await refreshListing()
        }
      }
    }, target.thread)
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
      local(thread).stream?.abort(); local(thread).status = active(current) ? "已停止回复。" : "回复已结束。"; changed()
      await refreshAfter(thread, generation)
    }
    catch (error) { if (generation === epoch.current) report(error, thread) }
  }
  const setText = (value: string) => { const state = local(); state.text = value; state.editVersion++; changed() }
  const pendingThreads = [...threads.current.entries()].flatMap(([id, item]) => id && item.pending && !listing?.data.some(row => row.thread_id === id)
    ? [{ thread_id: id, title: item.pending.text.slice(0, 40) }] : [])
  return { history, listing, pendingThreads, model, text, setText, working, anyWorking, listingBusy: listingLoading.current, fresh: freshScope, status, pendingSend, send, lastActive: active(last),
    canSend: props.canInteract && model?.mode !== "stale" && freshScope && !working && !pendingSend && !active(last) && (!history || history.thread.status === "active") && navigator.onLine,
    stop, refresh: () => void refreshRef.current().catch(report),
    continueTask: (turn: ChatTurn) => {
      if (turn.turn_id === history?.turns.at(-1)?.turn_id && turn.action_receipt && !active(last))
        return send("继续完成上面的任务，只处理尚未完成的步骤。")
    },
    select: (thread: string) => latest.current.onSelect(thread),
    newChat: () => latest.current.onSelect(""),
    recoverSend: () => operate(async (generation, thread, api, state) => {
      const pendingSend = state.pending
      if (!pendingSend) return
      // Explicit human recovery reuses the original UUID and bytes. It can
      // restore an unsaved input, but never starts or retries a model run.
      const restored = await api.send(pendingSend.thread, pendingSend.request, pendingSend.text)
      if (generation !== epoch.current) return
      if (restored.turn.request_id !== pendingSend.request || restored.turn.user_text !== pendingSend.text) throw new Error("原输入恢复响应不匹配")
      const saved = await api.history(thread)
      if (generation !== epoch.current) return
      const turn = saved?.turns.find(row => row.request_id === pendingSend.request)
      if (turn && turn.user_text === pendingSend.text) { state.pending = null; clearSentDraft(state, pendingSend); state.status = "消息已保存，可以继续回复。"; changed(); await refreshAfter(thread, generation) }
    }),
    startQueued: (turn: ChatTurn) => operate(async (generation, thread, api) => { if (props.canInteract && freshScope && turn.state === "queued" && history?.thread.status === "active") { await runSaved(thread, turn, generation, api); await refreshAfter(thread, generation) } }),
    preview: (turn: ChatTurn) => operate(async (generation, thread, api) => { if (props.canInteract && freshScope && history?.thread.status === "active" && turn.candidate && !turn.action_receipt) {
      const currentView = view.current, value = await api.preview(thread, turn)
      if (generation === epoch.current && thread === selected.current && currentView === view.current) latest.current.onPreview(value) } }),
    control: (action: "archive" | "clear") => operate(async (generation, thread, api) => { if (!props.canInteract || !freshScope || !history || active(last)) return
      await api.control(thread, history.thread.version, action); await refreshAfter(thread, generation) }),
    moreThreads: async () => {
      if (!listing?.next_offset || listingLoading.current || !identity) return
      const generation = epoch.current, serial = ++listingRead.current; listingLoading.current = true; changed()
      try { const next = await client().listing(undefined, listing.next_offset)
        if (generation === epoch.current && serial === listingRead.current) setListing({ ...next, data: [...new Map([...listing.data, ...next.data].map(row => [row.thread_id, row])).values()] })
      } catch (error) { if (generation === epoch.current) report(error) }
      finally { if (generation === epoch.current) { listingLoading.current = false; changed() } }
    },
    moreHistory: () => operate(async (generation, thread, api) => { if (!history?.next_before) return; const currentView = view.current, next = await api.history(thread, undefined, history.next_before)
      if (generation !== epoch.current || thread !== selected.current || currentView !== view.current) return
      if (next.thread.version !== history.thread.version) throw new Error("会话已变化，请重新读取，未拼接旧版本")
      setHistory({ ...next, turns: [...next.turns, ...history.turns] }) }),
  }
}
export type WorkspaceChatController = ReturnType<typeof useWorkspaceChat>
