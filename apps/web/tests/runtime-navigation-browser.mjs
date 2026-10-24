import { chromium } from '@playwright/test'
import assert from 'node:assert/strict'
import { mkdir } from 'node:fs/promises'

const base = process.env.CLASS_OS_TEST_URL
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '')) throw new Error('Owned disposable fixture required')
const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) })
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, timezoneId: 'Asia/Shanghai' })
const page = await context.newPage()
const errors = [], external = [], mutations = []
page.on('pageerror', error => errors.push(error.message))
page.on('request', request => {
  if (/^https?:/.test(request.url()) && !request.url().startsWith(base + '/')) external.push(request.url())
  if (!['GET', 'HEAD'].includes(request.method())) mutations.push(new URL(request.url()).pathname)
})
const path = () => new URL(page.url()).pathname + new URL(page.url()).search
const waitEditable = () => page.waitForFunction(() => Array.from(document.querySelectorAll('button')).some(button => button.textContent.trim() === '添加学生' && !button.disabled))
async function commit(approved = false) {
  await page.getByRole('button', { name: '生成预览', exact: true }).click()
  await page.getByRole('button', { name: approved ? '明确批准并提交' : '确认提交', exact: true }).click()
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
  await waitEditable()
}
try {
  await page.goto(base + '/students?view=table')
  await page.getByLabel('Owner 密码').fill('synthetic-test-passphrase-2026')
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await page.getByRole('heading', { name: '学生', exact: true }).waitFor()
  await page.getByRole('button', { name: '建立班级与学期', exact: true }).click()
  await page.getByLabel('班级名称', { exact: true }).fill('合成导航验收班')
  await page.getByLabel('学期名称', { exact: true }).fill('合成导航学期')
  await page.getByLabel('学期开始').fill('2026-09-01')
  await page.getByLabel('学期结束（不包含该日）').fill('2027-01-31')
  await commit(true)
  for (const name of ['合成导航学生甲', '合成导航学生乙']) {
    await page.getByRole('button', { name: '添加学生', exact: true }).click()
    await page.getByLabel('学生姓名（允许同名，内部 ID 区分）').fill(name)
    await commit()
  }
  await page.getByRole('region', { name: '学生表格' }).getByRole('button', { name: /合成导航学生乙/ }).click()
  const idB = new URL(page.url()).pathname.split('/')[2]
  await page.getByRole('region', { name: '学生表格' }).getByRole('button', { name: /合成导航学生甲/ }).click()
  const idA = new URL(page.url()).pathname.split('/')[2]
  assert.notEqual(idA, idB)
  assert.match(idA, /^[0-9a-f-]{36}$/)
  await page.getByRole('button', { name: '记录事实', exact: true }).click()
  await page.getByLabel('发生时间（本机时区）').fill('2026-10-08T08:00')
  await page.getByLabel('事实原文（观察类型请留空）').fill('合成导航数据库事实')
  await commit()
  await page.getByRole('button', { name: '基于事实建立跟进', exact: true }).click()
  await page.getByLabel('跟进标题').fill('合成导航同源跟进')
  await commit()
  await page.getByRole('button', { name: '查看版本 / 更正', exact: true }).click()
  await page.getByLabel('教师观察', { exact: true }).fill('合成更正观察，记录仍只有一个')
  await page.getByLabel('更正理由', { exact: true }).fill('合成导航验收')
  await commit(true)
  let writesBeforeNavigation = mutations.length
  await page.getByRole('navigation', { name: '学生详情视图' }).getByRole('button', { name: '跟进', exact: true }).click()
  await page.waitForURL(base + `/students/${idA}?view=table&tab=tasks`)
  assert.equal(path(), `/students/${idA}?view=table&tab=tasks`)
  await page.reload()
  await waitEditable()
  await page.getByRole('region', { name: '学生详情摘要' }).getByText(/1 条当前记录 · 1 项未结束跟进/).waitFor()
  assert.equal(path(), `/students/${idA}?view=table&tab=tasks`)
  await page.getByRole('region', { name: '学生表格' }).waitFor()
  await page.goBack()
  await page.waitForURL(base + `/students/${idA}?view=table`)
  await page.getByRole('navigation', { name: '学生详情视图' }).getByRole('button', { name: '概览', exact: true }).waitFor()
  assert.equal(path(), `/students/${idA}?view=table`)
  await page.goForward()
  await page.waitForURL(base + `/students/${idA}?view=table&tab=tasks`)
  await page.getByRole('navigation', { name: '学生详情视图' }).getByRole('button', { name: '跟进', exact: true }).waitFor()
  assert.equal(path(), `/students/${idA}?view=table&tab=tasks`)
  await page.getByRole('button', { name: '视图', exact: true }).click()
  const rowA = page.getByRole('row').filter({ hasText: '合成导航学生甲' })
  assert.deepEqual((await rowA.getByRole('cell').allTextContents()).slice(-2), ['1', '1'])
  const rowB = page.getByRole('row').filter({ hasText: '合成导航学生乙' })
  assert.deepEqual((await rowB.getByRole('cell').allTextContents()).slice(-2), ['0', '0'])
  await page.reload(); await waitEditable()
  assert.equal(path(), '/students?view=table')
  await page.getByRole('region', { name: '学生表格' }).waitFor()
  await mkdir('test-results', { recursive: true })
  await page.screenshot({ path: 'test-results/runtime-real-student-table.png', fullPage: true })
  await page.setViewportSize({ width: 320, height: 760 })
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true)
  await page.screenshot({ path: 'test-results/runtime-real-student-table-mobile.png', fullPage: true })
  await page.setViewportSize({ width: 1440, height: 1000 })
  assert.equal(mutations.length, writesBeforeNavigation, 'Read/navigation/reload must not issue mutations or Agent calls')

  // Actual task/filter deep links, then a second real UI updates the same row.
  await page.goto(base + `/students/${idA}`); await waitEditable()
  await page.getByRole('button', { name: '工作', exact: true }).click()
  await page.locator('.r1-task-title').filter({ hasText: '合成导航同源跟进' }).click()
  await page.waitForURL(url => Boolean(url.searchParams.get('task')))
  const taskId = new URL(page.url()).searchParams.get('task')
  await page.reload()
  await page.getByRole('button', { name: '编辑标题与截止时间', exact: true }).waitFor()
  assert.equal(new URL(page.url()).searchParams.get('task'), taskId)
  await page.getByRole('button', { name: '等待别人', exact: true }).click()
  await page.getByRole('button', { name: '确认提交', exact: true }).click()
  await page.getByRole('dialog').waitFor({ state: 'hidden' })
  await page.getByLabel('按状态筛选任务').selectOption('waiting')
  await page.waitForURL(url => url.searchParams.get('filter') === 'waiting')
  await page.locator('.r1-task-title').filter({ hasText: '合成导航同源跟进' }).click()
  await page.waitForURL(url => url.searchParams.get('task') === taskId)
  await page.reload()
  await page.getByRole('button', { name: '编辑标题与截止时间', exact: true }).waitFor()
  assert.equal(await page.getByLabel('按状态筛选任务').inputValue(), 'waiting')
  assert.equal(await page.getByLabel('按学生筛选任务').inputValue(), idA)
  assert.equal(new URL(page.url()).searchParams.get('task'), taskId)
  const peer = await page.context().newPage()
  peer.on('pageerror', error => errors.push(error.message))
  peer.on('request', request => {
    if (/^https?:/.test(request.url()) && !request.url().startsWith(base + '/')) external.push(request.url())
    if (!['GET', 'HEAD'].includes(request.method())) mutations.push(new URL(request.url()).pathname)
  })
  try {
    await peer.goto(base + `/work?task=${taskId}`)
    await peer.getByRole('button', { name: '编辑标题与截止时间', exact: true }).click()
    await peer.getByLabel('跟进标题', { exact: true }).fill('合成导航跟进已更正')
    await peer.getByRole('button', { name: '生成预览', exact: true }).click()
    await peer.getByRole('button', { name: '确认提交', exact: true }).click()
    await peer.getByRole('dialog').waitFor({ state: 'hidden' })
    await peer.locator('.r1-task-title').filter({ hasText: '合成导航跟进已更正' }).waitFor()
  } finally { await peer.close() }
  await page.bringToFront()
  await page.evaluate(() => window.dispatchEvent(new Event('focus')))
  await page.locator('.r1-task-title').filter({ hasText: '合成导航跟进已更正' }).waitFor()
  await page.getByRole('button', { name: '编辑标题与截止时间', exact: true }).click()
  assert.equal(await page.getByLabel('跟进标题', { exact: true }).inputValue(), '合成导航跟进已更正')
  await page.keyboard.press('Escape')
  await page.goto(base + `/work?task=00000000-0000-0000-0000-000000000099`)
  await page.waitForFunction(() => Array.from(document.querySelectorAll('button')).some(button => button.textContent.trim() === '新建任务' && !button.disabled))
  await page.getByText('所选任务不在当前已授权查询中', { exact: false }).waitFor()
  assert.equal(await page.getByRole('button', { name: '编辑标题与截止时间', exact: true }).count(), 0)
  writesBeforeNavigation = mutations.length

  await page.goto(base + `/students/${idA}`); await waitEditable()
  await page.getByRole('button', { name: '总览', exact: true }).click()
  await page.getByRole('button', { name: '学生', exact: true }).click()
  await page.getByRole('button', { name: '记录事实', exact: true }).click()
  await page.getByLabel('事实原文（观察类型请留空）').fill('合成尚未提交的导航草稿')
  const historyLength = await page.evaluate(() => history.length)
  await page.goBack()
  await page.getByText('页面切换已延后。', { exact: false }).waitFor()
  assert.equal(await page.getByLabel('事实原文（观察类型请留空）').inputValue(), '合成尚未提交的导航草稿')
  await page.goBack(); await page.goForward()
  assert.equal(await page.evaluate(() => history.length), historyLength)
  assert.equal(await page.getByLabel('事实原文（观察类型请留空）').inputValue(), '合成尚未提交的导航草稿')
  assert.equal(mutations.length, writesBeforeNavigation)
  await page.keyboard.press('Escape')
  await page.getByRole('heading', { name: '今天的班级工作', exact: true }).waitFor()
  assert.equal(path(), '/dashboard')
  assert.equal(await page.evaluate(() => history.length), historyLength)
  await page.getByRole('button', { name: '学生', exact: true }).click()
  // The restored dashboard URL has no student hint. Explicitly select the
  // identity again; do not expect an invisible previous-student fallback.
  await page.getByRole('button', { name: /合成导航学生甲.*版本/ }).click()
  await page.getByRole('button', { name: '记录事实', exact: true }).click()
  await page.getByLabel('发生时间（本机时区）').fill('2026-10-08T08:00')
  await page.getByLabel('事实原文（观察类型请留空）').fill('合成待确认导航草稿')
  await page.getByRole('button', { name: '生成预览', exact: true }).click()
  await page.getByRole('heading', { name: '确认这次变更', exact: true }).waitFor()
  const writesBeforeBack = mutations.length
  await page.goBack()
  await page.getByText('页面切换已延后。', { exact: false }).waitFor()
  assert((await page.getByRole('dialog').innerText()).includes('合成待确认导航草稿'))
  assert.equal(mutations.length, writesBeforeBack)
  await page.keyboard.press('Escape') // Explicitly reject the proposal, not a navigation side effect.
  await page.waitForURL(base + '/students')
  await page.getByRole('heading', { name: '学生', exact: true }).waitFor()

  const unknown = '00000000-0000-0000-0000-000000000099'
  await page.goto(base + `/students/${unknown}`); await waitEditable()
  await page.getByText('此学生不在当前已授权班级查询中。', { exact: false }).waitFor()
  assert.equal(await page.getByText('合成导航数据库事实', { exact: true }).count(), 0)
  await page.goto(base + `/students/${idA}?tab=grades`); await waitEditable()
  await page.getByRole('heading', { name: '此学生视图尚未接入', exact: true }).waitFor()
  assert.equal(await page.getByText('合成导航数据库事实', { exact: true }).count(), 0)
  await page.goto(base + '/data/spreadsheets/score-001')
  await page.getByRole('heading', { name: '此页面尚未接入真实工作台', exact: true }).waitFor()
  await page.goto(base + `/students/${idA}?tab=records`); await waitEditable()
  await page.evaluate(other => history.replaceState({ studentId: other, draft: 'synthetic-untrusted-history', authority: 'owner' }, '', location.href), idB)
  await page.reload(); await waitEditable()
  assert.equal(path(), `/students/${idA}?tab=records`)
  assert.equal(await page.evaluate(() => history.state), null)
  await page.getByText('合成导航数据库事实', { exact: true }).waitFor()
  assert(!(await page.locator('body').innerText()).includes('synthetic-untrusted-history'))

  // Hold genuine old-session delivery across actual logout/login. For 401,
  // defer the upstream request itself until its captured cookie is revoked.
  const activityRoute = /\/terms\/[0-9a-f-]+\/activity$/
  for (const [oldStatus, switchScope] of [[200, false], [401, false], [200, true]]) {
    let release, reached, delivered, deliveryError, first = true
    const gate = new Promise(resolve => { release = resolve })
    const ready = new Promise(resolve => { reached = resolve })
    const done = new Promise(resolve => { delivered = resolve })
    const oldDelivery = async route => {
      if (!first) { await route.continue(); return }
      first = false
      try {
        let response
        if (oldStatus === 200) response = await route.fetch()
        reached()
        await gate
        if (oldStatus === 401) response = await route.fetch()
        assert.equal(response.status(), oldStatus)
        await route.fulfill({ response })
      } catch (error) { deliveryError = error }
      finally { reached(); delivered() }
    }
    await page.route(activityRoute, oldDelivery)
    try {
      await page.evaluate(() => window.dispatchEvent(new Event('focus')))
      await ready
      assert.equal(await page.getByLabel('切换班级学期', { exact: true }).isDisabled(), true)
      await page.locator('.r1-logout').click()
      await page.getByLabel('Owner 密码').fill('synthetic-test-passphrase-2026')
      await page.getByRole('button', { name: '登录', exact: true }).click()
      await page.getByRole('heading', { name: '今天想处理什么？', exact: true }).waitFor()
      await page.getByRole('button', { name: '学生', exact: true }).click()
      await waitEditable()
      await page.getByText('页面切换已延后。', { exact: false }).waitFor({ state: 'hidden' })
      if (switchScope) {
        await page.getByRole('button', { name: '设置', exact: true }).click()
        await page.getByRole('button', { name: '预览归档（历史仍可查看）', exact: true }).click()
        await page.getByRole('button', { name: '明确批准并提交', exact: true }).click()
        await page.getByRole('dialog').waitFor({ state: 'hidden' })
        await page.getByRole('complementary').getByRole('button', { name: '建立班级与学期', exact: true }).click()
        await page.getByLabel('班级名称', { exact: true }).fill('合成新范围空班')
        await page.getByLabel('学期名称', { exact: true }).fill('合成新范围学期')
        await page.getByLabel('学期开始').fill('2026-09-01')
        await page.getByLabel('学期结束（不包含该日）').fill('2027-01-31')
        await page.getByRole('button', { name: '生成预览', exact: true }).click()
        await page.getByRole('button', { name: '明确批准并提交', exact: true }).click()
        await page.getByRole('dialog').waitFor({ state: 'hidden' })
        // Creation does not silently replace the teacher's selected archive.
        // Select the actual new scope through its existing authorized control.
        await page.getByLabel('切换班级学期', { exact: true }).selectOption({ label: '合成新范围空班 · 合成新范围学期' })
        await page.getByRole('button', { name: '学生', exact: true }).click()
        await waitEditable()
      }
      const currentScope = await page.getByLabel('切换班级学期', { exact: true }).inputValue()
      const expectedFacts = switchScope ? 0 : 1 // No selected student means authorized class timeline, not an empty view.
      assert.equal(await page.getByText('合成导航数据库事实', { exact: true }).count(), expectedFacts)
      release(); await done
      assert.equal(deliveryError, undefined)
      await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))))
      assert.equal(await page.getByLabel('Owner 密码').count(), 0)
      assert.equal(await page.getByText('合成导航数据库事实', { exact: true }).count(), expectedFacts)
      assert.equal(await page.getByLabel('切换班级学期', { exact: true }).inputValue(), currentScope)
      // Complete another actual authorized read after the late delivery.
      await page.getByRole('button', { name: '刷新数据', exact: true }).click()
      await waitEditable()
      assert.equal(path(), '/students')
      assert.equal(await page.getByLabel('Owner 密码').count(), 0)
      assert.equal(await page.getByText('合成导航数据库事实', { exact: true }).count(), expectedFacts)
      await page.getByText('页面切换已延后。', { exact: false }).waitFor({ state: 'hidden' })
      assert.equal(await page.getByLabel('切换班级学期', { exact: true }).inputValue(), currentScope)
      if (switchScope) assert.equal(await page.getByRole('button', { name: /合成导航学生甲.*版本/ }).count(), 0)
      else await page.getByRole('button', { name: /合成导航学生甲.*版本/ }).waitFor()
    } finally { release(); await done; await page.unroute(activityRoute, oldDelivery) }
  }
  await page.getByRole('button', { name: '设置', exact: true }).click()
  await page.getByRole('button', { name: '注销当前会话', exact: true }).click()
  await page.getByRole('button', { name: '登录', exact: true }).waitFor()
  await page.goBack()
  assert.equal(await page.getByText('合成导航数据库事实', { exact: true }).count(), 0)
  assert.deepEqual(errors, [])
  assert.deepEqual(external, [])
  assert.equal(mutations.filter(path => /\/agent\//.test(path)).length, 0)
  console.log('PASS: real PG single-world table/detail/tabs/reload/back/deferred form+proposal/unknown/future/logout; Agent absent')
} finally { await browser.close() }
