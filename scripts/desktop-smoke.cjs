const { spawn } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const outputDir = path.resolve(process.env.EXPMON_DESKTOP_SMOKE_OUTPUT || path.join(root, "build", "desktop-smoke"));
const dataDir = path.resolve(process.env.EXPMON_DESKTOP_DATA_DIR || path.join(outputDir, "data"));
const screenshotPath = path.join(outputDir, "desktop.png");
const resultPath = path.join(outputDir, "result.json");
fs.mkdirSync(outputDir, { recursive: true });
for (const target of [screenshotPath, resultPath]) {
  if (fs.existsSync(target)) fs.unlinkSync(target);
}

const electron = require("electron");
const child = spawn(electron, [root], {
  cwd: root,
  env: {
    ...process.env,
    EXPMON_DESKTOP_DATA_DIR: dataDir,
    EXPMON_DESKTOP_SMOKE_OUTPUT: outputDir,
  },
  windowsHide: true,
  stdio: ["ignore", "pipe", "pipe"],
});

let output = "";
child.stdout.on("data", (chunk) => { output += chunk.toString(); });
child.stderr.on("data", (chunk) => { output += chunk.toString(); });
const timeout = setTimeout(() => {
  child.kill();
  throw new Error(`Electron smoke test timed out\n${output}`);
}, 45000);

child.on("exit", (code) => {
  clearTimeout(timeout);
  if (code !== 0) {
    throw new Error(`Electron exited with code ${code}\n${output}`);
  }
  if (!fs.existsSync(resultPath) || !fs.existsSync(screenshotPath)) {
    throw new Error(`Electron did not produce smoke artifacts\n${output}`);
  }
  const result = JSON.parse(fs.readFileSync(resultPath, "utf8"));
  const screenshotBytes = fs.statSync(screenshotPath).size;
  if (result.title !== "ExpMon" || screenshotBytes < 10000 || !result.bridgeReady || !result.collectorConnected || result.healthStatus !== 200) {
    throw new Error(`Unexpected Electron smoke result: ${JSON.stringify({ result, screenshotBytes })}`);
  }
  process.stdout.write(`PASS: Electron desktop (${screenshotBytes} byte screenshot, ${result.collectorUrl})\n`);
});
