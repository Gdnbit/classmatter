import type { Student } from "../types/student.ts"

export type SeatPlan = { changes: { studentId: string; name: string; before: string; after: string }[] }

export function validateSeats(students: Student[]): string[] {
  const issues: string[] = []
  if (new Set(students.map(s => s.id)).size !== students.length) issues.push("学生身份重复")
  if (new Set(students.map(s => s.seat)).size !== students.length) issues.push("一座多人")
  if (students.some(s => !/^[1-6]排[1-6]座$/.test(s.seat))) issues.push("座位超出当前演示布局")
  return issues
}

export function createSeatPlan(students: Student[], request: string): SeatPlan {
  if (!/(交换|互换|对调|调换|换一下|换座)/.test(request) || /不|取消|如果|假如|别|是否|能否|怎么/.test(request)) {
    throw new Error("演示仅支持明确交换两名合成学生的座位；请写明两人姓名或学号。未生成变更。")
  }
  const tokens = [...new Set(request.match(/合成学生\d+|\b99\d{3}\b/g) || [])]
  const people = tokens.map(token => students.find(s => s.name === token || s.id === token))
  const ids = [...new Set(people.map(s => s?.id))]
  if (tokens.length !== 2 || people.some(s => !s) || ids.length !== 2) throw new Error("请准确指定两名不同的合成学生。未生成变更。")
  const expression = tokens.reduce((text, token) => text.split(token).join("人"), request).replace(/[\s，。！、,!.]/g, "")
  if (!/^(?:请|帮我|请帮我)?(?:(?:交换|互换|对调|调换)人(?:和|与)人(?:的)?座位|把人(?:和|与)人(?:的座位)?(?:交换|互换|对调|调换|换一下)(?:座位)?)(?:先给我预览|先预览)?$/.test(expression)) {
    throw new Error("此演示未理解附加条件。请使用“交换合成学生01和合成学生02的座位，先给我预览”；未生成变更。")
  }
  const issues = validateSeats(students)
  if (issues.length) throw new Error(issues.join("；"))
  const [a, b] = people as Student[]
  return { changes: [
    { studentId: a.id, name: a.name, before: a.seat, after: b.seat },
    { studentId: b.id, name: b.name, before: b.seat, after: a.seat },
  ] }
}

export function projectSeatPlan(students: Student[], plan: SeatPlan): Student[] {
  if (plan.changes.length !== 2 || new Set(plan.changes.map(c => c.studentId)).size !== 2) throw new Error("草稿对象无效")
  for (const c of plan.changes) {
    const student = students.find(s => s.id === c.studentId)
    if (!student || student.name !== c.name || student.seat !== c.before) throw new Error("当前数据已变化，请重新生成预览")
  }
  const [a, b] = plan.changes
  if (a.after !== b.before || b.after !== a.before) throw new Error("草稿不是两人座位交换")
  const projected = students.map(s => ({ ...s, seat: plan.changes.find(c => c.studentId === s.id)?.after || s.seat }))
  const issues = validateSeats(projected)
  if (issues.length) throw new Error(issues.join("；"))
  return projected
}
