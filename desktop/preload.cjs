const { contextBridge } = require("electron");

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
}));
