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
  clipboard,
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
let notesWin = null;
let tray = null;
let topMostTimer = null;
let ecoModeActive = false;
let connectionInfo = { wsPort: 0, wsToken: "", httpUrl: "" };

let interactiveState = { quickBar: false, confirmCard: false };
let lastIgnoreState = true;
let mouseCheckInterval = null;

function createNotesWindow() {
  if (notesWin && !notesWin.isDestroyed()) return notesWin;

  const primary = screen.getPrimaryDisplay();
  const wa = primary.workArea;
  const winW = 480;
  const winH = 560;

  const avatarBounds = (avatarWin && !avatarWin.isDestroyed()) ? avatarWin.getBounds() : null;
  const x = avatarBounds
    ? Math.max(wa.x + 20, avatarBounds.x - winW - 16)
    : wa.x + wa.width - winW - 30;
  const y = avatarBounds
    ? Math.max(wa.y + 20, avatarBounds.y + 20)
    : wa.y + wa.height - winH - 30;

  notesWin = new BrowserWindow({
    width: winW,
    height: winH,
    x,
    y,
    frame: false,
    transparent: true,
    resizable: true,
    minWidth: 320,
    minHeight: 46,
    alwaysOnTop: true,
    skipTaskbar: false,
    show: false,
    title: "Amadeus Kurisu — Notas en Pantalla",
    webPreferences: {
      preload: path.join(__dirname, "..", "preload", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  notesWin.setAlwaysOnTop(true, "normal");
  notesWin.loadFile(path.join(__dirname, "..", "notes", "index.html"));
  notesWin.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  notesWin.webContents.on("will-navigate", (event, navUrl) => {
    if (!navUrl.startsWith("file://")) event.preventDefault();
  });

  notesWin.on("closed", () => {
    notesWin = null;
  });

  return notesWin;
}

function showNotesWindow(data) {
  const win = createNotesWindow();
  if (!win.isVisible()) {
    win.show();
  }
  win.focus();
  win.webContents.send("amadeus:notes-data", data);
}

function startMouseMonitor() {
  if (mouseCheckInterval) return;
  mouseCheckInterval = setInterval(() => {
    if (!avatarWin || avatarWin.isDestroyed() || dragTimer) return;
    const cursor = screen.getCursorScreenPoint();
    const bounds = avatarWin.getBounds();

    const inside = (
      cursor.x >= bounds.x &&
      cursor.x <= bounds.x + bounds.width &&
      cursor.y >= bounds.y &&
      cursor.y <= bounds.y + bounds.height
    );

    if (!inside) {
      if (!lastIgnoreState) {
        lastIgnoreState = true;
        avatarWin.setIgnoreMouseEvents(true, { forward: true });
      }
      return;
    }

    const relX = cursor.x - bounds.x;
    const relY = cursor.y - bounds.y;

    // 1. MiniDock (bottom right corner, dock width ~300px, height ~65px)
    const inDock = (relX >= bounds.width - 320 && relY >= bounds.height - 65);

    // 2. Quick input bar: bottom area above dock
    const inQuickBar = (interactiveState.quickBar && relY >= bounds.height - 120);

    // 3. Confirm card: top-left area
    const inConfirm = (interactiveState.confirmCard && relX <= 320 && relY >= 40 && relY <= 380);

    const isInteractive = inDock || inQuickBar || inConfirm;
    const shouldIgnore = !isInteractive;

    if (shouldIgnore !== lastIgnoreState) {
      lastIgnoreState = shouldIgnore;
      avatarWin.setIgnoreMouseEvents(shouldIgnore, { forward: true });
    }
  }, 40);
}

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
    avatarWin.showInactive();
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
    focusable: true,
    skipTaskbar: true,
    hasShadow: false,
    title: "Makise Kurisu — Avatar 3D",
    webPreferences: {
      preload: path.join(__dirname, "..", "preload", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      backgroundThrottling: false,
    },
  });

  // Mid-tier passive overlay ("normal" topmost level, click-through on transparent areas)
  // This keeps Kurisu floating above normal desktop windows without minimizing or tabbing out of fullscreen games.
  avatarWin.setAlwaysOnTop(true, "normal");
  avatarWin.setIgnoreMouseEvents(true, { forward: true });
  startMouseMonitor();

  avatarWin.webContents.on("console-message", (_ev, _level, msg, line) => {
    console.log(`[AVATAR-RENDERER:${line}] ${msg}`);
  });
  avatarWin.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  avatarWin.webContents.on("will-navigate", (event, navUrl) => {
    if (!navUrl.startsWith("file://")) event.preventDefault();
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
    width: 1040,
    height: 740,
    minWidth: 860,
    minHeight: 600,
    x: Math.max(20, wa.x + 60),
    y: Math.max(20, wa.y + 40),
    frame: false,
    transparent: true,
    backgroundColor: "#00000000",
    hasShadow: true,
    resizable: true,
    autoHideMenuBar: true,
    title: "Amadeus — Panel y Asistente",
    webPreferences: {
      preload: path.join(__dirname, "..", "preload", "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  panelWin.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
  panelWin.webContents.on("will-navigate", (event, navUrl) => {
    if (!navUrl.startsWith("file://")) event.preventDefault();
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
    if (notesWin && !notesWin.isDestroyed()) notesWin.close();
    avatarWin = null;
    notesWin = null;
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
    { label: "Abrir Notas / Detalle en Pantalla", click: () => showNotesWindow({ detail: "Notas de Amadeus Kurisu", title: "Notas" }) },
    {
      label: "Escribir a Kurisu (Ctrl+Alt+Espacio)",
      click: () => {
        if (avatarWin && !avatarWin.isDestroyed()) {
          avatarWin.setIgnoreMouseEvents(false);
          lastIgnoreState = false;
          interactiveState.quickBar = true;
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
    avatarWin.setIgnoreMouseEvents(false);
    lastIgnoreState = false;
    interactiveState.quickBar = true;
    avatarWin.show();
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

let dragTimer = null;

ipcMain.handle("amadeus:get-connection-info", () => connectionInfo);
ipcMain.on("amadeus:set-ignore-mouse", (_ev, ignore) => {
  if (dragTimer) return; // Keep capturing mouse while dragging window
  if (avatarWin && !avatarWin.isDestroyed()) {
    avatarWin.setIgnoreMouseEvents(Boolean(ignore), { forward: true });
  }
});
ipcMain.on("amadeus:set-focusable", (_ev, focusable) => {
  if (avatarWin && !avatarWin.isDestroyed()) {
    avatarWin.setFocusable(Boolean(focusable));
    if (focusable) avatarWin.focus();
  }
});
let dragSafetyTimeout = null;

ipcMain.on("amadeus:start-drag", () => {
  if (!avatarWin || avatarWin.isDestroyed()) return;
  avatarWin.setIgnoreMouseEvents(false);
  const startCursor = screen.getCursorScreenPoint();
  const [startX, startY] = avatarWin.getPosition();
  if (dragTimer) clearInterval(dragTimer);
  if (dragSafetyTimeout) clearTimeout(dragSafetyTimeout);
  dragTimer = setInterval(() => {
    if (!avatarWin || avatarWin.isDestroyed()) {
      clearInterval(dragTimer);
      dragTimer = null;
      return;
    }
    const cur = screen.getCursorScreenPoint();
    avatarWin.setPosition(
      startX + (cur.x - startCursor.x),
      startY + (cur.y - startCursor.y)
    );
  }, 16);
  // Failsafe watchdog to avoid infinite drag if mouseup is missed
  dragSafetyTimeout = setTimeout(() => {
    if (dragTimer) {
      clearInterval(dragTimer);
      dragTimer = null;
    }
  }, 15000);
});
ipcMain.on("amadeus:stop-drag", () => {
  if (dragTimer) {
    clearInterval(dragTimer);
    dragTimer = null;
  }
  if (dragSafetyTimeout) {
    clearTimeout(dragSafetyTimeout);
    dragSafetyTimeout = null;
  }
});
ipcMain.on("amadeus:set-dodge-enabled", () => {});
ipcMain.on("amadeus:open-panel", () => openSettingsPanel());

ipcMain.on("amadeus:show-notes", (_ev, data) => {
  showNotesWindow(data);
});
ipcMain.on("amadeus:hide-notes", () => {
  if (notesWin && !notesWin.isDestroyed()) notesWin.hide();
});
ipcMain.on("amadeus:set-notes-size", (_ev, { w, h }) => {
  if (notesWin && !notesWin.isDestroyed()) {
    notesWin.setSize(w, h);
  }
});
ipcMain.on("amadeus:copy-clipboard", (_ev, text) => {
  if (text) clipboard.writeText(String(text));
});
ipcMain.on("amadeus:set-interactive-state", (_ev, state) => {
  if (state && typeof state === "object") {
    interactiveState = { ...interactiveState, ...state };
    if (avatarWin && !avatarWin.isDestroyed()) {
      if (state.quickBar || state.confirmCard) {
        avatarWin.setIgnoreMouseEvents(false);
        lastIgnoreState = false;
      }
    }
  }
});

ipcMain.on("amadeus:minimize-panel", () => {
  if (panelWin && !panelWin.isDestroyed()) panelWin.minimize();
});
ipcMain.on("amadeus:maximize-panel", () => {
  if (panelWin && !panelWin.isDestroyed()) {
    if (panelWin.isMaximized()) panelWin.unmaximize();
    else panelWin.maximize();
  }
});
ipcMain.on("amadeus:close-panel", () => {
  if (panelWin && !panelWin.isDestroyed()) panelWin.hide();
});
ipcMain.handle("amadeus:is-panel-maximized", () => {
  return Boolean(panelWin && !panelWin.isDestroyed() && panelWin.isMaximized());
});

app.whenReady().then(() => {
  setupSystemTray();
  registerShortcuts();
  coreLink = new CoreProcessLink({
    projectRoot,
    onReady: (info) => {
      connectionInfo = info;
      createAvatarWindow();
      if (isSmokeTest) {
        openSettingsPanel();
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
    onExit: (code) => {
      if (!connectionInfo.wsPort && !isSmokeTest) {
        const { dialog } = require("electron");
        dialog.showErrorBox(
          "Amadeus Kurisu — Error de inicio",
          `El núcleo de Amadeus no pudo iniciarse (código ${code}).\nRevisa los logs o inicia Iniciar_Amadeus_Kurisu.bat.`
        );
      }
    },
  });
  coreLink.start();
});

app.on("window-all-closed", () => {
  // Keep running in system tray / background eco mode
});

app.on("will-quit", () => {
  globalShortcut.unregisterAll();
  if (mouseCheckInterval) clearInterval(mouseCheckInterval);
  if (topMostTimer) clearInterval(topMostTimer);
  if (coreLink) coreLink.stop();
});
