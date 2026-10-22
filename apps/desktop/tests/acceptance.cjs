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

    // Test the narrow Web layout in this isolated test window, not the product's desktop minimum.
    await app.evaluate(({ BrowserWindow }) => { const win = BrowserWindow.getAllWindows()[0]; win.setMinimumSize(320, 400); win.setSize(510, 720); });
    await page.waitForFunction(() => innerWidth < 767);
    await page.goto('classmatter://app/students');
    const search = page.getByRole('searchbox', { name: '搜索学生' });
    await search.fill('99001');
    assert.equal(await page.locator('.table-row').count(), 1);
    await page.getByText('共 1 位演示学生', {exact:true}).waitFor();
    await search.fill('no-such-student');
    await page.getByText(/未找到匹配学生/).waitFor();
    assert.equal(await page.locator('.table-row').count(), 0);
    await page.getByRole('button', {name:'清空搜索',exact:true}).click();
    assert.equal(await page.locator('.table-row').count(), 36);
    await page.locator('.table-row').filter({hasText:'合成学生01'}).click();
    const discuss = page.getByRole('button',{name:'围绕此学生对话',exact:true});
    assert.ok(await discuss.evaluate(el => { const b=el.getBoundingClientRect(); return b.width > 200 && b.height < 60 && b.right <= innerWidth; }));
    await page.screenshot({path:path.join(evidence,'04-narrow-student.png')});
    const mobileMore = page.getByRole('navigation',{name:'移动端导航'}).getByRole('button',{name:'更多',exact:true});
    await mobileMore.click();
    const mobileMenu = page.getByRole('menu',{name:'移动端更多功能'});
    await mobileMenu.waitFor();
    assert.ok(await mobileMenu.evaluate(el => {const b=el.getBoundingClientRect();return b.top >= 44 && b.bottom <= innerHeight-60;}));
    await page.keyboard.press('End');
    assert.equal(await mobileMenu.getByRole('menuitem',{name:'设置',exact:true}).evaluate(el=>document.activeElement===el),true);
    await page.screenshot({path:path.join(evidence,'05-narrow-navigation.png')});
    await page.keyboard.press('Escape');
    await mobileMenu.waitFor({state:'hidden'});
    assert.equal(await mobileMore.evaluate(el=>document.activeElement===el),true);
    await mobileMore.click();
    await mobileMenu.getByRole('menuitem',{name:'设置',exact:true}).click();
    await page.getByRole('heading',{name:'模型与 API',exact:true}).waitFor();
    checks.push('A12: narrow student search/empty/reset/detail geometry; mobile menu, keyboard and settings navigation');

    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(1380,900));
    for (const section of ['用户与安全','外观','ClassMatter','Capture','自动化','集成','隐私与安全','数据','无障碍']) {
      await page.locator('.settings-side').getByRole('button',{name:section,exact:true}).click();
      await page.getByRole('heading',{name:section,exact:true}).waitFor();
      const learn = page.locator('.settings-controls button').first();
      await learn.click();
      await page.getByRole('dialog').getByText('未接入',{exact:true}).waitFor();
      await page.keyboard.press('Escape');
      assert.equal(await learn.evaluate(el=>document.activeElement===el),true);
    }
    await page.screenshot({path:path.join(evidence,'06-settings-boundary.png')});
    for (const [route,title] of [
      ['/dashboard','班级总览'],['/students','学生'],['/students?view=table','视图'],['/work','工作'],
      ['/data','数据与内容'],['/data/spreadsheets/score-001','表格'],['/data/documents/parents-001','文档'],
      ['/inbox','AI 待处理'],['/automation','自动化'],['/knowledge','知识库'],['/reports','报告与导出']
    ]) {
      const response = await page.goto('classmatter://app'+route);
      assert.equal(response.status(),200,route);
      await page.getByRole('heading',{name:title,exact:true}).waitFor();
      assert.equal(await page.getByRole('alert').count(),0,route);
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),route);
    }
    await page.goto('classmatter://app/students/99001');
    for(const label of ['概览','时间线','任务','记录','成绩','文件','关系']) {
      await page.getByRole('tab',{name:label,exact:true}).click();
      assert.equal(await page.getByRole('tab',{name:label,exact:true}).getAttribute('aria-selected'),'true');
      await page.getByRole('heading',{name:label==='概览'?'当前情况':label+'记录',exact:true}).waitFor();
    }
    checks.push('A13: all settings sections are explanatory, eleven route headings and seven student detail tabs render without overflow');
    await page.goto('classmatter://app/students?view=dorm');
    await page.getByRole('heading',{name:'宿舍',exact:true}).waitFor();
    assert.equal(await page.locator('.room-grid > section').count(),3);
    await page.getByRole('button',{name:'仅看有空位',exact:true}).click();
    assert.equal(await page.locator('.room-grid > section').count(),1);
    await page.getByRole('button',{name:'1号楼',exact:true}).click();
    await page.getByText('此楼层暂无演示布局；没有复用其他楼层的床位数据。',{exact:true}).waitFor();
    assert.equal(await page.locator('.room-grid > section').count(),0);
    await page.goto('classmatter://app/students?view=group');
    await page.getByRole('heading',{name:'小队与画布',exact:true}).waitFor();
    await page.getByRole('button',{name:'自动排布',exact:true}).click();
    await page.getByRole('alertdialog').getByText(/当前没有接入分组求解器/).waitFor();
    await page.keyboard.press('Escape');
    await page.goto('classmatter://app/');
    await send('打开名单');
    await page.getByRole('heading',{name:'名单事务',exact:true}).waitFor();
    assert.equal(await page.locator('.table-row').count(),36);
    await page.goto('classmatter://app/inbox');
    await page.getByRole('button',{name:'查看来源',exact:true}).first().click();
    await page.getByRole('dialog').getByText('合成样例 · 无真实模型置信度或敏感度判定',{exact:true}).waitFor();
    await page.keyboard.press('Escape');
    checks.push('A14: dorm scope/empty filter, group non-solver boundary, roster entry and no fabricated confidence');
    await page.goto('classmatter://app/data');
    await page.getByRole('button',{name:'图片 / OCR',exact:true}).click();
    await page.locator('.content-list').getByRole('button').first().click();
    await page.getByRole('dialog').getByRole('button',{name:'延后处理',exact:true}).click();
    await page.getByText('延后处理尚未接入；未移动文件或创建提醒',{exact:true}).waitFor();
    await page.keyboard.press('Escape');
    await page.goto('classmatter://app/data/spreadsheets/score-001');
    await page.getByRole('button',{name:'字段映射',exact:true}).click();
    await page.getByRole('dialog').getByText('保持未录入，需人工核对；不自动等同缺考或零分',{exact:true}).waitFor();
    await page.getByRole('dialog').getByRole('button',{name:'返回表格',exact:true}).click();
    assert.equal(await page.getByRole('dialog').count(),0);
    const sheetButton=page.getByRole('button',{name:'成绩汇总',exact:true});
    await sheetButton.click();
    await page.getByRole('menu',{name:'选择工作表'}).waitFor();
    await page.keyboard.press('Escape');
    assert.equal(await sheetButton.evaluate(el=>document.activeElement===el),true);
    await page.getByRole('button',{name:'查看 Diff',exact:true}).click();
    await page.getByRole('alertdialog').getByRole('button',{name:'取消',exact:true}).click();
    assert.equal(await page.getByRole('alertdialog').count(),0);
    await page.goto('classmatter://app/data/documents/parents-001');
    await page.getByRole('button',{name:'原文',exact:true}).click();
    await page.getByText('会议流程包含班级情况、学科汇报、分组沟通、问答及后续安排。',{exact:true}).waitFor();
    await page.getByRole('button',{name:'修订记录',exact:true}).click();
    await page.getByText('版本 3：删除重复的学科汇报环节，保留最后三项安排。',{exact:true}).waitFor();
    await page.getByRole('button',{name:'来源：班会材料 · 9月3日',exact:true}).click();
    await page.getByRole('dialog').getByText('合成来源样例 · 未验证',{exact:true}).waitFor();
    await page.keyboard.press('Escape');
    await page.goto('classmatter://app/reports');
    for(const row of await page.locator('.report-list article').all()) {
      for(const action of ['预览','来源','编辑']) {
        await row.getByRole('button',{name:action,exact:true}).click();
        await page.getByRole('dialog').waitFor();
        await page.keyboard.press('Escape');
      }
    }
    const exitRow=page.locator('.report-list article').filter({hasText:'数据退出包'});
    await exitRow.getByRole('button',{name:'导出',exact:true}).click();
    await page.getByRole('alertdialog').getByRole('button',{name:'取消',exact:true}).click();
    await exitRow.getByRole('button',{name:'导出',exact:true}).click();
    await page.getByRole('alertdialog').getByRole('button',{name:'确认生成',exact:true}).click();
    await page.getByText('退出包为演示入口；未生成或下载任何文件',{exact:true}).waitFor();
    checks.push('A15: file feedback, missing-score semantics, sheet Escape/return/cancel, document modes/source and five report detail/cancel flows');
    await page.goto('classmatter://app/data/spreadsheets/score-001');
    const formula=page.getByRole('textbox',{name:'选中单元格样例值'});
    await page.getByRole('button',{name:'单元格 B2：88',exact:true}).click();
    assert.equal(await formula.inputValue(),'88');
    await page.getByRole('button',{name:'单元格 C4：缺考',exact:true}).click();
    assert.equal(await formula.inputValue(),'缺考');
    await page.getByRole('button',{name:'单元格 C5：空白',exact:true}).click();
    assert.equal(await formula.inputValue(),'');
    await page.getByRole('button',{name:'成绩汇总',exact:true}).click();
    await page.getByRole('menu',{name:'选择工作表'}).getByRole('button',{name:'导入问题',exact:true}).click();
    await page.getByRole('button',{name:'单元格 D2：需确认',exact:true}).waitFor();
    await page.getByRole('button',{name:'导入问题',exact:true}).click();
    await page.getByRole('menu',{name:'选择工作表'}).getByRole('button',{name:'原始数据',exact:true}).click();
    await page.getByRole('button',{name:'单元格 F2：合成样例',exact:true}).waitFor();
    checks.push('A16: sheet selection changes actual sample rows; accessible cell selection and formula agree, blank remains blank');
    await page.goto('classmatter://app/automation');
    await page.getByRole('button',{name:/午休前确认迟到后续/}).click();
    await page.getByRole('dialog').getByRole('button',{name:'暂停计划',exact:true}).click();
    await page.getByText('仅修改当前演示暂停标记；未暂停实际后台计划',{exact:true}).waitFor();
    await page.getByRole('button',{name:'运行记录',exact:true}).click();
    await page.getByRole('button',{name:/迟到后续检查/}).click();
    await page.getByRole('dialog').getByText('样例步骤：检查触发条件（未执行）',{exact:true}).waitFor();
    await page.keyboard.press('Escape');
    await page.goto('classmatter://app/knowledge');
    const knowledgeSearch=page.getByRole('searchbox',{name:'搜索知识样例'});
    await knowledgeSearch.fill('no-matching-knowledge');
    await page.getByText('没有找到相关内容',{exact:true}).waitFor();
    await knowledgeSearch.fill('');
    assert.equal(await page.locator('.knowledge-grid > button').count(),5);
    await page.getByRole('button',{name:'添加来源',exact:true}).click();
    await page.getByRole('dialog').getByRole('button',{name:'知道了',exact:true}).click();
    assert.equal(await page.getByRole('dialog').count(),0);
    await page.goto('classmatter://app/students/99003?tab=tasks');
    await page.getByText('此学生暂无任务样例；没有复制其他学生的数据。',{exact:true}).waitFor();
    await page.getByRole('button',{name:'返回学生列表',exact:true}).click();
    await page.getByRole('heading',{name:'学生',exact:true}).waitFor();
    await app.evaluate(({ BrowserWindow })=>BrowserWindow.getAllWindows()[0].setSize(510,720));
    await page.waitForFunction(()=>innerWidth<767);
    for (const [label,title] of [['总览','班级总览'],['数据与内容','数据与内容'],['AI 待处理','AI 待处理'],['自动化','自动化'],['知识库','知识库'],['报告与导出','报告与导出'],['设置','模型与 API']]) {
      await page.getByRole('navigation',{name:'移动端导航'}).getByRole('button',{name:'更多',exact:true}).click();
      await page.getByRole('menu',{name:'移动端更多功能'}).getByRole('menuitem',{name:label,exact:true}).click();
      await page.getByRole('heading',{name:title,exact:true}).waitFor();
    }
    await page.getByRole('navigation',{name:'移动端导航'}).getByRole('button',{name:'更多',exact:true}).click();
    await page.getByRole('heading',{name:'模型与 API',exact:true}).click();
    await page.getByRole('menu',{name:'移动端更多功能'}).waitFor({state:'hidden'});
    checks.push('A17: automation has no real scheduler, knowledge empty/reset/dismiss, student empty/back and all seven mobile destinations/outside dismissal');
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
