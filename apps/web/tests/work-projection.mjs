import test from 'node:test'
import assert from 'node:assert/strict'
import { projectAttention, filterWorkTasks } from '../src/runtime/work-projection.ts'

const tasks = [
  { task_id: '1', student_id: 's1', status: 'not-started' },
  { task_id: '2', student_id: 's2', status: 'waiting', overdue: true },
  { task_id: '3', student_id: null, status: 'in-progress' },
  { task_id: '4', student_id: 's1', status: 'done' },
  { task_id: '5', student_id: 's2', status: 'cancelled' },
]
const ids = values => values.map(value => value.task_id)
test('class attention partitions open tasks once, irrespective of student views', () => {
  const view = projectAttention(tasks)
  assert.deepEqual(ids(view.open), ['1', '2', '3'])
  assert.deepEqual(ids(view.needsAction), ['1', '3'])
  assert.deepEqual(ids(view.waiting), ['2']) // Overdue waiting is still waiting, not inferred handoff.
  assert.equal(new Set([...view.needsAction, ...view.waiting].map(t => t.task_id)).size, view.open.length)
  assert.deepEqual(projectAttention([]), { open: [], needsAction: [], waiting: [] })
})
test('work filters intersect explicit identity and status without fallback', () => {
  assert.deepEqual(ids(filterWorkTasks(tasks, 's1', 'all')), ['1', '4'])
  assert.deepEqual(ids(filterWorkTasks(tasks, '', 'open')), ['1', '2', '3'])
  assert.deepEqual(ids(filterWorkTasks(tasks, '', 'closed')), ['4', '5'])
  assert.deepEqual(ids(filterWorkTasks(tasks, 's2', 'waiting')), ['2'])
  assert.deepEqual(filterWorkTasks(tasks, 's1', 'waiting'), [])
  assert.deepEqual(filterWorkTasks(tasks, 'unknown', 'all'), [])
  assert.deepEqual(ids(tasks), ['1', '2', '3', '4', '5'])
})
