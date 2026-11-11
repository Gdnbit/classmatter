import assert from 'node:assert/strict';
import { chromium, expect } from '@playwright/test';
import nodePath from 'node:path';

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
  await page.getByLabel('密码', { exact: true }).fill('synthetic-test-passphrase-2026');
  await page.getByRole('button', { name: '登录', exact: true }).click();
  const input = page.getByLabel('输入消息'), history = page.getByRole('region', { name: '已保存的对话' });
  await input.waitFor();
  assert.equal(await page.getByText('CLASSMATTER · 对话', { exact: true }).count(), 0);
  assert.equal(await page.getByText('少记、少追、少重复。事实由你确认，系统帮你复用。', { exact: true }).count(), 0);
  for (const name of ['刷新对话', '归档对话', '清除聊天正文', '刷新数据']) assert.equal(await page.getByRole('button', { name, exact: true }).count(), 0);
  async function assertFixedHome(width, height) {
    await page.setViewportSize({ width, height });
    await page.locator('.r1-conversation-home').waitFor();
    await page.locator('.r1-welcome').evaluate(element => Promise.all(element.getAnimations().map(animation => animation.finished)));
    const bounds = await page.evaluate(() => {
      const home = document.querySelector('.r1-conversation-home');
      const composer = document.querySelector('.r1-composer').getBoundingClientRect();
      const targets = [...document.querySelectorAll('.r1-heading, .r1-quick, .r1-attention h3')].map(element => {
        const rect = element.getBoundingClientRect();
        return { top: rect.top, bottom: rect.bottom };
      });
      return { overflow: home.scrollHeight - home.clientHeight, documentOverflow: document.documentElement.scrollHeight - innerHeight, top: home.getBoundingClientRect().top, composerTop: composer.top, composerBottom: composer.bottom, targets };
    });
    assert(bounds.overflow <= 1, JSON.stringify({ width, height, bounds }));
    assert(bounds.documentOverflow <= 1);
    assert(bounds.composerBottom <= height);
    for (const target of bounds.targets) {
      assert(target.top >= bounds.top && target.bottom <= bounds.composerTop, JSON.stringify({ width, height, target, bounds }));
    }
    assert.equal(await page.getByRole('button', { name: '刷新对话', exact: true }).count(), 0);
    await page.locator('.r1-heading').hover();
    await page.mouse.wheel(0, 600);
    assert.equal(await page.locator('.r1-conversation-home').evaluate(element => element.scrollTop), 0);
  }
  for (const [width, height] of [[1440, 900], [1280, 720], [1024, 600], [390, 844]]) await assertFixedHome(width, height);
  await page.setViewportSize({ width: 1440, height: 1000 });
  assert.equal(await page.locator('nav[aria-label="主要工作组件"] > button').count(), 4);
  assert.equal(await page.locator('.sidebar .scope').count(), 0);
  assert.equal(await page.getByRole('region', { name: '聊天列表' }).getByRole('button', { name: '新对话', exact: true }).count(), 1);
  await input.fill('保留未发送的草稿');
  const initialPath = new URL(page.url()).pathname;
  await page.getByRole('button', { name: '设置', exact: true }).click();
  await page.getByRole('dialog').getByRole('heading', { name: '设置', exact: true }).waitFor();
  assert.equal(new URL(page.url()).pathname, initialPath);
  await page.getByRole('button', { name: '关闭设置', exact: true }).click();
  assert.equal(await input.inputValue(), '保留未发送的草稿');
  await page.getByRole('button', { name: '切换模型', exact: true }).click();
  await page.getByRole('region', { name: '选择模型', exact: true }).waitFor();
  assert.equal(await page.getByText('GLM-4.7-Flash', { exact: true }).count(), 0);
  await page.keyboard.press('Escape');
  await page.getByRole('region', { name: '选择模型', exact: true }).waitFor({ state: 'hidden' });
  await input.fill('合成普通聊天，不涉及班级');
  await page.getByRole('button', { name: '发送消息', exact: true }).click({ timeout: 5000 }).catch(async error => { throw new Error(JSON.stringify({ body: await page.locator('body').innerText(), errors }), { cause: error }); });
  await history.getByText('合成普通聊天已回复，不需要班级。', { exact: true }).waitFor();
  await page.waitForURL(/\/chats\/[a-f0-9-]{36}$/);
  for (const name of ['刷新对话', '归档对话', '清除聊天正文', '刷新数据']) assert.equal(await page.getByRole('button', { name, exact: true }).count(), 0);
  await page.screenshot({ path: '../../test-results/minimal-chat-conversation.png' });
  assert.equal(await page.locator('.r1-conversation-home').count(), 0);
  await page.waitForFunction(() => getComputedStyle(document.querySelector('.r1-welcome')).visibility === 'hidden');
  assert((await page.locator('.r1-welcome').boundingBox()).height < 1);
  assert.equal(await page.locator('.r1-messages .avatar').count(), 0);
  for (const copy of ['聊天由本机数据库保存，普通聊天无需班级', '聊天已接入数据库 · 涉及班级时才使用班级工具', '聊天 · 涉及班级时再关联', '本轮运行记录']) assert.equal(await page.getByText(copy, { exact: true }).count(), 0);
  const answer = history.getByRole('article', { name: '助手回复', exact: true }).first();
  await answer.getByText(/^用时 \d+\.\d 秒$/).waitFor();
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'], { origin: base });
  await answer.getByRole('button', { name: '复制回答', exact: true }).click();
  await answer.getByText('已复制回答', { exact: true }).waitFor();
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), '合成普通聊天已回复，不需要班级。');
  await page.evaluate(() => { globalThis.originalClipboardWrite = navigator.clipboard.writeText.bind(navigator.clipboard); navigator.clipboard.writeText = async () => { throw new Error('Owned clipboard denial'); }; });
  await answer.getByRole('button', { name: '复制回答', exact: true }).click();
  await answer.getByText('复制失败，请选择文字复制', { exact: true }).waitFor();
  await page.evaluate(() => { navigator.clipboard.writeText = globalThis.originalClipboardWrite; delete globalThis.originalClipboardWrite; });
  const leftInset = await page.locator('article.assistant').first().evaluate(element => element.getBoundingClientRect().left - document.querySelector('.r1-scroll').getBoundingClientRect().left);
  assert(leftInset >= 20 && leftInset <= 44);
  assert.deepEqual(await page.evaluate(() => ({ x: scrollX, overflow: document.documentElement.scrollWidth > innerWidth, sidebar: document.querySelector('.sidebar').scrollLeft })), { x: 0, overflow: false, sidebar: 0 });
  await page.screenshot({ path: nodePath.resolve('../../test-results/ui-v3-conversation.png') });
  assert.equal(await page.getByLabel('对话方式').count(), 0);
  const path = new URL(page.url()).pathname;
  await page.reload();
  await history.getByText('合成普通聊天已回复，不需要班级。', { exact: true }).waitFor();
  assert.equal(starts.length, 1);
  const savePath = '**/workspace-chat/threads/*/turns';
  await page.route(savePath, async route => { await route.fetch(); await route.abort('failed'); }, { times: 1 });
  await input.fill('合成发送响应丢失');
  await page.getByRole('button', { name: '发送消息', exact: true }).click();
  // The final read recovers a committed input even when the POST reply was lost.
  await history.getByRole('button', { name: '继续回复', exact: true }).waitFor();
  assert.equal(starts.length, 1);
  await history.getByRole('button', { name: '继续回复', exact: true }).click();
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
  const changes = [];
  for (const [message, title] of messages) {
    await input.fill(message); await page.getByRole('button', { name: '发送消息', exact: true }).click();
    const card = history.getByRole('region', { name: '对话中的操作候选' }).filter({ has: page.getByRole('heading', { name: title, exact: true }) });
    await card.getByRole('heading', { name: title, exact: true }).waitFor();
    const comparison = card.getByRole('region', { name: '变更前后对比', exact: true });
    await comparison.waitFor();
    const oldContent = await comparison.getByLabel('修改前', { exact: true }).innerText();
    const newContent = await comparison.getByLabel('待确认的结果', { exact: true }).innerText();
    changes.push({ oldContent, newContent: newContent.replace(/^调整后/, '已保存') });
    assert.equal(await page.getByRole('dialog').count(), 0); // No manual data-entry form.
    const before = starts.length;
    await page.reload();
    await card.getByRole('heading', { name: title, exact: true }).waitFor();
    assert.equal(starts.length, before);
    if (title === '建立班级与学期') {
      const csrf = (await page.context().cookies()).find(cookie => cookie.name === 'class_os_csrf');
      const legacy = await page.request.post(base + '/__fixture__/legacy-pending-preview', { data: {}, headers: { origin: base, 'x-class-os-csrf': csrf.value } });
      assert.equal(legacy.status(), 200);
      await page.reload();
      await card.getByRole('button', { name: '预览这项操作', exact: true }).waitFor();
      assert.equal(await comparison.count(), 0);
    }
    await card.getByRole('button', { name: '预览这项操作', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await dialog.getByRole('button', { name: /^(确认提交|明确批准并提交)$/ }).waitFor();
    await expect.poll(() => dialog.getByLabel('修改前', { exact: true }).innerText()).toBe(oldContent);
    await expect.poll(() => dialog.getByLabel('待确认的结果', { exact: true }).innerText()).toBe(newContent);
    assert.equal(await dialog.locator('.change-comparison dl > div').first().evaluate(element => getComputedStyle(element).display), 'block');
    if (title === '建立班级与学期') {
      await dialog.getByRole('button', { name: '放弃变更', exact: true }).click();
      await dialog.waitFor({ state: 'hidden' });
      await expect.poll(() => comparison.getByLabel('待确认的结果', { exact: true }).innerText()).toBe(newContent);
      await page.reload();
      await card.getByRole('button', { name: '预览这项操作', exact: true }).click();
      await dialog.getByRole('button', { name: /^(确认提交|明确批准并提交)$/ }).waitFor();
      await expect.poll(() => dialog.getByLabel('修改前', { exact: true }).innerText()).toBe(oldContent);
      await expect.poll(() => dialog.getByLabel('待确认的结果', { exact: true }).innerText()).toBe(newContent);
    }
    assert(!/payload_hash|expected_version|schema_version|[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}/.test(await dialog.innerText()));
    assert.equal(await dialog.locator('input,textarea,select').count(), 0);
    await dialog.getByRole('button', { name: /^(确认提交|明确批准并提交)$/ }).click();
    await dialog.waitFor({ state: 'hidden', timeout: 5000 }).catch(async error => { throw new Error(JSON.stringify({ message, dialog: await dialog.innerText(), errors }), { cause: error }); });
    await card.getByRole('status').filter({ hasText: '已保存' }).waitFor();
    await page.reload();
    await expect.poll(() => comparison.getByLabel('修改前', { exact: true }).innerText()).toBe(oldContent);
    await expect.poll(() => comparison.getByLabel('已保存的结果', { exact: true }).innerText()).toBe(changes.at(-1).newContent);
    assert.equal(new URL(page.url()).pathname, path);
  }
  const cards = history.getByRole('region', { name: '变更前后对比', exact: true });
  for (let index = 0; index < changes.length; index++) {
    await expect.poll(() => cards.nth(index).getByLabel('修改前', { exact: true }).innerText()).toBe(changes[index].oldContent);
    await expect.poll(() => cards.nth(index).getByLabel('已保存的结果', { exact: true }).innerText()).toBe(changes[index].newContent);
  }
  await page.getByRole('button', { name: '学生', exact: true }).click();
  await page.getByRole('region', { name: '学生清单', exact: true }).getByRole('button', { name: /合成学生乙/ }).waitFor();
  assert(!/内部 ID|状态 \/ 版本|共享实体/.test(await page.getByRole('main').innerText()));
  await page.getByRole('region', { name: '学生清单', exact: true }).getByRole('button', { name: /合成学生乙/ }).click();
  assert(!/[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}/.test(await page.getByRole('main').innerText()));
  await page.getByRole('button', { name: '返回学生列表', exact: true }).click();
  await page.getByRole('button', { name: '工作', exact: true }).click();
  await page.getByRole('main').getByRole('button', { name: /合成收集签字回执/ }).waitFor();
  await page.getByLabel('按状态筛选任务').selectOption('closed');
  await page.getByRole('region', { name: '事件', exact: true }).getByRole('button', { name: /合成收集签字回执/ }).click();
  await page.getByRole('button', { name: '编辑标题与截止时间', exact: true }).waitFor();
  assert.equal(await page.getByLabel('按状态筛选任务').inputValue(), 'all');
  await page.getByLabel('更多功能', { exact: true }).click();
  await page.getByRole('button', { name: '数据与内容', exact: true }).click();
  await page.getByRole('button', { name: /合成班级小结/ }).first().click();
  await page.getByRole('button', { name: '原文', exact: true }).click();
  await page.locator('.document-text').filter({ hasText: '合成补充段落' }).waitFor();
  assert(!/作者标识|完整性摘要|不展示样例|未接入|同一数据世界/.test(await page.getByRole('main').innerText()));
  await page.getByRole('button', { name: '设置', exact: true }).click();
  const settings = page.getByRole('dialog', { name: '设置', exact: true });
  assert(!/可替换 AI|R1 实现|数据库|原型|后台调度/.test(await settings.innerText()));
  await settings.getByRole('button', { name: '关闭设置', exact: true }).click();
  await page.goto(base + path);
  await history.getByText('合成普通聊天已回复，不需要班级。', { exact: true }).first().waitFor();
  assert.equal(starts.length, messages.length + 2);
  await input.fill('继续任务时保留的未发送草稿');
  await history.getByRole('button', { name: '继续任务', exact: true }).click();
  await history.getByText('继续完成上面的任务，只处理尚未完成的步骤。', { exact: true }).waitFor();
  await page.waitForFunction(() => document.querySelectorAll('article.assistant').length === 11);
  assert.equal(await input.inputValue(), '继续任务时保留的未发送草稿');
  assert.equal(starts.length, messages.length + 3);
  await input.fill('');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: '切换模型', exact: true }).click();
  const mobileMenu = await page.getByRole('region', { name: '选择模型', exact: true }).boundingBox();
  assert(mobileMenu.x >= 0 && mobileMenu.x + mobileMenu.width <= 390);
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '新对话', exact: true }).count().then(count => assert.equal(count, 0)); // Mobile hides the history group.
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole('button', { name: '新对话', exact: true }).click();
  await page.getByRole('heading', { name: '今天想处理什么？', exact: true }).waitFor();
  await page.waitForFunction(() => document.querySelector('.r1-welcome').getBoundingClientRect().height > 0);
  await assertFixedHome(1280, 720);
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  console.log('PASS original UI: no-class persisted chat; refresh never replays; AI candidates create/edit via original confirmation; same students/tasks/documents; no data forms or external calls');
} finally { await browser.close(); }
