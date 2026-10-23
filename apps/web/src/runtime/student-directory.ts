import type { Student, TaskItem, RecordItem } from "./api.ts"

// Presentation-only projections of an already authorized, current-scope query.
// A name match never selects or merges an identity. No fixture fallback/cache.
export function searchStudents(students: readonly Student[], query: string): Student[] {
  const needle = query.trim().normalize("NFC").toLocaleLowerCase("zh-CN")
  return students.filter(student =>
    !needle || [student.name, student.student_id].some(value =>
      value.normalize("NFC").toLocaleLowerCase("zh-CN").includes(needle),
    ),
  )
}

export function studentFollowUps(tasks: readonly TaskItem[], studentId: string): TaskItem[] {
  // Missing identity must not expose a class-wide list in a student's summary.
  return studentId ? tasks.filter(task => task.student_id === studentId) : []
}

export function isOpenTask(task: TaskItem): boolean {
  return task.status !== "done" && task.status !== "cancelled"
}

export function studentRows(students: readonly Student[], records: readonly RecordItem[], tasks: readonly TaskItem[]) {
  const facts = new Map<string, Set<string>>()
  const followUps = new Map<string, number>()
  for (const record of records) {
    const ids = facts.get(record.student_id) || new Set<string>()
    ids.add(record.record_id) // Corrections do not become additional facts.
    facts.set(record.student_id, ids)
  }
  for (const task of tasks) {
    if (task.student_id && isOpenTask(task)) followUps.set(task.student_id, (followUps.get(task.student_id) || 0) + 1)
  }
  return students.map(student => ({ student, recordCount: facts.get(student.student_id)?.size || 0, openTaskCount: followUps.get(student.student_id) || 0 }))
}
