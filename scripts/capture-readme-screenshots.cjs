const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const root = path.resolve(__dirname, "..");
const workDir = path.join(root, "build", "readme-screenshots");
const imageDir = path.join(root, "docs", "images");
const fixturePath = path.join(workDir, "snapshot.json");

function series(length, base, spread, phase = 0) {
  return Array.from({ length }, (_, index) => Math.max(0, Math.round(base + Math.sin((index + phase) / 3) * spread)));
}

function gpu(index, model, memoryTotalMiB, utilization, memoryPercent, busy = true) {
  const usedMemoryMiB = Math.round(memoryTotalMiB * memoryPercent / 100);
  return {
    index,
    uuid: `GPU-DEMO-${model.replace(/\W/g, "")}-${index}`,
    name: model,
    memoryTotalMiB,
    memoryUsedMiB: usedMemoryMiB,
    memoryPercent,
    utilization,
    powerDrawW: Math.round(65 + utilization * 4.1),
    powerLimitW: model.includes("H200") ? 700 : (model.includes("4090") ? 450 : 350),
    powerLimitSource: "catalog",
    temperatureC: Math.round(36 + utilization * 0.28),
    busy,
    processes: busy ? [{
      pid: 42000 + index,
      name: "python",
      command: `python train.py --config configs/experiment-${index}.yaml`,
      usedMemoryMiB,
      gpuUuid: `GPU-DEMO-${model.replace(/\W/g, "")}-${index}`,
      gpuIndex: index,
      runId: `demo-run-${index}`,
      project: index % 2 ? "NeuroAtlas" : "VisionLab",
      runName: index % 2 ? "foundation-pretrain" : "segmentation-fold-2",
      role: "run",
    }] : [],
  };
}

function host({ id, name, address, user, cpu, memoryUsed, memoryTotal, model, gpuCount, busyGpus, coreCount, phase }) {
  const cores = series(coreCount, cpu, Math.min(28, Math.max(8, cpu / 2)), phase).map((value) => Math.min(100, value));
  const gpus = Array.from({ length: gpuCount }, (_, index) => gpu(
    index,
    model,
    model.includes("H200") ? 143360 : 49140,
    index < busyGpus ? Math.max(18, Math.min(98, 91 - index * 7 + phase)) : 1,
    index < busyGpus ? Math.max(22, Math.min(94, 78 - index * 5 + phase)) : 2,
    index < busyGpus,
  ));
  return {
    id,
    name,
    os: "Linux-6.8.0-x86_64",
    address,
    user,
    cpuUsage: cpu,
    memoryUsedGb: memoryUsed,
    memoryTotalGb: memoryTotal,
    memoryBreakdown: [
      { key: "used", label: "Used", valueGb: memoryUsed, percent: Math.round(memoryUsed / memoryTotal * 100) },
      { key: "cache", label: "Cache", valueGb: Math.round(memoryTotal * 0.42), percent: 42 },
      { key: "available", label: "Available", valueGb: Math.round((memoryTotal - memoryUsed) * 10) / 10, percent: Math.round((memoryTotal - memoryUsed) / memoryTotal * 100) },
      { key: "shared", label: "Shared", valueGb: 3.8, percent: 1 },
    ],
    gpusTotal: gpuCount,
    gpusBusy: busyGpus,
    gpus,
    diskRead: 186.4 + phase * 4,
    diskWrite: 42.8 + phase,
    netRx: 72.3 + phase,
    netTx: 18.6 + phase,
    runningRuns: busyGpus,
    warnings: [],
    cores,
    history: Array.from({ length: 36 }, (_, index) => ({
      time: `${String(14 + Math.floor(index / 12)).padStart(2, "0")}:${String((index % 12) * 5).padStart(2, "0")}`,
      cpu: Math.max(2, Math.round(cpu + Math.sin((index + phase) / 4) * 12)),
      memory: Math.round((memoryUsed + Math.sin(index / 7) * 3) * 10) / 10,
      gpuUtil: Math.max(0, Math.min(100, Math.round(72 + Math.sin((index + phase) / 3) * 20))),
      gpuMemory: Math.round(gpus.reduce((sum, item) => sum + item.memoryUsedMiB, 0) / 1024 * 10) / 10,
    })),
  };
}

