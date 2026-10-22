import test from 'node:test'
import assert from 'node:assert/strict'
import { searchStudents, studentFollowUps, isOpenTask } from '../src/runtime/student-directory.ts'

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
