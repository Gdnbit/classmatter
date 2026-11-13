import { chromium, expect } from '@playwright/test'
import assert from 'node:assert/strict'

const base = process.env.CLASS_OS_TEST_URL
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '')) throw new Error('Owned disposable fixture required')
const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) })
const page = await browser.newPage({ timezoneId: 'Asia/Shanghai' })
const external = [], errors = [], writes = [], snapshots = []
const snapshotReads = []
let reads = 0
let releaseInitialObserver
const initialObserver = new Promise(resolve => { releaseInitialObserver = resolve })
let firstResponse = true
let phase = 'initial'
const activity = /\/terms\/[0-9a-f-]+\/activity$/
page.on('pageerror', error => errors.push(error.message))
page.on('request', request => {
  if (/^https?:/.test(request.url()) && !request.url().startsWith(base + '/')) external.push(request.url())
  if (!['GET', 'HEAD'].includes(request.method())) writes.push(request.url())
  if (activity.test(request.url())) reads++
})
page.on('response', response => {
  if (activity.test(response.url()) && response.status() === 200) {
    const first = firstResponse; firstResponse = false
    snapshotReads.push((async () => {
      if (first) await initialObserver
      snapshots.push((await response.json()).data)
    })())
  }
})
const ready = () => page.waitForFunction(() => Array.from(document.querySelectorAll('button')).some(button => button.textContent.trim() === '新建任务' && !button.disabled))
try {
  await page.clock.setFixedTime(new Date('2035-01-01T00:00:00Z')) // Timers still run normally; host wall clock is intentionally wrong.
  await page.goto(base + '/work')
  await page.getByLabel('密码', { exact: true }).fill('synthetic-test-passphrase-2026')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await ready()
  assert.equal(snapshots.length, 0, 'The test response observer is deliberately deferred')
  releaseInitialObserver()
  // An enabled action is not proof that this async response observer decoded
  // the real QG body. Keep the exact count and source assertions after delivery.
  await expect.poll(() => snapshots.length, { timeout: 30000 }).toBe(1)
  assert.equal(snapshots.length, 1)
  assert(snapshots[0].tasks.every(task => !task.overdue && task.version === 1))
  assert(snapshots[0].as_of.startsWith('2026-10-08T'))
  assert.equal(await page.evaluate(() => new Date().getUTCFullYear()), 2035)
  phase = 'draft-and-failed-read'
  const writesBefore = writes.length
  await page.getByRole('button', { name: /合成到期核对1.*未开始/ }).click()
  await page.getByRole('button', { name: '编辑标题与截止时间', exact: true }).click()
  await page.getByLabel('跟进标题').fill('合成未提交标题必须保留')
  await page.waitForTimeout(14500) // Real server monotonic clock crosses first deadline.
  assert.equal(reads, 1)
  assert.equal(await page.getByLabel('跟进标题').inputValue(), '合成未提交标题必须保留')
  let deliveryFaults = 0
  await page.route(activity, async route => {
    const response = await route.fetch() // Actual QG/PG read, only failure delivery injected.
    assert.equal(response.status(), 200)
    deliveryFaults++
    await route.fulfill({ response, status: 503, contentType: 'text/plain', body: 'synthetic-private-deadline-outage' })
  })
  await page.keyboard.press('Escape')
  await page.getByText('当前列表尚未刷新。', { exact: true }).waitFor()
  await page.waitForTimeout(6000)
  assert.equal(deliveryFaults, 1, 'No autonomous failed-read retry')
  assert(!(await page.locator('body').innerText()).includes('synthetic-private-deadline-outage'))
  await page.unroute(activity)
  phase = 'focus-recovery'
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await ready()
  await page.getByRole('button', { name: /合成到期核对1.*已逾期/ }).waitFor()

  // Controlled visibility events exercise actual timer wiring; API responses
  // and clocks remain real. No successful response/body is fabricated.
  phase = 'hidden'
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, value: 'hidden' })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  const beforeHidden = reads
  await page.waitForTimeout(10000)
  assert.equal(reads, beforeHidden)
  phase = 'visibility-recovery'
  const visibleRead = page.waitForResponse(response => activity.test(response.url()) && response.status() === 200)
  await page.evaluate(() => {
    delete document.visibilityState
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await (await visibleRead).json()
  await Promise.all(snapshotReads)
  await page.getByRole('button', { name: /合成到期核对2.*已逾期/ }).waitFor()
  await ready()
  assert.equal(reads, beforeHidden + 1, 'Visibility recovery requests exactly one real projection')
  phase = 'idle-deadline'
  const beforeIdle = reads
  await page.getByRole('button', { name: /合成到期核对3.*已逾期/ }).waitFor({ timeout: 20000 })
  await ready()
  assert.equal(reads, beforeIdle + 1, 'Visible idle deadline requests exactly one fresh projection')
  await Promise.all(snapshotReads)
  const final = snapshots.at(-1)
  assert.equal(final.tasks.length, 3)
  assert(final.tasks.every(task => task.overdue && task.version === 1 && Date.parse(final.as_of) > Date.parse(task.due_at)))
  phase = 'quiet-after-deadlines'
  const finalReads = reads
  await page.waitForTimeout(5500)
  assert.equal(reads, finalReads, 'No recurring timer after all known tasks are overdue')
  assert.equal(writes.length, writesBefore, 'No business, model, preview or approval POST during clock progression')
  assert.deepEqual(external, [])
  assert.deepEqual(errors, [])
  console.log('PASS: server-time real PG overdue refresh; draft deferred, failed read stops, hidden suppressed, idle once, versions unchanged')
} catch (error) {
  console.error('Deadline projection observation', JSON.stringify({ phase, reads, snapshots: snapshots.map(value => ({
    as_of: value.as_of, tasks: value.tasks.map(task => ({ due_at: task.due_at, overdue: task.overdue, version: task.version })),
  })) }))
  throw error
} finally {
  releaseInitialObserver()
  try { await Promise.all(snapshotReads) } finally { await browser.close() }
}
