"use strict";

const {
  app,
  BrowserWindow,
  ipcMain,
  Tray,
  Menu,
  nativeImage,
  screen,
  globalShortcut,
} = require("electron");
const path = require("path");
const fs = require("fs");
const { computeDodgeTarget } = require("./dodge");
const { CoreProcessLink } = require("./core-link");

const isSmokeTest = process.argv.includes("--smoke-test");
const projectRoot = path.resolve(__dirname, "..", "..", "..");

// Prevent Chromium utility/audio/network process sandbox crashes on Windows
app.commandLine.appendSwitch("no-sandbox");
app.commandLine.appendSwitch(
  "disable-features",
  "AudioServiceOutOfProcess,AudioServiceSandbox,NetworkServiceSandbox"
);
app.commandLine.appendSwitch("autoplay-policy", "no-user-gesture-required");

let coreLink = null;
let avatarWin = null;
let panelWin = null;
let tray = null;
let ecoModeActive = false;
let connectionInfo = { wsPort: 0, wsToken: "", httpUrl: "" };

function createTrayEmblem() {
  const size = 16;
  const buf = Buffer.alloc(size * size * 4);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const idx = (y * size + x) * 4;
      const dist = Math.hypot(x - 7.5, y - 7.5);
      if (dist <= 7.2) {
        const isBorder = dist >= 5.8;
        buf[idx] = isBorder ? 255 : 47;     // B
        buf[idx + 1] = isBorder ? 225 : 143; // G
        buf[idx + 2] = isBorder ? 180 : 220; // R
        buf[idx + 3] = 255;
      } else {
        buf[idx + 3] = 0;
      }
    }
  }
  return nativeImage.createFromBuffer(buf, { width: size, height: size });
}

