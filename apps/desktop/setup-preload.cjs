const {contextBridge,ipcRenderer}=require('electron');
// Dedicated first-run window only. Never loaded by the business web page.
contextBridge.exposeInMainWorld('classMatterSetup',Object.freeze({
  status:()=>ipcRenderer.invoke('setup:request',{operation:'status'}),
  createOwner:password=>ipcRenderer.invoke('setup:request',{operation:'create_owner',password}),
  preview:password=>ipcRenderer.invoke('setup:request',{operation:'preview_control',password}),
  approve:(operation_id,payload_hash)=>ipcRenderer.invoke('setup:request',{operation:'approve_control',operation_id,payload_hash,confirmed:true}),
  continue:()=>ipcRenderer.invoke('setup:continue'),
}));
