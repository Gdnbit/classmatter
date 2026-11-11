import * as validators from "./workspace-chat-validators.cjs"
import { ApiError, workspace, type Session } from "./api"
import { consumeEvents } from "./events"
import { classroomClient, type ClassroomCommand } from './classroom-work'

type Scope = { class_id: string; term_id: string }
type SeatBoard = { rows: number; columns: number; cells: { row: number; column: number; student: string | null; student_id: string | null }[] }
export type ChangePreview = { schema_version: 'classmatter.change-preview.v1'; candidate_hash: string; kind: 'create' | 'edit' | 'seating';
  fields: { field: string; before: string | null; after: string | null }[]; before_seats: SeatBoard | null; after_seats: SeatBoard | null }
export type ChatCandidate =
  | ClassroomCommand
  | (Scope & { command: "class.create"; name: string; term_name: string; start_date: string; end_date: string })
  | (Scope & { command: "class.update"; name: string; expected_version: number })
  | (Scope & { command: "term.update"; expected_version: number; previous_name: string; name: string; previous_start_date: string; start_date: string; previous_end_date: string; end_date: string })
  | (Scope & { command: "student.create"; student_id: string; expected_class_version: number; name: string })
  | (Scope & { command: "student.update_name"; student_id: string; expected_version: number; previous_name: string; name: string })
  | (Scope & { command: "task.create"; task_id: string; title: string; due_at: string | null; student_id: string | null; source_record_id: string | null })
  | (Scope & { command: "task.update"; task_id: string; expected_version: number; status: string; evidence: string; title?: string | null; due_at?: string | null; change_due_date?: boolean })
  | (Scope & { command: "document.create"; document_id: string; title: string; body: string; format: "plain-text" | "markdown" })
  | (Scope & { command: "document.revise"; document_id: string; expected_version: number; title: string; body: string; format: "plain-text" | "markdown" })
export type ChatThread = { thread_id: string; title: string; status: "active" | "archived" | "cleared"; version: number; created_at: string; updated_at: string; cleared_at: string | null }
export type ChatTurn = { turn_id: string; request_id: string; ordinal: number; state: "queued" | "running" | "completed" | "failed" | "cancelled" | "unknown"; version: number;
  user_text: string | null; assistant_text: string | null; candidate: ChatCandidate | null; candidate_hash: string | null;
  created_at: string; started_at: string | null; lease_until: string | null; ended_at: string | null; input_tokens: number | null; output_tokens: number | null; duration_ms: number | null;
  action_receipt: { receipt_id: string; resource_id: string; version: number } | null; change_preview: ChangePreview | null }
