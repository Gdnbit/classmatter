import test from 'node:test'
import assert from 'node:assert/strict'
import { parseUrl, serializeStack } from '../src/store/UrlAdapter.ts'

globalThis.window = { location: { origin: 'http://127.0.0.1:8443' } }

test('table/seat/dorm/group views survive URL round trip without falling back to list', () => {
  for (const view of ['table', 'seat', 'dorm', 'group']) {
    const url = `/students?view=${view}`
    const stack = parseUrl(url)
    assert.equal(stack.viewSurfaceId, `VIEW-${view.toUpperCase()}`)
    assert.equal(serializeStack(stack), url)
  }
})

test('student detail tabs preserve the exact identity and tab across reload', () => {
  for (const tab of ['timeline', 'tasks', 'records', 'grades', 'files', 'relations']) {
    const url = `/students/99001?tab=${tab}`
    const stack = parseUrl(url)
    assert.equal(stack.params.studentId, '99001')
    assert.equal(serializeStack(stack), url)
  }
})
