const { app, BrowserWindow } = require('electron');
const fs = require('node:fs');
const path = require('node:path');

const [dir, title] = process.argv.slice(-2);
app.setPath('userData', path.join(dir, 'profile'));
app.whenReady().then(async () => {
  const window = new BrowserWindow({ title, webPreferences: { sandbox: true } });
  window.on('page-title-updated', event => event.preventDefault());
  window.webContents.session.webRequest.onBeforeRequest({urls: ['http://*/*', 'https://*/*', 'ws://*/*', 'wss://*/*']},
    (_, callback) => callback({ cancel: true }));
  window.webContents.on('will-navigate', event => event.preventDefault());
  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  window.webContents.on('console-message', event => {
    if (event.message.startsWith('DROP ')) fs.appendFileSync(path.join(dir, 'events'), event.message.slice(5) + '\n');
    else console.error(event.message);
  });
  await window.loadFile(path.join(__dirname, 'index.html'));
  window.on('closed', () => app.quit());
});