const hosts = [
  host({ id: "local", name: "Local Workstation", address: "127.0.0.1", user: "researcher", cpu: 24, memoryUsed: 31.4, memoryTotal: 64, model: "NVIDIA RTX 4090", gpuCount: 1, busyGpus: 1, coreCount: 20, phase: 1 }),
  host({ id: "ssh:atlas-01", name: "Atlas-01", address: "10.20.0.21", user: "alice", cpu: 37, memoryUsed: 148.7, memoryTotal: 512, model: "NVIDIA RTX A6000", gpuCount: 8, busyGpus: 6, coreCount: 64, phase: 3 }),
  host({ id: "ssh:h200-01", name: "H200-01", address: "10.20.0.31", user: "mlops", cpu: 68, memoryUsed: 612.5, memoryTotal: 1024, model: "NVIDIA H200", gpuCount: 8, busyGpus: 7, coreCount: 96, phase: 6 }),
  host({ id: "ssh:vision-02", name: "Vision-02", address: "10.20.0.42", user: "bob", cpu: 46, memoryUsed: 219.2, memoryTotal: 512, model: "NVIDIA RTX 6000 Ada", gpuCount: 4, busyGpus: 3, coreCount: 48, phase: 8 }),
  host({ id: "ssh:compute-01", name: "Compute-01", address: "10.20.0.51", user: "carol", cpu: 82, memoryUsed: 386.4, memoryTotal: 768, model: "NVIDIA L40S", gpuCount: 4, busyGpus: 4, coreCount: 72, phase: 10 }),
];

function run({ id, project, name, status, hostId, user, pid, cpu, memory, gpuIndex, metric, runtime, kind = "python" }) {
  const finished = status !== "running";
  return {
    id,
    project,
    name,
    status,
    resourceType: "gpu",
    hostId,
    user,
    rootPid: pid,
    rootCreateTime: "2026-07-17 09:15:00",
    command: `python train.py --project ${project} --name ${name}`,
    cwd: `/workspace/${project.toLowerCase()}`,
    runtime,
    endedAt: finished ? "2026-07-17 13:26:40" : undefined,
    rootCpuPercent: cpu,
    processTreeCpuPercent: Math.round(cpu * 1.8 * 10) / 10,
    cpuPercent: Math.round(cpu * 1.8 * 10) / 10,
    memoryGb: memory,
    gpuLabel: `GPU ${gpuIndex}`,
    gpuMemoryGb: Math.round(memory * 1.7 * 10) / 10,
    gpuUtilPercent: finished ? 0 : 88 - gpuIndex * 3,
    gpuPowerW: finished ? 0 : 410 - gpuIndex * 12,
    gpuTemperatureC: finished ? 38 : 61 - gpuIndex,
    diskIo: 128.4,
    latestMetric: metric,
    bestMetric: metric,
    entrypointKind: kind,
    tags: ["remote", status],
    accessLevel: "A",
    processTree: { pid, name: kind === "shell" ? "bash" : "python", cpu, memoryGb: memory, role: "root", children: [] },
    hparams: { batch_size: 16, learning_rate: 0.0002, precision: "bf16" },
    logs: [],
    metrics: [],
    resources: [],
    events: [],
    summary: {
      durationSeconds: 15116,
      duration: runtime,
      gpuHours: 18.4,
      avgGpuUtil: 84.2,
      maxGpuUtil: 100,
      maxGpuMemoryGb: Math.round(memory * 1.7 * 10) / 10,
      avgCpu: cpu,
      maxMemoryGb: memory,
      totalReadMiB: 42560,
      totalWriteMiB: 8840,
      bestMetric: metric,
      finalMetric: metric,
      failReason: "-",
      eventCount: 3,
      errorCount: 0,
    },
    metadata: { pinned: false, mark: "none", note: "" },
    gpuProcesses: [],
    remote: hostId !== "local",
    remoteServerId: hostId.replace("ssh:", ""),
    remoteRunId: id,
    visualizations: [],
  };
}

