// Single workbench host; offline fixtures are explicit developer-only entries.
const {app,BrowserWindow,Menu,session,ipcMain,dialog}=require('electron');
const fs=require('node:fs');
const path=require('node:path');
const {desktopService}=require('./runtime-service.cjs');
const {allowed,CSP,exitDownload,clipboardWrite,microphoneRequest,microphoneCheck}=require('./runtime-policy.cjs');
const {networkFromSwitches,validateNetwork}=require('./model-network.cjs');
let source,d1=false,sourceInvalid=false;
let modelNetwork;
try {
  modelNetwork=networkFromSwitches(
    app.commandLine.hasSwitch('classmatter-model-api-bases')?app.commandLine.getSwitchValue('classmatter-model-api-bases'):undefined,
    app.commandLine.hasSwitch('classmatter-model-api-proxy')?app.commandLine.getSwitchValue('classmatter-model-api-proxy'):undefined);
} catch {sourceInvalid=true;}
try {
  source=JSON.parse(fs.readFileSync(path.join(__dirname,'runtime-source.json'),'utf8'));
  const keys=Object.keys(source).sort().join(',');
  d1=source.schema_version===2 && ['conversation-d1','workspace-chat-d3','classroom-work-d4'].includes(source.profile) && keys==='profile,repositoryRoot,runtimeRoot,schema_version,servicePort'
    && Number.isInteger(source.servicePort) && source.servicePort>=1024 && source.servicePort<=65535;
  if(!d1 && (source.schema_version!==1 || keys!=='repositoryRoot,runtimeRoot,schema_version'))sourceInvalid=true;
} catch {sourceInvalid=true;}
app.setName(d1?'ClassMatter Synthetic D1':'ClassMatter Synthetic Runtime');
// Separate native locks/cache for each owned runtime; disposable acceptance
// instances must not attach to or close the user's already-open workbench.
const instanceKey=!sourceInvalid&&typeof source.repositoryRoot==='string'&&typeof source.runtimeRoot==='string'
  ? require('node:crypto').createHash('sha256').update(path.resolve(source.repositoryRoot)+'\n'+path.resolve(source.runtimeRoot)).digest('hex').slice(0,16):'invalid';
