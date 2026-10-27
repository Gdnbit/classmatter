import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';

const base = process.env.CLASS_OS_TEST_URL;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '')) throw new Error('Owned synthetic fixture required');
const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, permissions: ['clipboard-read', 'clipboard-write'] });
const page = await context.newPage(), errors = [], external = [], writes = [];
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => {
  if (/^https?:/.test(request.url()) && !request.url().startsWith(base + '/')) external.push(request.url());
  if (!['GET', 'HEAD'].includes(request.method())) writes.push(new URL(request.url()).pathname);
});
try {
  await page.goto(base);
  await page.getByLabel('Owner 密码').fill('synthetic-test-passphrase-2026');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await page.getByRole('button', { name: '总览', exact: true }).click();
  const generate = page.getByRole('button', { name: '整理班级工作小结', exact: true });
  await generate.waitFor();
  await page.waitForFunction(() => !Array.from(document.querySelectorAll('button')).find(b => b.textContent === '整理班级工作小结')?.disabled);
  const writeCount = writes.length;
  await generate.click();
  const editor = page.getByLabel('可编辑小结（未保存）');
  const original = await editor.inputValue();
  assert(original.includes('synthetic summary fact'));
  assert(original.includes('教师观察字段（不等于事实）：synthetic summary observation'));
  assert(original.includes('synthetic summary task'));
  assert.match(original, /\[record:[a-f0-9-]{36}@1\]/);
  assert.match(original, /\[task:[a-f0-9-]{36}@1\]/);
  assert(original.includes('来源作者：'));
  await editor.fill(original + '\n人工补充：仍为未核对草稿。');
  await page.screenshot({ path: '../../test-results/work-summary.png', fullPage: true });
  await page.getByRole('button', { name: '复制已核对草稿', exact: true }).click();
  await page.getByText('已按本人操作复制；未保存或发送。', { exact: true }).waitFor();
  // Windows clipboard normalizes LF to CRLF; compare all text after only EOL normalization.
  assert.equal((await page.evaluate(() => navigator.clipboard.readText())).replaceAll('\r\n', '\n'), original + '\n人工补充：仍为未核对草稿。');
  await page.evaluate(() => Object.defineProperty(navigator, 'clipboard', { configurable: true,
    value: { writeText: async () => { throw new Error('synthetic clipboard denied'); } } }));
  await page.getByRole('button', { name: '复制已核对草稿', exact: true }).click();
  await page.getByText('系统未允许剪贴板写入；可在文本框全选后手动复制。', { exact: true }).waitFor();
  assert((await editor.inputValue()).includes('人工补充'));
  await page.evaluate(() => { delete navigator.clipboard; });
  await context.setOffline(true);
  await page.getByText('来源已变化或尚未重新核对；不能标作当前小结复制。', { exact: false }).waitFor();
  assert(await page.getByRole('button', { name: '复制已核对草稿', exact: true }).isDisabled());
  assert((await editor.inputValue()).includes('人工补充'));
  await context.setOffline(false);
  await page.getByText('来源版本与当前查询一致；编辑文字仍需本人核对。', { exact: true }).waitFor();
  // Independent authorized client adds a task via the original BCG, never a mocked read.
  const session = await (await context.request.get(base + '/api/identity/session')).json();
  const workspace = `${base}/api/workspaces/${session.subject.workspace_id}`;
  const headers = { origin: base, 'x-class-os-csrf': session.csrf_token };
  const command = { command: 'task.create', task_id: crypto.randomUUID(), class_id: process.env.CLASS_OS_TEST_CLASS,
    term_id: process.env.CLASS_OS_TEST_TERM, title: 'synthetic independent new task' };
  const previewResponse = await context.request.post(workspace + '/commands/preview', { headers, data: command });
  assert.equal(previewResponse.status(), 200);
  const preview = await previewResponse.json();
  const committed = await context.request.post(workspace + '/commands/commit', { headers,
    data: { proposal_id: preview.proposal_id, idempotency_key: crypto.randomUUID() } });
  assert.equal(committed.status(), 200);
  await page.getByRole('button', { name: '刷新数据', exact: true }).click();
  await page.getByText('来源已变化或尚未重新核对；不能标作当前小结复制。', { exact: false }).waitFor();
  await page.getByRole('button', { name: /synthetic independent new task/ }).waitFor();
  assert(await page.getByRole('button', { name: '复制已核对草稿', exact: true }).isDisabled());
  assert((await editor.inputValue()).includes('人工补充'));
  await page.getByRole('button', { name: '学生', exact: true }).click();
  assert(await editor.isVisible()); // Draft prevents navigation, not foreground QG reads.
  await page.getByRole('button', { name: '丢弃小结草稿', exact: true }).click();
  await editor.waitFor({ state: 'hidden' });
  await page.getByRole('heading', { name: '学生', exact: true }).waitFor();
  await page.getByRole('button', { name: '总览', exact: true }).click();
  await generate.click();
  assert((await editor.inputValue()).includes('synthetic independent new task'));
  assert(!(await editor.inputValue()).includes('人工补充'));
  let warned = false;
  page.once('dialog', async dialog => { assert.equal(dialog.type(), 'beforeunload'); warned = true; await dialog.accept(); });
  await page.reload();
  await generate.waitFor();
  assert(warned);
  assert.equal(await editor.count(), 0); // Explicitly temporary, no recovery/cache claim.
  assert.equal(writes.length, writeCount); // No Agent, BCG or new persistence request.
  await page.getByRole('button', { name: '学生', exact: true }).click();
  await page.getByRole('button', { name: '总览', exact: true }).click();
  assert.equal(await editor.count(), 0);
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  console.log(JSON.stringify({ summary: 'actual QG/PG, editable/copy/offline/navigation/discard', writes: 0, errors, external }));
} finally { await context.close(); await browser.close(); }
