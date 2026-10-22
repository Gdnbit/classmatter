// Development-only synthetic runtime host. Offline Demo remains unchanged.
const {app,BrowserWindow,Menu,session,ipcMain,dialog}=require('electron');
const fs=require('node:fs');
const path=require('node:path');
const {desktopService}=require('./runtime-service.cjs');
const {allowed,CSP,exitDownload}=require('./runtime-policy.cjs');
app.setName('ClassMatter Synthetic Runtime');
app.setPath('userData',path.join(app.getPath('appData'),'ClassMatter-Synthetic-Runtime'));
app.setAppUserModelId('org.classmatter.synthetic-runtime');
app.enableSandbox();
let window,service,quitting=false,origin;
if(!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance',()=>{if(window){if(window.isMinimized())window.restore();window.show();window.focus();}});
  app.on('before-quit',event=>{
    if(quitting || !service) return;
    event.preventDefault();quitting=true;
    service.stop().then(()=>app.quit()).catch(()=>app.exit(1));
  });
  app.on('window-all-closed',()=>app.quit());
  app.whenReady().then(async()=>{
    if(app.isPackaged) throw new Error('This runtime entry is development-only; binary distribution is not approved.');
    const source=JSON.parse(fs.readFileSync(path.join(__dirname,'runtime-source.json'),'utf8'));
    if(source.schema_version!==1 || Object.keys(source).sort().join(',')!=='repositoryRoot,runtimeRoot,schema_version') throw new Error('Invalid runtime source');
    service=desktopService(source.repositoryRoot,path.join(__dirname,'ui'),()=>{
      if(window) window.close();
      // No automatic replay or reattachment after a service crash.
      app.quit();
    },source.runtimeRoot);
    origin=await service.start();
    const isolated=session.fromPartition('classmatter-synthetic-runtime');
    isolated.setPermissionRequestHandler((_wc,_permission,callback)=>callback(false));
    isolated.setPermissionCheckHandler(()=>false);
    isolated.webRequest.onBeforeRequest((details,callback)=>callback({cancel:!allowed(origin,details.url)}));
    isolated.webRequest.onHeadersReceived((details,callback)=>callback({responseHeaders:{...details.responseHeaders,'Content-Security-Policy':[CSP],'X-Content-Type-Options':['nosniff']}}));
    isolated.on('will-download',(event,item,contents)=>{
      if(!window || contents!==window.webContents || !exitDownload(origin,item.getURL(),item.getMimeType(),item.getTotalBytes())){event.preventDefault();return;}
      // Only the existing authorized JSON receipt route; native Save dialog
      // leaves the destination to the user. Never set an arbitrary save path.
      item.setSaveDialogOptions({title:'保存已批准的合成核心退出包',defaultPath:'ClassMatter-synthetic-core.json',filters:[{name:'JSON',extensions:['json']}]});
    });
    window=new BrowserWindow({width:1380,height:900,minWidth:1000,minHeight:680,title:'班事有谱 · 合成持久化开发',show:false,backgroundColor:'#ffffff',titleBarStyle:'hidden',titleBarOverlay:{color:'#eef3f6',symbolColor:'#505c63',height:44},webPreferences:{preload:path.join(__dirname,'preload.cjs'),session:isolated,sandbox:true,contextIsolation:true,nodeIntegration:false,webSecurity:true,allowRunningInsecureContent:false,webviewTag:false,spellcheck:false,devTools:false}});
    window.webContents.setWindowOpenHandler(()=>({action:'deny'}));
    window.webContents.on('will-navigate',(event,url)=>{if(!allowed(origin,url))event.preventDefault();});
    window.webContents.on('will-redirect',(event,url)=>{if(!allowed(origin,url))event.preventDefault();});
    window.webContents.on('will-attach-webview',event=>event.preventDefault());
    window.on('page-title-updated',event=>event.preventDefault());
    const menu=Menu.buildFromTemplate([
      {label:'文件',submenu:[{label:'关于运行模式',click:()=>dialog.showMessageBox(window,{type:'info',message:'合成持久化开发模式',detail:'复用现有R1业务页面和后端；不是完整冻结UX迁移或正式发行。仅合成数据。关闭时停止本次API进程，不初始化/迁移/停止数据库。仅允许已批准的JSON退出包下载并由你选择保存位置。真实模型和系统工具未启用。'})},{role:'quit',label:'退出'}]},
      {label:'编辑',submenu:[{role:'undo',label:'撤销'},{role:'redo',label:'重做'},{role:'cut',label:'剪切'},{role:'copy',label:'复制'},{role:'paste',label:'粘贴'},{role:'selectAll',label:'全选'}]},
      {label:'视图',submenu:[{role:'reload',label:'重新加载'},{role:'resetZoom',label:'实际大小'},{role:'zoomIn',label:'放大'},{role:'zoomOut',label:'缩小'},{role:'togglefullscreen',label:'全屏'}]},
      {label:'帮助',submenu:[{label:'运行范围',click:()=>menu.items[0].submenu.items[0].click()}]},
    ]);
    Menu.setApplicationMenu(menu);window.setMenuBarVisibility(false);
    const indices={application:0,edit:1,view:2,help:3};
    ipcMain.on('desktop:menu',(event,name)=>{
      if(!window || event.sender!==window.webContents || event.senderFrame!==window.webContents.mainFrame || !allowed(origin,event.senderFrame.url) || typeof name!=='string' || !Object.hasOwn(indices,name))return;
      menu.items[indices[name]].submenu.popup({window,x:120+48*indices[name],y:44});
    });
    window.once('ready-to-show',()=>window.show());
    window.on('closed',()=>{window=null;});
    await window.loadURL(origin+'/');
  }).catch(async()=>{
    if(service) await service.stop().catch(()=>{});
    // Static error only; never raw process output, local paths, keys or database details.
    dialog.showErrorBox('运行环境尚未准备好','未连接业务服务；原数据未更改。请按桌面运行文档准备自有合成数据库并启动 PostgreSQL；如已有实例，请检查版本和8000端口。系统没有自动初始化、迁移或重放请求。');
    app.exit(1);
  });
}
