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
  showNotes: (data) => ipcRenderer.send("amadeus:show-notes", data),
  hideNotes: () => ipcRenderer.send("amadeus:hide-notes"),
  setNotesWindowSize: (w, h) => ipcRenderer.send("amadeus:set-notes-size", { w, h }),
  copyToClipboard: (text) => ipcRenderer.send("amadeus:copy-clipboard", text),
  setInteractiveState: (state) => ipcRenderer.send("amadeus:set-interactive-state", state),
  minimizePanel: () => ipcRenderer.send("amadeus:minimize-panel"),
  maximizePanel: () => ipcRenderer.send("amadeus:maximize-panel"),
  closePanel: () => ipcRenderer.send("amadeus:close-panel"),
  isPanelMaximized: () => ipcRenderer.invoke("amadeus:is-panel-maximized"),
  onNotesData: (callback) => {
    ipcRenderer.on("amadeus:notes-data", (_event, data) => callback(data));
  },
});
