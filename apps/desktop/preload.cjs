const { contextBridge, ipcRenderer } = require('electron');
// Fixed desktop capabilities; identity helpers exist only for the explicit
// local development flag. Never expose raw IPC, files or business commands.
const development=typeof process!=='undefined'&&Array.isArray(process.argv)&&process.argv.includes('--classmatter-development-no-password');
contextBridge.exposeInMainWorld('classMatterDesktop', Object.freeze({
  ...(development?{
    development:true,
    enterDevelopment:()=>ipcRenderer.invoke('desktop:development-session','enter'),
    reauthenticateDevelopment:()=>ipcRenderer.invoke('desktop:development-session','reauthenticate'),
  }:{}),
  openMenu(name) {
    if (['application', 'edit', 'view', 'help'].includes(name)) ipcRenderer.send('desktop:menu', name);
  },
}));