const runs = [
  run({ id: "run-neuro-1", project: "NeuroAtlas", name: "hcp-foundation-pretrain", status: "running", hostId: "ssh:h200-01", user: "alice", pid: 42018, cpu: 312, memory: 74.6, gpuIndex: 0, metric: "train_loss=0.184", runtime: "8h42m" }),
  run({ id: "run-vision-1", project: "VisionLab", name: "segmentation-fold-2", status: "running", hostId: "ssh:atlas-01", user: "bob", pid: 38104, cpu: 228, memory: 42.3, gpuIndex: 2, metric: "dice=0.914", runtime: "3h16m" }),
  run({ id: "run-language-1", project: "MedLLM", name: "instruction-tune", status: "running", hostId: "ssh:h200-01", user: "carol", pid: 42188, cpu: 486, memory: 128.7, gpuIndex: 4, metric: "valid_loss=0.231", runtime: "6h05m" }),
  run({ id: "run-diffusion-1", project: "ImageForge", name: "latent-diffusion-xl", status: "running", hostId: "ssh:compute-01", user: "dana", pid: 29876, cpu: 364, memory: 89.4, gpuIndex: 1, metric: "fid=7.82", runtime: "11h20m" }),
  run({ id: "run-neuro-2", project: "NeuroAtlas", name: "ablation-mask-075", status: "finished", hostId: "ssh:h200-01", user: "alice", pid: 39872, cpu: 0, memory: 0, gpuIndex: 3, metric: "test_loss=0.207", runtime: "4h11m", kind: "shell" }),
  run({ id: "run-vision-2", project: "VisionLab", name: "segmentation-fold-1", status: "finished", hostId: "ssh:vision-02", user: "bob", pid: 27641, cpu: 0, memory: 0, gpuIndex: 0, metric: "dice=0.908", runtime: "5h47m" }),
  run({ id: "run-forecast-1", project: "ForecastNet", name: "multisite-baseline", status: "failed", hostId: "ssh:atlas-01", user: "carol", pid: 25118, cpu: 0, memory: 0, gpuIndex: 5, metric: "valid_mae=0.143", runtime: "1h32m" }),
];

const projectNames = ["NeuroAtlas", "VisionLab", "MedLLM", "ImageForge", "ForecastNet"];
const snapshot = {
  hosts,
  runs,
  projects: projectNames.map((name, index) => {
    const projectRuns = runs.filter((item) => item.project === name);
    return {
      id: `project-${index}`,
      name,
      path: `/workspace/${name.toLowerCase()}`,
      isGit: true,
      runs: projectRuns.map((item) => item.id),
      runningRuns: projectRuns.filter((item) => item.status === "running").length,
      finishedRuns: projectRuns.filter((item) => item.status === "finished").length,
      failedRuns: projectRuns.filter((item) => item.status === "failed").length,
      totalGpuHours: Math.round((16 + index * 7.4) * 10) / 10,
      avgGpuUtil: 74 + index * 3,
      lastActivity: `2026-07-17T${14 - index}:42:00`,
    };
  }),
  diagnostics: [],
  sshServers: hosts.filter((item) => item.id.startsWith("ssh:")).map((item) => ({
    id: item.id.slice(4),
    name: item.name,
    host: item.address,
    port: 22,
    username: item.user,
    authType: "key",
    keyPath: "~/.ssh/id_ed25519",
  })),
  sshKeyCandidates: [],
  updatedAt: "2026-07-17T15:42:00",
};

fs.mkdirSync(workDir, { recursive: true });
fs.mkdirSync(imageDir, { recursive: true });
fs.writeFileSync(fixturePath, `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");

for (const view of ["dashboard", "hosts", "runs"]) {
  const outputDir = path.join(workDir, view);
  const result = spawnSync(process.execPath, [path.join(root, "scripts", "desktop-smoke.cjs")], {
    cwd: root,
    env: {
      ...process.env,
      EXPMON_DESKTOP_DATA_DIR: path.join(outputDir, "data"),
      EXPMON_DESKTOP_SMOKE_OUTPUT: outputDir,
      EXPMON_DESKTOP_SMOKE_VIEW: view,
      EXPMON_DESKTOP_SMOKE_SETTLE_MS: "500",
      EXPMON_SNAPSHOT_FIXTURE: fixturePath,
    },
    encoding: "utf8",
    timeout: 60000,
  });
  if (result.status !== 0) {
    throw new Error(`Failed to capture ${view}\n${result.stdout}\n${result.stderr}`);
  }
  const source = path.join(outputDir, "desktop.png");
  const destination = path.join(imageDir, `expmon-${view}.png`);
  fs.copyFileSync(source, destination);
  process.stdout.write(`Captured ${path.relative(root, destination)}\n`);
}
