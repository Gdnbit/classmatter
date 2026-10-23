import type { Activity, Student } from "./api"
import { studentRows } from "./student-directory"
import "./student-directory.css"

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
  if (view === "table") return <div className="r1-directory-table" role="region" aria-label="学生表格" tabIndex={0}>
    <table><thead><tr><th scope="col">学生</th><th scope="col">状态 / 版本</th><th scope="col">当前记录</th><th scope="col">未结束跟进</th></tr></thead>
      <tbody>{studentRows(students, activity?.records || [], activity?.tasks || []).map(row => <tr key={row.student.student_id}>
        <td><button disabled={disabled} aria-pressed={row.student.student_id === selectedId} onClick={() => onSelect(row.student.student_id)}>
          <strong>{row.student.name}</strong><small>{row.student.student_id.slice(0, 8)}</small></button></td>
        <td>{row.student.status === "inactive" ? "已停用（历史可查）" : "在班"} · v{row.student.version}</td>
        <td>{row.recordCount}</td><td>{row.openTaskCount}</td>
      </tr>)}</tbody></table>
  </div>
  return <>{students.map(item => <button key={item.student_id} disabled={disabled} aria-pressed={selectedId === item.student_id} onClick={() => onSelect(item.student_id)}>
    <strong>{item.name}</strong><small>版本 {item.version} · {item.student_id.slice(0, 8)}{item.status === "inactive" ? " · 已停用（历史可查）" : ""}</small>
  </button>)}</>
}
