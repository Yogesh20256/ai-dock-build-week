const { app, BrowserWindow, ipcMain, screen } = require('electron');
const fs = require('fs');
const path = require('path');

app.setName('AI Dock');
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) app.quit();

let win;
let collapsed = false;
let expandedBounds = { width: 500, height: 760 };

function sites() {
  const custom = path.join(app.getPath('userData'), 'sites.json');
  const source = fs.existsSync(custom) ? custom : path.join(__dirname, 'sites.json');
  return JSON.parse(fs.readFileSync(source, 'utf8')).sites;
}

function positionAtRight(width, height) {
  const area = screen.getPrimaryDisplay().workArea;
  return { x: area.x + area.width - width - 24, y: area.y + 70, width, height };
}

function createWindow() {
  win = new BrowserWindow({
    ...positionAtRight(500, 760),
    title: 'AI Dock',
    frame: false,
    transparent: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: true,
    minWidth: 380,
    minHeight: 500,
    backgroundColor: '#11131a',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      webviewTag: true,
    },
  });
  win.setAlwaysOnTop(true, 'floating');
  win.loadFile('index.html');
  win.on('closed', () => { win = null; });
}

function expand() {
  if (!win) return;
  if (collapsed) {
    const [x, y] = win.getPosition();
    win.setResizable(true);
    win.setBounds({ x: Math.max(0, x - expandedBounds.width + 68), y, ...expandedBounds }, true);
    collapsed = false;
    win.webContents.send('dock-state', false);
    win.setTitle('AI Dock');
  }
  win.show();
  win.focus();
}

function collapse() {
  if (!win || collapsed) return;
  const bounds = win.getBounds();
  expandedBounds = { width: bounds.width, height: bounds.height };
  win.webContents.send('dock-state', true);
  win.setResizable(false);
  win.setBounds({ x: bounds.x + bounds.width - 68, y: bounds.y, width: 68, height: 68 }, true);
  collapsed = true;
  win.setTitle('AI Dock Orb');
}

function toggle() {
  if (!win) return;
  if (collapsed || !win.isVisible()) expand(); else collapse();
}

app.on('second-instance', (_event, argv) => {
  if (argv.includes('--quit')) app.quit();
  else if (argv.includes('--hide')) collapse();
  else if (argv.includes('--show')) expand();
  else toggle();
});

app.whenReady().then(() => {
  createWindow();
  app.on('web-contents-created', (_event, contents) => {
    if (contents.getType() === 'webview') {
      contents.setWindowOpenHandler(({ url }) => {
        contents.loadURL(url);
        return { action: 'deny' };
      });
    }
  });
});

ipcMain.handle('get-sites', () => sites());
ipcMain.handle('ollama-chat', async (_event, model, messages, think) => {
  const response = await fetch('http://127.0.0.1:11434/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, messages, think: Boolean(think), stream: false }),
  });
  if (!response.ok) throw new Error(`Ollama returned ${response.status}: ${await response.text()}`);
  const data = await response.json();
  return data.message.content;
});
ipcMain.on('collapse', collapse);
ipcMain.on('expand', expand);
ipcMain.on('quit', () => app.quit());
ipcMain.on('reload-current', (_event, id) => win.webContents.send('reload-site', id));

app.on('window-all-closed', () => app.quit());