app.setPath('userData',path.join(app.getPath('appData'),(d1?'ClassMatter-Synthetic-D1-':'ClassMatter-Synthetic-Runtime-')+instanceKey));
app.setAppUserModelId(d1?'org.classmatter.synthetic-d1':'org.classmatter.synthetic-runtime');
app.enableSandbox();
const development=app.commandLine.hasSwitch('classmatter-development-no-password');
if(development&&!d1)sourceInvalid=true;
let window,service,quitting=false,origin,setupWindow;
if(sourceInvalid) app.whenReady().then(()=>{
  dialog.showErrorBox('运行环境尚未准备好','运行描述无效；未连接或接管其他实例。原数据未更改。');
  app.exit(1);
});
else if(!app.requestSingleInstanceLock()) app.quit();
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
    if(sourceInvalid) throw new Error('Invalid runtime source');
    let developerCookies;
    if(development){
      const pipe=require('./setup-service.cjs').setupService(source.repositoryRoot,source.runtimeRoot,true,source.profile);
      try{
        const opened=await pipe.request({operation:'development_access'});
        developerCookies=opened.cookies;
        // Only the current local workspace may restore the previously tested
        // and explicitly enabled transport. Explicit operator flags win.
        if(['workspace-chat-d3','classroom-work-d4'].includes(source.profile)&&!modelNetwork.bases.length&&opened.model_network!==undefined)modelNetwork=validateNetwork(opened.model_network);
      }finally{pipe.stop();}
    }else if(d1)setupWindow=await require('./setup-window.cjs').prepareWorkspace({BrowserWindow,ipcMain,session},source);
    service=desktopService(source.repositoryRoot,path.join(__dirname,'ui'),()=>{
      if(window) window.close();
      // No automatic replay or reattachment after a service crash.
      app.quit();
    },source.runtimeRoot,d1?source.profile:'r1',d1?source.servicePort:8000,modelNetwork,development&&['workspace-chat-d3','classroom-work-d4'].includes(source.profile));
    origin=await service.start();
    const isolated=session.fromPartition(d1?'classmatter-synthetic-d1':'classmatter-synthetic-runtime');
    const installDeveloperCookies=async cookies=>{
      if(!cookies||Object.keys(cookies).sort().join(',')!=='client,csrf,session')throw new Error('Invalid local identity');
      for(const [name,value] of Object.entries(cookies)){
        if(typeof value!=='string'||!/^[A-Za-z0-9_-]{32,128}$/.test(value))throw new Error('Invalid local identity');
        await isolated.cookies.set({url:origin+'/api',name:'class_os_'+name,value,httpOnly:true,sameSite:'strict',path:'/api',secure:false});
      }
    };
    if(developerCookies){await installDeveloperCookies(developerCookies);developerCookies=null;}
    let microphoneGranted=false, microphonePrompt=false;
    isolated.setPermissionRequestHandler((contents,permission,callback,details)=>{
      if(!window || window.isDestroyed() || contents!==window.webContents){callback(false);return;}
      if(clipboardWrite(origin,permission,details)){callback(true);return;}
      if(!microphoneRequest(origin,permission,details)){callback(false);return;}
      if(microphoneGranted){callback(true);return;}
      if(microphonePrompt){callback(false);return;}
      microphonePrompt=true;
      dialog.showMessageBox(window,{type:'question',title:'使用麦克风',message:'允许本次使用麦克风，将语音转为可编辑文字？',buttons:['取消','允许'],defaultId:0,cancelId:0}).then(result=>{
        microphoneGranted=result.response===1 && !!window && !window.isDestroyed() && contents===window.webContents && allowed(origin,contents.getURL());
        callback(microphoneGranted);
      }).catch(()=>callback(false)).finally(()=>{microphonePrompt=false;});
    });
    isolated.setPermissionCheckHandler((contents,permission,_requestingOrigin,details)=>!!window && contents===window.webContents && (clipboardWrite(origin,permission,details)||microphoneGranted&&microphoneCheck(origin,permission,details)));
    isolated.webRequest.onBeforeRequest((details,callback)=>callback({cancel:!allowed(origin,details.url)}));
    isolated.webRequest.onHeadersReceived((details,callback)=>callback({responseHeaders:{...details.responseHeaders,'Content-Security-Policy':[CSP],'X-Content-Type-Options':['nosniff']}}));
    isolated.on('will-download',(event,item,contents)=>{
      if(!window || contents!==window.webContents || !exitDownload(origin,item.getURL(),item.getMimeType(),item.getTotalBytes())){event.preventDefault();return;}
      // Only the existing authorized JSON receipt route; native Save dialog
      // leaves the destination to the user. Never set an arbitrary save path.
      item.setSaveDialogOptions({title:d1?'保存已批准的合成证据退出包':'保存已批准的合成核心退出包',defaultPath:d1?'ClassMatter-synthetic-conversation-v6.json':'ClassMatter-synthetic-core.json',filters:[{name:'JSON',extensions:['json']}]});
    });
    window=new BrowserWindow({width:1380,height:900,minWidth:1000,minHeight:680,title:'班事有谱 · ClassMatter',show:false,backgroundColor:'#ffffff',titleBarStyle:'hidden',titleBarOverlay:{color:'#eef3f6',symbolColor:'#505c63',height:44},webPreferences:{preload:path.join(__dirname,'preload.cjs'),additionalArguments:development?['--classmatter-development-no-password',...(['workspace-chat-d3','classroom-work-d4'].includes(source.profile)?['--classmatter-local-only']:[])]:[],session:isolated,sandbox:true,contextIsolation:true,nodeIntegration:false,webSecurity:true,allowRunningInsecureContent:false,webviewTag:false,spellcheck:false,devTools:false}});
    let developmentBusy=false;
    ipcMain.handle('desktop:development-session',async(event,action)=>{
      if(!development||developmentBusy||!window||event.sender!==window.webContents||event.senderFrame!==window.webContents.mainFrame||!allowed(origin,event.senderFrame.url)||!['enter','reauthenticate'].includes(action))throw new Error('开发会话不可用');
      developmentBusy=true;let pipe;
      try{
        let request={operation:'development_access'};
        if(action==='reauthenticate'){
          const cookies=await isolated.cookies.get({url:origin+'/api'});
          request={operation:'development_reauthenticate'};
          for(const name of ['client','session','csrf']){
            const matches=cookies.filter(cookie=>cookie.name==='class_os_'+name&&cookie.path==='/api');
            if(matches.length!==1)throw new Error('Missing original identity');
            request[name]=matches[0].value;
          }
        }
        pipe=require('./setup-service.cjs').setupService(source.repositoryRoot,source.runtimeRoot,true,source.profile);
        const result=await pipe.request(request);
        if(!window||window.isDestroyed())throw new Error('Window closed');
        await installDeveloperCookies(result.cookies);return true;
      }catch{throw new Error('开发会话未完成，请重新打开应用后核对。');}
      finally{pipe?.stop();developmentBusy=false;}
    });
    window.webContents.setWindowOpenHandler(()=>({action:'deny'}));
    window.webContents.on('will-navigate',(event,url)=>{if(!allowed(origin,url))event.preventDefault();});
    window.webContents.on('will-redirect',(event,url)=>{if(!allowed(origin,url))event.preventDefault();});
    window.webContents.on('will-attach-webview',event=>event.preventDefault());
    window.on('page-title-updated',event=>event.preventDefault());
    const menu=Menu.buildFromTemplate([
      {label:'文件',submenu:[{label:'关于班事有谱',click:()=>dialog.showMessageBox(window,{type:'info',message:'班事有谱 · ClassMatter',detail:'数据保存在本机。当前仅使用合成数据，尚未开放真实师生数据。修改先预览、再确认；未接通的功能会明确提示。退出应用不会删除数据库。'+(modelNetwork.bases.length?'模型需要在设置中配置、测试并明确启用；默认离线。':'当前模型离线。')})},{role:'quit',label:'退出'}]},
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
    if(setupWindow&&!setupWindow.isDestroyed())setupWindow.close();
  }).catch(async()=>{
    if(service) await service.stop().catch(()=>{});
    // Static error only; never raw process output, local paths, keys or database details.
    dialog.showErrorBox('运行环境尚未准备好','未连接业务服务；原数据未更改。请按桌面运行文档准备自有合成数据库并启动 PostgreSQL；如已有实例，请检查版本和8000端口。系统没有自动初始化、迁移或重放请求。');
    app.exit(1);
  });
}
