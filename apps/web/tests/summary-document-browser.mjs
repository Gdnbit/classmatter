import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';

const base = process.env.CLASS_OS_TEST_URL;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '')) throw new Error('Owned synthetic fixture required');
const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage(), errors = [], external = [], writes = [];
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => {
  if (/^https?:/.test(request.url()) && !request.url().startsWith(base + '/')) external.push(request.url());
  if (!['GET', 'HEAD'].includes(request.method())) writes.push(new URL(request.url()).pathname);
});
try {
  await page.goto(base);
  await page.getByLabel('密码', { exact: true }).fill('synthetic-test-passphrase-2026');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await page.getByRole('button', { name: '总览', exact: true }).click();
  await page.getByRole('button', { name: '整理班级工作小结', exact: true }).click();
  const editor = page.getByLabel('可编辑小结（未保存）', { exact: true });
  const original = await editor.inputValue();
  assert(!original.includes(process.env.CLASS_OS_TEST_RECORD));
  assert(!original.includes(process.env.CLASS_OS_TEST_TASK));
  assert(original.includes('学生记录') && original.includes('工作跟进'));
  assert(original.includes('事实：synthetic sourced document fact'));
  assert(original.includes('教师观察：synthetic observation is not a fact'));
  const edited = original + '\n本人补充，仍为工作草稿。';
  await editor.fill(edited);
  await context.setOffline(true);
  await page.waitForFunction(() => Array.from(document.querySelectorAll('button')).find(node => node.textContent === '转入文档草稿')?.disabled);
  assert.equal(await editor.inputValue(), edited);
  await context.setOffline(false);
  await page.getByRole('button', { name: '刷新数据', exact: true }).click();
  await page.waitForFunction(() => !Array.from(document.querySelectorAll('button')).find(node => node.textContent === '转入文档草稿')?.disabled);
  const before = writes.length;
  await page.getByRole('button', { name: '转入文档草稿', exact: true }).click();
  await page.waitForURL('**/data/documents/new');
  const document = page.getByLabel('文档正文', { exact: true });
  await document.waitFor();
  assert.equal(await document.inputValue(), edited);
  assert.equal(writes.length, before); // Handoff is not a command or automatic save.
  assert(!(new URL(page.url()).search));
  assert(await page.evaluate(text => !JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage)]).includes(text), edited));
  const session = await (await context.request.get(base + '/api/identity/session')).json();
  const collection = `${base}/api/workspaces/${session.subject.workspace_id}/classes/${process.env.CLASS_OS_TEST_CLASS}/terms/${process.env.CLASS_OS_TEST_TERM}/documents`;
  const headers = { 'x-class-os-csrf': session.csrf_token };
  assert.equal((await (await context.request.get(collection, { headers })).json()).data.length, 0);
  await page.getByRole('button', { name: '保存草稿', exact: true }).click();
  const preview = page.getByRole('dialog', { name: '确认文档变更', exact: true });
  await preview.waitFor();
  assert((await preview.innerText()).includes('本人补充，仍为工作草稿。'));
  await preview.getByRole('button', { name: '明确批准并保存', exact: true }).click();
  await page.waitForURL(/\/data\/documents\/[a-f0-9-]{36}$/);
  await page.reload(); await document.waitFor();
  assert.equal(await document.inputValue(), edited);
  const id = new URL(page.url()).pathname.split('/').at(-1);
  const stored = await context.request.get(collection + '/' + id, { headers });
  assert.equal(stored.status(), 200); assert.equal((await stored.json()).data.body, edited);
  await page.getByRole('button', { name: '新建文档', exact: true }).click();
  await page.waitForURL('**/data/documents/new'); await document.waitFor();
  assert.equal(await document.inputValue(), ''); // Seed consumed once, not silently reused.
  assert.deepEqual(writes.slice(before).map(path => path.split('/').at(-1)), ['preview', 'approve', 'commit']);
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  console.log('PASS sourced edited summary transferred without write, explicitly saved and restored as an independent working document');
} finally { await context.close(); await browser.close(); }
