const { app, BrowserWindow, dialog, shell } = require("electron");
const { spawn, spawnSync } = require("node:child_process");
const { randomBytes } = require("node:crypto");
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");

const SOURCE_ROOT = path.resolve(__dirname, "..");
if (process.env.EXPMON_DESKTOP_DATA_DIR) {
  app.setPath("userData", path.resolve(process.env.EXPMON_DESKTOP_DATA_DIR));
}
let collectorProcess = null;
let collectorLog = null;
let mainWindow = null;
let quitting = false;

function existingPath(candidates) {
  return candidates.find((candidate) => candidate && fs.existsSync(candidate));
}

function resolvePython() {
  return existingPath([
    process.env.EXPMON_PYTHON,
    path.join(SOURCE_ROOT, ".venv", "Scripts", "python.exe"),
    path.join(SOURCE_ROOT, ".venv", "bin", "python"),
  ]) || "python";
}

function freeLocalPort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close((error) => error ? reject(error) : resolve(port));
    });
  });
}

function desktopDataDir() {
  return path.resolve(process.env.EXPMON_DESKTOP_DATA_DIR || app.getPath("userData"));
}

function ensureDesktopConfig(dataDir) {
  const configPath = path.join(dataDir, "expmon-local.yaml");
  const runsRoot = path.join(dataDir, "expmon-runs");
  fs.mkdirSync(runsRoot, { recursive: true });
  if (!fs.existsSync(configPath)) {
    const initialConfig = {
      experiment_roots: [],
      run_discovery: { include_cwd_under: [] },
      protocol: { scan_roots: [runsRoot] },
    };
    fs.writeFileSync(configPath, `${JSON.stringify(initialConfig, null, 2)}\n`, "utf8");
  }
  return { configPath, runsRoot };
}

function collectorLaunch(dataDir, port, token) {
  const packagedRoot = path.join(process.resourcesPath, "expmon");
  const appRoot = app.isPackaged ? packagedRoot : SOURCE_ROOT;
  const { configPath, runsRoot } = ensureDesktopConfig(dataDir);
  const env = {
    ...process.env,
    EXPMON_APP_ROOT: appRoot,
    EXPMON_COLLECTOR_PORT: String(port),
    EXPMON_API_TOKEN: token,
    EXPMON_CONFIG: configPath,
    EXPMON_LOGDIR: runsRoot,
    EXPMON_RUN_METADATA: path.join(dataDir, "expmon-run-metadata.json"),
    EXPMON_SSH_SERVERS: path.join(dataDir, "expmon-ssh-servers.json"),
    PYTHONUNBUFFERED: "1",
  };

  if (app.isPackaged) {
    return {
      command: path.join(process.resourcesPath, "collector", "expmon-collector.exe"),
      args: [],
      cwd: appRoot,
      env,
    };
  }
  return {
    command: resolvePython(),
    args: [path.join(SOURCE_ROOT, "scripts", "local_collector.py")],
    cwd: SOURCE_ROOT,
    env,
  };
}

