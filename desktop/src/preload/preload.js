"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("amadeusDesktop", {
  getConnectionInfo: () => ipcRenderer.invoke("amadeus:get-connection-info"),
  setIgnoreMouse: (ignore) => ipcRenderer.send("amadeus:set-ignore-mouse", Boolean(ignore)),
  setDodgeEnabled: (enabled) => ipcRenderer.send("amadeus:set-dodge-enabled", Boolean(enabled)),
  openSettingsPanel: () => ipcRenderer.send("amadeus:open-panel"),
  onShortcutEvent: (callback) => {
    ipcRenderer.on("amadeus:shortcut", (_event, action) => callback(action));
  },
});
