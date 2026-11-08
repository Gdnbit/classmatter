import assert from 'node:assert/strict';
import { chromium } from '@playwright/test';

const base = process.env.CLASS_OS_TEST_URL;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '')) throw new Error('Owned synthetic fixture required');
const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } }), errors = [], external = [], starts = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (/^https?:/.test(request.url()) && !request.url().startsWith(base + '/')) external.push(request.url());
    if (request.method() === 'POST' && request.url().endsWith('/events')) starts.push(request.url());
  });
  await page.goto(base);
  await page.getByLabel('Owner 密码').fill('synthetic-test-passphrase-2026');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  const input = page.getByLabel('输入消息'), history = page.getByRole('region', { name: '已保存的对话' });
  await input.fill('合成普通聊天，不涉及班级');
  await page.getByRole('button', { name: '发送消息', exact: true }).click({ timeout: 5000 }).catch(async error => { throw new Error(JSON.stringify({ body: await page.locator('body').innerText(), errors }), { cause: error }); });
  await history.getByText('合成普通聊天已回复，不需要班级。', { exact: true }).waitFor();
  await page.waitForURL(/\/chats\/[a-f0-9-]{36}$/);
  assert.equal(await page.getByLabel('Agent 交互模式').count(), 0);
  const path = new URL(page.url()).pathname;
  await page.reload();
  await history.getByText('合成普通聊天已回复，不需要班级。', { exact: true }).waitFor();
  assert.equal(starts.length, 1);
  const savePath = '**/workspace-chat/threads/*/turns';
  await page.route(savePath, async route => { await route.fetch(); await route.abort('failed'); }, { times: 1 });
  await input.fill('合成发送响应丢失');
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  // The final read recovers a committed input even when the POST reply was lost.
  await history.getByRole('button', { name: '继续已保存的本轮', exact: true }).waitFor();
  assert.equal(starts.length, 1);
  await history.getByRole('button', { name: '继续已保存的本轮', exact: true }).click();
  await history.getByText('合成普通聊天已回复，不需要班级。', { exact: true }).nth(1).waitFor();
  assert.equal(starts.length, 2);
  const messages = [
    ['建立合成七一班，合成第一学期，2026-09-01至2027-01-30', '建立班级与学期'],
    ['把班名改为合成七二班', '修改班级名称'],
    ['添加合成学生甲', '添加学生'],
    ['将合成学生甲改名为合成学生乙', '更正学生姓名'],
    ['建立任务合成收集回执', '建立任务'],
    ['把任务合成收集回执改为合成收集签字回执', '修改任务'],
    ['生成文档合成班级小结', '创建工作文档'],
    ['给合成班级小结追加合成补充段落', '修改工作文档'],
  ];
  for (const [message, title] of messages) {
    await input.fill(message); await page.getByRole('button', { name: '发送消息', exact: true }).click();
    const card = history.getByRole('region', { name: '对话中的操作候选' }).filter({ has: page.getByRole('heading', { name: title, exact: true }) });
    await card.getByRole('heading', { name: title, exact: true }).waitFor();
    assert.equal(await page.getByRole('dialog').count(), 0); // No manual data-entry form.
    const before = starts.length;
    await page.reload();
    await card.getByRole('heading', { name: title, exact: true }).waitFor();
    assert.equal(starts.length, before);
    await card.getByRole('button', { name: '预览这项操作', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('button', { name: /^(确认提交|明确批准并提交)$/ }).waitFor();
    assert.equal(await dialog.locator('input,textarea,select').count(), 0);
    await dialog.getByRole('button', { name: /^(确认提交|明确批准并提交)$/ }).click();
    await dialog.waitFor({ state: 'hidden', timeout: 5000 }).catch(async error => { throw new Error(JSON.stringify({ message, dialog: await dialog.innerText(), errors }), { cause: error }); });
    await card.getByRole('status').filter({ hasText: '已保存' }).waitFor();
    assert.equal(new URL(page.url()).pathname, path);
  }
  await page.getByRole('button', { name: '学生', exact: true }).click();
  await page.getByRole('region', { name: '学生清单', exact: true }).getByRole('button', { name: /合成学生乙/ }).waitFor();
  await page.getByRole('button', { name: '工作', exact: true }).click();
  await page.getByRole('button', { name: /合成收集签字回执/ }).waitFor();
  await page.getByRole('button', { name: '数据与内容', exact: true }).click();
  await page.getByRole('button', { name: /合成班级小结/ }).first().click();
  await page.getByRole('button', { name: '原文', exact: true }).click();
  await page.locator('.document-text').filter({ hasText: '合成补充段落' }).waitFor();
  await page.goto(base + path);
  await history.getByText('合成普通聊天已回复，不需要班级。', { exact: true }).first().waitFor();
  assert.equal(starts.length, messages.length + 2);
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  console.log('PASS original UI: no-class persisted chat; refresh never replays; AI candidates create/edit via original confirmation; same students/tasks/documents; no data forms or external calls');
} finally { await browser.close(); }