async function waitForCollector(url, token, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  let lastError = "collector did not respond";
  while (Date.now() < deadline) {
    if (collectorProcess?.exitCode != null) {
      throw new Error(`collector exited with code ${collectorProcess.exitCode}`);
    }
    try {
      const response = await fetch(`${url}/health`, {
        headers: { "X-ExpMon-Token": token },
        signal: AbortSignal.timeout(1500),
      });
      if (response.ok) {
        return;
      }
      lastError = `collector health returned ${response.status}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(lastError);
}

async function startCollector() {
  const dataDir = desktopDataDir();
  const logsDir = path.join(dataDir, "logs");
  fs.mkdirSync(logsDir, { recursive: true });
  const port = await freeLocalPort();
  const token = randomBytes(32).toString("hex");
  const launch = collectorLaunch(dataDir, port, token);
  const logPath = path.join(logsDir, "collector.log");
  collectorLog = fs.createWriteStream(logPath, { flags: "a" });
  collectorLog.write(`\n[${new Date().toISOString()}] starting ${launch.command}\n`);
  collectorProcess = spawn(launch.command, launch.args, {
    cwd: launch.cwd,
    env: launch.env,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  collectorProcess.stdout.pipe(collectorLog, { end: false });
  collectorProcess.stderr.pipe(collectorLog, { end: false });
  collectorProcess.once("exit", (code, signal) => {
    collectorLog?.write(`[${new Date().toISOString()}] exited code=${code} signal=${signal}\n`);
    if (!quitting) {
      dialog.showErrorBox("ExpMon collector stopped", `The local collector exited unexpectedly.\n\nLog: ${logPath}`);
      app.quit();
    }
  });
  collectorProcess.once("error", (error) => collectorLog?.write(`${error.stack || error}\n`));

  const collectorUrl = `http://127.0.0.1:${port}`;
  await waitForCollector(collectorUrl, token);
  return { collectorUrl, token, logPath };
}

function stopCollector() {
  if (!collectorProcess || collectorProcess.exitCode != null) {
    collectorLog?.end();
    return;
  }
  const pid = collectorProcess.pid;
  if (process.platform === "win32" && pid) {
    spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { windowsHide: true, stdio: "ignore" });
  } else {
    collectorProcess.kill("SIGTERM");
  }
  collectorLog?.end();
}

async function runSmokeCapture(window, collectorUrl, logPath) {
  const outputDir = process.env.EXPMON_DESKTOP_SMOKE_OUTPUT;
  if (!outputDir) {
    return;
  }
  let rendererState = { bridgeReady: false, collectorConnected: false, healthStatus: 0 };
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    rendererState = await window.webContents.executeJavaScript(`(async () => {
      const bridge = window.expmonDesktop;
      let healthStatus = 0;
      if (bridge?.collectorUrl && bridge?.apiToken) {
        try {
          const response = await fetch(bridge.collectorUrl + "/health", {
            headers: { "X-ExpMon-Token": bridge.apiToken }
          });
          healthStatus = response.status;
        } catch (_) {}
      }
      return {
        bridgeReady: Boolean(bridge?.collectorUrl && bridge?.apiToken),
        collectorConnected: document.body.innerText.includes("collector connected"),
        healthStatus
      };
    })()`);
    if (rendererState.collectorConnected && rendererState.healthStatus === 200) {
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  const smokeView = process.env.EXPMON_DESKTOP_SMOKE_VIEW || "dashboard";
  const navLabels = { dashboard: "Resources", hosts: "Host / SSH", runs: "Runs" };
  const navLabel = navLabels[smokeView];
  if (navLabel) {
    await window.webContents.executeJavaScript(`(() => {
      const englishButton = [...document.querySelectorAll("button")].find((button) => button.textContent.trim() === "EN");
      englishButton?.click();
      const target = [...document.querySelectorAll("button")].find((button) => button.textContent.trim() === ${JSON.stringify(navLabel)});
      target?.click();
    })()`);
    await new Promise((resolve) => setTimeout(resolve, 750));
  }
  if (smokeView === "hosts") {
    await window.webContents.executeJavaScript(`(() => {
      const target = [...document.querySelectorAll("button")].find((button) => {
        const text = button.textContent.replace(/\s+/g, " ").trim();
        return text.startsWith("H200-01") && text.includes("CPU");
      });
      target?.click();
    })()`);
  }
  const settleMs = Number(process.env.EXPMON_DESKTOP_SMOKE_SETTLE_MS || 0);
  if (settleMs > 0) {
    await new Promise((resolve) => setTimeout(resolve, settleMs));
  }
  fs.mkdirSync(outputDir, { recursive: true });
  const image = await window.webContents.capturePage();
  fs.writeFileSync(path.join(outputDir, "desktop.png"), image.toPNG());
  fs.writeFileSync(path.join(outputDir, "result.json"), JSON.stringify({
    title: window.getTitle(),
    url: window.webContents.getURL(),
    collectorUrl,
    collectorLog: logPath,
    smokeView,
    ...rendererState,
  }, null, 2));
  app.quit();
}

async function createMainWindow() {
  const { collectorUrl, token, logPath } = await startCollector();
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1024,
    minHeight: 700,
    show: false,
    autoHideMenuBar: true,
    backgroundColor: "#f6f8f8",
    title: "ExpMon",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      additionalArguments: [
        `--expmon-collector-url=${collectorUrl}`,
        `--expmon-api-token=${token}`,
        `--expmon-version=${app.getVersion()}`,
      ],
    },
  });
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//i.test(url)) {
      void shell.openExternal(url);
    }
    return { action: "deny" };
  });
  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith("file://") && !url.startsWith("http://127.0.0.1:")) {
      event.preventDefault();
    }
  });
  mainWindow.once("ready-to-show", () => mainWindow?.show());
  mainWindow.on("closed", () => { mainWindow = null; });

  const devUrl = process.env.EXPMON_DESKTOP_DEV_URL;
  if (devUrl) {
    await mainWindow.loadURL(devUrl);
  } else {
    await mainWindow.loadFile(path.join(SOURCE_ROOT, "dist", "index.html"));
  }
  void runSmokeCapture(mainWindow, collectorUrl, logPath);
}

const hasSingleInstanceLock = app.requestSingleInstanceLock();
if (!hasSingleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
  app.whenReady().then(createMainWindow).catch((error) => {
    dialog.showErrorBox("ExpMon could not start", error instanceof Error ? error.message : String(error));
    app.quit();
  });
}

app.on("before-quit", () => {
  quitting = true;
  stopCollector();
});

app.on("window-all-closed", () => app.quit());
