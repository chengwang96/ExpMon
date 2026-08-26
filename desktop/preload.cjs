const { contextBridge, ipcRenderer } = require("electron");

function argumentValue(name) {
  const prefix = `--${name}=`;
  const argument = process.argv.find((value) => value.startsWith(prefix));
  return argument ? argument.slice(prefix.length) : "";
}

contextBridge.exposeInMainWorld("expmonDesktop", Object.freeze({
  collectorUrl: argumentValue("expmon-collector-url"),
  apiToken: argumentValue("expmon-api-token"),
  version: argumentValue("expmon-version"),
  platform: process.platform,
  // Native folder picker (used by the directory-monitoring UI).
  pickDirectory: () => ipcRenderer.invoke("expmon:pick-directory"),
  // Lightweight SQLite-backed history store (main process).
  db: Object.freeze({
    get: (key) => ipcRenderer.invoke("expmon:db:get", key),
    set: (key, value) => ipcRenderer.invoke("expmon:db:set", key, value),
    append: (kind, payload) => ipcRenderer.invoke("expmon:db:append", kind, payload),
    list: (kind, options) => ipcRenderer.invoke("expmon:db:list", kind, options),
    clear: (kind) => ipcRenderer.invoke("expmon:db:clear", kind),
    stats: () => ipcRenderer.invoke("expmon:db:stats"),
  }),
}));
