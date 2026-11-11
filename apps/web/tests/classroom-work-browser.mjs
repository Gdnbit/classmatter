import assert from 'node:assert/strict';
import { chromium, expect } from '@playwright/test';
import { comparisonContent } from './change-comparison-content.mjs';
const base = process.env.CLASS_OS_TEST_URL;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '')) throw new Error('Owned synthetic fixture required');
const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }), errors = [], external = [], runs = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (/^https?:/.test(request.url()) && !request.url().startsWith(base + '/')) external.push(request.url());
    if (request.method() === 'POST' && request.url().endsWith('/events')) runs.push(request.url());
  });
  await page.goto(base);
  await page.getByLabel('密码', { exact: true }).fill('synthetic-test-passphrase-2026');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  const input = page.getByLabel('输入消息');
  await input.fill('建立合成浏览月考，数学满分100；合成学生0成绩80；建立2排3座，把合成学生0放1排1座、合成学生1放1排2座，然后交换两人的座位。');
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  async function confirm() {
    const dialog = page.getByRole('dialog', { name: '确认这次变更', exact: true });
    await dialog.waitFor().catch(async error => { throw new Error(JSON.stringify({ body: await page.locator('body').innerText(), errors }), { cause: error }); });
    assert(!/[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}|expected_version|schema_version/.test(await dialog.innerText()));
    await dialog.getByRole('button', { name: '明确批准并提交', exact: true }).click();
    await dialog.waitFor({ state: 'hidden' });
  }
  const comparisons = [];
  for (const title of ['建立考试', '记录成绩', '建立座位表', '安排座位', '安排座位', '交换座位']) {
    const card = page.getByRole('region', { name: '对话中的操作候选' }).filter({ has: page.getByRole('heading', { name: title, exact: true }) }).last();
    await card.getByRole('button', { name: '预览这项操作', exact: true }).waitFor();
    const comparison = card.getByRole('region', { name: '变更前后对比', exact: true });
    await comparison.waitFor();
    const before = await comparisonContent(comparison.getByLabel('修改前', { exact: true }));
    const after = await comparisonContent(comparison.getByLabel('待确认的结果', { exact: true }));
    await card.getByRole('button', { name: '预览这项操作', exact: true }).click().catch(async error => {
      throw new Error(JSON.stringify({ title, body: await page.locator('body').innerText(), errors, runs }), { cause: error });
    });
    const dialogComparison = page.getByRole('dialog').getByRole('region', { name: '变更前后对比', exact: true });
    await expect.poll(() => comparisonContent(dialogComparison.getByLabel('修改前', { exact: true }))).toEqual(before);
    await expect.poll(() => comparisonContent(dialogComparison.getByLabel('待确认的结果', { exact: true }))).toEqual(after);
    await confirm();
    await card.getByRole('status').filter({ hasText: '已保存' }).waitFor();
    comparisons.push({ before, after: { ...after, heading: '已保存' } });
    await page.reload();
    await expect.poll(() => comparisonContent(comparison.getByLabel('修改前', { exact: true }))).toEqual(before);
    await expect.poll(() => comparisonContent(comparison.getByLabel('已保存的结果', { exact: true }))).toEqual(comparisons.at(-1).after);
    if (title === '交换座位') {
      const beforeBoard = comparison.getByLabel('修改前', { exact: true });
      const afterBoard = comparison.getByLabel('已保存的结果', { exact: true });
      await expect(beforeBoard.getByRole('cell', { name: '1排1座：合成学生0（有变动）', exact: true })).toBeVisible();
      await expect(afterBoard.getByRole('cell', { name: '1排1座：合成学生1（有变动）', exact: true })).toBeVisible();
      await page.screenshot({ path: '../../test-results/chat-seat-comparison.png' });
      await page.setViewportSize({ width: 390, height: 844 });
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      await expect(afterBoard.getByRole('cell', { name: '1排1座：合成学生1（有变动）', exact: true })).toBeVisible();
      await page.screenshot({ path: '../../test-results/chat-seat-comparison-narrow.png' });
      await page.setViewportSize({ width: 1440, height: 1000 });
    }
    await card.getByRole('button', { name: '继续任务', exact: true }).click();
  }
  await page.getByText('六步已完成，没有重复操作。', { exact: true }).waitFor();
  assert.equal(runs.length, 7);
  const conversation = page.url();
  await page.getByLabel('更多功能', { exact: true }).click();
  await page.getByRole('button', { name: '成绩', exact: true }).click();
  const grades = page.getByRole('region', { name: '成绩表格', exact: true });
  await grades.getByRole('row').filter({ hasText: '合成学生0' }).filter({ hasText: '80.00' }).waitFor();
  await grades.getByRole('button', { name: '编辑合成学生0的成绩', exact: true }).click();
  await page.getByLabel('分数', { exact: true }).fill('81');
  await page.getByLabel('成绩更正原因', { exact: true }).fill('合成复核');
  await page.getByRole('button', { name: '预览修改', exact: true }).click();
  assert.equal(await page.getByRole('dialog').count(), 1);
  // The original receipt recovery must work for new score commands too.
  await page.route('**/commands/commit', async route => { await route.fetch(); await route.abort('failed'); }, { times: 1 });
  await page.getByRole('dialog').getByRole('button', { name: '明确批准并提交', exact: true }).click();
  await page.getByRole('dialog').getByRole('alert').waitFor();
  await page.getByRole('button', { name: '核对提交结果', exact: true }).click();
  await grades.getByRole('row').filter({ hasText: '合成学生0' }).filter({ hasText: '81.00' }).waitFor();
  await page.reload();
  await grades.getByRole('row').filter({ hasText: '合成学生0' }).filter({ hasText: '81.00' }).waitFor();
  await grades.getByRole('button', { name: '编辑合成学生0的成绩', exact: true }).click();
  await page.getByLabel('分数', { exact: true }).fill('82');
  await page.getByLabel('成绩更正原因', { exact: true }).fill('合成旧快照');
  const csrf = (await page.context().cookies()).find(cookie => cookie.name === 'class_os_csrf');
  const concurrent = await page.request.post(base + '/__fixture__/concurrent-score', { data: {}, headers: { origin: base, 'x-class-os-csrf': csrf.value } });
  assert.equal(concurrent.status(), 200);
  await page.getByRole('button', { name: '预览修改', exact: true }).click();
  // Preview is rejected against the actual new DB version, preserving the edit.
  await page.getByRole('alert').waitFor();
  assert.equal(await page.getByLabel('分数', { exact: true }).inputValue(), '82');
  await page.getByRole('dialog').getByRole('button', { name: '取消', exact: true }).click();
  await grades.getByRole('row').filter({ hasText: '合成学生0' }).filter({ hasText: '86.00' }).waitFor();
  await page.screenshot({ path: '../../test-results/classroom-grades.png' });
  await page.getByLabel('更多功能', { exact: true }).click();
  await page.getByRole('button', { name: '座位', exact: true }).click();
  const seats = page.getByRole('region', { name: '座位图', exact: true });
  await seats.getByRole('button', { name: '1排1座 合成学生1', exact: true }).click();
  await seats.getByRole('button', { name: '1排2座 合成学生0', exact: true }).click();
  await confirm();
  await seats.getByRole('button', { name: '1排1座 合成学生0', exact: true }).waitFor();
  const source = seats.getByRole('button', { name: '1排1座 合成学生0', exact: true });
  await expect(source).toBeEnabled();
  await source.dragTo(seats.getByRole('button', { name: '2排3座 空座', exact: true }));
  await confirm();
  await seats.getByRole('button', { name: '2排3座 合成学生0', exact: true }).waitFor();
  await page.reload();
  await seats.getByRole('button', { name: '2排3座 合成学生0', exact: true }).waitFor();
  await seats.getByRole('button', { name: '1排1座 空座', exact: true }).waitFor();
  await page.screenshot({ path: '../../test-results/classroom-seating.png' });
  await page.goto(conversation);
  await page.getByText('六步已完成，没有重复操作。', { exact: true }).waitFor();
  const historical = page.getByRole('region', { name: '对话中的操作候选' }).getByRole('region', { name: '变更前后对比', exact: true });
  assert.equal(await historical.count(), comparisons.length);
  for (let index = 0; index < comparisons.length; index++) {
    await expect.poll(() => comparisonContent(historical.nth(index).getByLabel('修改前', { exact: true }))).toEqual(comparisons[index].before);
    await expect.poll(() => comparisonContent(historical.nth(index).getByLabel('已保存的结果', { exact: true }))).toEqual(comparisons[index].after);
  }
  assert.equal(runs.length, 7); // No implicit continuation after reload/navigation.
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  console.log('PASS six-step chat → confirmed grades/seats → original views; lost receipt recovery; stale rejection; manual swap/drag; persistence; zero external calls');
} finally { await browser.close(); }
