import * as validators from "./agent-conversation-validators.cjs"
import { request, workspace, type Session, type Classroom } from "./api"

export type ScopedConversation = {
  schema_version: "class-os.agent-conversation.v2"
  conversation_id: string
  expires_at: string
  memory: "ephemeral-not-fact"
  class_id: string
  term_id: string
  student_id: string | null
}

export class ConversationScopeInvalid extends Error {
  constructor() { super("对话范围响应不匹配，未回落到全班或采纳旧上下文。请核对当前班级与学生。") }
}

export type RecordNoteCandidate = Readonly<{
  schema_version: "class-os.record-note-candidate.v1"
  status: "unverified-user-note"
  note_quote: string
  source_start: number
  source_end: number
  source_hash: string
}>

export class RecordNoteSourceInvalid extends Error {
  constructor() { super("原文草稿来源核对失败；未采纳为事实、观察或保存请求。") }
}

export async function parseRecordNoteCandidate(data: unknown, sourceText: string, signal?: AbortSignal): Promise<RecordNoteCandidate> {
  signal?.throwIfAborted()
  const snapshot = data && typeof data === "object" && !Array.isArray(data) ? { ...data } : data
  const valid = validators.recordNoteCandidate(snapshot); validators.recordNoteCandidate.errors = null
  if (!valid || typeof sourceText !== "string" || sourceText.length > 4000) throw new RecordNoteSourceInvalid()
  const value = Object.freeze(snapshot as RecordNoteCandidate), points = Array.from(sourceText)
  if (!points.length || points.length > 2000 || value.source_start >= value.source_end
      || value.source_end > points.length || points.slice(value.source_start, value.source_end).join("") !== value.note_quote) {
    throw new RecordNoteSourceInvalid()
  }
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(sourceText))
  signal?.throwIfAborted()
  const hash = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("")
  if (hash !== value.source_hash) throw new RecordNoteSourceInvalid()
  return value
}

export async function createScopedConversation(session: Session, current: Pick<Classroom, "class_id" | "term_id">,
  studentId: string | null, signal?: AbortSignal): Promise<ScopedConversation> {
  signal?.throwIfAborted()
  const classId = current.class_id, termId = current.term_id
  const body = { schema_version: "class-os.agent-conversation-request.v2", student_id: studentId }
  const inputValid = validators.body(body); validators.body.errors = null
  if (!inputValid) throw new ConversationScopeInvalid()
  const data = await request<unknown>(`${workspace(session)}/agent/conversations`, body, session.csrf_token, signal)
  signal?.throwIfAborted()
  const valid = validators.reply(data); validators.reply.errors = null
  if (!valid) throw new ConversationScopeInvalid()
  const value = data as ScopedConversation
  const expiry = Date.parse(value.expires_at)
  if (value.class_id !== classId || value.term_id !== termId || value.student_id !== studentId
      || !Number.isFinite(expiry) || new Date(expiry).toISOString().slice(0, 19) !== value.expires_at.slice(0, 19)) {
    throw new ConversationScopeInvalid()
  }
  return value
}
