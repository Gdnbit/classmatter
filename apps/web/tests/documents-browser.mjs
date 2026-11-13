import { chromium } from '@playwright/test';
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { mkdir } from 'node:fs/promises';

const base = process.env.CLASS_OS_TEST_URL, classroom = process.env.CLASS_OS_TEST_CLASS, term = process.env.CLASS_OS_TEST_TERM;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '') || !/^[a-f0-9-]{36}$/.test(classroom || '')
  || !/^[a-f0-9-]{36}$/.test(term || '')) throw new Error('Owned synthetic fixture required');
const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage(), errors = [], external = [], commits = [];
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => {
  if (/^https?:/.test(request.url()) && !request.url().startsWith(base + '/')) external.push(request.url());
  if (request.method() === 'POST' && new URL(request.url()).pathname.endsWith('/document-commands/commit')) commits.push(request.postDataJSON());
});
const body = '# 合成工作小结\n\n- 核对**展示作品**\n\n| 事项 | 结果 |\n| --- | --- |\n| 作品 | 已核对 |\n\n认识分数 $\\frac{1}{2}$。\n\n<script>throw new Error("untrusted body executed")</script>\n不作为正式事实。';
const editor = page.getByLabel('文档正文', { exact: true });
const dialog = page.getByRole('dialog', { name: '确认文档变更', exact: true });
const readReleases = [];
async function assertRendered(content) {
  await content.getByRole('heading', { name: '合成工作小结', exact: true }).waitFor();
  assert.equal(await content.locator('li strong').textContent(), '展示作品');
  assert.equal(await content.getByRole('cell', { name: '已核对', exact: true }).count(), 1);
  assert.equal(await content.locator('script,img,iframe').count(), 0);
  assert.equal(await content.locator('.katex-mathml mfrac').count(), 1);
  assert.equal(await content.locator('annotation[encoding="application/x-tex"]').textContent(), '\\frac{1}{2}');
  assert((await content.innerText()).includes('<script>throw new Error("untrusted body executed")</script>'));
}
async function confirm() {
  await dialog.getByRole('button', { name: '明确批准并保存', exact: true }).click();
  await dialog.waitFor({ state: 'hidden' });
}
try {
  await page.goto(base);
  await page.getByLabel('密码', { exact: true }).fill('synthetic-test-passphrase-2026');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await page.getByLabel('更多功能', { exact: true }).click();
  await page.getByRole('button', { name: '数据与内容', exact: true }).click();
  await page.getByText('尚无已保存文档。', { exact: true }).waitFor();
  await page.getByRole('button', { name: '新建文档', exact: true }).click();
  await page.waitForURL('**/data/documents/new');
  await page.getByLabel('文档标题', { exact: true }).fill('合成文档浏览器验收');
  await page.getByLabel('正文格式', { exact: true }).selectOption('markdown');
  await editor.fill(body);
  await page.getByRole('complementary', { name: '文档列表' }).getByRole('button', { name: '合成工作小结', exact: true }).click();
  assert.equal(await editor.evaluate(node => node.selectionStart), 0);
  assert.equal(await editor.evaluate(node => node.selectionEnd), '# 合成工作小结'.length);
  await page.getByRole('button', { name: '学生', exact: true }).click();
  await page.getByText('请先完成或取消当前操作，再切换页面。', { exact: false }).waitFor();
  assert.equal(await editor.inputValue(), body);
  await page.getByRole('button', { name: '保存草稿', exact: true }).click();
  await dialog.waitFor();
  await assertRendered(dialog.locator('.document-text').last());
  await mkdir('test-results', { recursive: true });
  await page.screenshot({ path: `test-results/teaching-math-document-${process.env.CLASS_OS_TEST_LOST_REPLY === '1' ? 'lost' : 'normal'}.png` });
  const identity = await (await context.request.get(base + '/api/identity/session')).json();
  const prefix = `/api/workspaces/${identity.subject.workspace_id}`;
  const collection = `${prefix}/classes/${classroom}/terms/${term}/documents`;
  const headers = { origin: base, 'x-class-os-csrf': identity.csrf_token };
  assert.equal((await (await context.request.get(base + collection, { headers })).json()).data.length, 0);
  await dialog.getByRole('button', { name: '明确批准并保存', exact: true }).click();
  if (process.env.CLASS_OS_TEST_LOST_REPLY === '1') {
    await dialog.getByText('保存结果尚未确认，请先核对，避免重复保存。', { exact: true }).waitFor();
    assert.equal(commits.length, 1);
    assert(await dialog.getByRole('button', { name: '明确批准并保存', exact: true }).isDisabled());
    await dialog.getByRole('button', { name: '核对原文档提交', exact: true }).click();
  }
  await dialog.waitFor({ state: 'hidden' });
  await page.waitForURL('**/students');
  await page.getByLabel('更多功能', { exact: true }).click();
  await page.getByRole('button', { name: '数据与内容', exact: true }).click();
  await page.waitForURL(/\/data\/documents\/[a-f0-9-]{36}$/);
  const documentId = new URL(page.url()).pathname.split('/').at(-1);
  await page.reload();
  await editor.waitFor();
  assert.equal(await editor.inputValue(), body);
  const persisted = await (await context.request.get(base + collection + '/' + documentId, { headers })).json();
  assert.equal(persisted.data.body, body); assert.equal(persisted.data.format, 'markdown');
  await page.getByRole('button', { name: '原文', exact: true }).click();
  await assertRendered(page.locator('.document-text').last());
  await page.setViewportSize({ width: 390, height: 844 });
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('button', { name: '修改后', exact: true }).click();
  assert.equal(await editor.inputValue(), body);
  assert.equal(commits.length, 1);
  let releaseRead, readReached, readFinished;
  const readGate = new Promise(resolve => { releaseRead = resolve; }); readReleases.push(releaseRead);
  const reached = new Promise(resolve => { readReached = resolve; });
  const finished = new Promise(resolve => { readFinished = resolve; });
  await page.route(`**${collection}/${documentId}`, async route => {
    const response = await route.fetch(); readReached(); await readGate;
    try { await route.fulfill({ response }); } catch { /* Navigation aborted this owned read. */ }
    finally { readFinished(); }
  }, { times: 1 });
  await page.getByRole('button', { name: '重新读取文档', exact: true }).click();
  await Promise.race([reached, new Promise((_, reject) => setTimeout(() => reject(new Error('Owned document read not reached')), 10000))]);
  assert(await page.getByRole('button', { name: '新建文档', exact: true }).isEnabled());
  await page.getByRole('button', { name: '新建文档', exact: true }).click();
  await page.getByLabel('文档标题', { exact: true }).fill('切换后的未保存草稿');
  await editor.fill('迟到的旧文档不得覆盖此草稿');
  releaseRead(); await finished;
  assert.equal(await editor.inputValue(), '迟到的旧文档不得覆盖此草稿');
  assert.equal(await page.getByLabel('文档标题', { exact: true }).inputValue(), '切换后的未保存草稿');
  await page.getByRole('button', { name: '放弃本地编辑并重新读取', exact: true }).click();
  await page.getByRole('complementary', { name: '文档列表' }).getByRole('button', { name: /合成文档浏览器验收/ }).click();
  await page.waitForFunction(expected => document.querySelector('[aria-label="文档正文"]')?.value === expected, body);
  await context.setOffline(true);
  await editor.fill(body + '\n保留离线编辑。');
  assert.equal(await editor.inputValue(), body + '\n保留离线编辑。');
  await context.setOffline(false);
  await page.getByRole('button', { name: '刷新数据', exact: true }).click();
  await page.waitForFunction(() => !document.querySelector('[aria-label="文档正文"]')?.readOnly);
  await page.getByRole('button', { name: '保存草稿', exact: true }).click();
  await confirm();
  await page.getByText('版本 2 · 可审阅草稿', { exact: true }).waitFor();
  await page.getByRole('button', { name: '修订记录', exact: true }).click();
  let releaseRevision, revisionReached, revisionFinished;
  const revisionGate = new Promise(resolve => { releaseRevision = resolve; }); readReleases.push(releaseRevision);
  const revisionReady = new Promise(resolve => { revisionReached = resolve; });
  const revisionDone = new Promise(resolve => { revisionFinished = resolve; });
  await page.route(`**${collection}/${documentId}/revisions/1`, async route => {
    const response = await route.fetch(); revisionReached(); await revisionGate;
    try { await route.fulfill({ response }); } catch { /* Selection invalidates this owned read. */ }
    finally { revisionFinished(); }
  }, { times: 1 });
  await page.getByRole('region', { name: '已保存文档版本' }).getByRole('button', { name: /版本 1 · 新建/ }).click();
  await Promise.race([revisionReady, new Promise((_, reject) => setTimeout(() => reject(new Error('Owned revision not reached')), 10000))]);
  assert(await page.getByRole('button', { name: '新建文档', exact: true }).isEnabled());
  await page.getByRole('button', { name: '新建文档', exact: true }).click();
  await editor.fill('版本读取期间的新草稿'); releaseRevision(); await revisionDone;
  assert.equal(await editor.inputValue(), '版本读取期间的新草稿');
  await page.getByRole('button', { name: '修订记录', exact: true }).click();
  assert.equal(await page.getByRole('region', { name: '已保存文档版本' }).locator('h2').count(), 0);
  await page.getByRole('button', { name: '放弃本地编辑并重新读取', exact: true }).click();
  await page.getByRole('complementary', { name: '文档列表' }).getByRole('button', { name: /合成文档浏览器验收/ }).click();
  await editor.waitFor(); await page.getByRole('button', { name: '修订记录', exact: true }).click();
  await page.getByRole('region', { name: '已保存文档版本' }).getByRole('button', { name: /版本 1 · 新建/ }).click();
  await assertRendered(page.locator('.document-text').last());
  const revision = await (await context.request.get(base + collection + '/' + documentId + '/revisions/1', { headers })).json();
  assert.equal(revision.data.body, body); assert.equal(revision.data.format, 'markdown');
  await page.getByRole('button', { name: '修改后', exact: true }).click();
  await editor.fill('本地拟修改，不覆盖并发版本');
  await page.getByRole('button', { name: '保存草稿', exact: true }).click();
  await dialog.waitFor();
  // A second authorized client updates the same record through real BCG.
  const commands = base + prefix + '/document-commands';
  const proposed = await context.request.post(commands + '/preview', { headers, data: {
    command: 'document.revise', document_id: documentId, class_id: classroom, term_id: term,
    expected_version: 2, title: '合成并发版本', body: '由第二个授权客户端保存', format: 'plain-text' } });
  assert.equal(proposed.status(), 200); const proposal = await proposed.json();
  const approved = await context.request.post(commands + '/approve', { headers, data: { proposal_id: proposal.proposal_id, payload_hash: proposal.payload_hash } });
  assert.equal(approved.status(), 200);
  const concurrent = await context.request.post(commands + '/commit', { headers,
    data: { proposal_id: proposal.proposal_id, idempotency_key: randomUUID(), approval: (await approved.json()).approval } });
  assert.equal(concurrent.status(), 200);
  await dialog.getByRole('button', { name: '明确批准并保存', exact: true }).click();
  await dialog.getByText('文档版本或列表已变化。', { exact: false }).waitFor();
  await dialog.getByRole('button', { name: '核对原文档提交', exact: true }).click();
  await page.getByText('尚未保存，可重试或放弃本次修改。', { exact: false }).waitFor();
  await dialog.getByRole('button', { name: '放弃文档预览', exact: true }).click();
  await page.getByRole('button', { name: '放弃本地编辑并重新读取', exact: true }).click();
  await page.waitForFunction(() => document.querySelector('[aria-label="文档正文"]')?.value === '由第二个授权客户端保存');
  await page.getByRole('button', { name: '归档文档', exact: true }).click(); await confirm();
  await page.getByText('版本 4 · 已归档，只读', { exact: true }).waitFor();
  assert(await editor.evaluate(node => node.readOnly));
  assert(await page.getByRole('button', { name: '保存草稿', exact: true }).isDisabled());
  await page.getByRole('button', { name: '恢复文档', exact: true }).click(); await confirm();
  await page.getByText('版本 5 · 可审阅草稿', { exact: true }).waitFor();
  await page.reload(); await editor.waitFor();
  assert.equal(await editor.inputValue(), '由第二个授权客户端保存');
  const forbidden = await context.request.get(base + `/api/workspaces/${randomUUID()}/classes/${classroom}/terms/${term}/documents`, { headers });
  assert.equal(forbidden.status(), 401); // Original ISB rejects a different workspace binding.
  assert(!(await forbidden.text()).includes('由第二个授权客户端保存'));
  const retained = await context.request.get(base + collection + '/' + documentId, { headers });
  assert.equal(retained.status(), 200); assert.equal((await retained.json()).data.version, 5);
  await page.screenshot({ path: `../../test-results/document-editor-${process.env.CLASS_OS_TEST_LOST_REPLY}-wide.png`, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await editor.scrollIntoViewIfNeeded();
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  assert.equal(await editor.inputValue(), '由第二个授权客户端保存');
  await page.screenshot({ path: `../../test-results/document-editor-${process.env.CLASS_OS_TEST_LOST_REPLY}-mobile.png`, fullPage: true });
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  console.log('PASS original document create/revise/history/reload/offline draft/CAS/archive/restore and lost commit recovery');
} finally { for (const release of readReleases) release(); await context.close(); await browser.close(); }
