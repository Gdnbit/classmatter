import type { TaskItem } from "./api.ts"
import { isOpenTask } from "./student-directory.ts"

export type WorkFilter = "all" | "open" | "waiting" | "closed"

// Input is already authorized for one class/term. These are views, not a
// responsibility assignment, reminder engine or new source of business truth.
export function projectAttention(tasks: readonly TaskItem[]) {
  const open = tasks.filter(isOpenTask)
  return {
    open,
    needsAction: open.filter(task => task.status !== "waiting"),
    waiting: open.filter(task => task.status === "waiting"),
  }
}

export function filterWorkTasks(tasks: readonly TaskItem[], studentId: string, filter: WorkFilter): TaskItem[] {
  return tasks.filter(task =>
    (!studentId || task.student_id === studentId) &&
    (filter === "all" ||
      (filter === "open" && isOpenTask(task)) ||
      (filter === "waiting" && task.status === "waiting") ||
      (filter === "closed" && !isOpenTask(task))),
  )
}
