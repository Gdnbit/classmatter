import { adjust, solve } from "./solver.mjs"
const byId = id => document.getElementById(id)
const form = byId("settings"), seats = byId("seats"), errors = byId("errors"), status = byId("status")
const sample = Object.fromEntries([...form.querySelectorAll("input,textarea")].map(node => [node.id, node.value]))
let config = null, current = null, solutions = [], history = [], selected = null, candidateIndex = 0
const lines = value => value.split(/\r?\n/).map(line => line.trim()).filter(Boolean)
function mapping(value) {
  const entries = lines(value).map(line => line.split("=").map(part => part.trim()))
  if (entries.some(parts => parts.length !== 2 || !parts[0] || !parts[1]) || new Set(entries.map(parts => parts[0])).size !== entries.length) throw new Error("座位映射请使用每行 ID=排-列，且 ID 不重复")
  return entries
}
function readConfig() {
  return { rows: Number(byId("rows").value), columns: Number(byId("columns").value), students: lines(byId("students").value),
    blocked: byId("blocked").value.split(/[,，\s]+/).filter(Boolean),
    fixed: mapping(byId("fixed").value).map(([student, seat]) => ({ student, seat })),
    apart: lines(byId("apart").value).map(line => line.split(/[,，]/).map(part => part.trim())), previous: Object.fromEntries(mapping(byId("previous").value)) }
}
function error(message) { errors.hidden = !message; errors.textContent = message || "" }
function setStatus(message) { status.textContent = message }
function position(seat) { return seat ? seat.replace("-", "排 ") + "座" : "未安排" }
function focusSeat(seat) { seats.querySelector(`[data-seat="${seat}"]`)?.focus() }
function move(student, seat) {
  try {
    const next = adjust(readConfig(), current, student, seat)
    history.push(current); current = next; selected = null; error("")
    render(); focusSeat(seat); setStatus(`人工调整已预览，${current.changes.length}名学生与原方案不同。尚未保存正式分配。`)
  } catch (cause) { error(cause.message); selected = null; render(); focusSeat(seat) }
}
function choose(seat, student) {
  if (selected && current) { move(selected, seat); return }
  if (!student) { setStatus("这是空位；请先点选一名学生。"); return }
  selected = student; render(); focusSeat(seat); setStatus(`已选 ${student}，请选择目标座位；也可再次选择原位取消。`)
}
function render() {
  const rows = config?.rows || Number(byId("rows").value) || 3, columns = config?.columns || Number(byId("columns").value) || 4
  seats.style.setProperty("--columns", Math.min(8, Math.max(1, columns)))
  seats.replaceChildren()
  if (rows * columns <= 48 && rows > 0 && columns > 0) {
    for (let row = 1; row <= rows; row++) for (let column = 1; column <= columns; column++) {
      const seat = `${row}-${column}`, student = current ? Object.keys(current.assignment).find(id => current.assignment[id] === seat) : null
      const blocked = config?.blocked.includes(seat), fixed = config?.fixed.some(item => item.student === student)
      const changed = current?.changes.some(item => item.student === student)
      const button = document.createElement("button")
      button.type = "button"; button.dataset.seat = seat
      button.className = `seat${blocked ? " blocked" : ""}${changed ? " changed" : ""}`
      button.disabled = !current || blocked
      button.setAttribute("aria-label", `${position(seat)} ${blocked ? "不可用" : student || "空位"}${fixed ? " 固定" : ""}`)
      button.setAttribute("aria-pressed", String(Boolean(selected && selected === student)))
      const coord = document.createElement("span"); coord.className = "position"; coord.textContent = position(seat)
      const label = document.createElement("strong"); label.textContent = blocked ? "不可用" : student || "空位"
      const note = document.createElement("span"); note.className = "note"; note.textContent = fixed ? "固定座位" : changed ? "预览调整" : current ? "" : "待生成"
      button.append(coord, label, note)
      button.addEventListener("click", () => choose(seat, student))
      button.draggable = Boolean(student && !blocked && !fixed)
      button.addEventListener("dragstart", event => { event.dataTransfer.setData("text/plain", student); selected = student })
      button.addEventListener("dragover", event => { if (current && !blocked) event.preventDefault() })
      button.addEventListener("drop", event => { event.preventDefault(); const person = event.dataTransfer.getData("text/plain"); if (current) move(person, seat) })
      button.addEventListener("dragend", () => { selected = null })
      seats.append(button)
    }
  }
  byId("undo").disabled = !history.length
  byId("diff").replaceChildren()
  for (const change of current?.changes || []) {
    const tr = document.createElement("tr")
    for (const text of [change.student, position(change.before), position(change.after)]) { const td = document.createElement("td"); td.textContent = text; tr.append(td) }
    byId("diff").append(tr)
  }
  byId("diff-summary").textContent = current ? `${current.changes.length}名学生与当前方案不同。硬约束全部通过；移动人数仅为候选评分，不承诺全局最优。` : "生成候选后显示每位学生的移动位置。"
  byId("candidates").replaceChildren()
  solutions.forEach((solution, index) => {
    const button = document.createElement("button"); button.type = "button"
    button.textContent = `方案 ${index + 1} · ${solution.changes.length}人调整`
    button.setAttribute("aria-pressed", String(index === candidateIndex))
    button.addEventListener("click", () => { current = solution; candidateIndex = index; history = []; selected = null; error(""); render(); setStatus(`已显示方案 ${index + 1}，仅为预览草稿。`) })
    byId("candidates").append(button)
  })
}
form.addEventListener("submit", event => {
  event.preventDefault(); current = null; solutions = []; history = []; selected = null; error("")
  try {
    config = readConfig()
    const result = solve(config, { maxNodes: 20000, maxSolutions: 3 })
    if (result.status === "solved") {
      solutions = result.solutions; current = solutions[0]; candidateIndex = 0
      setStatus(`已生成 ${solutions.length}个候选，固定与不可相邻条件全部满足。请核对后人工调整。`)
    } else { error(result.reasons.join("；")); setStatus(result.status === "search_limited" ? "搜索尚不能判定，请调整条件后重试。" : "尚未生成可行方案，请核对左侧条件。") }
  } catch (cause) { error(cause.message); setStatus("配置未通过校验，请修正后重新生成。") }
  render()
})
form.addEventListener("input", () => { config = null; current = null; solutions = []; history = []; selected = null; error(""); setStatus("配置已更改，请重新生成候选；旧方案已失效。"); render() })
byId("undo").addEventListener("click", () => { if (history.length) { current = history.pop(); selected = null; error(""); render(); setStatus("已撤销上次人工调整；仍未保存正式分配。") } })
byId("reset").addEventListener("click", () => { for (const [id, value] of Object.entries(sample)) byId(id).value = value; config = null; current = null; solutions = []; history = []; selected = null; error(""); render(); setStatus("已恢复合成示例，请重新生成候选。") })
render()
