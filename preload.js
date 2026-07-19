const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('dock', {
  sites: () => ipcRenderer.invoke('get-sites'),
  ollamaChat: (model, messages, think) => ipcRenderer.invoke('ollama-chat', model, messages, think),
  collapse: () => ipcRenderer.send('collapse'),
  expand: () => ipcRenderer.send('expand'),
  quit: () => ipcRenderer.send('quit'),
  onState: callback => ipcRenderer.on('dock-state', (_event, value) => callback(value)),
  onReload: callback => ipcRenderer.on('reload-site', (_event, id) => callback(id)),
});
