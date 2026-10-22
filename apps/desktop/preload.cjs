const { contextBridge, ipcRenderer } = require('electron');
// Fixed UI-only capability; never expose raw IPC, filesystem or business writes.
contextBridge.exposeInMainWorld('classMatterDesktop', Object.freeze({
  openMenu(name) {
    if (['application', 'edit', 'view', 'help'].includes(name)) ipcRenderer.send('desktop:menu', name);
  },
}));
