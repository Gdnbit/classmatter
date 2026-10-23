import test from 'node:test'
import assert from 'node:assert/strict'
import { searchStudents, studentFollowUps, isOpenTask, studentRows } from '../src/runtime/student-directory.ts'

test('list/table use one identity snapshot; revisions count once and class/closed work is excluded', () => {
  const students = [{ student_id: 's1', name: '同名', status: 'active', version: 2 }, { student_id: 's2', name: '同名', status: 'inactive', version: 1 }]
  const records = [{ student_id: 's1', record_id: 'r1', version: 1 }, { student_id: 's1', record_id: 'r1', version: 2 }, { student_id: 'other', record_id: 'r2', version: 1 }]
  const tasks = [{ student_id: 's1', status: 'waiting' }, { student_id: 's1', status: 'done' }, { student_id: null, status: 'not-started' }, { student_id: 's2', status: 'cancelled' }]
  const before = JSON.stringify({ students, records, tasks })
  const rows = studentRows(students, records, tasks)
  assert.deepEqual(rows.map(row => [row.student.student_id, row.recordCount, row.openTaskCount]), [['s1', 1, 1], ['s2', 0, 0]])
  assert.equal(rows[0].student, students[0])
  assert.deepEqual(studentRows([], records, tasks), [])
  assert.equal(JSON.stringify({ students, records, tasks }), before)
})

const students = [
  { student_id: 'abcd-001', name: '同名学生', status: 'active', version: 1 },
  { student_id: 'abcd-002', name: '同名学生', status: 'inactive', version: 2 },
  { student_id: 'efgh-003', name: '另一个学生', status: 'active', version: 1 },
]
test('name search preserves duplicate identities and inactive history', () => {
  assert.deepEqual(searchStudents(students, ' 同名 '), students.slice(0, 2))
  assert.deepEqual(searchStudents(students, ' ABCD-002 '), [students[1]])
  assert.deepEqual(searchStudents(students, '不存在'), [])
  assert.deepEqual(searchStudents(students, '  '), students)
  assert.deepEqual(searchStudents([], '同名'), [])
  assert.equal(students.length, 3)
})
test('follow-up projection never substitutes missing identity or class tasks', () => {
  const tasks = [
    { task_id: '1', student_id: 'abcd-001', status: 'waiting' },
    { task_id: '2', student_id: 'abcd-001', status: 'done' },
    { task_id: '3', student_id: 'abcd-002', status: 'in-progress' },
    { task_id: '4', student_id: null, status: 'not-started' },
    { task_id: '5', student_id: 'abcd-001', status: 'cancelled' },
  ]
  assert.deepEqual(studentFollowUps(tasks, 'abcd-001').map(t => t.task_id), ['1', '2', '5'])
  assert.deepEqual(studentFollowUps(tasks, 'abcd-002').map(t => t.task_id), ['3'])
  assert.deepEqual(studentFollowUps(tasks, ''), [])
  assert.deepEqual(studentFollowUps(tasks, 'missing'), [])
  assert.deepEqual(studentFollowUps(tasks, 'abcd-001').filter(isOpenTask).map(t => t.task_id), ['1'])
})
