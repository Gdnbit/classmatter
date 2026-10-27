// Fixed D1 transport only. No business cache, localStorage, auto-dispatch or SDK loop.
import * as validators from "./durable-conversation-validators.cjs"
import { ApiError, type Session, type Classroom, type Activity, type AuditPage, type CommandReceipt } from "./api"
import { decodeApproval } from "./command-receipts"
import { consumeEvents } from "./events"

export type Attribution = Readonly<{
  origin: "local-owner" | "source-import"; created_by: string | null; last_modified_by: string | null
  source_workspace_id: string | null; source_owner_id: string | null; source_version: number | null
  content_authority: "domain-data" | "user-original" | "assistant-unverified"
}>
export type Mode = "read" | "draft" | "chat"
export type Run = { run_id: string; state: "queued" | "running" | "cancel_requested" | "completed" | "failed" | "cancelled" | "interrupted" | "unknown";
  version: number; created_at: string; queued_until: string; ended_at: string | null }
export type Turn = { turn_id: string; ordinal: number; client_request_id: string; mode: Mode; run: Run }
export type Thread = { thread_id: string; title: string; status: "active" | "archived" | "cleared"; version: number;
  student_id: string | null; updated_at: string; attribution: Attribution }
export type Listing = { data: Thread[]; snapshot: string; next_offset: number | null }
export type HistoricalSource = { source_id: string; source_workspace_id: string; source_owner_id: string;
  receipt_id: string; projection_hash: string; as_of: string }
export type History = {
  class_id: string; term_id: string; student_id: string | null
  history: { thread_id: string; title: string; status: Thread["status"]; version: number; truncated: boolean;
    messages: { message_id: string; turn_id: string; created_at: string;
      content: { role: "user" | "assistant"; origin: "user-original" | "assistant-unverified"; text: string } }[] }
  thread_attribution: Attribution; message_attributions: { message_id: string; attribution: Attribution }[]
  results: { message_id: string; content_authority: "assistant-unverified"; draft_status: "uncommitted";
    result: { text: string; sources: HistoricalSource[]; draft: { command: "task.create"; task_id: string;
      class_id: string; term_id: string; title: string; student_id: null; source_record_id: null; due_at: null } | null } }[]
  next_before: number | null; turns: Turn[]
}
export type Preview = { proposal_id: string; payload_hash: string; risk: "W1" | "X"; expires_at: string;
  payload: { command: "conversation.clear" | "conversation.archive"; thread_id: string; class_id: string; term_id: string; expected_version: number } }
export type ExitPreview = { proposal_id: string; payload_hash: string; risk: "X"; expires_at: string;
  payload: { command: "conversation_exit.create"; export_id: string; expected_snapshot_hash: string } }
const target = (preview: Preview | ExitPreview) => "thread_id" in preview.payload
  ? { id: preview.payload.thread_id, version: preview.payload.expected_version + 1 }
  : { id: preview.payload.export_id, version: 1 }
