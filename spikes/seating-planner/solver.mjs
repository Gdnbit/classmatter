// Synthetic-only deterministic bounded CSP. No product store or assignment writer.
const id = value => typeof value === "string" && /^[A-Za-z0-9_-]{1,40}$/.test(value) && !Object.hasOwn(Object.prototype, value) && value !== "prototype"
const object = value => value && Object.getPrototypeOf(value) === Object.prototype
const fail = reason => { throw new Error(reason) }

export function normalize(input) {
  if (!object(input) || Object.keys(input).some(key => !["rows", "columns", "students", "blocked", "fixed", "apart", "previous"].includes(key))) fail("配置字段不受支持")
  const { rows, columns, students, blocked = [], fixed = [], apart = [], previous = {} } = input
  if (![rows, columns].every(value => Number.isInteger(value) && value >= 1 && value <= 8) || rows * columns > 48) fail("布局须为1至8排/列，最多48个座位")
  if (!Array.isArray(students) || students.length < 1 || students.length > 20 || !students.every(id) || new Set(students).size !== students.length) fail("请提供1至20个不重复的合成学生ID")
  const people = [...students].sort()
  const seats = Array.from({ length: rows * columns }, (_, index) => `${Math.floor(index / columns) + 1}-${index % columns + 1}`)
  if (!Array.isArray(blocked) || new Set(blocked).size !== blocked.length || blocked.some(seat => !seats.includes(seat))) fail("不可用座位重复或超出布局")
  if (!Array.isArray(fixed) || fixed.length > people.length || fixed.some(value => !object(value) || Object.keys(value).sort().join() !== "seat,student" || !people.includes(value.student) || !seats.includes(value.seat))) fail("固定座位必须引用有效学生与座位")
  if (new Set(fixed.map(value => value.student)).size !== fixed.length) fail("同一学生不能固定两次")
  if (!Array.isArray(apart) || apart.length > 190 || apart.some(pair => !Array.isArray(pair) || pair.length !== 2 || pair[0] === pair[1] || pair.some(person => !people.includes(person)))) fail("不可相邻约束须指定两名不同的现有学生")
  if (!object(previous) || Object.keys(previous).some(person => !people.includes(person)) || Object.values(previous).some(seat => !seats.includes(seat)) || new Set(Object.values(previous)).size !== Object.keys(previous).length) fail("当前方案存在未知学生、无效座位或一座多人")
  const normalized = {
    rows, columns, students: people, blocked: [...blocked].sort(),
    fixed: fixed.map(value => ({ student: value.student, seat: value.seat })).sort((a, b) => a.student < b.student ? -1 : 1),
    apart: [...new Map(apart.map(pair => { const sorted = [...pair].sort(); return [sorted.join(":"), sorted] })).values()].sort((a, b) => a.join(":") < b.join(":") ? -1 : 1),
    previous: Object.fromEntries(Object.keys(previous).sort().map(person => [person, previous[person]])),
  }
  return normalized
}

export function adjacent(left, right) {
  const [lr, lc] = left.split("-").map(Number), [rr, rc] = right.split("-").map(Number)
  return Math.abs(lr - rr) + Math.abs(lc - rc) === 1
}

function available(config) {
  return Array.from({ length: config.rows * config.columns }, (_, index) => `${Math.floor(index / config.columns) + 1}-${index % config.columns + 1}`).filter(seat => !config.blocked.includes(seat))
}

export function violations(input, assignment, { partial = false } = {}) {
  const config = normalize(input)
  if (!object(assignment)) return ["方案格式无效"]
  const issues = [], seats = available(config)
  if (Object.keys(assignment).some(person => !config.students.includes(person))) issues.push("方案包含未知学生")
  if (!partial && config.students.some(person => !(person in assignment))) issues.push("方案缺少学生")
  if (Object.values(assignment).some(seat => !seats.includes(seat))) issues.push("座位不可用或越界")
  if (new Set(Object.values(assignment)).size !== Object.keys(assignment).length) issues.push("一座多人")
  for (const fixed of config.fixed) {
    if (fixed.student in assignment && assignment[fixed.student] !== fixed.seat) issues.push(`${fixed.student}的固定座位不能改变`)
  }
  for (const [left, right] of config.apart) {
    if (assignment[left] && assignment[right] && adjacent(assignment[left], assignment[right])) issues.push(`${left}与${right}不可上下左右相邻`)
  }
  return issues
}

