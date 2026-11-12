import assert from 'node:assert/strict';
import path from 'node:path';
import { chromium, expect } from '@playwright/test';

const base = process.env.CLASS_OS_TEST_URL, destination = process.env.CLASSMATTER_TEST_DOWNLOAD_ROOT;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '') || !path.isAbsolute(destination || '')) throw new Error('Owned synthetic fixture and download directory required');
const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
try {
  const page = await browser.newPage({ acceptDownloads: true }), errors = [], external = [], downloads = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => { if (/^https?:/.test(request.url()) && !request.url().startsWith(base + '/')) external.push(request.url()); });
  page.on('download', value => downloads.push(value));
  await page.goto(base);
  await page.getByLabel('密码', { exact: true }).fill('synthetic-test-passphrase-2026');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  await page.getByLabel('更多功能', { exact: true }).click();
  await page.getByRole('button', { name: '数据与内容', exact: true }).click();
  await page.getByRole('button', { name: /合成班级小结/ }).first().click();
  const word = page.getByRole('button', { name: '导出 Word', exact: true }), ppt = page.getByRole('button', { name: '导出 PPT', exact: true });
  for (const [button, extension] of [[word, 'docx'], [ppt, 'pptx']]) {
    await expect(button).toBeEnabled();
    const next = page.waitForEvent('download'); await button.click(); const file = await next;
    assert(file.suggestedFilename().endsWith('.' + extension));
    await file.saveAs(path.join(destination, 'lesson.' + extension));
    assert.equal(await file.failure(), null);
  }
  const editor = page.getByLabel('文档正文', { exact: true }), original = await editor.inputValue();
  await editor.fill(original + '\n未保存的课堂补充');
  await expect(word).toBeDisabled(); await expect(ppt).toBeDisabled();
  assert.equal(downloads.length, 2);
  await page.getByRole('button', { name: '放弃本地编辑并重新读取', exact: true }).click();
  await expect(editor).toHaveValue(original); await expect(word).toBeEnabled();
  for (const status of [409, 413, 503]) {
    await page.route('**/exports/**', route => route.fulfill({ status, contentType: 'application/json', body: '{}' }), { times: 1 });
    await word.click();
    await expect(page.getByRole('alert')).toContainText(status === 409 ? '文档已更新' : status === 413 ? '内容较长' : '暂时无法导出');
    assert.equal(await editor.inputValue(), original); assert.equal(downloads.length, 2);
  }
  let release;
  const held = new Promise(resolve => release = resolve);
  await page.route('**/exports/**', async route => { await held; await route.abort().catch(() => {}); }, { times: 1 });
  await word.click(); await expect(word).toBeDisabled();
  await page.getByRole('button', { name: '学生', exact: true }).click();
  await page.waitForURL('**/students'); release();
  await page.getByRole('region', { name: '学生清单', exact: true }).waitFor();
  assert.equal(downloads.length, 2);
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
} finally { await browser.close(); }
