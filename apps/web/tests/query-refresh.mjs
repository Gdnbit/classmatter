import test from 'node:test'
import assert from 'node:assert/strict'
import { createQueryRefresh, deadlineRefreshDelay } from '../src/runtime/query-refresh.ts'

test('deadline invalidation follows server as_of, excludes closed/overdue/no-date and bounds timers', () => {
  const as_of = '2026-10-08T12:00:00Z'
  const task = { status: 'waiting', overdue: false, due_at: '2026-10-08T12:01:00Z' }
  const delay = tasks => deadlineRefreshDelay({ as_of, records: [], tasks })
  assert.equal(delay([task]), 60250) // Independent of host date/timezone.
  assert.equal(delay([{ ...task, due_at: as_of }]), 5000)
  assert.equal(delay([{ ...task, due_at: '2020-01-01T00:00:00Z' }]), 5000)
  assert.equal(delay([{ ...task, due_at: '2030-01-01T00:00:00Z' }]), 2147483647)
  assert.equal(delay([task, { ...task, due_at: '2026-10-08T12:00:10Z' }]), 10250)
  assert.equal(delay(['done', 'cancelled'].map(status => ({ ...task, status }))), null)
  assert.equal(delay([{ ...task, overdue: true }, { ...task, due_at: null }, { ...task, due_at: 'invalid' }]), null)
  assert.equal(deadlineRefreshDelay({ as_of: 'invalid', records: [], tasks: [task] }), null)
})

function fixture(read = async () => {}) {
  let now = 0, next = 0
  const timers = new Map()
  const state = { available: true, idle: true, reads: 0, invalidations: 0, failures: [] }
  const controller = createQueryRefresh({
    read: async () => { state.reads++; await read() },
    invalidate: () => state.invalidations++, fail: reason => state.failures.push(reason),
    available: () => state.available, idle: () => state.idle, now: () => now,
    schedule: (callback, delay) => { const id = ++next; timers.set(id, { callback, at: now + delay }); return id },
    cancel: id => timers.delete(id),
  })
  async function tick(ms) {
    now += ms
    for (const [id, timer] of [...timers]) {
      if (timer.at <= now) { timers.delete(id); timer.callback() }
    }
    for (let index = 0; index < 6; index++) await Promise.resolve()
  }
  return { controller, state, timers, tick }
}

test('foreground bursts coalesce, then repeated events respect audited read cooldown', async () => {
  const f = fixture()
  for (let index = 0; index < 50; index++) f.controller.request()
  assert.equal(f.timers.size, 1)
  await f.tick(249); assert.equal(f.state.reads, 0)
  await f.tick(1); assert.equal(f.state.reads, 1)
  for (let index = 0; index < 50; index++) f.controller.request()
  await f.tick(4999); assert.equal(f.state.reads, 1)
  await f.tick(1); assert.equal(f.state.reads, 2)
  await f.tick(60000); assert.equal(f.state.reads, 2) // No periodic polling.
})

test('editing/approval/running work defers until idle and rechecks at execution', async () => {
  const f = fixture()
  f.state.idle = false; f.controller.request()
  assert.equal(f.timers.size, 0)
  f.state.idle = true; f.controller.resume()
  f.state.idle = false // A dialog opened after scheduling.
  await f.tick(250); assert.equal(f.state.reads, 0)
  f.state.idle = true; f.controller.resume()
  await f.tick(250); assert.equal(f.state.reads, 1)
})

test('hidden/offline cancels scheduled reads; reconnect replays only one invalidation', async () => {
  const f = fixture()
  f.controller.request()
  f.state.available = false; f.controller.resume()
  assert.equal(f.timers.size, 0)
  f.controller.offline(); assert.equal(f.state.invalidations, 1)
  await f.tick(10000); assert.equal(f.state.reads, 0)
  f.state.available = true; f.controller.request(); f.controller.request()
  await f.tick(250); assert.equal(f.state.reads, 1)
})

test('no read overlap; an event during a read queues one follow-up', async () => {
  let finish
  const f = fixture(() => new Promise(resolve => { finish = resolve }))
  f.controller.request(); await f.tick(250)
  for (let index = 0; index < 50; index++) f.controller.request()
  await f.tick(10000); assert.equal(f.state.reads, 1)
  finish(); await f.tick(0)
  await f.tick(250); assert.equal(f.state.reads, 2)
  finish(); await f.tick(0)
})

test('read failure is reported without an autonomous retry loop', async () => {
  const reason = new Error('synthetic controlled read failure')
  const f = fixture(async () => { throw reason })
  f.controller.request(); await f.tick(250)
  assert.deepEqual(f.state.failures, [reason])
  assert.equal(f.timers.size, 0)
  await f.tick(60000); assert.equal(f.state.reads, 1)
  f.controller.request(); await f.tick(250); assert.equal(f.state.reads, 2)
})

test('dispose clears timers and ignores late failure from the previous session', async () => {
  const pending = fixture()
  pending.controller.request(); pending.controller.dispose()
  await pending.tick(250); assert.equal(pending.state.reads, 0)
  let reject
  const f = fixture(() => new Promise((_, failure) => { reject = failure }))
  f.controller.request(); await f.tick(250)
  f.controller.dispose(); reject(new Error('synthetic old-session failure'))
  await f.tick(60000)
  f.controller.offline(); f.controller.request(); f.controller.resume()
  assert.equal(f.state.reads, 1)
  assert.deepEqual(f.state.failures, [])
  assert.equal(f.state.invalidations, 0)
  assert.equal(f.timers.size, 0)
})
