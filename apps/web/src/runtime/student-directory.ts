import type { Student, TaskItem } from "./api.ts"

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
