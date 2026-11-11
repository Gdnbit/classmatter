import assert from "node:assert/strict"
import test from "node:test"
import { adjust, adjacent, normalize, plan, solve, violations } from "./solver.mjs"

const base = () => ({ rows: 2, columns: 3, students: ["S001", "S002", "S003"], blocked: [], fixed: [], apart: [], previous: { S001: "1-1", S002: "1-2", S003: "1-3" } })
test("reproducible candidates preserve all hard constraints and source input", () => {
  const input = base(), before = JSON.stringify(input)
  const first = solve(input)
  assert.deepEqual(first, solve(input)); assert.equal(first.status, "solved")
  assert.equal(first.solutions.length, 3)
  for (const item of first.solutions) assert.deepEqual(violations(input, item.assignment), [])
  assert.equal(JSON.stringify(input), before)
  assert.equal(first.solutions[0].score.moved, 0)
})
test("adjacency means orthogonal neighbors only", () => {
  assert.equal(adjacent("1-1", "1-2"), true); assert.equal(adjacent("1-1", "2-1"), true)
  assert.equal(adjacent("1-1", "2-2"), false); assert.equal(adjacent("1-1", "1-3"), false)
})
test("unavailable seats, fixed student and apart pairs respected", () => {
  const input = { ...base(), blocked: ["2-3"], fixed: [{ student: "S001", seat: "1-1" }], apart: [["S002", "S003"]] }
  const result = solve(input)
  assert.equal(result.status, "solved")
  for (const item of result.solutions) {
    assert.equal(item.assignment.S001, "1-1"); assert.ok(!Object.values(item.assignment).includes("2-3"))
    assert.equal(adjacent(item.assignment.S002, item.assignment.S003), false)
  }
})
test("seat shortage is an explained unsatisfiable condition", () => {
  const result = solve({ ...base(), rows: 1, columns: 2, previous: {} })
  assert.equal(result.status, "unsatisfiable"); assert.match(result.reasons[0], /座位不足/)
})
test("fixed collisions, blocked seats and adjacent fixed pairs explain conflict", () => {
  for (const input of [
    { ...base(), fixed: [{ student: "S001", seat: "1-1" }, { student: "S002", seat: "1-1" }] },
    { ...base(), blocked: ["1-1"], fixed: [{ student: "S001", seat: "1-1" }] },
    { ...base(), fixed: [{ student: "S001", seat: "1-1" }, { student: "S002", seat: "1-2" }], apart: [["S001", "S002"]] },
  ]) { const result = solve(input); assert.equal(result.status, "unsatisfiable"); assert.ok(result.reasons.length) }
})
test("actual exhaustive no-solution distinct from search budget", () => {
  const input = { rows: 1, columns: 2, students: ["S001", "S002"], apart: [["S001", "S002"]] }
  assert.equal(solve(input).status, "unsatisfiable")
  const limited = solve(base(), { maxNodes: 1 })
  assert.equal(limited.status, "search_limited"); assert.equal(limited.search.complete, false)
})
test("manual move to empty seat and swap validate and preserve baseline diff", () => {
  const input = base(), original = plan(input, input.previous)
  const moved = adjust(input, original, "S001", "2-1")
  assert.equal(moved.assignment.S001, "2-1"); assert.equal(moved.changes[0].before, "1-1")
  const swapped = adjust(input, original, "S001", "1-2")
  assert.equal(swapped.assignment.S002, "1-1"); assert.equal(swapped.score.moved, 2)
  assert.equal(original.assignment.S001, "1-1")
})
test("manual swap cannot override fixed or apart constraints", () => {
  const fixed = { ...base(), fixed: [{ student: "S001", seat: "1-1" }] }
  assert.throws(() => adjust(fixed, plan(fixed, fixed.previous), "S001", "2-1"), /固定/)
  const input = { ...base(), apart: [["S001", "S002"]] }
  const original = plan(input, { S001: "1-1", S002: "1-3", S003: "2-3" })
  assert.throws(() => adjust(input, original, "S002", "1-2"), /不可/)
})
test("stale config and corrupted plans cannot be manually adjusted", () => {
  const input = base(), original = plan(input, input.previous)
  assert.throws(() => adjust({ ...input, blocked: ["2-3"] }, original, "S001", "2-1"), /变化/)
  assert.throws(() => adjust(input, { ...original, assignment: { S001: "1-1" } }, "S001", "2-1"), /无效/)
})
test("invalid layout, identities, unknown constraints and sensitive fields refused", () => {
  for (const changed of [{ rows: 0 }, { columns: 1.5 }, { students: ["S001", "S001"] }, { students: [] },
    { blocked: ["9-9"] }, { apart: [["S001", "UNKNOWN"]] }, { sensitiveInference: "forbidden" },
    { previous: { S001: "1-1", S002: "1-1" } }]) assert.equal(solve({ ...base(), ...changed }).status, "invalid")
})
test("partial and complete assignment validation are distinct", () => {
  assert.deepEqual(violations(base(), { S001: "1-1" }, { partial: true }), [])
  assert.ok(violations(base(), { S001: "1-1" }).includes("方案缺少学生"))
  assert.ok(violations(base(), { ...base().previous, unknown: "2-1" }).length)
})
test("normalized ordering and duplicate pair notation do not change result", () => {
  const input = { ...base(), apart: [["S002", "S003"]] }
  const reordered = { ...input, students: [...input.students].reverse(), apart: [["S003", "S002"], ["S002", "S003"]] }
  assert.deepEqual(solve(input), solve(reordered)); assert.deepEqual(normalize(input), normalize(reordered))
})
test("budgets bounded and never claim optimality from candidate limit", () => {
  assert.throws(() => solve(base(), { maxNodes: 0 }), /预算/)
  assert.throws(() => solve(base(), { maxSolutions: 6 }), /预算/)
  const result = solve(base(), { maxSolutions: 1 })
  assert.equal(result.search.stop, "candidate_limit")
  assert.equal(result.solutions[0].score.optimality, "not_claimed")
})
test("immutable candidate projection cannot accidentally mutate prior plan", () => {
  const current = solve(base()).solutions[0]
  assert.throws(() => { current.assignment.S001 = "2-1" }, TypeError)
  assert.throws(() => { current.changes.push({}) }, TypeError)
})
test("prototype-property IDs cannot corrupt assignment bookkeeping", () => {
  for (const student of ["__proto__", "constructor", "toString", "prototype"]) assert.equal(solve({ ...base(), students: [student], previous: {} }).status, "invalid")
})
