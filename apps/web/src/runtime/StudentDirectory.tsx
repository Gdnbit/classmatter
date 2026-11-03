import type { Activity, Student } from "./api"
import { studentRows } from "./student-directory"
import "./student-directory.css"
import { StudentRosterTable } from "@/shell/StudentPresentation"

// Both views consume the same authorized snapshot; no mock, local cache or
// writes. Only the available R1 fields are shown, not invented grades/traits.
export function StudentDirectory({ students, activity, selectedId, view, disabled, onSelect }: {
  students: Student[]
  activity: Activity | null
  selectedId: string
  view: "list" | "table"
  disabled: boolean
  onSelect: (id: string) => void
}) {
  return <div className="r1-directory-table" role="region" aria-label={view === "table" ? "学生表格" : "学生清单"} tabIndex={0}>
    <StudentRosterTable columns={["学生", "内部 ID", "当前工作", "状态 / 版本"]}
      rows={studentRows(students, activity?.records || [], activity?.tasks || []).map(row => ({
        id: row.student.student_id, name: row.student.name,
        cells: [row.student.student_id, `${row.recordCount} 条记录 · ${row.openTaskCount} 项未结束跟进`,
          `版本 ${row.student.version} · ${row.student.status === "inactive" ? "已停用（历史可查）" : "在班"}`],
      }))} selectedId={selectedId} disabled={disabled} onSelect={onSelect} />
  </div>
}