export function plan(input, assignment) {
  const config = normalize(input), issues = violations(config, assignment)
  if (issues.length) fail(issues.join("；"))
  const ordered = Object.fromEntries(config.students.map(student => [student, assignment[student]]))
  const changes = config.students.filter(student => config.previous[student] !== ordered[student]).map(student => ({ student, before: config.previous[student] ?? null, after: ordered[student] }))
  return Object.freeze({ basis: JSON.stringify(config), assignment: Object.freeze(ordered), changes: Object.freeze(changes.map(Object.freeze)),
    score: Object.freeze({ moved: changes.length, rule: "minimize_changes.v1", optimality: "not_claimed" }) })
}

export function adjust(input, current, student, target) {
  const config = normalize(input)
  if (!current || current.basis !== JSON.stringify(config)) fail("配置或来源已变化，请重新生成候选")
  if (violations(config, current.assignment).length) fail("当前候选已无效，请重新生成")
  if (!config.students.includes(student) || !available(config).includes(target)) fail("请选择有效学生与可用座位")
  const assignment = { ...current.assignment }
  const occupant = config.students.find(person => assignment[person] === target)
  const before = assignment[student]
  assignment[student] = target
  if (occupant && occupant !== student) assignment[occupant] = before
  return plan(config, assignment) // All hard constraints rechecked before any new preview.
}

export function solve(input, { maxNodes = 20000, maxSolutions = 3 } = {}) {
  if (!Number.isInteger(maxNodes) || maxNodes < 1 || maxNodes > 50000 || !Number.isInteger(maxSolutions) || maxSolutions < 1 || maxSolutions > 5) fail("搜索预算无效")
  let config
  try { config = normalize(input) } catch (error) { return { status: "invalid", reasons: [error.message], solutions: [] } }
  const seats = available(config), assignment = Object.fromEntries(config.fixed.map(value => [value.student, value.seat]))
  if (config.students.length > seats.length) return { status: "unsatisfiable", reasons: [`座位不足：${config.students.length}名学生，仅${seats.length}个可用位置`], solutions: [] }
  const fixedIssues = violations(config, assignment, { partial: true })
  if (fixedIssues.length) return { status: "unsatisfiable", reasons: fixedIssues, solutions: [] }
  const found = [], used = new Set(Object.values(assignment))
  let nodes = 0, stop = null
  const allowed = (student, seat) => config.apart.every(([left, right]) => {
    const peer = student === left ? right : student === right ? left : null
    return !peer || !assignment[peer] || !adjacent(seat, assignment[peer])
  })
  const search = () => {
    if (nodes >= maxNodes) { stop = "search_limit"; return }
    nodes++
    if (Object.keys(assignment).length === config.students.length) {
      found.push(plan(config, assignment))
      if (found.length === maxSolutions) stop = "candidate_limit"
      return
    }
    const domains = config.students.filter(student => !(student in assignment)).map(student => ({ student, seats: seats.filter(seat => !used.has(seat) && allowed(student, seat)) }))
    domains.sort((a, b) => a.seats.length - b.seats.length || (a.student < b.student ? -1 : 1))
    const selected = domains[0]
    selected.seats.sort((a, b) => Number(b === config.previous[selected.student]) - Number(a === config.previous[selected.student]))
    for (const seat of selected.seats) {
      assignment[selected.student] = seat; used.add(seat)
      search()
      used.delete(seat); delete assignment[selected.student]
      if (stop) return
    }
  }
  search()
  found.sort((a, b) => a.score.moved - b.score.moved || (JSON.stringify(a.assignment) < JSON.stringify(b.assignment) ? -1 : 1))
  return { status: found.length ? "solved" : stop === "search_limit" ? "search_limited" : "unsatisfiable",
    reasons: found.length ? [] : [stop === "search_limit" ? "搜索预算已用尽，尚不能判定是否有解；请简化约束后重试" : "当前不可相邻约束组合无可行方案；请人工核对约束"],
    solutions: found, search: { nodes, complete: stop === null, stop }, rule: "orthogonal_adjacency.v1" }
}
