import * as validators from './classroom-work-validators.cjs'
import { ApiError, workspace, type Session } from './api'

type Scope = { class_id: string; term_id: string }
export type ClassroomCommand = Scope & (
  { command: 'exam.create'; exam_id: string; title: string; subject: string; maximum_score: string }
  | { command: 'score.record'; exam_id: string; student_id: string; expected_version: number; status: ScoreStatus; score: string | null; reason: string }
  | { command: 'seat.layout.create'; layout_id: string; rows: number; columns: number }
  | { command: 'seat.assign'; layout_id: string; student_id: string; expected_version: number; row: number; column: number }
  | { command: 'seat.swap'; layout_id: string; expected_version: number; first_row: number; first_column: number; second_row: number; second_column: number })
export type ScoreStatus = 'scored' | 'absent' | 'exempt' | 'not-recorded'
export type Exam = { exam_id: string; title: string; subject: string; maximum_score: string; version: number }
export type Result = { student_id: string; version: number; status: ScoreStatus; score: string | null; reason: string; created_at: string }
export type ExamResults = Exam & { results: Result[]; scored_count: number; average: string | null }
export type Seating = { layout_id: string; rows: number; columns: number; version: number; seats: { row_index: number; column_index: number; student_id: string | null }[] }
export type ClassroomPreview = { schema_version: 'classmatter.classroom-preview.v1'; proposal_id: string; payload_hash: string; risk: 'W2'; expires_at: string; payload: ClassroomCommand }
const uuid = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/
function id(value: string) { if (!uuid.test(value)) throw new Error('未找到所选数据'); return value }
function cents(value: string): bigint {
  if (!/^(?:0|[1-9][0-9]{0,5})(?:\.[0-9]{1,2})?$/.test(value)) throw new Error('成绩内容无效，请重新读取')
  const [whole, fraction = ''] = value.split('.')
  return BigInt(whole) * 100n + BigInt((fraction + '00').slice(0, 2))
}
async function read<T>(kind: 'capabilities' | 'listing' | 'results' | 'seating' | 'preview', path: string, session: Session, signal?: AbortSignal, command?: ClassroomCommand): Promise<T> {
  const response = await fetch(path, { method: command ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store', redirect: 'error', signal,
    headers: command ? { 'content-type': 'application/json', 'x-class-os-csrf': session.csrf_token } : {}, body: command ? JSON.stringify(command) : undefined })
  if (!response.ok) throw new ApiError(response.status, response.headers.get('x-request-id') || '')
  if (!response.headers.get('content-type')?.startsWith('application/json') || !response.body) throw new Error('读取失败，请重试')
  const reader = response.body.getReader(), decoder = new TextDecoder('utf-8', { fatal: true })
  let raw = '', length = 0
  try { while (true) { const part = await reader.read(); signal?.throwIfAborted(); if (part.done) break
    length += part.value.byteLength; if (length > 4 * 1024 * 1024) throw new Error('内容过多，请缩小范围'); raw += decoder.decode(part.value, { stream: true }) }
    raw += decoder.decode()
  } finally { await reader.cancel().catch(() => {}); reader.releaseLock() }
  signal?.throwIfAborted()
  const value = JSON.parse(raw), valid = validators[kind](value); validators[kind].errors = null
  if (!valid) throw new Error('读取失败，请刷新后重试')
  return value as T
}
export async function classroomAvailable(session: Session, signal?: AbortSignal) {
  try { await read('capabilities', `${workspace(session)}/classroom-work/capabilities`, session, signal); return true }
  catch (error) { if (error instanceof ApiError && error.status === 404) return false; throw error }
}
export function classroomClient(session: Session, scope: Scope) {
  const root = `${workspace(session)}/classes/${id(scope.class_id)}/terms/${id(scope.term_id)}`
  return {
    exams: async (signal?: AbortSignal) => {
      const value = await read<{exams: Exam[]; truncated: boolean}>('listing', root + '/exams', session, signal)
      if (new Set(value.exams.map(exam => exam.exam_id)).size !== value.exams.length || value.exams.some(exam => cents(exam.maximum_score) <= 0n)) throw new Error('考试内容无效，请重新读取')
      return value
    },
    results: async (exam: string, signal?: AbortSignal) => {
      const value = await read<ExamResults>('results', root + `/exams/${id(exam)}`, session, signal)
      if (value.exam_id !== exam) throw new Error('所选考试已变化，请重新打开')
      const maximum = cents(value.maximum_score)
      if (new Set(value.results.map(row => row.student_id)).size !== value.results.length
          || value.scored_count !== value.results.filter(row => row.status === 'scored').length
          || value.results.some(row => (row.status === 'scored') !== (row.score !== null) || row.score !== null && cents(row.score) > maximum)
          || (value.average === null) !== (value.scored_count === 0) || value.average !== null && cents(value.average) > maximum
          || value.results.some(row => !Number.isFinite(new Date(row.created_at).getTime()))) throw new Error('成绩内容无效，请重新读取')
      return value
    },
    seating: async (signal?: AbortSignal) => {
      const value = await read<{layout: Seating | null}>('seating', root + '/seating', session, signal)
      const layout = value.layout
      if (layout && (layout.seats.length !== layout.rows * layout.columns
          || new Set(layout.seats.map(cell => `${cell.row_index}/${cell.column_index}`)).size !== layout.seats.length
          || layout.seats.some(cell => cell.row_index > layout.rows || cell.column_index > layout.columns)
          || new Set(layout.seats.filter(cell => cell.student_id).map(cell => cell.student_id)).size !== layout.seats.filter(cell => cell.student_id).length)) throw new Error('座位内容无效，请重新读取')
      return value
    },
    preview: async (command: ClassroomCommand) => {
      if (command.class_id !== scope.class_id || command.term_id !== scope.term_id) throw new Error('班级已变化，请重新操作')
      const value = await read<ClassroomPreview>('preview', `${workspace(session)}/classroom-commands/preview`, session, undefined, command)
      if (Object.keys(value.payload).length !== Object.keys(command).length || Object.entries(command).some(([key, item]) => value.payload[key as keyof ClassroomCommand] !== item)) throw new Error('预览已变化，请重新操作')
      return value
    },
  }
}
