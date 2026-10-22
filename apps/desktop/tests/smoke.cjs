// Real Electron integration, not a mocked browser or localhost preview.
const { _electron: electron } = require('playwright-core');
const expect = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const desktop = path.resolve(__dirname, '..');
const packaged = process.argv.includes('--packaged');
const executable = packaged ? path.join(desktop, 'out/ClassMatter-Demo-win32-x64/ClassMatter-Demo.exe') : require('electron');
const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;
const evidence = path.join(desktop, '.build/evidence');
fs.mkdirSync(evidence, { recursive: true });

async function main() {
  let app;
  const errors = [];
  const checks = [];
  try {
    app = await electron.launch({ executablePath: executable, args: packaged ? [] : [path.join(desktop, '.build/app')], env, timeout: 30000 });
    const page = await app.firstWindow();
    page.on('pageerror', error => errors.push(error.message));
    await page.getByText('今天想处理什么？', { exact: true }).waitFor();
    expect.match(page.url(), /^classmatter:\/\/app\//);
    const isolation = await app.evaluate(({ BrowserWindow, app: nativeApp }) => {
      const preferences = BrowserWindow.getAllWindows()[0].webContents.getLastWebPreferences();
      return { sandbox: preferences.sandbox, contextIsolation: preferences.contextIsolation, nodeIntegration: preferences.nodeIntegration, webSecurity: preferences.webSecurity, preload: preferences.preload, packaged: nativeApp.isPackaged };
    });
    expect.equal(isolation.sandbox, true);
    expect.equal(isolation.contextIsolation, true);
    expect.equal(isolation.nodeIntegration, false);
    expect.equal(isolation.webSecurity, true);
    expect.equal(isolation.packaged, packaged);
    expect.equal(await page.evaluate(() => typeof window.require), 'undefined');
    expect.equal(await page.evaluate(() => typeof window.process), 'undefined');
    expect.deepEqual(await page.evaluate(() => Object.keys(window.classMatterDesktop)), ['openMenu']);
    expect.equal(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].isMenuBarVisible()), false);
    await page.getByRole('banner', { name: '桌面窗口工具栏' }).waitFor();
    expect.equal(await page.locator('.desktop-titlebar').evaluate(el => getComputedStyle(el).getPropertyValue('-webkit-app-region')), 'drag');
    expect.equal(await page.getByRole('button', { name: '切换左侧栏', exact: true }).evaluate(el => getComputedStyle(el).getPropertyValue('-webkit-app-region')), 'no-drag');
    await page.getByRole('button', { name: '切换左侧栏', exact: true }).click();
    expect.equal(await page.locator('.app-shell > .sidebar').isVisible(), false);
    await page.getByRole('button', { name: '切换左侧栏', exact: true }).click();
    expect.equal(await page.locator('.app-shell > .sidebar').isVisible(), true);
    expect.equal(await page.locator('.app-shell').evaluate(el => Math.round(el.getBoundingClientRect().bottom - innerHeight)), 0);
    expect.equal(await page.locator('.app-shell > .sidebar').evaluate(el => Math.round(el.getBoundingClientRect().bottom - innerHeight)), 0);
    checks.push('integrated draggable titlebar; native menu hidden; fixed menu-only bridge; sidebar toggle');

    await page.screenshot({ path: path.join(evidence, packaged ? 'packaged-home.png' : 'home.png') });
    const viewport = await page.evaluate(() => ({ width: innerWidth, height: innerHeight, density: devicePixelRatio, nativeOverlay: navigator.windowControlsOverlay?.visible }));
    expect.equal(viewport.nativeOverlay, true);
    fs.writeFileSync(path.join(evidence, 'viewport.json'), JSON.stringify(viewport, null, 2));
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].setSize(1000, 680));
    // Windows fractional-DPI non-client rounding can add a few CSS pixels.
    await page.waitForFunction(() => innerWidth <= 1010);
    expect.ok(await page.getByPlaceholder('输入、查询、记录或安排班级工作……').evaluate(el => el.getBoundingClientRect().bottom <= innerHeight));
    expect.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].maximize());
    await page.waitForFunction(() => innerWidth > 1010);
    expect.ok(await page.getByPlaceholder('输入、查询、记录或安排班级工作……').evaluate(el => el.getBoundingClientRect().bottom <= innerHeight));
    await app.evaluate(({ BrowserWindow }) => { const win = BrowserWindow.getAllWindows()[0]; win.unmaximize(); win.setSize(1380, 900); });
    checks.push('native window-control overlay; minimum-size and maximized layout preserve composer');
    await page.getByRole('navigation', { name: '主要工作组件' }).getByRole('button', { name: '学生', exact: true }).click();
    await page.waitForURL('**/students');
    await page.locator('.table-row').filter({ hasText: '合成学生01' }).waitFor();
    await page.reload();
    await page.locator('.table-row').filter({ hasText: '合成学生01' }).waitFor();
    await page.locator('.table-row').filter({ hasText: '合成学生01' }).click();
    await page.waitForURL(/\/students\/.+/);
    await page.reload();
    await page.getByText('合成学生01', { exact: true }).first().waitFor();
    await page.getByRole('button', { name: '返回上一页', exact: true }).click();
    await page.waitForURL('**/students');
    await page.getByRole('button', { name: '前进下一页', exact: true }).click();
    await page.waitForURL(/\/students\/.+/);
    await page.getByRole('button', { name: '返回上一页', exact: true }).click();
    await page.waitForURL('**/students');
    checks.push('student navigation, detail deep-link reload, history back');

    await page.getByRole('navigation', { name: '主要工作组件' }).getByRole('button', { name: '工作', exact: true }).click();
    await page.waitForURL('**/work');
    await page.reload();
    await page.getByText('需要我处理', { exact: true }).first().waitFor();
    checks.push('work navigation and refresh');

    const blocked = await page.evaluate(async () => {
      const results = [];
      for (const url of ['http://127.0.0.1:8443/', 'https://example.com/', 'classmatter://app/api/students']) {
        try { const response = await fetch(url); results.push(response.ok); } catch { results.push(false); }
      }
      window.open('https://example.com');
      return results;
    });
    expect.deepEqual(blocked, [false, false, false]);
    expect.equal(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().length), 1);
    checks.push('network/API access and popups blocked');

    for (const route of ['/dashboard', '/data', '/data/spreadsheets/score-001', '/data/documents/parents-001', '/inbox', '/automation', '/knowledge', '/reports', '/settings/user', '/spaces/midterm']) {
      const response = await page.goto('classmatter://app' + route);
      expect.equal(response.status(), 200, route);
      await page.getByRole('navigation', { name: '主要工作组件' }).waitFor();
      expect.ok((await page.locator('body').innerText()).length > 100, route);
    }
    checks.push('ten additional existing surface/deep-link entries render');
    await page.goto('classmatter://app/');
    const composer = page.getByPlaceholder('输入、查询、记录或安排班级工作……');
    await composer.fill('查询合成演示');
    await composer.press('Enter');
    await page.getByText('查询合成演示', { exact: true }).first().waitFor();
    checks.push('bottom composer accepts and submits synthetic conversation');

    const second = spawn(executable, packaged ? [] : [path.join(desktop, '.build/app')], { env, stdio: 'ignore' });
    await new Promise((resolve, reject) => {
      const deadline = setTimeout(() => { second.kill(); reject(new Error('Second instance did not exit')); }, 15000);
      second.once('error', reject);
      second.once('exit', code => { clearTimeout(deadline); code === 0 ? resolve() : reject(new Error(`Second instance exit ${code}`)); });
    });
    expect.equal(await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows().length), 1);
    checks.push('single-instance lock');
    expect.deepEqual(errors, []);
    // Closing the last native window must terminate the application itself.
    const process = app.process();
    const exited = new Promise((resolve, reject) => {
      const deadline = setTimeout(() => reject(new Error('App survived closing its last window')), 15000);
      process.once('exit', () => { clearTimeout(deadline); resolve(); });
    });
    await app.evaluate(({ BrowserWindow }) => BrowserWindow.getAllWindows()[0].close());
    await exited;
    checks.push('last-window close terminates main process');
    console.log(JSON.stringify({ mode: packaged ? 'packaged' : 'development', checks, pageErrors: errors }, null, 2));
    fs.writeFileSync(path.join(evidence, packaged ? 'packaged-smoke.json' : 'smoke.json'), JSON.stringify({ checks, pageErrors: errors }, null, 2) + '\n');
  } catch (error) {
    if (app) {
      const page = await app.firstWindow();
      await page.screenshot({ path: path.join(evidence, 'failure.png') }).catch(() => {});
      console.error({ url: page.url(), pageErrors: errors });
    }
    throw error;
  } finally { if (app) await app.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
