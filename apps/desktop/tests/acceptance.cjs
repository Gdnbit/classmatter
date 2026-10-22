const { _electron: electron } = require('playwright-core');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');

const root = path.resolve(__dirname, '..');
const evidence = path.join(root, '.build/evidence/acceptance');
fs.mkdirSync(evidence, { recursive: true });
const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;

async function main() {
  let app;
  const checks = [];
  const errors = [];
  const remote = [];
  try {
    app = await electron.launch({ executablePath: path.join(root, 'out/ClassMatter-Demo-win32-x64/ClassMatter-Demo.exe'), env });
    const page = await app.firstWindow();
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => { if (/^https?:|^wss?:/.test(request.url())) remote.push(request.url()); });
    const nav = () => page.getByRole('navigation', { name: '主要工作组件' });
    const history = () => page.locator('.chat-history');
    const composer = () => page.getByPlaceholder('输入、查询、记录或安排班级工作……');
    const fresh = async () => { await page.locator('.new-chat').click(); await page.getByRole('heading', { name: '今天想处理什么？' }).waitFor(); };
    const send = async text => { await composer().fill(text); await composer().press('Enter'); };
    await page.getByRole('heading', { name: '今天想处理什么？' }).waitFor();

    // Menus must fit the actual content area even on the smallest supported window.
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(1000, 680));
    await page.waitForFunction(() => innerWidth <= 1010);
    await nav().getByRole('button', { name: '更多', exact: true }).click();
    const more = page.getByRole('menu', { name: '更多功能' });
    await more.waitFor();
    assert.ok(await more.evaluate(el => { const b=el.getBoundingClientRect(); return b.top >= 44 && b.bottom <= innerHeight && b.right <= innerWidth; }));
    await more.getByRole('button', { name: /设置/ }).scrollIntoViewIfNeeded();
    assert.ok(await more.getByRole('button', { name: /设置/ }).evaluate(el => el.getBoundingClientRect().bottom <= innerHeight));
    await page.screenshot({ path: path.join(evidence, '01-menu-minimum.png') });
    await page.keyboard.press('Escape');
    await more.waitFor({ state: 'hidden' });
    checks.push('A01: minimum-window menu bounds, scrollable settings and Escape');

    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(1380, 900));
    await nav().getByRole('button', { name: '工作', exact: true }).click();
    const task = page.getByRole('button', { name: /合成学生01迟到后续/ });
    await task.click();
    const detail = page.getByRole('dialog', { name: '合成学生01迟到后续' });
    await detail.waitFor();
    assert.ok(await detail.evaluate(el => el.getBoundingClientRect().top >= 44));
    assert.ok(await detail.getByRole('button', { name: '关闭详情' }).evaluate(el => el.getBoundingClientRect().top >= 44));
    for (let i=0;i<8;i++) { await page.keyboard.press('Tab'); assert.equal(await page.evaluate(() => !!document.activeElement.closest('.detail-sheet')), true); }
    await page.screenshot({ path: path.join(evidence, '02-detail-boundary.png') });
    await page.keyboard.press('Escape');
    await detail.waitFor({ state: 'hidden' });
    assert.equal(await task.evaluate(el => document.activeElement === el), true);
    assert.equal(await page.locator('.app-shell').evaluate(el => el.inert), false);
    checks.push('A02: drawer safe area, focus trap, Escape and trigger focus restoration');

    await task.click();
    await page.getByRole('button', { name: '标记完成', exact: true }).click();
    await history().getByRole('button', { name: '今天的班级工作', exact: true }).click();
    await page.getByRole('button', { name: /需要我处理 2 项/ }).waitFor();
    assert.equal(await page.locator('.ambient').getByRole('button', { name: /合成学生01迟到后续/ }).count(), 0);
    await nav().getByRole('button', { name: '总览', exact: true }).click();
    assert.equal(await page.locator('.widget').filter({hasText:'需要我处理'}).locator('strong').first().innerText(), '2 项');
    await nav().getByRole('button', { name: '学生', exact: true }).click();
    await page.locator('.table-row').filter({ hasText: '合成学生01' }).click();
    await page.getByText('0 项演示待跟进 · 1 项演示已完成', { exact: true }).waitFor();
    await page.getByRole('button', { name: '围绕此学生对话', exact: true }).click();
    assert.match(await composer().inputValue(), /合成学生01.*99001/);
    checks.push('A03: completion shared across home/counts/student; explicit object discussion context');

    await page.locator('.persistent-workspace').getByRole('button', { name: '期中考试', exact: true }).click();
    await page.waitForURL('**/spaces/midterm');
    await page.getByRole('heading', { name: '期中考试', exact: true }).waitFor();
    await page.locator('.persistent-workspace').getByRole('button', { name: '座位与分组调整', exact: true }).click();
    await page.waitForURL('**/spaces/seating');
    await page.getByRole('heading', { name: '座位与分组调整', exact: true }).waitFor();
    await page.getByText('此范围暂无该类演示事项。未自动创建任务或修改其他工作空间。').waitFor();
    checks.push('A04: named workspaces have distinct stable IDs, scopes and empty states');

    await fresh();
    await send('整理今天待跟进事项');
    const answer = page.locator('.message.assistant').last();
    await answer.waitFor();
    assert.match(await answer.innerText(), /当前演示事项列表/);
    assert.doesNotMatch(await answer.innerText(), /合成学生01迟到后续/);
    await history().getByRole('button', { name: '整理今天待跟进事项', exact: true }).dblclick();
    await page.getByRole('textbox', { name: '重命名对话' }).fill('验收对话');
    await page.getByRole('textbox', { name: '重命名对话' }).press('Enter');
    await history().getByRole('button', { name: '验收对话', exact: true }).waitFor();
    await fresh();
    await history().getByRole('button', { name: '验收对话', exact: true }).click();
    assert.match(await page.locator('.message.assistant').last().innerText(), /当前演示事项列表/);
    const draftChatId = await history().locator('[aria-current="page"]').getAttribute('data-conversation-id');
    await composer().fill('尚未发送的会话草稿');
    await fresh();
    assert.equal(await composer().inputValue(), '');
    await composer().fill('另一会话的草稿');
    await history().locator(`[data-conversation-id="${draftChatId}"]`).click();
    assert.equal(await composer().inputValue(), '尚未发送的会话草稿');
    await page.locator('.sidebar-search').getByRole('button', { name: '搜索', exact: true }).click();
    await page.getByRole('textbox', { name: '搜索当前演示对话' }).fill('整理今天待跟进事项');
    await history().getByRole('button', { name: '验收对话', exact: true }).waitFor();
    await page.keyboard.press('Escape');
    checks.push('A05: real history, generated title, rename, message search and session switching');

    await fresh();
    await page.locator('.model-switch').click();
    const modelMenu = page.getByRole('menu', { name: '选择模型' });
    await modelMenu.waitFor();
    await composer().click();
    await modelMenu.waitFor({ state: 'hidden' });
    await page.locator('.model-switch').click();
    await page.keyboard.press('Escape');
    await modelMenu.waitFor({ state: 'hidden' });
    assert.equal(await page.locator('.model-switch').evaluate(el => document.activeElement === el), true);
    await composer().fill('组合输入尚未完成');
    await composer().dispatchEvent('keydown', { key: 'Enter', code: 'Enter', isComposing: true, bubbles: true });
    assert.equal(await page.locator('.message.user').count(), 0);
    await composer().press('Enter');
    await page.locator('.message.user').waitFor();
    checks.push('A06: outside/Escape menu dismissal, focus restoration and IME Enter protection');

    await fresh();
    await send('调整座位');
    await page.locator('.message.assistant').filter({ hasText: '未生成变更' }).waitFor();
    assert.equal(await page.locator('.seat-grid').count(), 0);
    await send('交换合成学生01和合成学生02的座位，先给我预览');
    await page.locator('.seat-grid').waitFor();
    const seatNames = await page.locator('.seat-grid .seat strong').allTextContents();
    assert.equal(seatNames.length, 36);
    assert.equal(new Set(seatNames).size, 36);
    const diff = await page.locator('.inspector .diff').innerText();
    assert.match(diff, /合成学生01/); assert.match(diff, /合成学生02/); assert.doesNotMatch(diff, /合成学生05/);
    assert.match(await page.locator('.seat').filter({ hasText: '1排1座' }).innerText(), /合成学生02/);
    const y = await page.locator('.seat-row').first().locator('.seat').evaluateAll(items => items.map(el => Math.round(el.getBoundingClientRect().top)));
    assert.equal(new Set(y).size, 1);
    assert.equal(await page.locator('.desktop-titlebar').evaluate(el => Math.round(el.getBoundingClientRect().top)), 0);
    await page.locator('.toast').waitFor({ state: 'hidden' });
    await page.screenshot({ path: path.join(evidence, '03-correct-preview.png') });
    checks.push('A07: ambiguous request rejected; exact requested identities, 36 unique seats and six-column topology');

    const previewChat = '调整座位';
    await fresh();
    assert.equal(await page.locator('.inspector .diff').count(), 0);
    await history().getByRole('button', { name: previewChat.trim(), exact: true }).click();
    await nav().getByRole('button', { name: '学生', exact: true }).click();
    await page.getByRole('tab', { name: '座位', exact: true }).click();
    if (await page.getByRole('button', { name: '打开检查器' }).count()) await page.getByRole('button', { name: '打开检查器' }).click();
    await page.getByRole('button', { name: '应用变更', exact: true }).click();
    await page.getByRole('button', { name: '确认应用', exact: true }).waitFor();
    assert.equal(await page.getByText('已应用到当前演示内存；未写入业务数据库').count(), 0);
    await page.getByRole('button', { name: '确认应用', exact: true }).click();
    await page.getByText('已应用到当前演示内存；未写入业务数据库').waitFor();
    assert.equal(new Set(await page.locator('.seat-grid .seat strong').allTextContents()).size, 36);
    await nav().getByRole('button', { name: '学生', exact: true }).click();
    await page.getByRole('tab', { name: '清单', exact: true }).click();
    assert.match(await page.locator('.table-row').filter({ hasText: '合成学生01' }).innerText(), /1排2座/);
    checks.push('A08: draft is conversation-scoped; confirmation required; applied memory agrees with student list');

    await history().getByRole('button', { name: previewChat.trim(), exact: true }).click();
    await send('交换合成学生01和合成学生02的座位');
    await page.getByRole('button', { name: '演示：提交状态待确认', exact: true }).click();
    assert.equal(await page.getByRole('button', { name: '应用变更', exact: true }).isDisabled(), true);
    await page.getByRole('button', { name: '检查状态', exact: true }).click();
    assert.equal(await page.getByText('已应用到当前演示内存；未写入业务数据库').count(), 0);
    checks.push('A09: unknown-state demonstration never fabricates an applied result');

    await page.goto('classmatter://app/settings/user');
    await page.getByRole('button', { name: '测试连接', exact: true }).click();
    await page.getByText(/仅模拟界面反馈；未发起网络请求/).waitFor();
    assert.equal(await page.getByLabel('API Key', { exact: true }).getAttribute('type'), 'password');
    await page.goto('classmatter://app/students/unknown');
    await page.getByRole('heading', { name: '未知学生', exact: true }).waitFor();
    await page.goto('classmatter://app/');
    await page.locator('input[type=file]').nth(1).setInputFiles({ name: 'synthetic.txt', mimeType: 'text/plain', buffer: Buffer.from('synthetic fixture') });
    await page.getByText('仅选中文件 · 本演示未上传或解析', { exact: true }).waitFor();
    await page.getByRole('button', { name: '移除附件', exact: true }).click();
    const dropped = await page.evaluateHandle(() => { const data = new DataTransfer(); data.items.add(new File(['synthetic'], 'synthetic-drop.md', {type:'text/markdown'})); return data; });
    await page.locator('.composer').dispatchEvent('drop', { dataTransfer: dropped });
    await page.getByText('synthetic-drop.md', {exact:true}).waitFor();
    await page.getByRole('button', { name: '移除附件', exact: true }).click();
    const multiple = await page.evaluateHandle(() => { const data = new DataTransfer(); for(const name of ['first.txt','second.txt']) data.items.add(new File(['synthetic'],name,{type:'text/plain'})); return data; });
    await page.locator('.composer').dispatchEvent('drop', { dataTransfer: multiple });
    await page.getByText('本演示一次仅选择一个附件，未选择或上传任何文件').waitFor();
    assert.equal(await page.locator('.attachment').count(), 0);
    checks.push('A10: honest connection/file states, masked secret input and no unknown-identity fallback');

    await page.getByRole('button', { name: '语音转文字', exact: true }).click();
    await page.getByText('模拟录音 · 未开启麦克风', {exact:true}).waitFor();
    await page.getByRole('button', { name: '停止', exact: true }).click();
    await fresh();
    await page.waitForTimeout(900); // Prove the old 700ms synthetic timer cannot affect the new conversation.
    assert.equal(await composer().inputValue(), '');
    assert.equal(await page.locator('.voice-state').count(), 0);
    checks.push('A11: synthetic drag/drop, multi-file rejection, isolated drafts and cancelled late voice result');
    assert.deepEqual(remote, []);
    assert.deepEqual(errors, []);
    const result = { checks, pageErrors: errors, externalRequests: remote, scope: 'Synthetic memory only; no business API/model/database' };
    fs.writeFileSync(path.join(evidence, 'result.json'), JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify(result, null, 2));
  } catch(error) {
    if(app) { const page=await app.firstWindow(); await page.screenshot({path:path.join(evidence,'failure.png')}).catch(()=>{}); console.error('URL:',page.url(),'page errors:',errors); }
    throw error;
  } finally { if(app) await app.close(); }
}
main().catch(error => { console.error(error); process.exitCode=1; });
