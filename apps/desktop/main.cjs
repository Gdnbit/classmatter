const { app, BrowserWindow, Menu, dialog, protocol, session } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const { ORIGIN, localURL, serveResource } = require('./policy.cjs');

const TITLE = '班事有谱 · ClassMatter — 合成演示';
app.setName('ClassMatter Demo');
// No persistence of Demo students/conversations between launches.
app.setPath('userData', path.join(app.getPath('appData'), 'ClassMatter-Demo'));
app.setAppUserModelId('org.classmatter.demo');
protocol.registerSchemesAsPrivileged([{ scheme: 'classmatter', privileges: { standard: true, secure: true, supportFetchAPI: true } }]);
app.enableSandbox();

let window;
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (!window) return;
    if (window.isMinimized()) window.restore();
    window.show();
    window.focus();
  });
  app.whenReady().then(async () => {
    const ui = path.join(__dirname, 'ui');
    // Fail closed on missing/mismatched build; never fall back to localhost or R1.
    const marker = path.join(ui, 'desktop-demo.json');
    if (!fs.existsSync(marker) || JSON.parse(fs.readFileSync(marker, 'utf8')).mode !== 'synthetic-demo') {
      throw new Error('Desktop Demo assets are missing. Run the desktop build first.');
    }
    const isolated = session.fromPartition('classmatter-demo'); // Memory-only partition.
    isolated.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
    isolated.setPermissionCheckHandler(() => false);
    isolated.on('will-download', event => event.preventDefault());
    isolated.webRequest.onBeforeRequest((details, callback) => {
      // No API, telemetry, remote images, websockets, file:// or localhost access.
      callback({ cancel: !localURL(details.url) });
    });
    isolated.protocol.handle('classmatter', request => serveResource(ui, request));
    window = new BrowserWindow({
      width: 1380, height: 900, minWidth: 1000, minHeight: 680,
      title: TITLE, backgroundColor: '#ffffff', show: false,
      icon: path.join(__dirname, 'app.png'),
      webPreferences: { session: isolated, sandbox: true, contextIsolation: true, nodeIntegration: false, webSecurity: true, allowRunningInsecureContent: false, webviewTag: false, devTools: !app.isPackaged, spellcheck: false },
    });
    window.on('page-title-updated', event => event.preventDefault());
    window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    window.webContents.on('will-navigate', (event, url) => { if (!localURL(url)) event.preventDefault(); });
    window.webContents.on('will-redirect', (event, url) => { if (!localURL(url)) event.preventDefault(); });
    window.webContents.on('will-attach-webview', event => event.preventDefault());
    Menu.setApplicationMenu(Menu.buildFromTemplate([
      { label: '应用', submenu: [
        { label: '关于班事有谱', click: () => dialog.showMessageBox(window, { type: 'info', title: 'ClassMatter Desktop Demo', message: TITLE, detail: `桌面版 ${app.getVersion()}\n仅合成数据；修改在退出后重置。\n不连接数据库、模型或业务 API。文件解析、录音和 Agent 执行未在此 Demo 启用。\nCopyright 2026 Gdnbit · Apache-2.0` }) },
        { type: 'separator' }, { label: '退出', role: 'quit' },
      ] },
      { label: '编辑', submenu: [{ role: 'undo', label: '撤销' }, { role: 'redo', label: '重做' }, { type: 'separator' }, { role: 'cut', label: '剪切' }, { role: 'copy', label: '复制' }, { role: 'paste', label: '粘贴' }, { role: 'selectAll', label: '全选' }] },
      { label: '视图', submenu: [{ role: 'reload', label: '重新加载演示' }, { type: 'separator' }, { role: 'resetZoom', label: '实际大小' }, { role: 'zoomIn', label: '放大' }, { role: 'zoomOut', label: '缩小' }, { type: 'separator' }, { role: 'togglefullscreen', label: '全屏' }] },
    ]));
    window.once('ready-to-show', () => window.show());
    window.on('closed', () => { window = null; });
    await window.loadURL(`${ORIGIN}/`);
  }).catch(error => {
    dialog.showErrorBox('ClassMatter 启动失败', error.message);
    app.exit(1);
  });
  app.on('window-all-closed', () => app.quit());
}
