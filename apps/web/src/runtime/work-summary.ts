import type { Activity, Classroom, RecordItem, Student } from "./api.ts"
import type { Attribution } from "./durable-conversation.ts"

const date = (value: string) => Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : value
const kind: Record<string, string> = { ordinary_fact: "事实记录", teacher_observation: "教师观察", attendance_late_fact: "迟到", attendance_absent_fact: "缺勤", leave_requested_fact: "请假申请", leave_approved_fact: "请假批准", leave_returned_fact: "销假", homework_missing_fact: "作业未交", homework_submitted_fact: "作业补交", discipline_fact: "纪律记录", conversation_fact: "谈话记录" }
const state: Record<string, string> = { "not-started": "未开始", "in-progress": "进行中", waiting: "等待别人", done: "已完成", cancelled: "已取消" }
const author = (value?: Attribution) => value?.content_authority === "assistant-unverified" ? "AI 草稿，待核对" : value?.origin === "source-import" ? "导入内容" : "已登记内容"

// Presentation of an already authorized QG snapshot, never a business writer.
export function workSummary(classroom: Classroom, activity: Activity, students: readonly Student[]) {
  const latest = new Map<string, RecordItem>()
  for (const record of activity.records) {
    if (!latest.has(record.record_id) || latest.get(record.record_id)!.version < record.version)
      latest.set(record.record_id, record)
  }
  const records = [...latest.values()].sort((a, b) => a.record_id.localeCompare(b.record_id))
  const tasks = [...activity.tasks].sort((a, b) => a.task_id.localeCompare(b.task_id))
  if (records.length + tasks.length > 100) throw new Error("内容超过100项，请分批整理。")
  const names = new Map(students.map(student => [student.student_id, student.name]))
  const who = (id: string | null) => id ? `${names.get(id) || "未在当前名册"}` : "全班任务"
  // Include the complete set and content, not just references selected earlier.
  // as_of/overdue are time-derived and do not identify a stored source version.
  const basis = JSON.stringify({ classroom, records, tasks: tasks.map(({ overdue: _, ...task }) => task),
    students: [...students].sort((a, b) => a.student_id.localeCompare(b.student_id)) })
  const lines = ["班级工作小结（草稿）", `${classroom.name} · ${classroom.term_name}`,
    `更新于：${date(activity.as_of)}`, `记录 ${records.length} 项 · 跟进 ${tasks.length} 项`, "", "学生记录"]
  for (const record of records) lines.push(
    `${who(record.student_id)} · ${kind[record.kind] || "记录"} · ${date(record.occurred_at)}`,
    `事实：${record.fact_text || "无"}`, `教师观察：${record.observation_text || "无"}`,
    `来源：${author(record.attribution)}`, ...(record.revision_reason ? [`更正说明：${record.revision_reason}`] : []), "")
  lines.push("工作跟进")
  for (const task of tasks) {
    const related = task.source_record_id ? latest.get(task.source_record_id) : null
    lines.push(task.title, `对象：${who(task.student_id)} · 状态：${state[task.status]} · 截止：${task.due_at ? date(task.due_at) : "未设"}`,
      ...(related ? [`关联记录：${who(related.student_id)} · ${kind[related.kind] || "记录"} · ${date(related.occurred_at)}`] : []),
      ...(task.evidence ? [`结果说明：${task.evidence}`] : []), `来源：${author(task.attribution)}`, "")
  }
  if (!records.length && !tasks.length) lines.push("暂无记录或任务。")
  const text = lines.join("\n")
  if (text.length > 64000) throw new Error("内容超过64000字，请缩小范围后重试。")
  return { basis, text, recordCount: records.length, taskCount: tasks.length }
}
