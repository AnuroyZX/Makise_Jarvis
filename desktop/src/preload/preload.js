"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("amadeusDesktop", {
  getConnectionInfo: () => ipcRenderer.invoke("amadeus:get-connection-info"),
  setIgnoreMouse: (ignore) => ipcRenderer.send("amadeus:set-ignore-mouse", Boolean(ignore)),
  setFocusable: (focusable) => ipcRenderer.send("amadeus:set-focusable", Boolean(focusable)),
  startWindowDrag: () => ipcRenderer.send("amadeus:start-drag"),
  stopWindowDrag: () => ipcRenderer.send("amadeus:stop-drag"),
  setDodgeEnabled: (enabled) => ipcRenderer.send("amadeus:set-dodge-enabled", Boolean(enabled)),
  openPanel: () => ipcRenderer.send("amadeus:open-panel"),
  openSettingsPanel: () => ipcRenderer.send("amadeus:open-panel"),
  onShortcutEvent: (callback) => {
    ipcRenderer.on("amadeus:shortcut", (_event, action) => callback(action));
  },
});
