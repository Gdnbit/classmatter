import test from 'node:test'
import assert from 'node:assert/strict'
import { parseRuntimeRoute, runtimePath } from '../src/runtime/navigation.ts'

const id = '00000000-0000-0000-0000-000000000001'
const task = '00000000-0000-0000-0000-000000000002'

test('supported R1 paths round-trip exact identity/view/filter without domain objects', () => {
  for (const path of ['/', '/dashboard', '/settings', '/students', '/students?view=table',
    ...['overview', 'timeline', 'tasks', 'records'].flatMap(tab => [`/students/${id}${tab === 'overview' ? '' : `?tab=${tab}`}`, `/students/${id}?view=table${tab === 'overview' ? '' : `&tab=${tab}`}`]),
    '/work', `/work?student=${id}&task=${task}&filter=waiting`, '/work?filter=closed']) {
    const route = parseRuntimeRoute(path)
    assert.equal(runtimePath(route), path)
    assert.deepEqual(parseRuntimeRoute(runtimePath(route)), route)
    assert.deepEqual(Object.keys(route).sort(), ['conversationClassId', 'conversationId', 'conversationTermId', 'page', 'studentId', 'studentTab', 'studentView', 'taskId', 'workFilter'])
  }
})

test('D1 deep link retains only exact class/term/thread identifiers, never a capability', () => {
  const path = `/conversations/${id}/${task}/00000000-0000-0000-0000-000000000003`
  assert.equal(runtimePath(parseRuntimeRoute(path)), path)
  for (const bad of [path + '?text=private', path + '#approval', path.replace(id, 'not-a-class'), path + '/events']) {
    assert.equal(parseRuntimeRoute(bad).page, 'unavailable')
  }
})

test('invalid identities/views/duplicate hints and normalized external paths do not guess', () => {
  for (const path of ['/students/99001', '/students/not-a-person', '/students?view=seat', '/students?view=table&view=list',
    '/work?student=wrong', `/work?task=${task}&filter=unknown`, `/work?student=${id}&student=${task}`,
    '//evil.invalid/students', '/\\evil.invalid/students', 'https://evil.invalid/students',
    '/students/../dashboard', '/students/%2e%2e/dashboard', '/students\n', '/' + 'x'.repeat(1024)]) {
    assert.equal(parseRuntimeRoute(path).page, 'unavailable', path)
  }
})

test('future pages/detail fields never turn into an existing mock module', () => {
  for (const path of ['/data/spreadsheets/score-001', '/spaces/midterm', '/automation', '/reports', '/knowledge']) {
    assert.equal(parseRuntimeRoute(path).page, 'unavailable')
    assert.equal(runtimePath(parseRuntimeRoute(path)), '/unavailable')
  }
  const route = parseRuntimeRoute(`/students/${id}?tab=grades`)
  assert.equal(route.studentId, id)
  assert.equal(route.studentTab, 'unavailable')
  assert.equal(runtimePath(route), `/students/${id}?tab=unavailable`)
})

test('free text, credentials, draft and unrelated query hints are never retained', () => {
  const route = parseRuntimeRoute(`/students/${id}?tab=tasks&name=synthetic-private-name&csrf=synthetic-private-token&text=synthetic-private-draft`)
  assert.equal(runtimePath(route), `/students/${id}?tab=tasks`)
  assert(!JSON.stringify(route).includes('synthetic-private'))
  assert.equal(runtimePath(parseRuntimeRoute('/settings/user?provider=synthetic-private-config')), '/settings')
})
