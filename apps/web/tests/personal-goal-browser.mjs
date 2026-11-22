import assert from 'node:assert/strict';
import { chromium, expect } from '@playwright/test';

const { CLASS_OS_TEST_URL: base, CLASS_OS_GOAL_PHASE: phase, CLASS_OS_GOAL_REQUEST: request,
  CLASS_OS_GOAL_REPLY: reply, CLASS_OS_GOAL_DELIVERABLE: deliverable, CLASS_OS_GOAL_LABEL: material } = process.env;
if (!/^http:\/\/127\.0\.0\.1:\d+$/.test(base || '') || !['start', 'resume'].includes(phase)) {
  throw new Error('Disposable goal fixture required');
}
const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [], external = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => {
    if (/^https?:/.test(request.url()) && !request.url().startsWith(base + '/')) external.push(request.url());
  });
  await page.goto(base);
  await page.getByLabel('密码', { exact: true }).fill('synthetic-test-passphrase-2026');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  const input = page.getByLabel('输入消息');
  await expect(input).toBeEnabled();
  const send = async text => {
    await input.fill(text);
    const submit = page.getByRole('button', { name: '发送消息', exact: true });
    await expect(submit).toBeEnabled();
    await submit.click();
  };
  const cards = page.getByRole('region', { name: '对话中的操作候选' });
  const confirm = async card => {
    await card.getByRole('button', { name: '预览这项操作', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: '确认这次变更', exact: true });
    await dialog.getByRole('button', { name: /^(明确批准并提交|确认提交)$/ }).click();
    await expect(dialog).toHaveCount(0);
    await card.getByRole('status').filter({ hasText: '已保存' }).waitFor({ timeout: 20000 });
  };
  const question = page.getByRole('article', { name: '助手回复', exact: true }).filter({ hasText: `请补充${material}` });
  if (phase === 'start') {
    await send(request);
    const instruction = cards.filter({ hasText: '班级目标委托' });
    await expect(instruction).toContainText(deliverable);
    await expect(instruction).toContainText(material);
    await expect(question).toHaveCount(0);
    await confirm(instruction);
    await question.waitFor({ timeout: 25000 });
    await expect(question).toHaveCount(1);
  } else {
    const conversation = page.getByRole('region', { name: '聊天列表', exact: true }).getByRole('button').filter({ hasText: request });
    await expect(conversation.getByRole('img', { name: '有待处理的小结', exact: true })).toBeVisible();
    await conversation.click();
    await expect(question).toBeVisible();
    await send(reply);
    const result = cards.filter({ hasText: '合成甲、合成乙。' });
    const comparison = result.getByRole('region', { name: '变更前后对比' });
    await comparison.getByLabel('待确认的结果', { exact: true }).getByText(deliverable, { exact: true }).waitFor({ timeout: 25000 });
    await expect(page.locator('.r1-error')).toHaveCount(0);
    await confirm(result);
    await page.reload();
    const saved = comparison.getByLabel('已保存的结果', { exact: true });
    await expect(saved).toContainText('老师补充：回执名单：合成甲、合成乙。');
    await expect(result).toHaveCount(1);
    await expect(question).toHaveCount(1);
    await expect(conversation.getByRole('img', { name: '有待处理的小结', exact: true })).toHaveCount(0);
  }
  assert.deepEqual(errors, []);
  assert.deepEqual(external, []);
  console.log(`PASS original goal UI ${phase}`);
} finally { await browser.close(); }