type State = { status: "committed" | "not_committed" | "unavailable"; proposal_id: string; payload_hash: string; receipt: CommandReceipt | null }
type Schema = Exclude<keyof typeof validators, "default">
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/
const mismatch = () => new Error("耐久工作台响应未通过范围或契约核对；未采纳结果，也未回退演示数据。")
function id(value: string) { if (!uuid.test(value)) throw mismatch(); return value }
function integer(value: number, maximum = 2147483647) { if (!Number.isSafeInteger(value) || value < 1 || value > maximum) throw mismatch(); return value }
const times = new Set(["as_of", "created_at", "updated_at", "ended_at", "queued_until", "expires_at", "occurred_at", "recorded_at", "due_at"])
function calendar(value: unknown): void {
  if (!value || typeof value !== "object") return
  for (const [key, item] of Object.entries(value)) {
    if (times.has(key) && typeof item === "string") {
      const time = new Date(item)
      if (!Number.isFinite(time.getTime()) || time.toISOString().slice(0, 19) !== item.slice(0, 19)) throw mismatch()
    } else if (item && typeof item === "object") calendar(item)
  }
}
export function decodeD1<T>(schema: Schema, value: unknown): T {
  const validate = validators[schema], valid = validate(value); validate.errors = null
  if (!valid) throw mismatch()
  calendar(value)
  return value as T
}
async function json<T>(schema: Schema, path: string, session: Session, body?: unknown, signal?: AbortSignal): Promise<T> {
  signal?.throwIfAborted()
  const response = await fetch(path, { method: body === undefined ? "GET" : "POST", credentials: "same-origin", signal,
    headers: body === undefined ? {} : { "content-type": "application/json", "x-class-os-csrf": session.csrf_token },
    body: body === undefined ? undefined : JSON.stringify(body) })
  if (!response.ok) throw new ApiError(response.status, response.headers.get("x-request-id") || "")
  if (!response.headers.get("content-type")?.startsWith("application/json") || !response.body) throw mismatch()
  const reader = response.body.getReader(), decoder = new TextDecoder("utf-8", { fatal: true })
  let text = "", bytes = 0
  try {
    while (true) {
      const item = await reader.read(); signal?.throwIfAborted()
      if (item.done) break
      bytes += item.value.byteLength
      if (bytes > 20 * 1024 * 1024) throw mismatch()
      text += decoder.decode(item.value, { stream: true })
    }
    text += decoder.decode()
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
  signal?.throwIfAborted()
  return decodeD1<T>(schema, JSON.parse(text))
}
function root(session: Session) { return `/api/workspaces/${id(session.subject.workspace_id)}` }
export async function discoverD1(session: Session, signal?: AbortSignal): Promise<"r1" | "conversation-d1"> {
  try { await json("capabilities", `${root(session)}/conversation-d1/capabilities`, session, undefined, signal); return "conversation-d1" }
  catch (error) { if (error instanceof ApiError && error.status === 404) return "r1"; throw error }
}
export function d1Client(session: Session, current: Pick<Classroom, "class_id" | "term_id">) {
  const classId = id(current.class_id), termId = id(current.term_id)
  const base = `${root(session)}/conversation-d1/classes/${classId}/terms/${termId}`
  const thread = (value: string) => `${base}/conversations/${id(value)}`
  return {
    list: (signal?: AbortSignal, cursor?: { snapshot: string; offset: number }) => {
      if (cursor && (!/^[a-f0-9]{64}$/.test(cursor.snapshot) || !Number.isInteger(cursor.offset) || cursor.offset < 50 || cursor.offset >= 10000 || cursor.offset % 50)) throw mismatch()
      return json<Listing>("listing", `${base}/conversations${cursor ? `/pages/${cursor.snapshot}/${cursor.offset}` : ""}`, session, undefined, signal)
    },
    async history(threadId: string, signal?: AbortSignal, cursor?: { version: number; before: number }) {
      const suffix = cursor ? `/pages/${integer(cursor.version)}/${integer(cursor.before, 10000)}` : ""
      const value = await json<History>("history", thread(threadId) + "/history" + suffix, session, undefined, signal)
      if (value.class_id !== classId || value.term_id !== termId || value.history.thread_id !== threadId) throw mismatch()
      const turns = new Map(value.turns.map(turn => [turn.turn_id, turn]))
      const messages = new Map(value.history.messages.map(message => [message.message_id, message]))
      if (turns.size !== value.turns.length || messages.size !== value.history.messages.length
        || new Set(value.turns.map(turn => turn.client_request_id)).size !== value.turns.length
        || new Set(value.turns.map(turn => turn.run.run_id)).size !== value.turns.length
        || value.history.messages.some(message => !turns.has(message.turn_id)
          || message.content.origin !== (message.content.role === "user" ? "user-original" : "assistant-unverified"))
        || value.turns.some((turn, index) => (index > 0 && turn.ordinal <= value.turns[index - 1].ordinal)
          || value.history.messages.filter(message => message.turn_id === turn.turn_id && message.content.role === "user").length !== 1
          || value.history.messages.filter(message => message.turn_id === turn.turn_id && message.content.role === "assistant").length !== (turn.run.state === "completed" ? 1 : 0))
        || value.message_attributions.length !== messages.size
        || new Set(value.message_attributions.map(item => item.message_id)).size !== messages.size
        || value.message_attributions.some(item => !messages.has(item.message_id)
          || item.attribution.content_authority !== (messages.get(item.message_id)?.content.role === "user" ? "user-original" : "assistant-unverified"))
        || new Set(value.results.map(item => item.message_id)).size !== value.results.length
        || value.results.some(item => messages.get(item.message_id)?.content.role !== "assistant"
          || messages.get(item.message_id)?.content.text !== item.result.text
          || (item.result.draft && (item.result.draft.class_id !== classId || item.result.draft.term_id !== termId)))) throw mismatch()
      return value
    },
    async create(threadId: string, requestId: string, studentId: string | null, signal?: AbortSignal) {
      const value = await json<State>("state", `${base}/conversations`, session,
        { thread_id: id(threadId), request_id: id(requestId), title: "新对话", student_id: studentId === null ? null : id(studentId) }, signal)
      if (value.status !== "committed" || value.receipt?.resource_id !== threadId || value.receipt.version !== 1) throw mismatch()
      return value
    },
    async rename(threadId: string, requestId: string, version: number, title: string, signal?: AbortSignal) {
      const value = await json<State>("state", thread(threadId) + "/rename", session,
        { request_id: id(requestId), expected_version: integer(version, 2147483646), title }, signal)
      if (value.status !== "committed" || value.receipt?.resource_id !== threadId || value.receipt.version !== version + 1) throw mismatch()
      return value
    },
    enqueue: (threadId: string, requestId: string, text: string, mode: Mode, signal?: AbortSignal) =>
      json<State>("state", thread(threadId) + "/turns", session, { request_id: id(requestId), text, mode }, signal),
    status: (threadId: string, requestId: string, signal?: AbortSignal) =>
      json<Run>("run", thread(threadId) + "/turns/" + id(requestId), session, undefined, signal),
    async start(threadId: string, requestId: string, signal: AbortSignal, onStatus: (text: string) => void) {
      signal.throwIfAborted()
      const response = await fetch(thread(threadId) + "/turns/" + id(requestId) + "/events", { method: "POST", credentials: "same-origin", signal,
        headers: { "content-type": "application/json", "x-class-os-csrf": session.csrf_token }, body: "{}" })
      if (!response.ok) throw new ApiError(response.status, response.headers.get("x-request-id") || "")
      await consumeEvents(response, event => { signal.throwIfAborted(); onStatus(event.type) })
      // NEVER release stream text/draft as authority. Caller re-reads QG history.
    },
    cancel: (threadId: string, run: Run) => json("control", thread(threadId) + `/runs/${id(run.run_id)}/cancel`, session, { expected_version: integer(run.version, 2147483646) }),
    reconcile: (threadId: string, run: Run) => json("control", thread(threadId) + `/runs/${id(run.run_id)}/reconcile`, session, {}),
    async preview(threadId: string, version: number, action: "clear" | "archive") {
      const value = await json<Preview>("preview", thread(threadId) + `/${action}/preview`, session, { expected_version: integer(version, 2147483646) })
      if (value.payload.thread_id !== threadId || value.payload.class_id !== classId || value.payload.term_id !== termId
        || value.payload.expected_version !== version || value.payload.command !== `conversation.${action}` || (action === "clear" && value.risk !== "X")) throw mismatch()
      return value
    },
    async approve(preview: Preview | ExitPreview) {
      const response = await fetch(`${root(session)}/commands/approve`, { method: "POST", credentials: "same-origin",
        headers: { "content-type": "application/json", "x-class-os-csrf": session.csrf_token },
        body: JSON.stringify({ proposal_id: preview.proposal_id, payload_hash: preview.payload_hash }) })
      if (!response.ok) throw new ApiError(response.status, response.headers.get("x-request-id") || "")
      return decodeApproval(await response.json())
    },
    async commit(preview: Preview | ExitPreview, key: string, approval: string | null) {
      const value = await json<CommandReceipt>("receipt", `${root(session)}/commands/commit`, session,
        { proposal_id: preview.proposal_id, idempotency_key: id(key), approval })
      const expected = target(preview)
      if (value.resource_id !== expected.id || value.version !== expected.version) throw mismatch()
      return value
    },
    async commandState(preview: Preview | ExitPreview, key: string) {
      const value = await json<State>("state", `${root(session)}/commands/${id(preview.proposal_id)}/receipts/${id(key)}`, session)
      if (value.proposal_id !== preview.proposal_id || value.payload_hash !== preview.payload_hash
        || (value.status === "committed") !== (value.receipt !== null)
        || (value.receipt && (value.receipt.resource_id !== target(preview).id || value.receipt.version !== target(preview).version))) throw mismatch()
      return value
    },
    async exitPreview(exportId: string) {
      const summary = await json<{ snapshot_hash: string }>("exitSummary", `${root(session)}/conversation-d1/exit/summary`, session)
      const value = await json<ExitPreview>("exitPreview", `${root(session)}/conversation-d1/exit/preview`, session,
        { export_id: id(exportId), expected_snapshot_hash: summary.snapshot_hash })
      if (value.payload.export_id !== exportId || value.payload.expected_snapshot_hash !== summary.snapshot_hash) throw mismatch()
      return value
    },
    exitDownload: (exportId: string) => `${root(session)}/conversation-d1/exit/${id(exportId)}/download`,
    activity: (signal?: AbortSignal, studentId?: string) => json<{ data: Activity }>("activity",
      base + (studentId ? `/students/${id(studentId)}/timeline` : "/activity"), session, undefined, signal),
    audit: () => json<AuditPage>("audit", base + "/audit", session),
  }
}
