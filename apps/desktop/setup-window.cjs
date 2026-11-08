const path=require('node:path');
const {pathToFileURL}=require('node:url');
const {setupService,validRequest}=require('./setup-service.cjs');

async function prepareWorkspace({BrowserWindow,ipcMain,session},source) {
  const pipe=setupService(source.repositoryRoot,source.runtimeRoot,false,source.profile);
  try {
    if((await pipe.request({operation:'status'})).ready){pipe.stop();return null;}
  } catch {pipe.stop();throw new Error('setup_unavailable');}
  const url=pathToFileURL(path.join(__dirname,'setup.html')).href;
  const isolated=session.fromPartition('classmatter-setup-'+require('node:crypto').randomBytes(16).toString('hex'));
  const assets=new Set(['setup.html','setup.css','setup-ui.js'].map(file=>pathToFileURL(path.join(__dirname,file)).href));
  isolated.setPermissionRequestHandler((_wc,_permission,callback)=>callback(false));
  isolated.setPermissionCheckHandler(()=>false);
  isolated.webRequest.onBeforeRequest((details,callback)=>callback({cancel:!assets.has(details.url)}));
  const window=new BrowserWindow({width:800,height:820,minWidth:660,minHeight:600,title:'班事有谱 · 首次设置',autoHideMenuBar:true,webPreferences:{preload:path.join(__dirname,'setup-preload.cjs'),session:isolated,sandbox:true,contextIsolation:true,nodeIntegration:false,webSecurity:true,devTools:false,webviewTag:false}});
  window.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  window.webContents.on('will-navigate',event=>event.preventDefault());
  window.webContents.on('will-redirect',event=>event.preventDefault());
  window.webContents.on('will-attach-webview',event=>event.preventDefault());
  const trusted=event=>event.sender===window.webContents&&event.senderFrame===window.webContents.mainFrame&&event.senderFrame.url===url;
  let completed=false,resolve,reject;
  const completion=new Promise((yes,no)=>{resolve=yes;reject=no;});
  ipcMain.handle('setup:request',async(event,request)=>{
    if(!trusted(event)||!validRequest(request))throw new Error('setup_not_completed');
    try {return await pipe.request(request);} catch {throw new Error('setup_not_completed');}
  });
  ipcMain.handle('setup:continue',async event=>{
    if(!trusted(event))throw new Error('setup_not_completed');
    const status=await pipe.request({operation:'status'});
    if(!status.ready)throw new Error('setup_not_completed');
    completed=true;resolve();return true;
  });
  const cleanup=()=>{ipcMain.removeHandler('setup:request');ipcMain.removeHandler('setup:continue');pipe.stop();};
  window.once('closed',()=>{cleanup();if(!completed)reject(new Error('setup_cancelled'));});
  try {await window.loadURL(url);await completion;cleanup();return window;}
  catch {cleanup();if(!window.isDestroyed())window.destroy();throw new Error('setup_not_completed');}
}
module.exports={prepareWorkspace};