export type ChatListing = { schema_version: "classmatter.workspace-chat-list.v1"; data: ChatThread[]; next_offset: number | null }
export type ChatHistory = { schema_version: "classmatter.workspace-chat-history.v1"; thread: ChatThread; turns: ChatTurn[]; next_before: number | null }
export type ChatPreview = { schema_version: "classmatter.workspace-chat-preview.v1"; proposal_id: string; payload_hash: string; risk: "W1" | "W2"; expires_at: string; payload: ChatCandidate; change_preview: ChangePreview | null; displayNames?: Record<string, string> }
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/
function id(value: string) { if (!uuid.test(value)) throw new Error("对话标识无效"); return value }
function dates(value: unknown): void {
  if (!value || typeof value !== "object") return
  for (const [key, item] of Object.entries(value)) {
    if (typeof item === "string" && (key.endsWith("_at") || key === "lease_until" || key.endsWith("_date"))) {
      const date = new Date(item)
      if (!Number.isFinite(date.getTime()) || date.toISOString().slice(0, item.length === 10 ? 10 : 19) !== item.slice(0, item.length === 10 ? 10 : 19)) throw new Error("聊天时间契约不匹配")
    } else if (item && typeof item === "object") dates(item)
  }
}
function checkComparison(preview: ChangePreview | null | undefined, candidate: ChatCandidate | null, hash: string | null) {
  if (!preview) return
  if (!candidate || preview.candidate_hash !== hash || new Set(preview.fields.map(field => field.field)).size !== preview.fields.length) throw new Error('预览与对话不匹配')
  const expectedKind = candidate.command.startsWith('seat.') ? 'seating' : candidate.command.endsWith('.create') ? 'create' : 'edit'
  if (preview.kind !== expectedKind) throw new Error('预览类型不匹配')
  if (preview.kind === 'seating' ? !candidate.command.startsWith('seat.') || !preview.after_seats || preview.fields.length > 0
    : preview.before_seats || preview.after_seats || !preview.fields.length) throw new Error('预览内容不完整')
  if (preview.kind === 'create' && preview.fields.some(field => field.before !== null)) throw new Error('预览内容不匹配')
  for (const board of [preview.before_seats, preview.after_seats]) {
    if (!board) continue
    const positions = new Set<string>(), people = new Set<string>()
    for (const cell of board.cells) {
      const key = `${cell.row}-${cell.column}`
      if (cell.row > board.rows || cell.column > board.columns || positions.has(key)
        || (cell.student === null) !== (cell.student_id === null) || cell.student_id !== null && people.has(cell.student_id)) throw new Error('座位预览不完整')
      positions.add(key); if (cell.student_id) people.add(cell.student_id)
    }
    if (positions.size !== board.rows * board.columns) throw new Error('座位预览不完整')
  }
}
type Schema = "capabilities" | "listing" | "history" | "send" | "turn" | "version" | "clear" | "thread" | "previewBody" | "preview"
function decode<T>(schema: Schema, data: unknown): T {
  const validate = validators[schema], valid = validate(data); validate.errors = null
  if (!valid) throw new Error("聊天响应契约不匹配；未回退到演示数据。")
  const value = data as { turns?: ChatTurn[]; turn?: ChatTurn; change_preview?: ChangePreview | null; payload?: ChatCandidate; payload_hash?: string }
  for (const row of [...(value.turns || []), ...(value.turn ? [value.turn] : [])]) checkComparison(row.change_preview, row.candidate, row.candidate_hash)
  if (schema === 'preview') checkComparison(value.change_preview, value.payload || null, value.payload_hash || null)
  dates(data)
  return data as T
}
async function json<T>(schema: Schema, path: string, session: Session, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(path, { method: body === undefined ? "GET" : "POST", credentials: "same-origin", cache: "no-store", redirect: "error", signal,
    headers: body === undefined ? {} : { "content-type": "application/json", "x-class-os-csrf": session.csrf_token }, body: body === undefined ? undefined : JSON.stringify(body) })
  if (!response.ok) throw new ApiError(response.status, response.headers.get("x-request-id") || "")
  if (!response.headers.get("content-type")?.startsWith("application/json") || !response.body) throw new Error("聊天响应不是有效 JSON")
  const reader = response.body.getReader(), decoder = new TextDecoder("utf-8", { fatal: true })
  let raw = "", bytes = 0
  try { while (true) { const part = await reader.read(); signal?.throwIfAborted(); if (part.done) break
    bytes += part.value.byteLength; if (bytes > 12 * 1024 * 1024) throw new Error("聊天响应超出限制"); raw += decoder.decode(part.value, { stream: true }) }
    raw += decoder.decode()
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
  signal?.throwIfAborted(); return decode<T>(schema, JSON.parse(raw))
}
export async function workspaceChatAvailable(session: Session, signal?: AbortSignal): Promise<boolean> {
  try { await json("capabilities", `${workspace(session)}/workspace-chat/capabilities`, session, undefined, signal); return true }
  catch (error) { if (error instanceof ApiError && error.status === 404) return false; throw error }
}
export function workspaceChatClient(session: Session) {
  const root = `${workspace(session)}/workspace-chat`, thread = (value: string) => `${root}/threads/${id(value)}`
  return {
    listing: (signal?: AbortSignal, offset = 0) => json<ChatListing>("listing", `${root}/threads${offset ? `/pages/${offset}` : ""}`, session, undefined, signal),
    history: async (threadId: string, signal?: AbortSignal, before?: number) => {
      const result = await json<ChatHistory>("history", thread(threadId) + (before ? `/before/${before}` : ""), session, undefined, signal)
      if (result.thread.thread_id !== threadId || result.turns.some((row, index) => index > 0 && row.ordinal <= result.turns[index - 1].ordinal)) throw new Error("聊天范围或顺序不匹配")
      if (result.turns.some(row => row.change_preview && (!row.candidate || row.change_preview.candidate_hash !== row.candidate_hash))) throw new Error('预览与对话不匹配')
      return result
    },
    send: (threadId: string, requestId: string, text: string, signal?: AbortSignal) => json<{turn: ChatTurn}>("turn", thread(threadId) + "/turns", session, { request_id: id(requestId), text }, signal),
    start: async (threadId: string, requestId: string, signal: AbortSignal, onProgress: (kind: string) => void, reasoning?: 'low' | 'medium' | 'high') => {
      const response = await fetch(`${thread(threadId)}/turns/${id(requestId)}/events`, { method: "POST", credentials: "same-origin", signal,
        headers: { "content-type": "application/json", "x-class-os-csrf": session.csrf_token, ...(reasoning ? { 'x-classmatter-reasoning': reasoning } : {}) }, body: "{}" })
      if (!response.ok) throw new ApiError(response.status, response.headers.get("x-request-id") || "")
      await consumeEvents(response, item => onProgress(item.type)) // Render only QG-saved output, never these payloads.
    },
    cancel: (threadId: string, turn: ChatTurn) => json("turn", `${thread(threadId)}/turns/${id(turn.request_id)}/cancel`, session, { expected_version: turn.version }),
    control: (threadId: string, version: number, action: "archive" | "clear") => json("thread", `${thread(threadId)}/${action}`, session, { expected_version: version, ...(action === "clear" ? {confirm_clear: true} : {}) }),
    preview: async (threadId: string, turn: ChatTurn) => {
      if (!turn.candidate || !turn.candidate_hash || turn.action_receipt) throw new Error("没有待确认的操作候选")
      const result = await json<ChatPreview>("preview", `${thread(threadId)}/turns/${id(turn.request_id)}/proposal`, session, { candidate_hash: turn.candidate_hash })
      if (result.payload_hash !== turn.candidate_hash || Object.keys(result.payload).length !== Object.keys(turn.candidate).length
        || Object.entries(turn.candidate).some(([key, value]) => result.payload[key as keyof ChatCandidate] !== value)) throw new Error("预览与原聊天候选不匹配")
      if (result.change_preview && (result.change_preview.candidate_hash !== turn.candidate_hash || turn.change_preview && JSON.stringify(result.change_preview) !== JSON.stringify(turn.change_preview))) throw new Error('预览已变化，请重新查看')
      if (result.payload.command === 'score.record') {
        const exam = await classroomClient(session, result.payload).results(result.payload.exam_id)
        result.displayNames = { [exam.exam_id]: `${exam.title} · ${exam.subject}` }
      }
      return result
    },
  }
}