function createAvatarWindow() {
  if (avatarWin && !avatarWin.isDestroyed()) {
    avatarWin.show();
    return avatarWin;
  }

  const primary = screen.getPrimaryDisplay();
  const wa = primary.workArea;
  const winW = 580;
  const winH = 620;

  avatarWin = new BrowserWindow({
    width: winW,
    height: winH,
    x: wa.x + wa.width - winW - 20,
    y: wa.y + wa.height - winH - 10,
    frame: false,
    transparent: true,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: false,
    hasShadow: false,
    title: "Makise Kurisu — Avatar 3D",
    webPreferences: {
      preload: path.join(__dirname, "..", "preload", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
    },
  });

  avatarWin.setAlwaysOnTop(true, "floating");
  avatarWin.webContents.on("console-message", (_ev, _level, msg, line) => {
    console.log(`[AVATAR-RENDERER:${line}] ${msg}`);
  });
  avatarWin.webContents.on("did-finish-load", () => {
    if (avatarWin && !avatarWin.isDestroyed()) {
      avatarWin.show();
      avatarWin.moveTop();
    }
  });
  avatarWin.loadFile(path.join(__dirname, "..", "avatar", "index.html"));
  return avatarWin;
}

function openSettingsPanel() {
  if (panelWin && !panelWin.isDestroyed()) {
    panelWin.show();
    panelWin.focus();
    return panelWin;
  }
  const primary = screen.getPrimaryDisplay();
  const wa = primary.workArea;
  panelWin = new BrowserWindow({
    width: 960,
    height: 720,
    x: Math.max(20, wa.x + 60),
    y: Math.max(20, wa.y + 40),
    frame: true,
    backgroundColor: "#d9eeff",
    autoHideMenuBar: true,
    title: "Amadeus Kurisu — Ventana Soft Air (Aero Glass)",
    webPreferences: {
      preload: path.join(__dirname, "..", "preload", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  panelWin.loadFile(path.join(__dirname, "..", "panel", "index.html"));
  panelWin.on("closed", () => {
    panelWin = null;
  });
  return panelWin;
}

function toggleEcoMode() {
  ecoModeActive = !ecoModeActive;
  if (ecoModeActive) {
    if (panelWin && !panelWin.isDestroyed()) panelWin.close();
    if (avatarWin && !avatarWin.isDestroyed()) avatarWin.close();
    avatarWin = null;
  } else {
    createAvatarWindow();
    openSettingsPanel();
  }
}

function setupSystemTray() {
  tray = new Tray(createTrayEmblem());
  tray.setToolTip("Amadeus System // Makise Kurisu");
  const menu = Menu.buildFromTemplate([
    { label: "Abrir Ventana Principal Soft Air", click: () => openSettingsPanel() },
    { label: "Mostrar / Enfocar Avatar 3D (.VRM)", click: () => createAvatarWindow() },
    {
      label: "Escribir a Kurisu (Ctrl+Alt+Espacio)",
      click: () => {
        if (avatarWin && !avatarWin.isDestroyed()) {
          avatarWin.focus();
          avatarWin.webContents.send("amadeus:shortcut", "toggle-input");
        }
      },
    },
    {
      label: "Mirar mi pantalla (Ctrl+Alt+V)",
      click: () => {
        if (avatarWin && !avatarWin.isDestroyed()) {
          avatarWin.webContents.send("amadeus:shortcut", "look-screen");
        }
      },
    },
    { label: "Alternar Modo Eco (Ahorrar RAM)", click: () => toggleEcoMode() },
    { type: "separator" },
    {
      label: "Salir de Amadeus",
      click: () => {
        if (coreLink) coreLink.stop();
        app.quit();
      },
    },
  ]);
  tray.setContextMenu(menu);
  tray.on("click", () => openSettingsPanel());
  tray.on("double-click", () => openSettingsPanel());
}

function registerShortcuts() {
  globalShortcut.register("CommandOrControl+Alt+Space", () => {
    if (!avatarWin || avatarWin.isDestroyed()) createAvatarWindow();
    avatarWin.focus();
    avatarWin.webContents.send("amadeus:shortcut", "toggle-input");
  });
  globalShortcut.register("CommandOrControl+Alt+K", () => {
    if (avatarWin && !avatarWin.isDestroyed()) {
      avatarWin.webContents.send("amadeus:shortcut", "push-to-talk");
    }
  });
  globalShortcut.register("CommandOrControl+Alt+V", () => {
    if (avatarWin && !avatarWin.isDestroyed()) {
      avatarWin.webContents.send("amadeus:shortcut", "look-screen");
    }
  });
  globalShortcut.register("CommandOrControl+Alt+E", () => toggleEcoMode());
}

ipcMain.handle("amadeus:get-connection-info", () => connectionInfo);
ipcMain.on("amadeus:set-ignore-mouse", () => {});
ipcMain.on("amadeus:set-dodge-enabled", () => {});
ipcMain.on("amadeus:open-panel", () => openSettingsPanel());

app.whenReady().then(() => {
  coreLink = new CoreProcessLink({
    projectRoot,
    onReady: (info) => {
      connectionInfo = info;
      createAvatarWindow();
      openSettingsPanel();
      setupSystemTray();
      registerShortcuts();
      if (isSmokeTest) {
        setTimeout(async () => {
          try {
            if (avatarWin && !avatarWin.isDestroyed()) {
              const img = await avatarWin.webContents.capturePage();
              fs.writeFileSync(path.join(projectRoot, "dist", "smoke_avatar.png"), img.toPNG());
            }
            if (panelWin && !panelWin.isDestroyed()) {
              const img2 = await panelWin.webContents.capturePage();
              fs.writeFileSync(path.join(projectRoot, "dist", "smoke_panel.png"), img2.toPNG());
            }
          } catch (_e) {}
          coreLink.stop();
          app.exit(0);
        }, 3200);
      }
    },
    onExit: () => {},
  });
  coreLink.start();
});

app.on("window-all-closed", () => {
  // Keep running in system tray / background eco mode
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
  if (coreLink) coreLink.stop();
});
