import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  Cpu,
  Database,
  FileText,
  Gauge,
  HardDrive,
  Layers3,
  ListFilter,
  MemoryStick,
  Network,
  Play,
  RefreshCw,
  Search,
  Server,
  Plus,
  Settings,
  SlidersHorizontal,
  TerminalSquare,
  Trash2,
  Workflow,
  Zap
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent
} from "react";

type ResourceType = "cpu_only" | "gpu" | "hybrid" | "unknown";
type RunStatus = "running" | "finished" | "failed" | "killed" | "unmanaged";
type Language = "zh" | "en";
type TimeRange = "5m" | "15m" | "1h" | "all";
type ConfirmTone = "default" | "danger";
type EntrypointKind =
  | "python"
  | "shell"
  | "native_binary"
  | "java"
  | "r"
  | "julia"
  | "other";

type Host = {
  id: string;
  name: string;
  os: string;
  address: string;
  user: string;
  cpuUsage: number;
  memoryUsedGb: number;
  memoryTotalGb: number;
  memoryBreakdown?: MemoryBreakdown[];
  gpusTotal: number;
  gpusBusy: number;
  gpus?: GpuSample[];
  diskRead: number;
  diskWrite: number;
  netRx: number;
  netTx: number;
  runningRuns: number;
  warnings: string[];
  cores: number[];
  history?: Array<Record<string, number | string>>;
  processes?: HostProcess[];
};

type MemoryBreakdown = {
  key: string;
  label: string;
  valueGb: number;
  percent: number;
  note?: string;
};

type GpuSample = {
  index: number;
  uuid?: string;
  name: string;
  memoryTotalMiB: number;
  memoryUsedMiB: number;
  memoryPercent: number;
  utilization: number;
  powerDrawW: number;
  powerLimitW?: number | null;
  powerLimitSource?: "nvidia-smi" | "catalog" | "unknown" | string;
  temperatureC: number;
  busy: boolean;
  processes?: GpuProcess[];
};

type GpuProcess = {
  pid: number;
  name: string;
  command?: string;
  usedMemoryMiB: number;
  gpuUuid: string;
  gpuIndex: number;
  runId?: string;
  project?: string;
  runName?: string;
  role?: string;
};

type RunEvent = {
  time: string;
  type: string;
  severity: "info" | "warning" | "error" | string;
  message: string;
  source: string;
  line: string;
};

type RunSummary = {
  durationSeconds: number;
  duration: string;
  gpuHours: number;
  avgGpuUtil: number;
  maxGpuUtil: number;
  maxGpuMemoryGb: number;
  avgCpu: number;
  maxMemoryGb: number;
  totalReadMiB: number;
  totalWriteMiB: number;
  bestMetric: string;
  finalMetric: string;
  failReason: string;
  eventCount: number;
  errorCount: number;
};

type RunMetadata = {
  note: string;
  mark: string;
  pinned: boolean;
  updatedAt: string;
};

type SshServer = {
  id: string;
  name: string;
  host: string;
  port: number;
  username: string;
  authType: "key" | "password";
  keyPath?: string;
  hasPassword?: boolean;
  createdAt?: string;
  updatedAt?: string;
};

type SshServerForm = {
  name: string;
  host: string;
  port: number;
  username: string;
  authType: "key" | "password";
  keyPath: string;
  password: string;
};

type SshSaveResult = {
  server?: SshServer;
  test?: SshTestResult;
  storagePath?: string;
};

type SshTestResult = {
  ok: boolean;
  supported?: boolean;
  testedAt?: string;
  sampledAt?: string;
  latencyMs?: number;
  hostname?: string;
  remoteOs?: string;
  pythonPath?: string;
  host?: Host;
  stdout?: string;
  stderr?: string;
  message?: string;
  error?: string;
};

type ProcessNode = {
  pid: number;
  name: string;
  cpu: number;
  memoryGb: number;
  role: string;
  children?: ProcessNode[];
};

type HostProcess = {
  pid: number;
  name: string;
  command?: string;
  cpu: number;
  memoryGb: number;
};

type RunVisualization = {
  id: string;
  kind: "tensorboard" | "wandb" | "mlflow" | "metrics-jsonl" | "metrics-csv" | string;
  label: string;
  path: string;
  relativePath: string;
  viewer: "inline" | "external" | string;
  fileCount: number;
  sizeMb: number;
  updatedAt: string;
};

type VisualizationPreview = {
  ok: boolean;
  visualization?: RunVisualization;
  summary?: Record<string, string | number | boolean>;
  rows?: Array<Record<string, number | string>>;
  message?: string;
  error?: string;
};

type Run = {
  id: string;
  project: string;
  name: string;
  status: RunStatus;
  resourceType: ResourceType;
  hostId: string;
  user: string;
  rootPid: number;
  rootCreateTime: string;
  command: string;
  cwd: string;
  runtime: string;
  rootCpuPercent?: number;
  processTreeCpuPercent?: number;
  cpuPercent: number;
  memoryGb: number;
  gpuLabel: string;
  gpuMemoryGb: number;
  gpuUtilPercent: number;
  gpuPowerW: number;
  gpuTemperatureC: number;
  diskIo: number;
  latestMetric: string;
  bestMetric: string;
  entrypointKind: EntrypointKind;
  tags: string[];
  accessLevel: "A" | "B" | "C";
  processTree: ProcessNode;
  hparams: Record<string, string | number | boolean>;
  logs: string[];
  metrics: Array<Record<string, number | string>>;
  resources: Array<Record<string, number | string>>;
  events?: RunEvent[];
  summary?: RunSummary;
  metadata?: RunMetadata;
  visualizations?: RunVisualization[];
  gpuProcesses?: GpuProcess[];
};

type Project = {
  id: string;
  name: string;
  path: string;
  isGit: boolean;
  runs: string[];
  runningRuns: number;
  finishedRuns: number;
  failedRuns?: number;
  totalGpuHours?: number;
  avgGpuUtil?: number;
  lastActivity: string;
};

type Diagnostic = {
  id: string;
  severity: "info" | "warning" | "error" | string;
  type: string;
  title: string;
  message: string;
  runId?: string;
  project?: string;
  evidence?: string;
};

type GitProjectPayload = {
  ok: boolean;
  project?: Project;
  branch?: string;
  remotes?: string[];
  status?: string[];
  changedFiles?: Array<{ status: string; path: string }>;
  log?: string[];
  diffStat?: string;
  stagedDiffStat?: string;
  diff?: string;
  errors?: string[];
  error?: string;
};

type NavKey = "dashboard" | "hosts" | "projects" | "runs" | "detail" | "config" | "protocol";

type Snapshot = {
  hosts: Host[];
  runs: Run[];
  projects?: Project[];
  diagnostics?: Diagnostic[];
  connected: boolean;
  error?: string;
  config?: CollectorConfig;
  configMetadata?: ConfigMetadata;
  sshServers?: SshServer[];
  sshKeyCandidates?: string[];
};

type CollectorConfig = {
  host_id?: string;
  sampling?: {
    interval_seconds?: number;
    unmanaged_top_n?: number;
  };
  experiment_roots?: string[];
  run_discovery?: {
    include_command_keywords?: string[];
    exclude_command_keywords?: string[];
    include_cwd_under?: string[];
    explicit_rules?: Array<{ name?: string; project?: string; command_regex?: string }>;
  };
  protocol?: {
    scan_roots?: string[];
    max_scan_depth?: number;
    max_metric_points?: number;
  };
};

type ConfigMetadata = {
  path?: string;
  samplePath?: string;
  usingEnvConfig?: boolean;
  writable?: boolean;
};

type PendingConfirm = {
  title: string;
  body: string;
  confirmLabel: string;
  tone?: ConfirmTone;
  onConfirm: () => void;
};

const initialHosts: Host[] = [
  {
    id: "local",
    name: "Local Host",
    os: "Windows",
    address: "127.0.0.1",
    user: "local",
    cpuUsage: 0,
    memoryUsedGb: 0,
    memoryTotalGb: 0,
    gpusTotal: 0,
    gpusBusy: 0,
    gpus: [],
    diskRead: 0,
    diskWrite: 0,
    netRx: 0,
    netTx: 0,
    runningRuns: 0,
    warnings: ["collector offline"],
    cores: Array.from({ length: 12 }, () => 0)
  }
];

const timeline = ["15:31", "15:36", "15:41", "15:46", "15:51", "15:56", "16:01", "16:06"];

const initialRuns: Run[] = [];

const REFRESH_INTERVAL_MS = 3000;
const VITE_ENV = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env ?? {};
const API_BASE = (VITE_ENV.VITE_COLLECTOR_URL ?? "http://127.0.0.1:5184").replace(/\/$/, "");

const TEXT = {
  zh: {
    appSubtitle: "通用实验任务监控系统",
    navDashboard: "资源总览",
    navHosts: "Host / SSH",
    navProjects: "项目",
    navRuns: "任务列表",
    navDetail: "任务详情",
    navConfig: "配置",
    navProtocol: "协议模型",
    titleDashboard: "资源总览",
    titleHosts: "Host / SSH 服务器",
    titleProjects: "项目",
    titleRuns: "实验任务",
    titleDetail: "任务详情",
    titleConfig: "配置",
    titleProtocol: "任务协议模型",
    eyebrow: "任务 = 根进程 + 进程树 + 资源",
    searchPlaceholder: "搜索项目、主机、命令",
    refresh: "刷新",
    collectorLive: "采集器已连接",
    collectorOffline: "采集器未连接",
    refreshEvery: "每 3 秒刷新",
    language: "语言",
    chinese: "中文",
    english: "EN",
    all: "全部",
    cpuOnly: "CPU-only",
    gpu: "GPU",
    hybrid: "Hybrid",
    unknown: "Unknown",
    status: "状态",
    projectRun: "项目 / 任务",
    resource: "资源",
    host: "主机",
    rootPid: "Root PID",
    userLabel: "用户",
    runtimeLabel: "运行时长",
    cpuTreeLabel: "CPU 根进程/进程树",
    accessLevelLabel: "级别",
    cpu: "CPU",
    memory: "内存",
    diskIo: "磁盘 I/O",
    metric: "指标",
    kind: "类型",
    actions: "操作",
    parserRules: "解析规则",
    noTasks: "暂无任务",
    noTasksBody: "任务监控会定时刷新；当本机采集器或 expmon launch 写入任务后，会出现在这里。",
    deleteFinishedRecord: "删除已结束的任务记录",
    hosts: "主机",
    busyGpus: "占用 GPU",
    cpuAvg: "CPU 平均",
    memoryAvg: "内存平均",
    runningRuns: "运行任务",
    resourceMix: "主机资源组合",
    activeRuns: "运行中任务",
    noExperimentTasks: "暂无实验任务",
    noExperimentTasksBody: "启动采集器或通过 expmon launch 创建任务后，这里会显示运行中的任务。",
    perCoreCpu: "CPU 单核",
    diskNetwork: "磁盘 / 网络",
    topProcesses: "进程排行",
    noProcessSamples: "暂无进程采样",
    noProcessSamplesBody: "本机采集器接入后，这里会定时显示 CPU 排行、内存排行和未托管进程。",
    sshServers: "SSH 服务器",
    addSshServer: "添加 SSH 服务器",
    sshPasswordNotice: "密码会按要求保存到本机配置文件；前端不会回显密码。",
    saveServer: "保存服务器",
    saving: "保存中",
    deleteSshServer: "删除 SSH 服务器",
    testSshServer: "测试连接",
    testingSsh: "测试中",
    refreshRemoteResources: "刷新资源",
    loadingRemoteResources: "读取中",
    remoteResourceSnapshot: "远端资源快照",
    sshTestOk: "连接正常",
    sshTestFailed: "连接失败",
    sshTestUnsupported: "暂不支持测试",
    latency: "延迟",
    auth: "认证",
    credential: "凭据",
    configured: "已配置",
    updated: "更新",
    savedLocally: "本地已保存",
    missing: "缺失",
    noRemoteServer: "未配置远端服务器",
    noRemoteServerBody: "添加 SSH host 后会在这里展示远端资源、进程和日志采集状态。",
    hostResourceMix: "主机资源组合",
    cpuCores: "CPU 核心",
    resourceCurves: "资源曲线",
    processTree: "进程树",
    metrics: "指标",
    hyperparameters: "超参数",
    logs: "日志",
    runIdentity: "任务身份",
    noRunDetail: "暂无任务详情",
    noRunDetailBody: "当前没有可查看的任务。任务监控页会每 3 秒刷新一次，后端接入后会自动显示新任务。",
    backToRuns: "返回任务列表",
    killTask: "终止任务",
    killing: "终止中",
    deleteRecord: "删除记录",
    deleting: "删除中",
    noResourceSamples: "暂无资源采样",
    noResourceSamplesBody: "受管任务在采集器运行期间被采样后会显示资源历史；如果已结束任务为空，通常说明任务运行时采集器未采样到它。",
    samplingNow: "正在采样",
    historySamples: "历史采样",
    waitingForSamples: "等待采样",
    noHistorySamples: "无历史采样",
    sampleCount: "采样点",
    collectorSamplingHint: "采集器需要在任务运行期间保持连接，结束后才能查看这段历史。",
    noTrainingMetrics: "暂无训练指标",
    noTrainingMetricsBody: "通过 expmon launch 输出 EXPMON_METRIC 或调用 expmon.py log 后会显示指标曲线。",
    unmanagedProcess: "未托管进程",
    accessLevels: "访问级别",
    sqliteSchema: "SQLite schema v2",
    commandWrapper: "命令包装器",
    collectorChannels: "采集通道",
    localLive: "本机在线",
    offline: "离线",
    localHostName: "本机",
    normal: "正常",
    noLocalResource: "暂无本机资源",
    noLocalResourceBody: "采集器启动后会显示 GPU、内存和 CPU 核心使用率。",
    noNvidiaGpu: "未检测到 NVIDIA GPU",
    noNvidiaGpuBody: "如果机器有 NVIDIA 显卡，请确认 nvidia-smi 可用。",
    remoteInitializing: "初始化环境中",
    remoteResourcesNotLoaded: "远端资源尚未读取",
    remoteResourceLoadFailed: "远端资源读取失败",
    systemMemory: "系统内存",
    memoryBreakdown: "内存分类",
    memoryBreakdownHint: "不同系统的内存定义不同，下面按系统原始语义展示。",
    memoryBreakdownUnavailable: "暂无内存分类采样",
    notOccupied: "未占用",
    notDetected: "未检测",
    notConnected: "采集器未连接",
    warnings: "警告",
    runsLabel: "任务",
    runningSuffix: "运行中",
    failed: "失败",
    gpuHour: "GPU 小时",
    avgGpuUtil: "平均 GPU 利用率",
    cores: "核心",
    memoryLabel: "内存",
    gpuUtil: "GPU 利用率",
    gpuMemory: "GPU 显存",
    power: "功率",
    temperature: "温度",
    read: "读",
    write: "写",
    receive: "接收",
    transmit: "发送",
    network: "网络",
    visibleOnHost: "此主机可见",
    runNotes: "任务备注",
    runSummary: "任务摘要",
    gpuProcesses: "GPU 进程",
    events: "事件",
    noGpuProcessForRun: "未归属到该任务的 GPU 进程",
    noGpuProcesses: "暂无 GPU 进程",
    noSummary: "暂无摘要",
    noEvents: "暂无事件",
    duration: "时长",
    avgCpu: "平均 CPU",
    maxRam: "最大内存",
    totalIo: "总 I/O",
    bestMetric: "最佳指标",
    finalMetric: "最终指标",
    failReason: "失败原因",
    eventCount: "事件",
    runIdentityLabel: "任务身份",
    statusRunning: "运行中",
    statusFinished: "已结束",
    statusFailed: "失败",
    statusKilled: "已终止",
    statusUnmanaged: "未托管",
    noInsights: "暂无洞察",
    noInsightsBody: "当前快照未发现可疑任务或资源问题。",
    pin: "置顶",
    pinned: "已置顶",
    mark: "标记",
    none: "无",
    noNoteSaved: "暂无备注",
    updatedAt: "更新于",
    saveNotes: "保存备注",
    addRunNote: "添加这个任务的备注...",
    savingShort: "保存中",
    errors: "错误",
    rootProcess: "根进程",
    childProcess: "子进程",
    processLabel: "进程",
    gpuMemShort: "GPU 显存",
    runLabel: "任务",
    metricCountLabel: "个指标",
    metricRangeAll: "全部",
    metricLossGroup: "损失 / 误差",
    metricScoreGroup: "评分指标",
    metricLearningRateGroup: "学习率",
    metricTimeGroup: "时间 / 速度",
    metricOtherGroup: "其他指标",
    resourceCpuMemoryGroup: "CPU / 内存",
    resourceDiskGroup: "磁盘 I/O",
    resourceGpuUsageGroup: "GPU 利用率 / 显存",
    resourceGpuThermalGroup: "GPU 功率 / 温度",
    resourceSnapshot: "资源快照",
    protocolLogs: "协议日志",
    confirmTitle: "确认操作",
    confirm: "确认",
    cancel: "取消",
    searchLogs: "搜索日志",
    logLevelAll: "全部级别",
    logLevelError: "错误",
    logLevelWarning: "警告",
    logLevelInfo: "信息",
    logLevelOther: "其他",
    latestLogs: "最新日志",
    matchingLines: "匹配行",
    noMatchingLogs: "没有匹配的日志"
  },
  en: {
    appSubtitle: "General experiment task monitor",
    navDashboard: "Resources",
    navHosts: "Host / SSH",
    navProjects: "Projects",
    navRuns: "Runs",
    navDetail: "Run Detail",
    navConfig: "Config",
    navProtocol: "Protocol",
    titleDashboard: "Resource Dashboard",
    titleHosts: "Host / SSH Servers",
    titleProjects: "Projects",
    titleRuns: "Experiment Runs",
    titleDetail: "Run Detail",
    titleConfig: "Config",
    titleProtocol: "Run Protocol",
    eyebrow: "Run = root process + process tree + resources",
    searchPlaceholder: "Search project, host, command",
    refresh: "Refresh",
    collectorLive: "collector connected",
    collectorOffline: "collector offline",
    refreshEvery: "refreshes every 3s",
    language: "Language",
    chinese: "中文",
    english: "EN",
    all: "All",
    cpuOnly: "CPU-only",
    gpu: "GPU",
    hybrid: "Hybrid",
    unknown: "Unknown",
    status: "Status",
    projectRun: "Project / Run",
    resource: "Resource",
    host: "Host",
    rootPid: "Root PID",
    userLabel: "User",
    runtimeLabel: "Runtime",
    cpuTreeLabel: "CPU root/tree",
    accessLevelLabel: "Level",
    cpu: "CPU",
    memory: "Memory",
    diskIo: "Disk I/O",
    metric: "Metric",
    kind: "Kind",
    actions: "Actions",
    parserRules: "Parser rules",
    noTasks: "No runs",
    noTasksBody: "The task list refreshes automatically. Runs appear here after the local collector or expmon launch writes them.",
    deleteFinishedRecord: "Delete finished run record",
    hosts: "Hosts",
    busyGpus: "Busy GPUs",
    cpuAvg: "CPU Avg",
    memoryAvg: "Memory Avg",
    runningRuns: "Running Runs",
    resourceMix: "Host Resource Mix",
    activeRuns: "Active Runs",
    noExperimentTasks: "No experiment runs",
    noExperimentTasksBody: "Running tasks appear here after the collector starts or a run is created through expmon launch.",
    perCoreCpu: "Per-core CPU",
    diskNetwork: "Disk / Network",
    topProcesses: "Top Processes",
    noProcessSamples: "No process samples",
    noProcessSamplesBody: "After the local collector connects, top CPU, top memory, and unmanaged processes appear here.",
    sshServers: "SSH Servers",
    addSshServer: "Add SSH Server",
    sshPasswordNotice: "Passwords are saved to a local config file as requested and are not echoed back in the UI.",
    saveServer: "Save Server",
    saving: "Saving",
    deleteSshServer: "Delete SSH server",
    testSshServer: "Test Connection",
    testingSsh: "Testing",
    refreshRemoteResources: "Refresh Resources",
    loadingRemoteResources: "Loading",
    remoteResourceSnapshot: "Remote Resource Snapshot",
    sshTestOk: "Connection OK",
    sshTestFailed: "Connection failed",
    sshTestUnsupported: "Test unsupported",
    latency: "Latency",
    auth: "Auth",
    credential: "Credential",
    configured: "Configured",
    updated: "Updated",
    savedLocally: "saved locally",
    missing: "missing",
    noRemoteServer: "No remote servers configured",
    noRemoteServerBody: "After adding an SSH host, remote resources, processes, and log collection status will appear here.",
    hostResourceMix: "Host Resource Mix",
    cpuCores: "CPU Cores",
    resourceCurves: "Resource Curves",
    processTree: "Process Tree",
    metrics: "Metrics",
    hyperparameters: "Hyperparameters",
    logs: "Logs",
    runIdentity: "Run Identity",
    noRunDetail: "No run detail",
    noRunDetailBody: "No run is selected. The run page refreshes every 3 seconds and will show new tasks automatically.",
    backToRuns: "Back to Runs",
    killTask: "Kill Task",
    killing: "Killing",
    deleteRecord: "Delete Record",
    deleting: "Deleting",
    noResourceSamples: "No resource samples",
    noResourceSamplesBody: "Resource history appears after the collector samples a managed run while it is running. If a finished run is empty, the collector likely did not sample it during execution.",
    samplingNow: "Sampling now",
    historySamples: "Historical samples",
    waitingForSamples: "Waiting for samples",
    noHistorySamples: "No history samples",
    sampleCount: "samples",
    collectorSamplingHint: "The collector must stay connected while the task is running so this history can be shown after it finishes.",
    noTrainingMetrics: "No training metrics",
    noTrainingMetricsBody: "Metric curves appear after expmon launch emits EXPMON_METRIC or expmon.py log is called.",
    unmanagedProcess: "unmanaged process",
    accessLevels: "Access Levels",
    sqliteSchema: "SQLite schema v2",
    commandWrapper: "Command Wrapper",
    collectorChannels: "Collector Channels",
    localLive: "local live",
    offline: "offline",
    localHostName: "Local Host",
    normal: "normal",
    noLocalResource: "No local resources",
    noLocalResourceBody: "GPU, memory, and CPU core usage appear after the collector starts.",
    noNvidiaGpu: "No NVIDIA GPU detected",
    noNvidiaGpuBody: "If this machine has an NVIDIA GPU, check that nvidia-smi is available.",
    remoteInitializing: "initializing environment",
    remoteResourcesNotLoaded: "remote resources not loaded",
    remoteResourceLoadFailed: "remote resource loading failed",
    systemMemory: "System Memory",
    memoryBreakdown: "Memory Breakdown",
    memoryBreakdownHint: "Memory categories differ by OS; rows keep the source system semantics.",
    memoryBreakdownUnavailable: "No memory breakdown samples",
    notOccupied: "not occupied",
    notDetected: "not detected",
    notConnected: "collector offline",
    warnings: "Warnings",
    runsLabel: "Runs",
    runningSuffix: "running",
    failed: "Failed",
    gpuHour: "GPU-hour",
    avgGpuUtil: "Avg GPU util",
    cores: "cores",
    memoryLabel: "Memory",
    gpuUtil: "GPU Util",
    gpuMemory: "GPU Memory",
    power: "Power",
    temperature: "Temp",
    read: "Read",
    write: "Write",
    receive: "Rx",
    transmit: "Tx",
    network: "Network",
    visibleOnHost: "visible on this host",
    runNotes: "Run Notes",
    runSummary: "Run Summary",
    gpuProcesses: "GPU Processes",
    events: "Events",
    noGpuProcessForRun: "No GPU process attributed to this run",
    noGpuProcesses: "No GPU processes",
    noSummary: "No summary available",
    noEvents: "No events detected",
    duration: "Duration",
    avgCpu: "Avg CPU",
    maxRam: "Max RAM",
    totalIo: "Total I/O",
    bestMetric: "Best metric",
    finalMetric: "Final metric",
    failReason: "Fail reason",
    eventCount: "Events",
    runIdentityLabel: "Run Identity",
    statusRunning: "running",
    statusFinished: "finished",
    statusFailed: "failed",
    statusKilled: "killed",
    statusUnmanaged: "unmanaged",
    noInsights: "No insights",
    noInsightsBody: "No suspicious runs or resource issues detected in the current snapshot.",
    pin: "Pin",
    pinned: "Pinned",
    mark: "Mark",
    none: "none",
    noNoteSaved: "No note saved",
    updatedAt: "Updated",
    saveNotes: "Save Notes",
    addRunNote: "Add notes about this run...",
    savingShort: "Saving",
    errors: "errors",
    rootProcess: "root",
    childProcess: "child",
    processLabel: "Process",
    gpuMemShort: "GPU Mem",
    runLabel: "Run",
    metricCountLabel: "metrics",
    metricRangeAll: "All",
    metricLossGroup: "Loss / Error",
    metricScoreGroup: "Scores",
    metricLearningRateGroup: "Learning Rate",
    metricTimeGroup: "Time / Speed",
    metricOtherGroup: "Other Metrics",
    resourceCpuMemoryGroup: "CPU / Memory",
    resourceDiskGroup: "Disk I/O",
    resourceGpuUsageGroup: "GPU Util / Memory",
    resourceGpuThermalGroup: "GPU Power / Temp",
    resourceSnapshot: "resource snapshot",
    protocolLogs: "protocol logs",
    confirmTitle: "Confirm action",
    confirm: "Confirm",
    cancel: "Cancel",
    searchLogs: "Search logs",
    logLevelAll: "All levels",
    logLevelError: "Error",
    logLevelWarning: "Warning",
    logLevelInfo: "Info",
    logLevelOther: "Other",
    latestLogs: "Latest logs",
    matchingLines: "matching lines",
    noMatchingLogs: "No matching logs"
  }
} as const;

type TextKey = keyof typeof TEXT.zh;
const I18nContext = createContext<Language>("zh");
const translate = (language: Language, key: TextKey) => TEXT[language][key] ?? TEXT.zh[key];
const useT = () => {
  const language = useContext(I18nContext);
  return useCallback((key: TextKey) => translate(language, key), [language]);
};

const navItems: Array<{ key: NavKey; labelKey: TextKey; icon: typeof Activity }> = [
  { key: "dashboard", labelKey: "navDashboard", icon: Gauge },
  { key: "hosts", labelKey: "navHosts", icon: Server },
  { key: "projects", labelKey: "navProjects", icon: Layers3 },
  { key: "runs", labelKey: "navRuns", icon: Workflow },
  { key: "config", labelKey: "navConfig", icon: Settings },
  { key: "protocol", labelKey: "navProtocol", icon: Database }
];

function App() {
  const [language, setLanguageState] = useState<Language>(() => (
    window.localStorage.getItem("expmon-language") === "zh" ? "zh" : "en"
  ));
  const [activeView, setActiveView] = useState<NavKey>("dashboard");
  const [snapshot, setSnapshot] = useState<Snapshot>({
    hosts: initialHosts,
    runs: initialRuns,
    connected: false
  });
  const [remoteHosts, setRemoteHosts] = useState<Host[]>([]);
  const [selectedRunId, setSelectedRunId] = useState(initialRuns[0]?.id ?? "");
  const [selectedHostId, setSelectedHostId] = useState(initialHosts[0].id);
  const [query, setQuery] = useState("");
  const [resourceFilter, setResourceFilter] = useState<ResourceType | "all">("all");
  const [lastRefreshAt, setLastRefreshAt] = useState(() => new Date());
  const [manualRefreshInFlight, setManualRefreshInFlight] = useState(false);
  const [operationMessage, setOperationMessage] = useState("");
  const [killInFlight, setKillInFlight] = useState("");
  const [deleteInFlight, setDeleteInFlight] = useState("");
  const [sshSaveInFlight, setSshSaveInFlight] = useState(false);
  const [sshDeleteInFlight, setSshDeleteInFlight] = useState("");
  const [metadataSaveInFlight, setMetadataSaveInFlight] = useState("");
  const [configSaveInFlight, setConfigSaveInFlight] = useState(false);
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirm | null>(null);
  const snapshotRef = useRef(snapshot);
  const remoteHostsRef = useRef(remoteHosts);
  const optimisticDeletedRunIdsRef = useRef<Set<string>>(new Set());
  const optimisticDeletedSshIdsRef = useRef<Set<string>>(new Set());
  const optimisticClearSshRef = useRef(false);
  const sshResourceInFlightRef = useRef<Set<string>>(new Set());
  const sshAutoStartedRef = useRef<Set<string>>(new Set());
  const sshServersRef = useRef<SshServer[]>([]);
  const t = useCallback((key: TextKey) => translate(language, key), [language]);
  const setLanguage = useCallback((nextLanguage: Language) => {
    setLanguageState(nextLanguage);
    window.localStorage.setItem("expmon-language", nextLanguage);
  }, []);

  useEffect(() => {
    snapshotRef.current = snapshot;
  }, [snapshot]);

  useEffect(() => {
    remoteHostsRef.current = remoteHosts;
  }, [remoteHosts]);

  const updateSnapshot = useCallback((updater: (current: Snapshot) => Snapshot) => {
    setSnapshot((current) => {
      const next = updater(current);
      snapshotRef.current = next;
      return next;
    });
  }, []);

  const updateRemoteHosts = useCallback((updater: (current: Host[]) => Host[]) => {
    setRemoteHosts((current) => {
      const next = updater(current);
      remoteHostsRef.current = next;
      return next;
    });
  }, []);

  const refreshSnapshot = useCallback(() => {
    return fetch(`${API_BASE}/api/snapshot`, { cache: "no-store" })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`collector ${response.status}`);
        }
        return response.json() as Promise<{ hosts: Host[]; runs: Run[]; projects?: Project[]; diagnostics?: Diagnostic[]; config?: CollectorConfig; configMetadata?: ConfigMetadata; sshServers?: SshServer[]; sshKeyCandidates?: string[] }>;
      })
      .then((payload) => {
        const hiddenRunIds = optimisticDeletedRunIdsRef.current;
        const hiddenSshIds = optimisticDeletedSshIdsRef.current;
        const visibleRuns = payload.runs.filter((run) => !hiddenRunIds.has(run.id));
        const visibleSshServers = optimisticClearSshRef.current
          ? []
          : (payload.sshServers ?? []).filter((server) => !hiddenSshIds.has(server.id));
        let nextSnapshot: Snapshot = {
          hosts: payload.hosts,
          runs: visibleRuns,
          projects: payload.projects ?? [],
          diagnostics: payload.diagnostics ?? [],
          connected: true,
          config: payload.config,
          configMetadata: payload.configMetadata,
          sshServers: visibleSshServers,
          sshKeyCandidates: payload.sshKeyCandidates ?? []
        };
        hiddenRunIds.forEach((runId) => {
          nextSnapshot = removeRunFromSnapshot(nextSnapshot, runId);
        });
        snapshotRef.current = nextSnapshot;
        setSnapshot(nextSnapshot);
        setLastRefreshAt(new Date());
      })
      .catch((error: Error) => {
        setSnapshot((current) => ({
          ...current,
          connected: false,
          error: error.message
        }));
        setLastRefreshAt(new Date());
      });
  }, []);

  const handleManualRefresh = useCallback(() => {
    setManualRefreshInFlight(true);
    const startedAt = window.performance.now();
    refreshSnapshot().finally(() => {
      const elapsed = window.performance.now() - startedAt;
      const remaining = Math.max(0, 520 - elapsed);
      window.setTimeout(() => setManualRefreshInFlight(false), remaining);
    });
  }, [refreshSnapshot]);

  useEffect(() => {
    refreshSnapshot();
    const timer = window.setInterval(() => {
      refreshSnapshot();
    }, REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [refreshSnapshot]);

  const requestConfirm = useCallback((config: PendingConfirm) => {
    setPendingConfirm(config);
  }, []);

  const performKillRun = useCallback((run: Run) => {
    setKillInFlight(run.id);
    setOperationMessage(language === "zh" ? "正在终止任务..." : "Killing task...");
    fetch(`${API_BASE}/api/runs/${encodeURIComponent(run.id)}/kill`, {
      method: "POST"
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.error || `collector ${response.status}`);
        }
        return payload as { terminated?: number[]; killed?: number[] };
      })
      .then((payload) => {
        const total = (payload.terminated?.length ?? 0) + (payload.killed?.length ?? 0);
        setOperationMessage(language === "zh" ? `已向 ${total} 个进程发送终止信号` : `Kill signal sent to ${total} processes`);
        refreshSnapshot();
      })
      .catch((error: Error) => {
        setOperationMessage(language === "zh" ? `终止失败：${error.message}` : `Kill failed: ${error.message}`);
      })
      .finally(() => {
        setKillInFlight("");
      });
  }, [language, refreshSnapshot]);

  const killRun = useCallback((run: Run) => {
    if (run.status !== "running") {
      setOperationMessage(language === "zh" ? "只能终止运行中的任务" : "Only running tasks can be killed");
      return;
    }
    requestConfirm({
      title: language === "zh" ? `终止任务 ${run.project}/${run.name}？` : `Kill task ${run.project}/${run.name}?`,
      body: language === "zh"
        ? `Root PID: ${run.rootPid}\n这会终止根进程及其子进程。`
        : `Root PID: ${run.rootPid}\nThis will terminate the root process and its child processes.`,
      confirmLabel: t("killTask"),
      tone: "danger",
      onConfirm: () => performKillRun(run)
    });
  }, [language, performKillRun, requestConfirm, t]);

  const performDeleteRunRecord = useCallback((run: Run) => {
    setDeleteInFlight(run.id);
    optimisticDeletedRunIdsRef.current.add(run.id);
    updateSnapshot((current) => removeRunFromSnapshot(current, run.id));
    setSelectedRunId((current) => (
      current === run.id
        ? (snapshotRef.current.runs.find((item) => item.id !== run.id)?.id ?? "")
        : current
    ));
    setOperationMessage(language === "zh" ? "任务记录已从列表移除，正在后台删除..." : "Run record hidden; deleting in the background...");
    fetch(`${API_BASE}/api/runs/${encodeURIComponent(run.id)}`, {
      method: "DELETE"
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.error || `collector ${response.status}`);
        }
        return payload as { deletedPath?: string };
      })
      .then(() => {
        optimisticDeletedRunIdsRef.current.delete(run.id);
        setOperationMessage(language === "zh" ? "任务记录已删除" : "Run record deleted");
        refreshSnapshot();
      })
      .catch((error: Error) => {
        optimisticDeletedRunIdsRef.current.delete(run.id);
        updateSnapshot((current) => restoreRunInSnapshot(current, run));
        setOperationMessage(language === "zh" ? `删除失败：${error.message}` : `Delete failed: ${error.message}`);
      })
      .finally(() => {
        setDeleteInFlight("");
      });
  }, [language, refreshSnapshot, updateSnapshot]);

  const deleteRunRecord = useCallback((run: Run) => {
    if (!canDeleteRunRecord(run)) {
      setOperationMessage(language === "zh" ? "只能删除已结束、失败或已终止的任务记录" : "Only finished, failed, or killed run records can be deleted");
      return;
    }
    requestConfirm({
      title: language === "zh" ? `删除任务记录 ${run.project}/${run.name}？` : `Delete run record ${run.project}/${run.name}?`,
      body: language === "zh"
        ? "这只会删除 ExpMon 记录和日志目录，不会终止进程。"
        : "This only deletes the ExpMon record and log directory. It will not terminate processes.",
      confirmLabel: t("deleteRecord"),
      tone: "danger",
      onConfirm: () => performDeleteRunRecord(run)
    });
  }, [language, performDeleteRunRecord, requestConfirm, t]);

  const saveSshServer = useCallback((form: SshServerForm): Promise<SshSaveResult> => {
    setSshSaveInFlight(true);
    setOperationMessage(language === "zh" ? "正在保存 SSH 服务器..." : "Saving SSH server...");
    return fetch(`${API_BASE}/api/ssh/servers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(form)
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          if (payload.test) {
            throw Object.assign(new Error(payload.error || payload.test.message || `collector ${response.status}`), {
              test: payload.test
            });
          }
          throw new Error(payload.error === "ssh server already exists"
            ? (language === "zh" ? "SSH 服务器已存在" : "SSH server already exists")
            : (payload.error || `collector ${response.status}`));
        }
        return payload as SshSaveResult;
      })
      .then((payload) => {
        setOperationMessage(language === "zh" ? "SSH 服务器已保存" : "SSH server saved");
        if (payload.server) {
          handleRemoteHostRefresh(hostFromSshServer(payload.server, payload.test, payload.test?.ok ? "initializing" : "idle"));
        }
        refreshSnapshot();
        return payload;
      })
      .catch((error: Error) => {
        setOperationMessage(language === "zh" ? `保存 SSH 服务器失败：${error.message}` : `Saving SSH server failed: ${error.message}`);
        throw error;
      })
      .finally(() => {
        setSshSaveInFlight(false);
      });
  }, [language, refreshSnapshot]);

  const performDeleteSshServer = useCallback((server: SshServer) => {
    setSshDeleteInFlight(server.id);
    optimisticDeletedSshIdsRef.current.add(server.id);
    sshAutoStartedRef.current.delete(server.id);
    sshResourceInFlightRef.current.delete(server.id);
    updateSnapshot((current) => removeSshServerFromSnapshot(current, server.id));
    updateRemoteHosts((current) => current.filter((host) => host.id !== `ssh:${server.id}`));
    if (selectedHostId === `ssh:${server.id}`) {
      setSelectedHostId(snapshotRef.current.hosts[0]?.id ?? "local");
    }
    setOperationMessage(language === "zh" ? "SSH 服务器已从列表移除，正在后台删除..." : "SSH server hidden; deleting in the background...");
    fetch(`${API_BASE}/api/ssh/servers/${encodeURIComponent(server.id)}`, {
      method: "DELETE"
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.error || `collector ${response.status}`);
        }
      })
      .then(() => {
        optimisticDeletedSshIdsRef.current.delete(server.id);
        setOperationMessage(language === "zh" ? "SSH 服务器已删除" : "SSH server deleted");
        refreshSnapshot();
      })
      .catch((error: Error) => {
        optimisticDeletedSshIdsRef.current.delete(server.id);
        updateSnapshot((current) => restoreSshServerInSnapshot(current, server));
        updateRemoteHosts((current) => (
          current.some((host) => host.id === `ssh:${server.id}`)
            ? current
            : [...current, hostFromSshServer(server)]
        ));
        setOperationMessage(language === "zh" ? `删除 SSH 服务器失败：${error.message}` : `Deleting SSH server failed: ${error.message}`);
      })
      .finally(() => {
        setSshDeleteInFlight("");
      });
  }, [language, refreshSnapshot, selectedHostId, updateRemoteHosts, updateSnapshot]);

  const deleteSshServer = useCallback((server: SshServer) => {
    const label = server.name || server.host;
    requestConfirm({
      title: language === "zh" ? `删除 SSH 服务器 ${label}？` : `Delete SSH server ${label}?`,
      body: language === "zh"
        ? "这会删除本地保存的 SSH 连接配置。"
        : "This removes the locally saved SSH connection configuration.",
      confirmLabel: t("deleteSshServer"),
      tone: "danger",
      onConfirm: () => performDeleteSshServer(server)
    });
  }, [language, performDeleteSshServer, requestConfirm, t]);

  const clearSshServers = useCallback(() => {
    requestConfirm({
      title: language === "zh" ? "清空所有 SSH 服务器？" : "Clear all SSH servers?",
      body: language === "zh"
        ? "这会删除本地保存的所有 SSH 连接配置。"
        : "This removes all locally saved SSH connection configurations.",
      confirmLabel: language === "zh" ? "清空" : "Clear all",
      tone: "danger",
      onConfirm: () => {
        const previousSshServers = snapshotRef.current.sshServers ?? [];
        const previousRemoteHosts = remoteHostsRef.current;
        optimisticClearSshRef.current = true;
        previousSshServers.forEach((server) => {
          sshAutoStartedRef.current.delete(server.id);
          sshResourceInFlightRef.current.delete(server.id);
        });
        setSshDeleteInFlight("all");
        updateSnapshot((current) => ({
          ...current,
          sshServers: []
        }));
        updateRemoteHosts((current) => current.filter((host) => !host.id.startsWith("ssh:")));
        if (selectedHostId.startsWith("ssh:")) {
          setSelectedHostId(snapshotRef.current.hosts[0]?.id ?? "local");
        }
        setOperationMessage(language === "zh" ? "SSH 服务器已从列表清空，正在后台删除..." : "SSH servers hidden; clearing in the background...");
        fetch(`${API_BASE}/api/ssh/servers`, { method: "DELETE" })
          .then(async (response) => {
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
              throw new Error(payload.error || `collector ${response.status}`);
            }
          })
          .then(() => {
            optimisticClearSshRef.current = false;
            setOperationMessage(language === "zh" ? "SSH 服务器已清空" : "SSH servers cleared");
            refreshSnapshot();
          })
          .catch((error: Error) => {
            optimisticClearSshRef.current = false;
            updateSnapshot((current) => ({
              ...current,
              sshServers: previousSshServers
            }));
            updateRemoteHosts(() => previousRemoteHosts);
            setOperationMessage(language === "zh" ? `清空 SSH 服务器失败：${error.message}` : `Clearing SSH servers failed: ${error.message}`);
          })
          .finally(() => setSshDeleteInFlight(""));
      }
    });
  }, [language, refreshSnapshot, requestConfirm, selectedHostId, updateRemoteHosts, updateSnapshot]);

  const saveRunMetadata = useCallback((run: Run, patch: Partial<RunMetadata>) => {
    setMetadataSaveInFlight(run.id);
    setOperationMessage(language === "zh" ? "正在保存任务备注..." : "Saving run metadata...");
    fetch(`${API_BASE}/api/runs/${encodeURIComponent(run.id)}/metadata`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch)
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.error || `collector ${response.status}`);
        }
      })
      .then(() => {
        setOperationMessage(language === "zh" ? "任务备注已保存" : "Run metadata saved");
        refreshSnapshot();
      })
      .catch((error: Error) => {
        setOperationMessage(language === "zh" ? `保存备注失败：${error.message}` : `Saving metadata failed: ${error.message}`);
      })
      .finally(() => {
        setMetadataSaveInFlight("");
      });
  }, [language, refreshSnapshot]);

  const saveCollectorConfig = useCallback((config: CollectorConfig) => {
    setConfigSaveInFlight(true);
    setOperationMessage(language === "zh" ? "正在保存采集器配置..." : "Saving collector config...");
    fetch(`${API_BASE}/api/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ config })
    })
      .then((response) => response.json().then((payload) => ({ response, payload })))
      .then(({ response, payload }) => {
        if (!response.ok || !payload.ok) {
          throw new Error(payload.error || `collector ${response.status}`);
        }
        setSnapshot((current) => ({
          ...current,
          config: payload.config,
          configMetadata: payload.metadata
        }));
        setOperationMessage(language === "zh" ? "采集器配置已保存" : "Collector config saved");
        refreshSnapshot();
      })
      .catch((error: Error) => {
        setOperationMessage(language === "zh" ? `保存配置失败：${error.message}` : `Saving config failed: ${error.message}`);
      })
      .finally(() => setConfigSaveInFlight(false));
  }, [language, refreshSnapshot]);

  const handleRemoteHostRefresh = useCallback((host: Host, navigate = true, preserveExisting = false) => {
    updateRemoteHosts((current) => {
      const existing = current.find((item) => item.id === host.id);
      const nextHost = preserveExisting && existing
        ? {
            ...existing,
            warnings: host.warnings.length ? host.warnings : existing.warnings,
          }
        : host;
      const next = current.filter((item) => item.id !== host.id);
      return [...next, nextHost];
    });
    if (navigate) {
      setSelectedHostId(host.id);
      setActiveView("hosts");
    }
  }, [updateRemoteHosts]);

  const refreshSshServerResources = useCallback((server: SshServer, markInitializing = false) => {
    if (sshResourceInFlightRef.current.has(server.id)) {
      return;
    }
    sshResourceInFlightRef.current.add(server.id);
    if (markInitializing) {
      handleRemoteHostRefresh(hostFromSshServer(server, undefined, "initializing"), false);
    }
    fetch(`${API_BASE}/api/ssh/servers/${encodeURIComponent(server.id)}/resources`, {
      method: "POST"
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.error || `collector ${response.status}`);
        }
        return payload as SshTestResult;
      })
      .then((payload) => {
        if (payload.ok && payload.host) {
          handleRemoteHostRefresh(payload.host, false);
        } else {
          handleRemoteHostRefresh(hostFromSshServer(server, payload, "failed"), false, true);
        }
      })
      .catch((error: Error) => {
        handleRemoteHostRefresh(hostFromSshServer(server, { ok: false, error: error.message, message: error.message }, "failed"), false, true);
      })
      .finally(() => {
        sshResourceInFlightRef.current.delete(server.id);
      });
  }, [handleRemoteHostRefresh]);

  useEffect(() => {
    const servers = snapshot.sshServers ?? [];
    sshServersRef.current = servers;
    const activeIds = new Set(servers.map((server) => server.id));
    Array.from(sshAutoStartedRef.current).forEach((serverId) => {
      if (!activeIds.has(serverId)) {
        sshAutoStartedRef.current.delete(serverId);
      }
    });
    servers.forEach((server) => {
      if (!sshAutoStartedRef.current.has(server.id)) {
        sshAutoStartedRef.current.add(server.id);
        refreshSshServerResources(server, true);
      }
    });
  }, [refreshSshServerResources, snapshot.sshServers]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      sshServersRef.current.forEach((server) => refreshSshServerResources(server, false));
    }, REFRESH_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [refreshSshServerResources]);

  const hosts = useMemo(() => {
    const merged = [...snapshot.hosts];
    const savedSshServers = snapshot.sshServers ?? [];
    savedSshServers.forEach((server) => {
      const host = hostFromSshServer(server);
      const index = merged.findIndex((item) => item.id === host.id);
      if (index >= 0) {
        merged[index] = host;
      } else {
        merged.push(host);
      }
    });
    const savedSshHostIds = new Set(savedSshServers.map((server) => `ssh:${server.id}`));
    remoteHosts.forEach((remoteHost) => {
      if (remoteHost.id.startsWith("ssh:") && !savedSshHostIds.has(remoteHost.id)) {
        return;
      }
      const index = merged.findIndex((host) => host.id === remoteHost.id);
      if (index >= 0) {
        merged[index] = remoteHost;
      } else {
        merged.push(remoteHost);
      }
    });
    return merged;
  }, [remoteHosts, snapshot.hosts, snapshot.sshServers]);
  const runs = snapshot.runs;
  useEffect(() => {
    if (runs.length && !runs.some((run) => run.id === selectedRunId)) {
      setSelectedRunId(runs[0].id);
    }
    if (hosts.length && !hosts.some((host) => host.id === selectedHostId)) {
      setSelectedHostId(hosts[0].id);
    }
  }, [hosts, runs, selectedHostId, selectedRunId]);
  const selectedRun = runs.find((run) => run.id === selectedRunId);
  const selectedHost = hosts.find((host) => host.id === selectedHostId) ?? hosts[0];
  const filteredRuns = useMemo(() => {
    return runs.filter((run) => {
      const host = hosts.find((item) => item.id === run.hostId);
      const text = [run.project, run.name, run.command, host?.name, run.tags.join(" ")]
        .join(" ")
        .toLowerCase();
      const matchesQuery = text.includes(query.toLowerCase());
      const matchesResource = resourceFilter === "all" || run.resourceType === resourceFilter;
      return matchesQuery && matchesResource;
    });
  }, [hosts, query, resourceFilter, runs]);

  return (
    <I18nContext.Provider value={language}>
      <div className="app-shell">
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-mark">
              <Activity size={22} />
            </div>
            <div>
              <strong>ExpMon</strong>
              <span>{t("appSubtitle")}</span>
            </div>
          </div>
          <nav className="nav-list" aria-label="main navigation">
            {navItems.map((item) => {
              const Icon = item.icon;
              const label = t(item.labelKey);
              return (
                <button
                  key={item.key}
                  className={activeView === item.key ? "nav-item active" : "nav-item"}
                  onClick={() => setActiveView(item.key)}
                  title={label}
                >
                  <Icon size={18} />
                  <span>{label}</span>
                </button>
              );
            })}
          </nav>
          <div className="collector-card">
            <div className="collector-row">
              <span>Collector</span>
              <strong>{snapshot.connected ? t("localLive") : t("offline")}</strong>
            </div>
            <div className="collector-pulse">
              <span />
              <span />
              <span />
              <span />
              <span />
            </div>
          </div>
        </aside>

        <main className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">{t("eyebrow")}</p>
            <h1>{viewTitle(activeView, t)}</h1>
          </div>
          <div className="topbar-actions">
            <div className="search-box">
              <Search size={16} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder={t("searchPlaceholder")}
              />
            </div>
            <div className="language-toggle" aria-label={t("language")}>
              <button className={language === "en" ? "active" : ""} onClick={() => setLanguage("en")}>EN</button>
              <button className={language === "zh" ? "active" : ""} onClick={() => setLanguage("zh")}>中文</button>
            </div>
            <button
              className={`icon-button refresh-button${manualRefreshInFlight ? " is-refreshing" : ""}`}
              title={t("refresh")}
              aria-label={t("refresh")}
              aria-busy={manualRefreshInFlight}
              onClick={handleManualRefresh}
            >
              <RefreshCw size={17} />
            </button>
            <span className="refresh-indicator">
              {snapshot.connected ? t("collectorLive") : `${t("collectorOffline")}${snapshot.error ? `: ${snapshot.error}` : ""}`} · {formatClock(lastRefreshAt)}
            </span>
          </div>
        </header>

        {activeView === "dashboard" && (
          <Dashboard
            hosts={hosts}
            runs={runs}
            diagnostics={snapshot.diagnostics ?? []}
            onOpenHost={(hostId) => {
              setSelectedHostId(hostId);
              setActiveView("hosts");
            }}
            onOpenRun={(runId) => {
              setSelectedRunId(runId);
              setActiveView("detail");
            }}
          />
        )}
        {activeView === "hosts" && (
          <HostsView
            hosts={hosts}
            runs={runs}
            selectedHost={selectedHost}
            sshServers={snapshot.sshServers ?? []}
            sshKeyCandidates={snapshot.sshKeyCandidates ?? []}
            onSelectHost={setSelectedHostId}
            onSaveSshServer={saveSshServer}
            onDeleteSshServer={deleteSshServer}
            onClearSshServers={clearSshServers}
            onRemoteHostRefresh={handleRemoteHostRefresh}
            sshSaveInFlight={sshSaveInFlight}
            sshDeleteInFlight={sshDeleteInFlight}
          />
        )}
        {activeView === "runs" && (
          <RunsView
            runs={filteredRuns}
            hosts={hosts}
            config={snapshot.config}
            resourceFilter={resourceFilter}
            onResourceFilter={setResourceFilter}
            onOpenRun={(runId) => {
              setSelectedRunId(runId);
              setActiveView("detail");
            }}
            onDeleteRun={deleteRunRecord}
            deleteInFlight={deleteInFlight}
          />
        )}
        {activeView === "projects" && (
          <ProjectsView
            projects={snapshot.projects ?? []}
            runs={runs}
            hosts={hosts}
            onOpenRun={(runId) => {
              setSelectedRunId(runId);
              setActiveView("detail");
            }}
            requestConfirm={requestConfirm}
          />
        )}
        {activeView === "detail" && (
          <RunDetail
            run={selectedRun}
            runs={runs}
            hosts={hosts}
            onSelectRun={setSelectedRunId}
            onBackToRuns={() => setActiveView("runs")}
            onKillRun={killRun}
            onDeleteRun={deleteRunRecord}
            onSaveMetadata={saveRunMetadata}
            killInFlight={killInFlight}
            deleteInFlight={deleteInFlight}
            metadataSaveInFlight={metadataSaveInFlight}
            operationMessage={operationMessage}
          />
        )}
        {activeView === "config" && (
          <ConfigView
            config={snapshot.config}
            metadata={snapshot.configMetadata}
            saving={configSaveInFlight}
            operationMessage={operationMessage}
            onSave={saveCollectorConfig}
          />
        )}
        {activeView === "protocol" && <ProtocolView />}
        </main>
      </div>
      {pendingConfirm && (
        <ConfirmDialog
          title={pendingConfirm.title}
          body={pendingConfirm.body}
          confirmLabel={pendingConfirm.confirmLabel || t("confirm")}
          cancelLabel={t("cancel")}
          tone={pendingConfirm.tone ?? "default"}
          onCancel={() => setPendingConfirm(null)}
          onConfirm={() => {
            const action = pendingConfirm.onConfirm;
            setPendingConfirm(null);
            action();
          }}
        />
      )}
    </I18nContext.Provider>
  );
}

function ConfirmDialog({
  title,
  body,
  confirmLabel,
  cancelLabel,
  tone,
  onCancel,
  onConfirm
}: {
  title: string;
  body: string;
  confirmLabel: string;
  cancelLabel: string;
  tone: ConfirmTone;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onCancel();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onCancel]);

  return (
    <div className="confirm-overlay" role="presentation" onMouseDown={onCancel}>
      <section
        className="confirm-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className={`confirm-icon ${tone}`}>
          {tone === "danger" ? <AlertTriangle size={20} /> : <Activity size={20} />}
        </div>
        <div className="confirm-content">
          <h2 id="confirm-dialog-title">{title}</h2>
          <p>{body}</p>
        </div>
        <div className="confirm-actions">
          <button className="action-button" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button className={tone === "danger" ? "action-button danger-action" : "action-button active-action"} onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}

function viewTitle(view: NavKey, t: (key: TextKey) => string) {
  switch (view) {
    case "dashboard":
      return t("titleDashboard");
    case "hosts":
      return t("titleHosts");
    case "projects":
      return t("titleProjects");
    case "runs":
      return t("titleRuns");
    case "detail":
      return t("titleDetail");
    case "config":
      return t("titleConfig");
    case "protocol":
      return t("titleProtocol");
  }
}

type DraggableCardProps = {
  draggable: false;
  "data-draggable-card": "true";
  "data-draggable-card-id": string;
  "data-draggable-card-group": string;
  "data-dragging"?: "true";
  "data-drag-over"?: "true";
  onClickCapture: (event: MouseEvent<HTMLElement>) => void;
};

type DragPreview = {
  element: HTMLElement;
  offsetX: number;
  offsetY: number;
  width: number;
  height: number;
  bounds: {
    left: number;
    top: number;
    right: number;
    bottom: number;
  };
};

function readStoredOrder(storageKey: string) {
  try {
    const raw = window.localStorage.getItem(storageKey);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((item): item is string => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function sameStringArray(left: string[], right: string[]) {
  return left.length === right.length && left.every((item, index) => item === right[index]);
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), Math.max(min, max));
}

function usePersistentCardOrder<T>(
  storageKey: string,
  items: T[],
  getId: (item: T) => string
) {
  const itemIds = useMemo(() => items.map(getId), [getId, items]);
  const itemIdsKey = itemIds.join("|");
  const [orderedIds, setOrderedIds] = useState<string[]>(() => readStoredOrder(storageKey));
  const [draggingId, setDraggingId] = useState("");
  const [dragOverId, setDragOverId] = useState("");
  const suppressNextClickRef = useRef(false);
  const dragSourceIdRef = useRef("");
  const lastReorderTargetRef = useRef("");
  const dragPreviewRef = useRef<DragPreview | null>(null);

  const removeDragPreview = useCallback(() => {
    dragPreviewRef.current?.element.remove();
    dragPreviewRef.current = null;
    document.body.classList.remove("is-card-dragging");
  }, []);

  const updateDragPreview = useCallback((clientX: number, clientY: number) => {
    const preview = dragPreviewRef.current;
    if (!preview) {
      return;
    }
    const left = clampNumber(
      clientX - preview.offsetX,
      preview.bounds.left,
      preview.bounds.right - preview.width
    );
    const top = clampNumber(
      clientY - preview.offsetY,
      preview.bounds.top,
      preview.bounds.bottom - preview.height
    );
    preview.element.style.left = `${left}px`;
    preview.element.style.top = `${top}px`;
  }, []);

  const createDragPreview = useCallback((card: HTMLElement, clientX: number, clientY: number) => {
    removeDragPreview();

    const cardRect = card.getBoundingClientRect();
    const panelRect = (card.closest<HTMLElement>(".panel") ?? card.parentElement ?? card).getBoundingClientRect();
    const preview = card.cloneNode(true) as HTMLElement;
    preview.classList.add("drag-card-preview");
    preview.setAttribute("data-drag-preview", "true");
    preview.removeAttribute("data-dragging");
    preview.removeAttribute("data-drag-over");
    preview.style.position = "fixed";
    preview.style.left = `${cardRect.left}px`;
    preview.style.top = `${cardRect.top}px`;
    preview.style.width = `${cardRect.width}px`;
    preview.style.height = `${cardRect.height}px`;
    preview.style.margin = "0";
    preview.style.boxSizing = "border-box";
    preview.style.pointerEvents = "none";
    preview.style.zIndex = "10000";
    document.body.appendChild(preview);
    document.body.classList.add("is-card-dragging");

    dragPreviewRef.current = {
      element: preview,
      offsetX: clientX - cardRect.left,
      offsetY: clientY - cardRect.top,
      width: cardRect.width,
      height: cardRect.height,
      bounds: {
        left: panelRect.left,
        top: panelRect.top,
        right: panelRect.right,
        bottom: panelRect.bottom,
      },
    };
    updateDragPreview(clientX, clientY);
  }, [removeDragPreview, updateDragPreview]);

  const clearDragState = useCallback(() => {
    setDragOverId("");
    setDraggingId("");
    dragSourceIdRef.current = "";
    lastReorderTargetRef.current = "";
    removeDragPreview();
  }, [removeDragPreview]);

  useEffect(() => {
    window.addEventListener("pointerup", clearDragState);
    window.addEventListener("pointercancel", clearDragState);
    window.addEventListener("mouseup", clearDragState);
    return () => {
      window.removeEventListener("pointerup", clearDragState);
      window.removeEventListener("pointercancel", clearDragState);
      window.removeEventListener("mouseup", clearDragState);
    };
  }, [clearDragState]);

  useEffect(() => {
    setOrderedIds((current) => {
      const known = current.filter((id) => itemIds.includes(id));
      const appended = itemIds.filter((id) => !known.includes(id));
      const next = [...known, ...appended];
      return sameStringArray(current, next) ? current : next;
    });
  }, [itemIdsKey]);

  useEffect(() => {
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(orderedIds));
    } catch {
      // localStorage can be unavailable in restricted browser modes.
    }
  }, [orderedIds, storageKey]);

  const orderedItems = useMemo(() => {
    const rank = new Map(orderedIds.map((id, index) => [id, index]));
    return [...items].sort((left, right) => {
      const leftRank = rank.get(getId(left)) ?? Number.MAX_SAFE_INTEGER;
      const rightRank = rank.get(getId(right)) ?? Number.MAX_SAFE_INTEGER;
      return leftRank - rightRank;
    });
  }, [getId, items, orderedIds]);

  const moveCard = useCallback((sourceId: string, targetId: string) => {
    if (!sourceId || sourceId === targetId) {
      return;
    }
    setOrderedIds((current) => {
      const known = current.filter((item) => itemIds.includes(item));
      const base = [...known, ...itemIds.filter((item) => !known.includes(item))];
      const sourceIndex = base.indexOf(sourceId);
      const targetIndex = base.indexOf(targetId);
      if (sourceIndex < 0 || targetIndex < 0) {
        return current;
      }
      const next = [...base];
      const [moved] = next.splice(sourceIndex, 1);
      next.splice(targetIndex, 0, moved);
      suppressNextClickRef.current = true;
      return next;
    });
  }, [itemIds]);

  const findCardElementAtPoint = useCallback((clientX: number, clientY: number) => {
    for (const element of document.elementsFromPoint(clientX, clientY)) {
      if (!(element instanceof HTMLElement)) {
        continue;
      }
      const card = element.closest<HTMLElement>("[data-draggable-card-id]");
      const targetId = card?.dataset.draggableCardId;
      if (
        targetId
        && itemIds.includes(targetId)
        && card?.dataset.draggableCardGroup === storageKey
      ) {
        return card;
      }
    }
    return null;
  }, [itemIds, storageKey]);

  const findCardIdAtPoint = useCallback((clientX: number, clientY: number) => {
    return findCardElementAtPoint(clientX, clientY)?.dataset.draggableCardId ?? "";
  }, [findCardElementAtPoint]);

  const shouldIgnoreGlobalDragStart = useCallback((event: globalThis.MouseEvent | globalThis.PointerEvent, card: HTMLElement) => {
    const target = event.target instanceof HTMLElement ? event.target : null;
    const interactive = target?.closest("button, input, select, textarea, a");
    return Boolean(interactive && interactive !== card);
  }, []);

  const startCardDrag = useCallback((id: string, card: HTMLElement, clientX: number, clientY: number) => {
    dragSourceIdRef.current = id;
    lastReorderTargetRef.current = "";
    setDraggingId(id);
    createDragPreview(card, clientX, clientY);
  }, [createDragPreview]);

  const handleGlobalPointerDown = useCallback((event: globalThis.PointerEvent) => {
    if (event.button !== 0) {
      return;
    }
    const card = findCardElementAtPoint(event.clientX, event.clientY);
    const id = card?.dataset.draggableCardId;
    if (!card || !id || shouldIgnoreGlobalDragStart(event, card)) {
      return;
    }
    startCardDrag(id, card, event.clientX, event.clientY);
  }, [findCardElementAtPoint, shouldIgnoreGlobalDragStart, startCardDrag]);

  const handleGlobalMouseDown = useCallback((event: globalThis.MouseEvent) => {
    if (event.button !== 0) {
      return;
    }
    const card = findCardElementAtPoint(event.clientX, event.clientY);
    const id = card?.dataset.draggableCardId;
    if (!card || !id || shouldIgnoreGlobalDragStart(event, card)) {
      return;
    }
    startCardDrag(id, card, event.clientX, event.clientY);
  }, [findCardElementAtPoint, shouldIgnoreGlobalDragStart, startCardDrag]);

  useEffect(() => {
    window.addEventListener("pointerdown", handleGlobalPointerDown);
    window.addEventListener("mousedown", handleGlobalMouseDown);
    return () => {
      window.removeEventListener("pointerdown", handleGlobalPointerDown);
      window.removeEventListener("mousedown", handleGlobalMouseDown);
    };
  }, [handleGlobalMouseDown, handleGlobalPointerDown]);

  const handlePointerMove = useCallback((event: globalThis.PointerEvent) => {
    const sourceId = dragSourceIdRef.current;
    if (!sourceId) {
      return;
    }
    updateDragPreview(event.clientX, event.clientY);
    const targetId = findCardIdAtPoint(event.clientX, event.clientY);
    if (!targetId || targetId === sourceId) {
      lastReorderTargetRef.current = "";
      setDragOverId("");
      return;
    }
    if (lastReorderTargetRef.current === targetId) {
      return;
    }
    lastReorderTargetRef.current = targetId;
    setDragOverId(targetId);
    moveCard(sourceId, targetId);
  }, [findCardIdAtPoint, moveCard, updateDragPreview]);

  useEffect(() => {
    window.addEventListener("pointermove", handlePointerMove);
    return () => window.removeEventListener("pointermove", handlePointerMove);
  }, [handlePointerMove]);

  const handleMouseMove = useCallback((event: globalThis.MouseEvent) => {
    const sourceId = dragSourceIdRef.current;
    if (!sourceId) {
      return;
    }
    updateDragPreview(event.clientX, event.clientY);
    const targetId = findCardIdAtPoint(event.clientX, event.clientY);
    if (!targetId || targetId === sourceId) {
      lastReorderTargetRef.current = "";
      setDragOverId("");
      return;
    }
    if (lastReorderTargetRef.current === targetId) {
      return;
    }
    lastReorderTargetRef.current = targetId;
    setDragOverId(targetId);
    moveCard(sourceId, targetId);
  }, [findCardIdAtPoint, moveCard, updateDragPreview]);

  useEffect(() => {
    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, [handleMouseMove]);

  useEffect(() => removeDragPreview, [removeDragPreview]);

  const dragPropsFor = useCallback((id: string): DraggableCardProps => ({
    draggable: false,
    "data-draggable-card": "true",
    "data-draggable-card-id": id,
    "data-draggable-card-group": storageKey,
    "data-dragging": draggingId === id ? "true" : undefined,
    "data-drag-over": dragOverId === id ? "true" : undefined,
    onClickCapture: (event) => {
      if (!suppressNextClickRef.current) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      suppressNextClickRef.current = false;
    },
  }), [dragOverId, draggingId, storageKey]);

  return { orderedItems, dragPropsFor };
}

function Dashboard({
  hosts,
  runs,
  diagnostics,
  onOpenHost,
  onOpenRun
}: {
  hosts: Host[];
  runs: Run[];
  diagnostics: Diagnostic[];
  onOpenHost: (hostId: string) => void;
  onOpenRun: (runId: string) => void;
}) {
  const t = useT();
  const language = useContext(I18nContext);
  const totals = useMemo(() => {
    const totalGpus = hosts.reduce((sum, host) => sum + host.gpusTotal, 0);
    const busyGpus = hosts.reduce((sum, host) => sum + host.gpusBusy, 0);
    return {
      hosts: hosts.length,
      totalGpus,
      busyGpus,
      idleGpus: totalGpus - busyGpus,
      cpuAvg: Math.round(avg(hosts.map((host) => host.cpuUsage))),
      memoryAvg: Math.round(avg(hosts.map((host) => memoryUsagePercent(host)))),
      runningRuns: runs.filter((run) => run.status === "running").length,
      cpuOnly: runs.filter((run) => run.resourceType === "cpu_only").length,
      gpu: runs.filter((run) => run.resourceType === "gpu").length,
      hybrid: runs.filter((run) => run.resourceType === "hybrid").length,
      unmanaged: runs.filter((run) => run.status === "unmanaged").length,
      warnings: hosts.reduce((sum, host) => sum + host.warnings.length, 0)
    };
  }, [hosts, runs]);

  const activeRuns = useMemo(() => runs.filter((run) => run.status === "running"), [runs]);
  const hostOrderId = useCallback((host: Host) => host.id, []);
  const runOrderId = useCallback((run: Run) => run.id, []);
  const { orderedItems: orderedHostMix, dragPropsFor: hostMixDragProps } = usePersistentCardOrder(
    "expmon.order.dashboard.hostMix",
    hosts,
    hostOrderId
  );
  const { orderedItems: orderedDashboardHosts, dragPropsFor: dashboardHostDragProps } = usePersistentCardOrder(
    "expmon.order.dashboard.hosts",
    hosts,
    hostOrderId
  );
  const { orderedItems: orderedActiveRuns, dragPropsFor: activeRunDragProps } = usePersistentCardOrder(
    "expmon.order.dashboard.activeRuns",
    activeRuns,
    runOrderId
  );

  return (
    <section className="view-stack">
      <div className="metric-grid">
        <MetricCard icon={Server} label={t("hosts")} value={totals.hosts} accent="cyan" />
        <MetricCard icon={Zap} label={t("busyGpus")} value={`${totals.busyGpus}/${totals.totalGpus}`} accent="blue" />
        <MetricCard icon={Cpu} label={t("cpuAvg")} value={`${totals.cpuAvg}%`} accent="amber" />
        <MetricCard icon={MemoryStick} label={t("memoryAvg")} value={`${totals.memoryAvg}%`} accent="rose" />
        <MetricCard icon={Play} label={t("runningRuns")} value={totals.runningRuns} accent="green" />
        <MetricCard icon={Workflow} label="CPU-only / GPU / Hybrid" value={`${totals.cpuOnly}/${totals.gpu}/${totals.hybrid}`} accent="violet" />
        <MetricCard icon={AlertTriangle} label={t("statusUnmanaged")} value={totals.unmanaged} accent="amber" />
        <MetricCard icon={AlertTriangle} label={t("warnings")} value={totals.warnings} accent="rose" />
      </div>

      <ResourceOverview host={hosts[0]} />

      <div className="dashboard-top">
        <div className="panel host-mix-panel">
          <PanelTitle icon={BarChart3} title={t("hostResourceMix")} />
          <div className="host-mix-list">
            {orderedHostMix.map((host) => (
              <button key={host.id} className="host-mix-card" onClick={() => onOpenHost(host.id)} {...hostMixDragProps(host.id)}>
                <div className="host-mix-head">
                  <strong>{displayHostName(host, t)}</strong>
                  <span>{host.runningRuns} {t("runningSuffix")}</span>
                </div>
                <div className="host-mix-meter-grid">
                  {hostMixRows(host, t).map((row) => (
                    <div key={row.label} className={`host-mix-meter ${row.accent}`}>
                      <div>
                        <span>{row.label}</span>
                        <strong>{row.detail}</strong>
                      </div>
                      <i><b style={{ width: `${clampPercent(row.value)}%` }} /></i>
                    </div>
                  ))}
                </div>
              </button>
            ))}
          </div>
        </div>

        <div className="panel dashboard-host-panel">
          <PanelTitle icon={Server} title={t("hosts")} />
          <div className="dashboard-host-grid">
            {orderedDashboardHosts.map((host) => (
              <button key={host.id} className="host-tile" onClick={() => onOpenHost(host.id)} {...dashboardHostDragProps(host.id)}>
                <div className="host-tile-top">
                  <span>{displayHostName(host, t)}</span>
                  {host.warnings.length ? <AlertTriangle size={16} /> : <Activity size={16} />}
                </div>
                <div className="host-readouts">
                  <Readout label="CPU" value={`${host.cpuUsage}%`} />
                  <Readout label={t("memoryLabel")} value={formatMemory(host, t)} />
                  <Readout label="GPU" value={formatGpu(host, t)} />
                  <Readout label={t("runsLabel")} value={`${host.runningRuns} ${t("runningSuffix")}`} />
                </div>
                <div className="warning-line">{formatHostWarning(host.warnings[0], t) ?? t("normal")}</div>
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="dashboard-bottom">
        <div className="panel run-queue">
          <PanelTitle icon={Workflow} title={t("activeRuns")} />
          <div className="run-stack">
            {orderedActiveRuns.length ? orderedActiveRuns.map((run) => (
              <button key={run.id} className="run-strip" onClick={() => onOpenRun(run.id)} {...activeRunDragProps(run.id)}>
                <span className={`status-dot ${run.status}`} />
                <span>
                  <strong>{run.project}</strong>
                  <small>{run.name}</small>
                </span>
                <ResourceBadge type={run.resourceType} />
                <em>{run.cpuPercent}% CPU · {formatGpuRunUsage(run, t)}</em>
              </button>
            )) : (
              <EmptyPanel
                title={t("noExperimentTasks")}
                body={t("noExperimentTasksBody")}
              />
            )}
          </div>
        </div>

        <div className="panel run-queue">
          <PanelTitle icon={AlertTriangle} title={language === "zh" ? "洞察" : "Insights"} />
          <DiagnosticList diagnostics={diagnostics} onOpenRun={onOpenRun} />
        </div>
      </div>
    </section>
  );
}

const CONFIG_TEXT = {
  zh: {
    title: "本地采集器配置",
    storage: "配置文件",
    envConfig: "由 EXPMON_CONFIG 指定",
    defaultLocal: "本地配置文件",
    writable: "可写",
    readOnly: "不可写",
    hostId: "Host ID",
    interval: "刷新间隔（秒）",
    unmanagedTop: "未托管进程上限",
    experimentRoots: "实验项目根目录",
    includeCwd: "自动发现 cwd 范围",
    protocolRoots: "受管任务扫描目录",
    includeKeywords: "命令包含关键词",
    excludeKeywords: "命令排除关键词",
    explicitRules: "显式解析规则 (JSON)",
    save: "保存配置",
    saving: "保存中",
    onePerLine: "每行一个值",
    jsonError: "显式解析规则必须是 JSON 数组",
    savedHint: "保存后采集器会立即按新配置刷新；真实本地路径会写入被 gitignore 忽略的配置文件。"
  },
  en: {
    title: "Local collector config",
    storage: "Config file",
    envConfig: "set by EXPMON_CONFIG",
    defaultLocal: "local config file",
    writable: "writable",
    readOnly: "read-only",
    hostId: "Host ID",
    interval: "Refresh interval (seconds)",
    unmanagedTop: "Unmanaged process limit",
    experimentRoots: "Experiment project roots",
    includeCwd: "Auto-discovery cwd roots",
    protocolRoots: "Managed run scan roots",
    includeKeywords: "Command include keywords",
    excludeKeywords: "Command exclude keywords",
    explicitRules: "Explicit parser rules (JSON)",
    save: "Save Config",
    saving: "Saving",
    onePerLine: "One value per line",
    jsonError: "explicit rules must be a JSON array",
    savedHint: "After saving, the collector refreshes with the new config. Real local paths are written to a gitignored local config file."
  }
} as const;

const linesToArray = (value: string) => (
  value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean)
);

const arrayToLines = (value?: string[]) => (value ?? []).join("\n");

const configFingerprint = (config?: CollectorConfig) => JSON.stringify(config ?? {});

function removeRunFromSnapshot(current: Snapshot, runId: string): Snapshot {
  return {
    ...current,
    runs: current.runs.filter((run) => run.id !== runId),
    projects: current.projects?.map((project) => ({
      ...project,
      runs: project.runs.filter((id) => id !== runId)
    })),
    diagnostics: current.diagnostics?.filter((item) => item.runId !== runId)
  };
}

function restoreRunInSnapshot(current: Snapshot, run: Run): Snapshot {
  if (current.runs.some((item) => item.id === run.id)) {
    return current;
  }
  return {
    ...current,
    runs: [run, ...current.runs],
    projects: current.projects?.map((project) => (
      project.name === run.project && !project.runs.includes(run.id)
        ? { ...project, runs: [run.id, ...project.runs] }
        : project
    ))
  };
}

function removeSshServerFromSnapshot(current: Snapshot, serverId: string): Snapshot {
  return {
    ...current,
    sshServers: (current.sshServers ?? []).filter((server) => server.id !== serverId)
  };
}

function restoreSshServerInSnapshot(current: Snapshot, server: SshServer): Snapshot {
  if ((current.sshServers ?? []).some((item) => item.id === server.id)) {
    return current;
  }
  return {
    ...current,
    sshServers: [server, ...(current.sshServers ?? [])]
  };
}

function ConfigView({
  config,
  metadata,
  saving,
  operationMessage,
  onSave
}: {
  config?: CollectorConfig;
  metadata?: ConfigMetadata;
  saving: boolean;
  operationMessage: string;
  onSave: (config: CollectorConfig) => void;
}) {
  const language = useContext(I18nContext);
  const labels = CONFIG_TEXT[language];
  const [hostId, setHostId] = useState(config?.host_id ?? "local");
  const [interval, setIntervalValue] = useState(String(config?.sampling?.interval_seconds ?? 3));
  const [unmanagedTop, setUnmanagedTop] = useState(String(config?.sampling?.unmanaged_top_n ?? 80));
  const [experimentRoots, setExperimentRoots] = useState(arrayToLines(config?.experiment_roots));
  const [includeCwd, setIncludeCwd] = useState(arrayToLines(config?.run_discovery?.include_cwd_under));
  const [protocolRoots, setProtocolRoots] = useState(arrayToLines(config?.protocol?.scan_roots));
  const [includeKeywords, setIncludeKeywords] = useState(arrayToLines(config?.run_discovery?.include_command_keywords));
  const [excludeKeywords, setExcludeKeywords] = useState(arrayToLines(config?.run_discovery?.exclude_command_keywords));
  const [rulesJson, setRulesJson] = useState(JSON.stringify(config?.run_discovery?.explicit_rules ?? [], null, 2));
  const [error, setError] = useState("");
  const [dirty, setDirty] = useState(false);
  const [syncedFingerprint, setSyncedFingerprint] = useState(configFingerprint(config));

  useEffect(() => {
    if (dirty) {
      return;
    }
    const nextFingerprint = configFingerprint(config);
    setHostId(config?.host_id ?? "local");
    setIntervalValue(String(config?.sampling?.interval_seconds ?? 3));
    setUnmanagedTop(String(config?.sampling?.unmanaged_top_n ?? 80));
    setExperimentRoots(arrayToLines(config?.experiment_roots));
    setIncludeCwd(arrayToLines(config?.run_discovery?.include_cwd_under));
    setProtocolRoots(arrayToLines(config?.protocol?.scan_roots));
    setIncludeKeywords(arrayToLines(config?.run_discovery?.include_command_keywords));
    setExcludeKeywords(arrayToLines(config?.run_discovery?.exclude_command_keywords));
    setRulesJson(JSON.stringify(config?.run_discovery?.explicit_rules ?? [], null, 2));
    setSyncedFingerprint(nextFingerprint);
  }, [config, dirty, syncedFingerprint]);

  const updateField = (setter: (value: string) => void) => (value: string) => {
    setDirty(true);
    setter(value);
  };

  const submit = () => {
    let explicitRules: Array<{ name?: string; project?: string; command_regex?: string }> = [];
    try {
      const parsed = JSON.parse(rulesJson || "[]");
      if (!Array.isArray(parsed)) {
        throw new Error(labels.jsonError);
      }
      explicitRules = parsed;
    } catch {
      setError(labels.jsonError);
      return;
    }
    setError("");
    onSave({
      host_id: hostId.trim() || "local",
      sampling: {
        interval_seconds: Number(interval) || 3,
        unmanaged_top_n: Number(unmanagedTop) || 80
      },
      experiment_roots: linesToArray(experimentRoots),
      run_discovery: {
        include_cwd_under: linesToArray(includeCwd),
        include_command_keywords: linesToArray(includeKeywords),
        exclude_command_keywords: linesToArray(excludeKeywords),
        explicit_rules: explicitRules
      },
      protocol: {
        scan_roots: linesToArray(protocolRoots),
        max_scan_depth: config?.protocol?.max_scan_depth ?? 5,
        max_metric_points: config?.protocol?.max_metric_points ?? 120
      }
    });
  };

  return (
    <section className="view-stack">
      <div className="panel">
        <PanelTitle icon={Settings} title={labels.title} />
        <div className="config-storage">
          <Readout label={labels.storage} value={metadata?.path ?? "-"} />
          <Readout label={metadata?.usingEnvConfig ? labels.envConfig : labels.defaultLocal} value={metadata?.writable ? labels.writable : labels.readOnly} />
        </div>
        <p className="config-hint">{labels.savedHint}</p>
      </div>

      <div className="config-grid">
        <div className="panel">
          <PanelTitle icon={Server} title="Collector" />
          <div className="config-form-grid">
            <ConfigField label={labels.hostId} value={hostId} onChange={updateField(setHostId)} />
            <ConfigField label={labels.interval} value={interval} onChange={updateField(setIntervalValue)} type="number" />
            <ConfigField label={labels.unmanagedTop} value={unmanagedTop} onChange={updateField(setUnmanagedTop)} type="number" />
          </div>
        </div>

        <div className="panel">
          <PanelTitle icon={Layers3} title="Discovery" />
          <div className="config-form-grid two">
            <ConfigTextarea label={labels.experimentRoots} hint={labels.onePerLine} value={experimentRoots} onChange={updateField(setExperimentRoots)} />
            <ConfigTextarea label={labels.includeCwd} hint={labels.onePerLine} value={includeCwd} onChange={updateField(setIncludeCwd)} />
            <ConfigTextarea label={labels.protocolRoots} hint={labels.onePerLine} value={protocolRoots} onChange={updateField(setProtocolRoots)} />
          </div>
        </div>

        <div className="panel">
          <PanelTitle icon={SlidersHorizontal} title="Parser" />
          <div className="config-form-grid two">
            <ConfigTextarea label={labels.includeKeywords} hint={labels.onePerLine} value={includeKeywords} onChange={updateField(setIncludeKeywords)} />
            <ConfigTextarea label={labels.excludeKeywords} hint={labels.onePerLine} value={excludeKeywords} onChange={updateField(setExcludeKeywords)} />
            <ConfigTextarea label={labels.explicitRules} value={rulesJson} onChange={updateField(setRulesJson)} mono />
          </div>
        </div>
      </div>

      <div className="config-save-bar">
        <div>
          {error && <strong>{error}</strong>}
          {!error && operationMessage && <span>{operationMessage}</span>}
        </div>
        <button className="action-button active-action" onClick={submit} disabled={saving || metadata?.writable === false}>
          {saving ? labels.saving : labels.save}
        </button>
      </div>
    </section>
  );
}

function ConfigField({
  label,
  value,
  onChange,
  type = "text"
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}) {
  return (
    <label className="config-field">
      <span>{label}</span>
      <input type={type} value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  );
}

function ConfigTextarea({
  label,
  hint,
  value,
  onChange,
  mono = false
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (value: string) => void;
  mono?: boolean;
}) {
  return (
    <label className={mono ? "config-field mono" : "config-field"}>
      <span>{label}</span>
      <textarea value={value} onChange={(event) => onChange(event.target.value)} rows={7} />
      {hint && <em>{hint}</em>}
    </label>
  );
}

function HostsView({
  hosts,
  runs,
  selectedHost,
  sshServers,
  sshKeyCandidates,
  onSelectHost,
  onSaveSshServer,
  onDeleteSshServer,
  onClearSshServers,
  onRemoteHostRefresh,
  sshSaveInFlight,
  sshDeleteInFlight
}: {
  hosts: Host[];
  runs: Run[];
  selectedHost: Host;
  sshServers: SshServer[];
  sshKeyCandidates: string[];
  onSelectHost: (hostId: string) => void;
  onSaveSshServer: (form: SshServerForm) => Promise<SshSaveResult>;
  onDeleteSshServer: (server: SshServer) => void;
  onClearSshServers: () => void;
  onRemoteHostRefresh: (host: Host) => void;
  sshSaveInFlight: boolean;
  sshDeleteInFlight: string;
}) {
  const t = useT();
  const language = useContext(I18nContext);
  const clearSshLabel = language === "zh" ? "清空 SSH" : "Clear SSH";
  const [historyRange, setHistoryRange] = useState<TimeRange>("15m");
  const [showSshForm, setShowSshForm] = useState(false);
  const hostRuns = runs.filter((run) => run.hostId === selectedHost.id);
  const topProcesses = selectedHost.processes?.length
    ? selectedHost.processes
        .map((proc) => ({ ...proc, run: "", role: "remote" }))
        .sort((a, b) => b.cpu - a.cpu)
        .slice(0, 8)
    : hostRuns
        .flatMap((run) => flattenProcessTree(run.processTree).map((proc) => ({ ...proc, run: run.name, command: undefined })))
        .sort((a, b) => b.cpu - a.cpu)
        .slice(0, 8);
  const memoryPercent = selectedHost.memoryTotalGb
    ? Math.round((selectedHost.memoryUsedGb / selectedHost.memoryTotalGb) * 100)
    : 0;
  const gpuMemoryUsed = selectedHost.gpus?.reduce((total, gpu) => total + (gpu.memoryUsedMiB ?? 0), 0) ?? 0;
  const gpuMemoryTotal = selectedHost.gpus?.reduce((total, gpu) => total + (gpu.memoryTotalMiB ?? 0), 0) ?? 0;
  const gpuUtil = selectedHost.gpus?.length
    ? Math.round(selectedHost.gpus.reduce((total, gpu) => total + (gpu.utilization ?? 0), 0) / selectedHost.gpus.length)
    : 0;
  const selectedSshServer = sshServers.find((server) => `ssh:${server.id}` === selectedHost.id);
  const hostIoSeries = filterSeriesByRange(makeHostSeries(selectedHost), historyRange);
  const initializingSelectedHost = isRemoteInitializing(selectedHost);

  return (
    <section className="view-stack">
      <div className="host-selector">
        {hosts.map((host) => (
          <button
            key={host.id}
            className={selectedHost.id === host.id ? "selector-chip active" : "selector-chip"}
            onClick={() => onSelectHost(host.id)}
          >
            <Server size={15} />
            <span>{displayHostName(host, t)}</span>
            <small>{isRemoteInitializing(host) ? t("remoteInitializing") : `${host.cpuUsage}% CPU / ${formatMemory(host, t)}`}</small>
          </button>
        ))}
        <div className="selector-chip ssh-manage-chip">
          <button
            type="button"
            className="ssh-manage-row add"
            onClick={() => setShowSshForm(true)}
            title={t("addSshServer")}
          >
            <Plus size={17} />
            <span>{t("addSshServer")}</span>
          </button>
          <button
            type="button"
            className="ssh-manage-row clear"
            onClick={onClearSshServers}
            disabled={sshServers.length === 0}
            title={clearSshLabel}
          >
            <Trash2 size={15} />
            <span>{clearSshLabel}</span>
            <small>{sshServers.length} SSH</small>
          </button>
        </div>
      </div>

      <div className="host-detail-grid">
        <div className="panel host-hero">
          <div className="host-heading">
            <div>
              <h2>{displayHostName(selectedHost, t)}</h2>
              <p>{selectedHost.user}@{selectedHost.address} · {selectedHost.os} · {selectedHost.id}</p>
            </div>
            <ResourceRing value={selectedHost.cpuUsage} label="CPU" />
          </div>
          <div className="host-metric-grid">
            <HostMetricTile icon={Cpu} label="CPU" value={initializingSelectedHost ? "-" : `${selectedHost.cpuUsage}%`} detail={initializingSelectedHost ? t("remoteInitializing") : `${selectedHost.cores.length} ${t("cores")}`} />
            <HostMetricTile icon={MemoryStick} label={t("memoryLabel")} value={`${memoryPercent}%`} detail={formatMemory(selectedHost, t)} />
            <HostMetricTile icon={Gauge} label={t("gpuUtil")} value={selectedHost.gpusTotal ? `${gpuUtil}%` : "-"} detail={formatGpu(selectedHost, t)} />
            <HostMetricTile icon={Database} label={t("gpuMemory")} value={gpuMemoryTotal ? `${gbFromMiB(gpuMemoryUsed)} / ${gbFromMiB(gpuMemoryTotal)} GB` : "-"} detail={initializingSelectedHost ? t("remoteInitializing") : `${selectedHost.gpusBusy}/${selectedHost.gpusTotal} ${t("runningSuffix")}`} />
            <HostMetricTile icon={HardDrive} label={t("diskIo")} value={`${(selectedHost.diskRead + selectedHost.diskWrite).toFixed(2)} MB/s`} detail={`${t("read")} ${selectedHost.diskRead} / ${t("write")} ${selectedHost.diskWrite}`} />
            <HostMetricTile icon={Network} label={t("network")} value={`${(selectedHost.netRx + selectedHost.netTx).toFixed(2)} MB/s`} detail={`${t("receive")} ${selectedHost.netRx} / ${t("transmit")} ${selectedHost.netTx}`} />
            <HostMetricTile icon={Workflow} label={t("runsLabel")} value={`${selectedHost.runningRuns}`} detail={`${hostRuns.length} ${t("visibleOnHost")}`} />
            <HostMetricTile icon={AlertTriangle} label={t("warnings")} value={`${selectedHost.warnings.length}`} detail={formatHostWarning(selectedHost.warnings[0], t) ?? t("normal")} />
          </div>
          <HostMemoryPanel host={selectedHost} />
          <HostGpuPanel host={selectedHost} />
        </div>

        <div className="panel host-core-panel">
          <PanelTitle icon={Cpu} title={t("perCoreCpu")} />
          <div className="core-grid">
            {selectedHost.cores.map((value, index) => (
              <div key={`${selectedHost.id}-${index}`} className="core-cell">
                <span style={{ height: `${Math.max(value, 8)}%` }} />
                <small>{index}</small>
              </div>
            ))}
          </div>
        </div>

        <div className="panel host-io-panel">
          <div className="panel-title-row">
            <PanelTitle icon={HardDrive} title={t("diskNetwork")} />
            <TimeRangePicker value={historyRange} onChange={setHistoryRange} />
          </div>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={hostIoSeries}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(143, 158, 183, .18)" />
              <XAxis dataKey="time" stroke="#8fa2bd" tick={{ fontSize: 11 }} />
              <YAxis stroke="#8fa2bd" tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Area type="monotone" dataKey="read" stroke="#E7A146" fill="#E7A14633" isAnimationActive={false} />
              <Area type="monotone" dataKey="write" stroke="#7EC7B8" fill="#7EC7B833" isAnimationActive={false} />
              <Area type="monotone" dataKey="rx" stroke="#7EA4FF" fill="#7EA4FF33" isAnimationActive={false} />
              <Area type="monotone" dataKey="tx" stroke="#D982A6" fill="#D982A626" isAnimationActive={false} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="panel host-process-panel">
          <PanelTitle icon={ListFilter} title={t("topProcesses")} />
          {topProcesses.length ? (
            <div className="process-table">
              {topProcesses.map((process) => (
              <div key={`${process.pid}-${process.name}`} className="process-row" title={process.command || process.name}>
                <span>{process.pid}</span>
                <strong>{process.name}</strong>
                <em>{process.cpu}%</em>
                <small>{process.memoryGb.toFixed(1)} GB</small>
              </div>
              ))}
            </div>
          ) : (
            <EmptyPanel
              title={t("noProcessSamples")}
              body={t("noProcessSamplesBody")}
            />
          )}
        </div>

        {selectedSshServer && (
          <div className="panel host-connection-panel">
            <PanelTitle icon={Server} title={t("sshServers")} />
            <SshServerPanel
              servers={[selectedSshServer]}
              onDelete={onDeleteSshServer}
              onRemoteHostRefresh={onRemoteHostRefresh}
              deletingId={sshDeleteInFlight}
            />
          </div>
        )}
      </div>
      {showSshForm && (
        <SshServerDialog
          keyCandidates={sshKeyCandidates}
          defaultUsername={hosts[0]?.user ?? ""}
          onSave={onSaveSshServer}
          onRemoteHostRefresh={onRemoteHostRefresh}
          onClose={() => setShowSshForm(false)}
          saving={sshSaveInFlight}
        />
      )}
    </section>
  );
}

function RunsView({
  runs,
  hosts,
  config,
  resourceFilter,
  onResourceFilter,
  onOpenRun,
  onDeleteRun,
  deleteInFlight
}: {
  runs: Run[];
  hosts: Host[];
  config?: CollectorConfig;
  resourceFilter: ResourceType | "all";
  onResourceFilter: (value: ResourceType | "all") => void;
  onOpenRun: (runId: string) => void;
  onDeleteRun: (run: Run) => void;
  deleteInFlight: string;
}) {
  const [showRules, setShowRules] = useState(false);
  const t = useT();
  return (
    <section className="view-stack">
      <div className="toolbar">
        <div className="segmented">
          {(["all", "cpu_only", "gpu", "hybrid", "unknown"] as const).map((value) => (
            <button
              key={value}
              className={resourceFilter === value ? "active" : ""}
              onClick={() => onResourceFilter(value)}
            >
              {resourceLabel(value, t)}
            </button>
          ))}
        </div>
        <button className={showRules ? "action-button active-action" : "action-button"} onClick={() => setShowRules((value) => !value)}>
          <SlidersHorizontal size={16} />
          {t("parserRules")}
        </button>
      </div>

      {showRules && <ParserRulesPanel config={config} />}

      <div className="run-table">
        <div className="run-table-head">
          <span>{t("status")}</span>
          <span>{t("projectRun")}</span>
          <span>{t("resource")}</span>
          <span>{t("host")}</span>
          <span>{t("rootPid")}</span>
          <span>{t("cpu")}</span>
          <span>{t("memory")}</span>
          <span>GPU</span>
          <span>{t("diskIo")}</span>
          <span>{t("metric")}</span>
          <span>{t("kind")}</span>
          <span>{t("actions")}</span>
        </div>
        {runs.length ? runs.map((run) => {
          const host = hosts.find((item) => item.id === run.hostId);
          return (
            <div
              key={run.id}
              className="run-table-row"
              role="button"
              tabIndex={0}
              onClick={() => onOpenRun(run.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onOpenRun(run.id);
                }
              }}
            >
              <span><StatusPill status={run.status} /></span>
              <span>
                <strong>{run.metadata?.pinned ? "★ " : ""}{run.project}</strong>
                <small>{run.name}</small>
                {run.metadata?.mark && <em className={`run-mark ${run.metadata.mark}`}>{run.metadata.mark}</em>}
              </span>
              <span><ResourceBadge type={run.resourceType} /></span>
              <span>
                {host ? displayHostName(host, t) : run.hostId}
                <small>{run.hostId}</small>
              </span>
              <span>{run.rootPid}</span>
              <span>{run.cpuPercent}%</span>
              <span>{run.memoryGb} GB</span>
              <span>{run.gpuLabel}</span>
              <span>{run.diskIo} MB/s</span>
              <span>{run.latestMetric}</span>
              <span>{run.entrypointKind}</span>
              <span className="run-row-actions">
                <button
                  className="icon-button danger-action"
                  disabled={!canDeleteRunRecord(run) || deleteInFlight === run.id}
                  onClick={(event) => {
                    event.stopPropagation();
                    onDeleteRun(run);
                  }}
                  title={t("deleteFinishedRecord")}
                >
                  <Trash2 size={15} />
                </button>
              </span>
            </div>
          );
        }) : (
          <div className="run-table-empty">
            <EmptyPanel
              title={t("noTasks")}
              body={t("noTasksBody")}
            />
          </div>
        )}
      </div>
    </section>
  );
}

const PARSER_RULE_TEXT = {
  zh: {
    title: "解析规则",
    body: "当前规则来自正在使用的采集器配置。可在配置页修改并立即生效。",
    experimentRoots: "实验根目录",
    includeKeywords: "包含关键词",
    excludeKeywords: "排除关键词",
    cwdUnder: "CWD 范围",
    scanRoots: "协议扫描目录",
    explicitRules: "显式规则",
    noExplicitRules: "暂无显式规则",
    none: "无"
  },
  en: {
    title: "Parser rules",
    body: "Current rules come from the active collector config. Edit them in the Config page to apply without restarting.",
    experimentRoots: "Experiment roots",
    includeKeywords: "Include keywords",
    excludeKeywords: "Exclude keywords",
    cwdUnder: "CWD under",
    scanRoots: "Protocol scan roots",
    explicitRules: "Explicit rules",
    noExplicitRules: "No explicit rules",
    none: "None"
  }
} as const;

function ParserRulesPanel({ config }: { config?: CollectorConfig }) {
  const language = useContext(I18nContext);
  const labels = PARSER_RULE_TEXT[language];
  const discovery = config?.run_discovery;
  const protocol = config?.protocol;
  return (
    <div className="rules-panel">
      <div className="rules-panel-header">
        <div>
          <strong>{labels.title}</strong>
          <span>{labels.body}</span>
        </div>
        <code>Config</code>
      </div>
      <div className="rules-grid">
        <RuleBlock title={labels.experimentRoots} items={config?.experiment_roots ?? []} emptyText={labels.none} />
        <RuleBlock title={labels.includeKeywords} items={discovery?.include_command_keywords ?? []} emptyText={labels.none} />
        <RuleBlock title={labels.excludeKeywords} items={discovery?.exclude_command_keywords ?? []} emptyText={labels.none} />
        <RuleBlock title={labels.cwdUnder} items={discovery?.include_cwd_under ?? []} emptyText={labels.none} />
        <RuleBlock title={labels.scanRoots} items={protocol?.scan_roots ?? []} emptyText={labels.none} />
        <div className="rule-block wide">
          <strong>{labels.explicitRules}</strong>
          {discovery?.explicit_rules?.length ? (
            <div className="rule-list">
              {discovery.explicit_rules.map((rule, index) => (
                <code key={`${rule.name}-${index}`}>
                  {rule.project ?? "project"} · {rule.name ?? "rule"} · {rule.command_regex ?? "-"}
                </code>
              ))}
            </div>
          ) : (
            <span>{labels.noExplicitRules}</span>
          )}
        </div>
      </div>
    </div>
  );
}

function RuleBlock({ title, items, emptyText }: { title: string; items: string[]; emptyText: string }) {
  return (
    <div className="rule-block">
      <strong>{title}</strong>
      {items.length ? (
        <div className="rule-list">
          {items.map((item) => <code key={item}>{item}</code>)}
        </div>
      ) : (
        <span>{emptyText}</span>
      )}
    </div>
  );
}

const PROJECT_TEXT = {
  en: {
    noProjects: "No projects detected",
    noProjectsBody: "Projects appear after runs are discovered or launched from a project directory.",
    running: "running",
    finished: "finished",
    failed: "Failed",
    gpuHour: "GPU-hour",
    avgGpuUtil: "Avg GPU util",
    gitRepo: "Git repository",
    noGitRepo: "Not a Git repository",
    runs: "Runs",
    gitWorkspace: "Git workspace",
    refreshGit: "Refresh Git",
    generateMessage: "Generate commit message",
    commit: "Commit selected",
    commitSubject: "Commit subject",
    commitBody: "Commit body",
    selectedFiles: "Selected files",
    pull: "Git pull",
    push: "Git push",
    branch: "Branch",
    remotes: "Remotes",
    changedFiles: "Changed files",
    gitLog: "Git log",
    diff: "Modified places",
    diffStat: "Diff stat",
    generatedMessage: "Generated commit message",
    noChanges: "No modified files",
    noLog: "No git log available",
    selectProject: "Select a project",
    loading: "Loading Git data...",
    notGit: "This project directory is not a Git repository.",
    commandOutput: "Command output",
    actionCompleted: "completed",
    committing: "Committing...",
    commitCompleted: "commit completed",
    confirmPullTitle: "Run git pull?",
    confirmPullBody: "This will fetch and merge remote changes into the selected project workspace.",
    confirmPushTitle: "Run git push?",
    confirmPushBody: "This will push local commits from the selected project workspace to its configured remote.",
    confirmCommitTitle: "Create commit?",
    confirmCommitBody: "This will commit the selected files in the selected project workspace."
  },
  zh: {
    noProjects: "暂无项目",
    noProjectsBody: "当任务从项目目录被发现或通过 expmon launch 启动后，会在这里按项目目录聚合。",
    running: "运行中",
    finished: "已结束",
    failed: "失败",
    gpuHour: "GPU 小时",
    avgGpuUtil: "平均 GPU 利用率",
    gitRepo: "Git 仓库",
    noGitRepo: "不是 Git 仓库",
    runs: "任务",
    gitWorkspace: "Git 工作区",
    refreshGit: "刷新 Git",
    generateMessage: "生成 commit message",
    commit: "提交选中文件",
    commitSubject: "Commit 标题",
    commitBody: "Commit 正文",
    selectedFiles: "已选文件",
    pull: "Git pull",
    push: "Git push",
    branch: "分支",
    remotes: "远端",
    changedFiles: "修改文件",
    gitLog: "Git log",
    diff: "修改位置",
    diffStat: "Diff 统计",
    generatedMessage: "生成的 commit message",
    noChanges: "暂无修改文件",
    noLog: "暂无 git log",
    selectProject: "选择项目",
    loading: "正在读取 Git 数据...",
    notGit: "这个项目目录不是 Git 仓库。",
    commandOutput: "命令输出",
    actionCompleted: "已完成",
    committing: "正在提交...",
    commitCompleted: "提交完成",
    confirmPullTitle: "执行 git pull？",
    confirmPullBody: "这会把远端修改拉取并合并到当前选中的项目工作区。",
    confirmPushTitle: "执行 git push？",
    confirmPushBody: "这会把当前项目工作区的本地提交推送到已配置的远端。",
    confirmCommitTitle: "创建 commit？",
    confirmCommitBody: "这会把选中的文件提交到当前项目工作区。"
  }
} as const;

function ProjectsView({
  projects,
  runs,
  hosts,
  onOpenRun,
  requestConfirm
}: {
  projects: Project[];
  runs: Run[];
  hosts: Host[];
  onOpenRun: (runId: string) => void;
  requestConfirm: (config: PendingConfirm) => void;
}) {
  const language = useContext(I18nContext);
  const labels = PROJECT_TEXT[language];
  const [selectedProjectId, setSelectedProjectId] = useState(projects[0]?.id ?? "");
  const [gitData, setGitData] = useState<GitProjectPayload | null>(null);
  const [loadingGit, setLoadingGit] = useState(false);
  const [gitMessage, setGitMessage] = useState("");
  const [generatedCommit, setGeneratedCommit] = useState<{ message: string; body: string } | null>(null);
  const [selectedGitPaths, setSelectedGitPaths] = useState<string[]>([]);
  const [commitSubject, setCommitSubject] = useState("");
  const [commitBody, setCommitBody] = useState("");
  const selectedProject = projects.find((project) => project.id === selectedProjectId) ?? projects[0];
  const hostNameById = useMemo(() => new Map(hosts.map((host) => [host.id, displayHostName(host, (key) => translate(language, key))])), [hosts, language]);
  const projectOrderId = useCallback((project: Project) => project.id, []);
  const { orderedItems: orderedProjects, dragPropsFor: projectDragProps } = usePersistentCardOrder(
    "expmon.order.projects.selector",
    projects,
    projectOrderId
  );

  useEffect(() => {
    if (!projects.length) {
      setSelectedProjectId("");
      setGitData(null);
      return;
    }
    if (!projects.some((project) => project.id === selectedProjectId)) {
      setSelectedProjectId(projects[0].id);
    }
  }, [projects, selectedProjectId]);

  const projectRuns = useMemo(() => {
    if (!selectedProject) {
      return [];
    }
    const runIds = new Set(selectedProject.runs);
    return runs.filter((run) => runIds.has(run.id));
  }, [runs, selectedProject]);
  const runHostLabel = useCallback((run: Run) => hostNameById.get(run.hostId) ?? run.hostId, [hostNameById]);
  const projectHostLabel = useCallback((project: Project) => {
    const runIds = new Set(project.runs);
    const labels = Array.from(new Set(runs.filter((run) => runIds.has(run.id)).map(runHostLabel))).filter(Boolean);
    return labels.length ? labels.join(", ") : "-";
  }, [runHostLabel, runs]);

  const loadGit = useCallback(() => {
    if (!selectedProject) {
      return;
    }
    if (!selectedProject.isGit) {
      setGitData({ ok: false, error: labels.notGit, project: selectedProject });
      return;
    }
    setLoadingGit(true);
    setGitMessage(labels.loading);
    fetch(`${API_BASE}/api/projects/${encodeURIComponent(selectedProject.id)}/git`, { cache: "no-store" })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.error || `collector ${response.status}`);
        }
        return payload as GitProjectPayload;
      })
      .then((payload) => {
        setGitData(payload);
        setSelectedGitPaths((payload.changedFiles ?? []).map((file) => file.path));
        setGitMessage("");
      })
      .catch((error: Error) => {
        setGitData({ ok: false, error: error.message, project: selectedProject });
        setGitMessage(error.message);
      })
      .finally(() => setLoadingGit(false));
  }, [labels.loading, labels.notGit, selectedProject]);

  useEffect(() => {
    setGeneratedCommit(null);
    setSelectedGitPaths([]);
    setCommitSubject("");
    setCommitBody("");
    setGitData(null);
    setGitMessage("");
    if (selectedProject?.isGit) {
      loadGit();
    }
  }, [loadGit, selectedProject?.id, selectedProject?.isGit]);

  const runGitAction = useCallback((action: "pull" | "push" | "commit-message") => {
    if (!selectedProject) {
      return;
    }
    setLoadingGit(true);
    setGitMessage(action === "commit-message" ? labels.generateMessage : `${action}...`);
    fetch(`${API_BASE}/api/projects/${encodeURIComponent(selectedProject.id)}/git/${action}`, {
      method: "POST"
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.error || payload.stderr || `collector ${response.status}`);
        }
        return payload;
      })
      .then((payload) => {
        if (action === "commit-message") {
          setGeneratedCommit({ message: payload.message ?? "", body: payload.body ?? "" });
          setCommitSubject(payload.message ?? "");
          setCommitBody(payload.body ?? "");
          setGitMessage("");
        } else {
          setGitMessage([payload.stdout, payload.stderr].filter(Boolean).join("\n") || `${action} ${labels.actionCompleted}`);
          loadGit();
        }
      })
      .catch((error: Error) => setGitMessage(error.message))
      .finally(() => setLoadingGit(false));
  }, [labels.actionCompleted, labels.generateMessage, loadGit, selectedProject]);

  const confirmGitAction = useCallback((action: "pull" | "push") => {
    if (!selectedProject) {
      return;
    }
    requestConfirm({
      title: action === "pull" ? labels.confirmPullTitle : labels.confirmPushTitle,
      body: `${action === "pull" ? labels.confirmPullBody : labels.confirmPushBody}\n${selectedProject.name}`,
      confirmLabel: action === "pull" ? labels.pull : labels.push,
      tone: action === "push" ? "danger" : "default",
      onConfirm: () => runGitAction(action)
    });
  }, [
    labels.confirmPullBody,
    labels.confirmPullTitle,
    labels.confirmPushBody,
    labels.confirmPushTitle,
    labels.pull,
    labels.push,
    requestConfirm,
    runGitAction,
    selectedProject
  ]);

  const toggleGitPath = useCallback((path: string) => {
    setSelectedGitPaths((current) => (
      current.includes(path)
        ? current.filter((item) => item !== path)
        : [...current, path]
    ));
  }, []);

  const performCommitSelectedFiles = useCallback(() => {
    if (!selectedProject) {
      return;
    }
    setLoadingGit(true);
    setGitMessage(labels.committing);
    fetch(`${API_BASE}/api/projects/${encodeURIComponent(selectedProject.id)}/git/commit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: commitSubject,
        body: commitBody,
        paths: selectedGitPaths
      })
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok || !payload.ok) {
          throw new Error(payload.error || payload.stderr || `collector ${response.status}`);
        }
        return payload;
      })
      .then((payload) => {
        setGitMessage([payload.stdout, payload.stderr].filter(Boolean).join("\n") || labels.commitCompleted);
        setGeneratedCommit(null);
        setCommitSubject("");
        setCommitBody("");
        if (payload.git) {
          setGitData(payload.git);
          setSelectedGitPaths((payload.git.changedFiles ?? []).map((file: { path: string }) => file.path));
        } else {
          loadGit();
        }
      })
      .catch((error: Error) => setGitMessage(error.message))
      .finally(() => setLoadingGit(false));
  }, [commitBody, commitSubject, labels.commitCompleted, labels.committing, loadGit, selectedGitPaths, selectedProject]);

  const commitSelectedFiles = useCallback(() => {
    if (!selectedProject) {
      return;
    }
    requestConfirm({
      title: labels.confirmCommitTitle,
      body: `${labels.confirmCommitBody}\n${selectedProject.name}\n${selectedGitPaths.length} ${labels.selectedFiles}`,
      confirmLabel: labels.commit,
      tone: "default",
      onConfirm: performCommitSelectedFiles
    });
  }, [
    labels.commit,
    labels.confirmCommitBody,
    labels.confirmCommitTitle,
    labels.selectedFiles,
    performCommitSelectedFiles,
    requestConfirm,
    selectedGitPaths.length,
    selectedProject
  ]);

  if (!projects.length) {
    return (
      <section className="view-stack">
        <div className="panel">
          <EmptyPanel title={labels.noProjects} body={labels.noProjectsBody} />
        </div>
      </section>
    );
  }

  return (
    <section className="project-workspace">
      <div className="project-list panel">
        <PanelTitle icon={Layers3} title={labels.selectProject} />
        <div className="project-selector-list">
          {orderedProjects.map((project) => (
            <button
              key={project.id}
              className={project.id === selectedProject?.id ? "project-selector active" : "project-selector"}
              onClick={() => setSelectedProjectId(project.id)}
              {...projectDragProps(project.id)}
            >
              <strong>{project.name}</strong>
              <span>{project.path}</span>
              <small>{project.isGit ? labels.gitRepo : labels.noGitRepo} · {project.runningRuns} {labels.running} · {projectHostLabel(project)}</small>
            </button>
          ))}
        </div>
      </div>

      <div className="project-main">
        {selectedProject && (
          <div className="panel project-hero">
            <div>
              <span>{selectedProject.isGit ? labels.gitRepo : labels.noGitRepo}</span>
              <h2>{selectedProject.name}</h2>
              <p>{selectedProject.path}</p>
              <p>{projectHostLabel(selectedProject)}</p>
            </div>
            <div className="project-stat-strip">
              <Readout label={labels.running} value={String(selectedProject.runningRuns)} />
              <Readout label={labels.finished} value={String(selectedProject.finishedRuns)} />
              <Readout label={labels.failed} value={String(selectedProject.failedRuns ?? 0)} />
              <Readout label={labels.gpuHour} value={String(selectedProject.totalGpuHours ?? 0)} />
              <Readout label={labels.avgGpuUtil} value={`${selectedProject.avgGpuUtil ?? 0}%`} />
              <Readout label={labels.runs} value={String(selectedProject.runs.length)} />
            </div>
          </div>
        )}

        <div className="panel">
          <PanelTitle icon={Workflow} title={labels.runs} />
          <div className="project-run-list">
            {projectRuns.map((run) => (
              <button key={run.id} className="project-run-row" onClick={() => onOpenRun(run.id)}>
                <StatusPill status={run.status} />
                <span className="project-run-title">
                  <strong>{run.metadata?.pinned ? "★ " : ""}{run.project} / {run.name}</strong>
                  <small>{runHostLabel(run)}</small>
                  {run.metadata?.mark && <em className={`run-mark ${run.metadata.mark}`}>{run.metadata.mark}</em>}
                </span>
                <span>{run.rootPid}</span>
                <span>{run.latestMetric}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="project-panel-head">
            <PanelTitle icon={Database} title={labels.gitWorkspace} />
            <div className="project-actions">
              <button className="action-button" onClick={loadGit} disabled={!selectedProject?.isGit || loadingGit}>
                <RefreshCw size={16} /> {labels.refreshGit}
              </button>
              <button className="action-button" onClick={() => runGitAction("commit-message")} disabled={!selectedProject?.isGit || loadingGit}>
                <FileText size={16} /> {labels.generateMessage}
              </button>
              <button className="action-button" onClick={() => confirmGitAction("pull")} disabled={!selectedProject?.isGit || loadingGit}>
                {labels.pull}
              </button>
              <button className="action-button active-action" onClick={() => confirmGitAction("push")} disabled={!selectedProject?.isGit || loadingGit}>
                {labels.push}
              </button>
            </div>
          </div>

          {gitMessage && <pre className="git-command-output">{gitMessage}</pre>}
          {!selectedProject?.isGit && <EmptyPanel title={labels.noGitRepo} body={labels.notGit} />}
          {selectedProject?.isGit && gitData && (
            <div className="git-grid">
              <div className="git-card">
                <strong>{labels.branch}</strong>
                <span>{gitData.branch || "-"}</span>
              </div>
              <div className="git-card">
                <strong>{labels.remotes}</strong>
                <pre>{(gitData.remotes ?? []).join("\n") || "-"}</pre>
              </div>
              <div className="git-card wide">
                <strong>{labels.changedFiles}</strong>
                {(gitData.changedFiles ?? []).length ? (
                  <div className="changed-file-list">
                    {(gitData.changedFiles ?? []).map((file) => (
                      <label key={`${file.status}-${file.path}`} className="changed-file-row">
                        <input
                          type="checkbox"
                          checked={selectedGitPaths.includes(file.path)}
                          onChange={() => toggleGitPath(file.path)}
                        />
                        <em>{file.status}</em>
                        <span>{file.path}</span>
                      </label>
                    ))}
                  </div>
                ) : (
                  <span>{labels.noChanges}</span>
                )}
              </div>
              {(gitData.changedFiles ?? []).length > 0 && (
                <div className="git-card wide">
                  <div className="git-commit-head">
                    <strong>{labels.selectedFiles}: {selectedGitPaths.length}</strong>
                    <button
                      className="action-button active-action"
                      onClick={commitSelectedFiles}
                      disabled={loadingGit || !selectedGitPaths.length || !commitSubject.trim()}
                    >
                      {labels.commit}
                    </button>
                  </div>
                  <label className="config-field">
                    <span>{labels.commitSubject}</span>
                    <input value={commitSubject} onChange={(event) => setCommitSubject(event.target.value)} />
                  </label>
                  <label className="config-field">
                    <span>{labels.commitBody}</span>
                    <textarea value={commitBody} onChange={(event) => setCommitBody(event.target.value)} rows={5} />
                  </label>
                </div>
              )}
              {generatedCommit && (
                <div className="git-card wide">
                  <strong>{labels.generatedMessage}</strong>
                  <pre>{generatedCommit.message}{generatedCommit.body ? `\n\n${generatedCommit.body}` : ""}</pre>
                </div>
              )}
              <div className="git-card wide">
                <strong>{labels.diffStat}</strong>
                <pre>{gitData.diffStat || gitData.stagedDiffStat || labels.noChanges}</pre>
              </div>
              <div className="git-card wide">
                <strong>{labels.diff}</strong>
                <pre>{gitData.diff || labels.noChanges}</pre>
              </div>
              <div className="git-card wide">
                <strong>{labels.gitLog}</strong>
                <pre>{(gitData.log ?? []).join("\n") || labels.noLog}</pre>
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function RunDetail({
  run,
  runs,
  hosts,
  onSelectRun,
  onBackToRuns,
  onKillRun,
  onDeleteRun,
  onSaveMetadata,
  killInFlight,
  deleteInFlight,
  metadataSaveInFlight,
  operationMessage
}: {
  run?: Run;
  runs: Run[];
  hosts: Host[];
  onSelectRun: (runId: string) => void;
  onBackToRuns: () => void;
  onKillRun: (run: Run) => void;
  onDeleteRun: (run: Run) => void;
  onSaveMetadata: (run: Run, patch: Partial<RunMetadata>) => void;
  killInFlight: string;
  deleteInFlight: string;
  metadataSaveInFlight: string;
  operationMessage: string;
}) {
  const t = useT();
  const language = useContext(I18nContext);
  const [resourceRange, setResourceRange] = useState<TimeRange>("15m");
  if (!run) {
    return (
      <section className="view-stack">
        <div className="panel">
          <EmptyPanel
            title={t("noRunDetail")}
            body={t("noRunDetailBody")}
          />
        </div>
      </section>
    );
  }

  const host = hosts.find((item) => item.id === run.hostId);
  const hparamRows = Object.entries(run.hparams);
  const filteredResources = filterSeriesByRange(run.resources, resourceRange);
  const resourceGroups = groupResourceSeries(filteredResources, t);
  const resourceHistory = resourceHistoryStatus(run, run.resources.length, t);
  const metricGroups = groupMetricSeries(run.metrics, t);

  return (
    <section className="view-stack">
      <div className="toolbar">
        <div className="run-detail-nav">
          <button className="action-button" onClick={onBackToRuns}>
            <ArrowLeft size={16} />
            {t("backToRuns")}
          </button>
          <div className="run-tabs">
            {runs.map((item) => (
              <button
                key={item.id}
                className={item.id === run.id ? "active" : ""}
                onClick={() => onSelectRun(item.id)}
              >
                {item.project}/{item.name}
              </button>
            ))}
          </div>
        </div>
        <div className="toolbar-actions">
          {operationMessage && <span className="operation-message">{operationMessage}</span>}
          <button
            className="action-button danger-action"
            disabled={run.status !== "running" || killInFlight === run.id}
            onClick={() => onKillRun(run)}
            title={language === "zh" ? "终止根进程及子进程" : "Kill root process and children"}
          >
            <AlertTriangle size={16} />
            {killInFlight === run.id ? t("killing") : t("killTask")}
          </button>
          <button
            className="action-button danger-action"
            disabled={!canDeleteRunRecord(run) || deleteInFlight === run.id}
            onClick={() => onDeleteRun(run)}
            title={t("deleteFinishedRecord")}
          >
            <Trash2 size={16} />
            {deleteInFlight === run.id ? t("deleting") : t("deleteRecord")}
          </button>
        </div>
      </div>

      <div className="detail-header">
        <div>
          <div className="detail-kicker">
            <StatusPill status={run.status} />
            <ResourceBadge type={run.resourceType} />
            {run.metadata?.pinned && <span className="run-mark important">{t("pinned")}</span>}
            {run.metadata?.mark && <span className={`run-mark ${run.metadata.mark}`}>{run.metadata.mark}</span>}
            <span>{t("accessLevelLabel")} {run.accessLevel}</span>
          </div>
          <h2>{run.project} / {run.name}</h2>
          <p>{run.command}</p>
        </div>
        <div className="header-meta">
          <Readout label={t("host")} value={host ? displayHostName(host, t) : run.hostId} />
          <Readout label={t("userLabel")} value={run.user} />
          <Readout label={t("rootPid")} value={run.rootPid.toString()} />
          <Readout label={t("runtimeLabel")} value={run.runtime} />
          <Readout label={t("cpuTreeLabel")} value={`${(run.rootCpuPercent ?? 0).toFixed(1)}% / ${(run.processTreeCpuPercent ?? run.cpuPercent).toFixed(1)}%`} />
          <Readout label="GPU" value={run.gpuLabel} />
          <Readout label={t("gpuUtil")} value={formatGpuRunUsage(run, t)} />
        </div>
      </div>

      <div className="detail-grid">
        <div className="panel wide">
          <div className="panel-title-row">
            <div className="panel-title-with-status">
              <PanelTitle icon={Activity} title={t("resourceCurves")} />
              <span className={`history-status ${resourceHistory.tone}`}>
                {resourceHistory.label}{run.resources.length ? ` · ${resourceHistory.detail}` : ""}
              </span>
            </div>
            <TimeRangePicker value={resourceRange} onChange={setResourceRange} />
          </div>
          {resourceGroups.length ? (
            <div className="metric-subchart-grid resource-subchart-grid">
              {resourceGroups.map((group) => (
                <div key={group.id} className="metric-subchart resource-subchart">
                  <div className="metric-subchart-title">
                    <strong>{group.title}</strong>
                    <span>{group.subtitle}</span>
                  </div>
                  <ResponsiveContainer width="100%" height={220}>
                    <AreaChart data={group.data}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(143, 158, 183, .18)" />
                      <XAxis dataKey="time" stroke="#8fa2bd" tick={{ fontSize: 11 }} />
                      <YAxis domain={[0, 100]} stroke="#8fa2bd" tick={{ fontSize: 11 }} />
                      <Tooltip content={<RawValueTooltip kind="resource" />} />
                      <Legend />
                      {group.series.map((item, index) => (
                        <Area
                          key={item.key}
                          type="monotone"
                          dataKey={item.key}
                          name={item.name}
                          stroke={chartColors[index % chartColors.length]}
                          fill={`${chartColors[index % chartColors.length]}22`}
                          strokeWidth={2}
                          isAnimationActive={false}
                        />
                      ))}
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              ))}
            </div>
          ) : (
            <EmptyPanel title={t("noResourceSamples")} body={`${t("noResourceSamplesBody")} ${resourceHistory.detail}`} />
          )}
        </div>

        <div className="panel wide">
          <PanelTitle icon={BarChart3} title={t("metrics")} />
          {metricGroups.length ? (
            <div className="metric-subchart-grid">
              {metricGroups.map((group) => (
                <div key={group.id} className="metric-subchart">
                  <div className="metric-subchart-title">
                    <strong>{group.title}</strong>
                    <span>{group.subtitle}</span>
                  </div>
                  <ResponsiveContainer width="100%" height={240}>
                    <AreaChart data={group.data}>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(143, 158, 183, .18)" />
                      <XAxis dataKey="time" stroke="#8fa2bd" tick={{ fontSize: 11 }} />
                      <YAxis domain={[0, 100]} stroke="#8fa2bd" tick={{ fontSize: 11 }} />
                      <Tooltip content={<RawValueTooltip kind="metric" />} />
                      {group.keys.length <= 4 && <Legend />}
                      {group.keys.map((key, index) => (
                        <Area
                          key={key}
                          type="monotone"
                          dataKey={key}
                          stroke={chartColors[index % chartColors.length]}
                          fill={`${chartColors[index % chartColors.length]}22`}
                          strokeWidth={2}
                          isAnimationActive={false}
                        />
                      ))}
                    </AreaChart>
                  </ResponsiveContainer>
                  {group.keys.length > 4 && <CompactMetricLegend keys={group.keys} />}
                </div>
              ))}
            </div>
          ) : (
            <EmptyPanel title={t("noTrainingMetrics")} body={t("noTrainingMetricsBody")} />
          )}
        </div>

        <div className="panel">
          <PanelTitle icon={AlertTriangle} title={t("events")} />
          <EventList events={run.events ?? []} />
        </div>

        <div className="panel">
          <PanelTitle icon={Layers3} title={t("processTree")} />
          <ProcessTree node={run.processTree} />
        </div>

        <div className="panel wide">
          <PanelTitle icon={TerminalSquare} title={t("logs")} />
          <LogView lines={run.logs} />
        </div>

        <div className="panel">
          <PanelTitle icon={Zap} title={t("gpuProcesses")} />
          <GpuProcessList processes={run.gpuProcesses ?? []} />
        </div>

        <div className="panel">
          <PanelTitle icon={Gauge} title={t("runSummary")} />
          <RunSummaryPanel summary={run.summary} />
        </div>

        <div className="panel">
          <PanelTitle icon={FileText} title={t("runNotes")} />
          <RunMetadataEditor
            run={run}
            saving={metadataSaveInFlight === run.id}
            onSave={(patch) => onSaveMetadata(run, patch)}
          />
        </div>

        <ExperimentLogsPanel run={run} />

        <div className="panel">
          <PanelTitle icon={FileText} title={t("hyperparameters")} />
          {hparamRows.length ? (
            <div className="kv-table">
              {hparamRows.map(([key, value]) => (
                <div key={key}>
                  <span>{key}</span>
                  <strong>{String(value)}</strong>
                </div>
              ))}
            </div>
          ) : (
            <div className="empty-state">{t("unmanagedProcess")}</div>
          )}
        </div>

        <div className="panel">
          <PanelTitle icon={Database} title={t("runIdentityLabel")} />
          <div className="identity-list">
            <Readout label="run_id" value={run.id} />
            <Readout label="create_time" value={run.rootCreateTime} />
            <Readout label="cwd" value={run.cwd} />
            <Readout label="tags" value={run.tags.join(", ")} />
          </div>
        </div>
      </div>
    </section>
  );
}

const VISUALIZATION_TEXT = {
  en: {
    title: "Experiment Logs",
    emptyTitle: "No experiment logs detected",
    emptyBody: "TensorBoard, W&B, MLflow, JSONL, and CSV logs appear here when they are found inside the run directory.",
    choose: "Choose log",
    preview: "Refresh Preview",
    open: "Open Viewer",
    starting: "Starting viewer...",
    loading: "Loading preview...",
    inlineOnly: "This log can be previewed inline.",
    externalOnly: "Use the external viewer for this log type.",
    rows: "rows",
    files: "files",
    summary: "Summary",
    noPreview: "No numeric preview data was found in this log.",
    viewerReady: "Viewer ready"
  },
  zh: {
    title: "实验日志",
    emptyTitle: "未检测到实验日志",
    emptyBody: "任务目录中检测到 TensorBoard、W&B、MLflow、JSONL 或 CSV 日志后，会在这里显示。",
    choose: "选择日志",
    preview: "刷新预览",
    open: "打开查看器",
    starting: "正在启动查看器...",
    loading: "正在读取预览...",
    inlineOnly: "这个日志可以在页面内预览。",
    externalOnly: "这个日志类型使用外部查看器打开。",
    rows: "行",
    files: "文件",
    summary: "摘要",
    noPreview: "这个日志中没有检测到可预览的数值数据。",
    viewerReady: "查看器已就绪"
  }
} as const;

function ExperimentLogsPanel({ run }: { run: Run }) {
  const language = useContext(I18nContext);
  const labels = VISUALIZATION_TEXT[language];
  const visualizations = run.visualizations ?? [];
  const signature = visualizations.map((item) => `${item.id}:${item.updatedAt}:${item.fileCount}`).join("|");
  const [selectedId, setSelectedId] = useState("");
  const [preview, setPreview] = useState<VisualizationPreview | null>(null);
  const [viewerUrl, setViewerUrl] = useState("");
  const [message, setMessage] = useState("");
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [openingViewer, setOpeningViewer] = useState(false);

  useEffect(() => {
    setSelectedId((current) => {
      if (visualizations.some((item) => item.id === current)) {
        return current;
      }
      return visualizations[0]?.id ?? "";
    });
    setPreview(null);
    setViewerUrl("");
    setMessage("");
  }, [run.id, signature]);

  const selected = visualizations.find((item) => item.id === selectedId);

  const loadPreview = useCallback(() => {
    if (!selected) {
      return;
    }
    setLoadingPreview(true);
    setMessage(labels.loading);
    fetch(`${API_BASE}/api/runs/${encodeURIComponent(run.id)}/visualizations/${encodeURIComponent(selected.id)}/preview`, {
      cache: "no-store"
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.error || `collector ${response.status}`);
        }
        return payload as VisualizationPreview;
      })
      .then((payload) => {
        setPreview(payload);
        setMessage(payload.message || labels.inlineOnly);
      })
      .catch((error: Error) => {
        setPreview({ ok: false, error: error.message });
        setMessage(error.message);
      })
      .finally(() => setLoadingPreview(false));
  }, [labels.inlineOnly, labels.loading, run.id, selected]);

  useEffect(() => {
    if (!selected) {
      return;
    }
    setViewerUrl("");
    if (selected.viewer === "inline") {
      loadPreview();
    } else {
      setPreview(null);
      setMessage(labels.externalOnly);
    }
  }, [labels.externalOnly, loadPreview, selected?.id, selected?.viewer]);

  const openViewer = useCallback(() => {
    if (!selected) {
      return;
    }
    setOpeningViewer(true);
    setMessage(labels.starting);
    fetch(`${API_BASE}/api/runs/${encodeURIComponent(run.id)}/visualizations/${encodeURIComponent(selected.id)}/open`, {
      method: "POST"
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.error || `collector ${response.status}`);
        }
        return payload as { url?: string };
      })
      .then((payload) => {
        setViewerUrl(payload.url ?? "");
        setMessage(labels.viewerReady);
      })
      .catch((error: Error) => {
        setViewerUrl("");
        setMessage(error.message);
      })
      .finally(() => setOpeningViewer(false));
  }, [labels.starting, labels.viewerReady, run.id, selected]);

  const rows = preview?.rows ?? [];
  const previewKeys = numericKeysForRows(rows).slice(0, 6);
  const summaryEntries = Object.entries(preview?.summary ?? {}).slice(0, 12);

  return (
    <div className="panel double">
      <PanelTitle icon={FileText} title={labels.title} />
      {visualizations.length ? (
        <div className="visualization-stack">
          <div className="visualization-controls">
            <label>
              <span>{labels.choose}</span>
              <select value={selectedId} onChange={(event) => setSelectedId(event.target.value)}>
                {visualizations.map((item) => (
                  <option key={item.id} value={item.id}>
                    {visualizationKindLabel(item.kind)} - {item.relativePath || item.label}
                  </option>
                ))}
              </select>
            </label>
            <div className="visualization-actions">
              {selected?.viewer === "inline" ? (
                <button className="action-button" onClick={loadPreview} disabled={loadingPreview}>
                  <RefreshCw size={16} />
                  {loadingPreview ? labels.loading : labels.preview}
                </button>
              ) : (
                <button className="action-button active-action" onClick={openViewer} disabled={openingViewer}>
                  <Play size={16} />
                  {openingViewer ? labels.starting : labels.open}
                </button>
              )}
            </div>
          </div>

          {selected && (
            <div className="visualization-meta">
              <span>{visualizationKindLabel(selected.kind)}</span>
              <span>{selected.fileCount} {labels.files}</span>
              {selected.sizeMb > 0 && <span>{selected.sizeMb} MB</span>}
              {selected.updatedAt && <span>{selected.updatedAt}</span>}
            </div>
          )}

          {message && <div className="visualization-message">{message}</div>}
          {viewerUrl && (
            <a className="viewer-link" href={viewerUrl} target="_blank" rel="noreferrer">
              {viewerUrl}
            </a>
          )}

          {summaryEntries.length > 0 && (
            <div className="visualization-summary">
              <strong>{labels.summary}</strong>
              <div>
                {summaryEntries.map(([key, value]) => (
                  <span key={key}>{key}: {String(value)}</span>
                ))}
              </div>
            </div>
          )}

          {rows.length > 0 && previewKeys.length > 0 ? (
            <div className="visualization-chart">
              <div className="metric-subchart-title">
                <strong>{selected ? visualizationKindLabel(selected.kind) : labels.title}</strong>
                <span>{rows.length} {labels.rows}</span>
              </div>
              <ResponsiveContainer width="100%" height={240}>
                <LineChart data={rows}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(143, 158, 183, .18)" />
                  <XAxis dataKey="time" stroke="#8fa2bd" tick={{ fontSize: 11 }} />
                  <YAxis stroke="#8fa2bd" tick={{ fontSize: 11 }} />
                  <Tooltip contentStyle={tooltipStyle} />
                  <Legend />
                  {previewKeys.map((key, index) => (
                    <Line
                      key={key}
                      type="monotone"
                      dataKey={key}
                      stroke={chartColors[index % chartColors.length]}
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={false}
                      connectNulls
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            selected?.viewer === "inline" && !loadingPreview && <div className="empty-state">{labels.noPreview}</div>
          )}
        </div>
      ) : (
        <EmptyPanel title={labels.emptyTitle} body={labels.emptyBody} />
      )}
    </div>
  );
}

function ProtocolView() {
  const t = useT();
  const schemaRows = [
    ["runs", "run_id, project, name, status, resource_type, root_pid, command, cwd"],
    ["processes", "host_id, pid, create_time, ppid, user, command, cwd, status"],
    ["run_process_links", "run_id, host_id, pid, create_time, role"],
    ["run_resource_samples", "cpu_percent_total, memory_rss_mib_total, gpu_memory_mib_total"],
    ["metrics", "run_id, step, metric_name, metric_value, ts"],
    ["artifacts", "run_id, path, type, created_at"]
  ];

  return (
    <section className="view-stack">
      <div className="protocol-grid">
        <div className="panel">
          <PanelTitle icon={Workflow} title={t("accessLevels")} />
          <div className="access-lanes">
            <div><strong>A</strong><span>expmon launch</span><em>manifest, metrics, logs, tree</em></div>
            <div><strong>B</strong><span>{t("protocolLogs")}</span><em>manifest, hparams, JSONL</em></div>
            <div><strong>C</strong><span>{t("unmanagedProcess")}</span><em>{t("resourceSnapshot")}</em></div>
          </div>
        </div>

        <div className="panel double">
          <PanelTitle icon={Database} title={t("sqliteSchema")} />
          <div className="schema-list">
            {schemaRows.map(([name, fields]) => (
              <div key={name}>
                <strong>{name}</strong>
                <span>{fields}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="panel double">
          <PanelTitle icon={TerminalSquare} title={t("commandWrapper")} />
          <pre className="code-block">{`expmon launch --project my-project --name local-cpu-run -- python script.py
expmon launch --project my-project --name local-shell-run -- powershell ./run.ps1
expmon log --step 100 result/error=0.00031 perf/throughput=812.4
EXPMON_METRIC step=100 train/loss=0.83 throughput=512`}</pre>
        </div>

        <div className="panel">
          <PanelTitle icon={Network} title={t("collectorChannels")} />
          <div className="channel-list">
            <span>psutil / WMI</span>
            <span>nvidia-smi</span>
            <span>SSH /proc</span>
            <span>metrics.jsonl</span>
            <span>stdout marker</span>
            <span>regex parser</span>
          </div>
        </div>
      </div>
    </section>
  );
}

function MetricCard({
  icon: Icon,
  label,
  value,
  accent
}: {
  icon: typeof Activity;
  label: string;
  value: string | number;
  accent: string;
}) {
  return (
    <div className={`metric-card ${accent}`}>
      <Icon size={19} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function DiagnosticList({
  diagnostics,
  onOpenRun
}: {
  diagnostics: Diagnostic[];
  onOpenRun: (runId: string) => void;
}) {
  const t = useT();
  const diagnosticOrderId = useCallback((item: Diagnostic) => item.id, []);
  const { orderedItems: orderedDiagnostics, dragPropsFor: diagnosticDragProps } = usePersistentCardOrder(
    "expmon.order.dashboard.diagnostics",
    diagnostics,
    diagnosticOrderId
  );
  if (!diagnostics.length) {
    return <EmptyPanel title={t("noInsights")} body={t("noInsightsBody")} />;
  }
  return (
    <div className="diagnostic-list">
      {orderedDiagnostics.map((item) => (
        <button
          key={item.id}
          className={`diagnostic-row ${item.severity}`}
          onClick={() => item.runId && onOpenRun(item.runId)}
          disabled={!item.runId}
          {...diagnosticDragProps(item.id)}
        >
          <strong>{diagnosticTitle(item, t)}</strong>
          <span>{diagnosticMessage(item, t)}</span>
          <small>{item.evidence || item.type}</small>
        </button>
      ))}
    </div>
  );
}

function diagnosticTitle(item: Diagnostic, t: (key: TextKey) => string) {
  if (t("language") === "语言") {
    if (item.type === "cpu_bottleneck") {
      return "可能存在 CPU 侧瓶颈";
    }
    if (item.type === "idle_gpu") {
      return "GPU 可能处于空转";
    }
    if (item.type === "notebook_gpu") {
      return "Notebook 正占用 GPU 显存";
    }
  }
  return item.title;
}

function diagnosticMessage(item: Diagnostic, t: (key: TextKey) => string) {
  if (t("language") !== "语言") {
    return item.message;
  }
  if (item.type === "cpu_bottleneck") {
    return `${item.project ? `${item.project}: ` : ""}CPU 使用率较高，但 GPU 利用率较低。`;
  }
  if (item.type === "idle_gpu") {
    return "检测到显存占用较高，但 GPU 利用率较低。";
  }
  if (item.type === "notebook_gpu") {
    return "Jupyter/ipykernel 进程正在占用 GPU 显存。";
  }
  return item.message;
}

function PanelTitle({ icon: Icon, title }: { icon: typeof Activity; title: string }) {
  return (
    <div className="panel-title">
      <Icon size={17} />
      <h3>{title}</h3>
    </div>
  );
}

function ResourceBadge({ type }: { type: ResourceType }) {
  const t = useT();
  return <span className={`resource-badge ${type}`}>{resourceLabel(type, t)}</span>;
}

function StatusPill({ status }: { status: RunStatus }) {
  const t = useT();
  return <span className={`status-pill ${status}`}>{statusLabel(status, t)}</span>;
}

function statusLabel(status: RunStatus, t: (key: TextKey) => string) {
  const labels: Record<RunStatus, TextKey> = {
    running: "statusRunning",
    finished: "statusFinished",
    failed: "statusFailed",
    killed: "statusKilled",
    unmanaged: "statusUnmanaged"
  };
  return t(labels[status]);
}

function canDeleteRunRecord(run: Run) {
  return run.accessLevel === "A" && ["finished", "failed", "killed"].includes(run.status);
}

function importantGpuProcesses(processes: GpuProcess[]) {
  return [...processes]
    .filter((process) => process.usedMemoryMiB >= 64 || Boolean(process.runId) || process.role === "notebook")
    .sort((left, right) => right.usedMemoryMiB - left.usedMemoryMiB)
    .slice(0, 5);
}

function formatGpuPower(gpu: GpuSample) {
  return gpu.powerLimitW && gpu.powerLimitW > 0
    ? `${gpu.powerDrawW} / ${gpu.powerLimitW} W${gpu.powerLimitSource === "catalog" ? "*" : ""}`
    : `${gpu.powerDrawW} W / limit n/a`;
}

function gpuPowerPercent(gpu: GpuSample) {
  return gpu.powerLimitW && gpu.powerLimitW > 0 ? (gpu.powerDrawW / gpu.powerLimitW) * 100 : 0;
}

function formatGpuPowerDetail(gpu: GpuSample) {
  if (gpu.powerLimitW && gpu.powerLimitW > 0) {
    const suffix = gpu.powerLimitSource === "catalog" ? " (catalog)" : "";
    return `${gpu.powerDrawW.toFixed(0)} / ${gpu.powerLimitW.toFixed(0)} W${suffix}`;
  }
  return `${gpu.powerDrawW.toFixed(0)} W / limit n/a`;
}

function HostMetricTile({
  icon: Icon,
  label,
  value,
  detail
}: {
  icon: typeof Activity;
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="host-metric-tile">
      <Icon size={17} />
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function HostMemoryPanel({ host }: { host: Host }) {
  const t = useT();
  const language = useContext(I18nContext);
  const rows = memoryBreakdownRows(host);
  return (
    <div className="host-memory-panel">
      <div className="host-memory-head">
        <PanelTitle icon={MemoryStick} title={t("memoryBreakdown")} />
        <span>{host.memoryTotalGb > 0 ? `${host.memoryUsedGb} / ${host.memoryTotalGb} GB` : t("notConnected")}</span>
      </div>
      <p>{t("memoryBreakdownHint")}</p>
      {rows.length ? (
        <div className="memory-breakdown-list">
          {rows.map((row) => (
            <div key={row.key} className="memory-breakdown-row" title={memoryBreakdownNote(row, language)}>
              <div className="memory-breakdown-label">
                <strong>{memoryBreakdownLabel(row, language)}</strong>
                <span>{row.valueGb.toFixed(2)} GB · {row.percent.toFixed(1)}%</span>
              </div>
              <div className="memory-breakdown-bar">
                <span style={{ width: `${Math.max(2, Math.min(100, row.percent))}%` }} />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="memory-breakdown-empty">{t("memoryBreakdownUnavailable")}</div>
      )}
    </div>
  );
}

function HostGpuPanel({ host }: { host: Host }) {
  const t = useT();
  if (!host.gpus?.length) {
    return (
      <div className="host-gpu-panel empty">
        <span>GPU</span>
        <strong>{t("noNvidiaGpu")}</strong>
      </div>
    );
  }
  return (
    <div className="host-gpu-panel">
      {host.gpus.map((gpu) => {
        const allProcesses = gpu.processes ?? [];
        const visibleProcesses = importantGpuProcesses(allProcesses);
        const hiddenCount = Math.max(0, allProcesses.length - visibleProcesses.length);
        return (
          <div key={`${host.id}-gpu-${gpu.index}`} className="host-gpu-row">
            <div className="host-gpu-main">
              <span>GPU {gpu.index}</span>
              <strong>{gpu.name}</strong>
              {gpu.uuid && <small>{shortGpuUuid(gpu.uuid)}</small>}
            </div>
            <Readout label={t("memoryLabel")} value={`${gbFromMiB(gpu.memoryUsedMiB)} / ${gbFromMiB(gpu.memoryTotalMiB)} GB`} />
            <Readout label={t("gpuUtil")} value={`${gpu.utilization}%`} />
            <Readout label={t("power")} value={formatGpuPower(gpu)} />
            <Readout label={t("temperature")} value={`${gpu.temperatureC} C`} />
            <div className="gpu-process-table">
              <div className="gpu-process-summary">
                <strong>{t("language") === "语言" ? "重点 GPU 进程" : "Key GPU processes"}</strong>
                <span>
                  {hiddenCount > 0
                    ? (t("language") === "语言" ? `已隐藏 ${hiddenCount} 个低显存进程` : `${hiddenCount} low-memory processes hidden`)
                    : (t("language") === "语言" ? "按显存占用排序" : "Sorted by GPU memory")}
                </span>
              </div>
              <div className="gpu-process-head">
                <span>PID</span>
                <span>{t("processLabel")}</span>
                <span>{t("gpuMemShort")}</span>
                <span>{t("runLabel")}</span>
              </div>
              {visibleProcesses.length ? visibleProcesses.map((process) => (
                <div
                  key={`${gpu.index}-${process.pid}-${process.usedMemoryMiB}`}
                  className={process.role === "notebook" ? "gpu-process-row notebook" : "gpu-process-row"}
                  title={process.command || process.name}
                >
                  <span>{process.pid}</span>
                  <strong>{process.name || t("processLabel")}</strong>
                  <span>{gbFromMiB(process.usedMemoryMiB)} GB</span>
                  <em>{formatGpuProcessOwner(process)}</em>
                </div>
              )) : (
                <div className="gpu-process-empty">{t("noGpuProcesses")}</div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function SshServerPanel({
  servers,
  onDelete,
  onRemoteHostRefresh,
  deletingId
}: {
  servers: SshServer[];
  onDelete: (server: SshServer) => void;
  onRemoteHostRefresh: (host: Host) => void;
  deletingId: string;
}) {
  const t = useT();
  const [testingId, setTestingId] = useState("");
  const [testResults, setTestResults] = useState<Record<string, SshTestResult>>({});
  const serverOrderId = useCallback((server: SshServer) => server.id, []);
  const { orderedItems: orderedServers, dragPropsFor: serverDragProps } = usePersistentCardOrder(
    "expmon.order.ssh.servers",
    servers,
    serverOrderId
  );
  const runServerTest = useCallback((server: SshServer) => {
    setTestingId(server.id);
    setTestResults((current) => ({
      ...current,
      [server.id]: { ok: false, message: t("testingSsh") }
    }));
    return fetch(`${API_BASE}/api/ssh/servers/${encodeURIComponent(server.id)}/test`, {
      method: "POST"
    })
      .then(async (response) => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(payload.error || `collector ${response.status}`);
        }
        return payload as SshTestResult;
      })
      .then((payload) => {
        setTestResults((current) => ({ ...current, [server.id]: payload }));
        if (payload.ok) {
          onRemoteHostRefresh(hostFromSshServer(server, payload));
        }
        return payload;
      })
      .catch((error: Error) => {
        setTestResults((current) => ({ ...current, [server.id]: { ok: false, error: error.message, message: error.message } }));
        throw error;
      })
      .finally(() => setTestingId(""));
  }, [onRemoteHostRefresh, t]);
  const testServer = (server: SshServer) => {
    runServerTest(server).catch(() => undefined);
  };

  return (
    <div className="ssh-server-stack">
      {orderedServers.map((server) => (
        <div key={server.id} className="ssh-server-card" {...serverDragProps(server.id)}>
          <div className="ssh-server-card-top">
            <div>
              <strong>{server.name}</strong>
              <span>{server.username}@{server.host}:{server.port}</span>
            </div>
            <div className="ssh-card-actions">
              <button
                className="action-button"
                disabled={testingId === server.id}
                onClick={() => testServer(server)}
                title={t("testSshServer")}
              >
                <Activity size={15} />
                {testingId === server.id ? t("testingSsh") : t("testSshServer")}
              </button>
              <button
                className="icon-button danger-action"
                disabled={deletingId === server.id}
                onClick={() => onDelete(server)}
                title={t("deleteSshServer")}
              >
                <Trash2 size={15} />
              </button>
            </div>
          </div>
          <div className="ssh-capability-grid">
            <Readout label={t("auth")} value={server.authType === "key" ? "SSH key" : "Password"} />
            <Readout label={t("credential")} value={server.authType === "key" ? (server.keyPath || "-") : (server.hasPassword ? t("savedLocally") : t("missing"))} />
            <Readout label={t("status")} value={t("configured")} />
            <Readout label={t("updated")} value={server.updatedAt || "-"} />
          </div>
          {testResults[server.id] && (
            <SshTestStatus result={testResults[server.id]} />
          )}
        </div>
      ))}
    </div>
  );
}

function hostFromSshServer(server: SshServer, result?: SshTestResult, state: "idle" | "initializing" | "failed" = "idle"): Host {
  const warnings = state === "initializing"
    ? ["remote initializing"]
    : state === "failed"
      ? [result?.message || result?.error || "remote resource load failed"]
      : result?.ok
        ? []
        : ["remote resources not loaded"];
  return {
    id: `ssh:${server.id}`,
    name: server.name || result?.hostname || server.host,
    os: result?.remoteOs ? `SSH / ${result.remoteOs}` : result?.hostname ? `SSH / ${result.hostname}` : "SSH",
    address: server.host,
    user: server.username,
    cpuUsage: 0,
    memoryUsedGb: 0,
    memoryTotalGb: 0,
    gpusTotal: 0,
    gpusBusy: 0,
    gpus: [],
    diskRead: 0,
    diskWrite: 0,
    netRx: 0,
    netTx: 0,
    runningRuns: 0,
    warnings,
    cores: [],
    history: []
  };
}

function SshServerDialog({
  keyCandidates,
  defaultUsername,
  onSave,
  onRemoteHostRefresh,
  onClose,
  saving
}: {
  keyCandidates: string[];
  defaultUsername: string;
  onSave: (form: SshServerForm) => Promise<SshSaveResult>;
  onRemoteHostRefresh: (host: Host) => void;
  onClose: () => void;
  saving: boolean;
}) {
  const t = useT();
  const [form, setForm] = useState<SshServerForm>({
    name: "",
    host: "",
    port: 22,
    username: defaultUsername,
    authType: "key",
    keyPath: keyCandidates[0] ?? "",
    password: ""
  });
  const [testResult, setTestResult] = useState<SshTestResult | null>(null);
  const [testing, setTesting] = useState(false);
  useEffect(() => {
    if (form.authType === "key" && !form.keyPath && keyCandidates[0]) {
      setForm((current) => ({ ...current, keyPath: keyCandidates[0] }));
    }
  }, [form.authType, form.keyPath, keyCandidates]);
  const updateForm = (patch: Partial<SshServerForm>) => setForm((current) => ({ ...current, ...patch }));
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setTestResult(null);
    onSave(form)
      .then(({ server, test }) => {
        if (test) {
          setTestResult(test);
        }
        if (server) {
          onClose();
        }
      })
      .catch((error: Error & { test?: SshTestResult }) => {
        if (error.test) {
          setTestResult(error.test);
          return;
        }
        setTestResult({ ok: false, error: error.message, message: error.message });
      });
  };

  return (
    <div className="confirm-overlay" role="presentation" onMouseDown={onClose}>
      <section
        className="ssh-server-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ssh-server-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <form className="ssh-server-form" onSubmit={submit}>
          <div className="ssh-form-heading">
            <strong id="ssh-server-dialog-title">{t("addSshServer")}</strong>
            <span>{t("sshPasswordNotice")}</span>
          </div>
          <label>
            <span>Name</span>
            <input value={form.name} onChange={(event) => updateForm({ name: event.target.value })} placeholder="server-01" />
          </label>
          <label>
            <span>IP / Host</span>
            <input value={form.host} onChange={(event) => updateForm({ host: event.target.value })} placeholder="192.168.1.20" required />
          </label>
          <label>
            <span>Port</span>
            <input type="number" min={1} max={65535} value={form.port} onChange={(event) => updateForm({ port: Number(event.target.value) })} required />
          </label>
          <label>
            <span>User</span>
            <input value={form.username} onChange={(event) => updateForm({ username: event.target.value })} placeholder="ubuntu" required />
          </label>
          <div className="ssh-auth-switch">
            <button type="button" className={form.authType === "key" ? "active" : ""} onClick={() => updateForm({ authType: "key" })}>SSH key</button>
            <button type="button" className={form.authType === "password" ? "active" : ""} onClick={() => updateForm({ authType: "password" })}>Password</button>
          </div>
          {form.authType === "key" ? (
            <label className="ssh-form-wide">
              <span>SSH key</span>
              <input
                list="ssh-key-candidates"
                value={form.keyPath}
                onChange={(event) => updateForm({ keyPath: event.target.value })}
                placeholder="~/.ssh/id_ed25519"
                required
              />
              <datalist id="ssh-key-candidates">
                {keyCandidates.map((path) => <option key={path} value={path} />)}
              </datalist>
            </label>
          ) : (
            <label className="ssh-form-wide">
              <span>Password</span>
              <input type="password" value={form.password} onChange={(event) => updateForm({ password: event.target.value })} required />
            </label>
          )}
          {testResult && <div className="ssh-form-wide"><SshTestStatus result={testResult} /></div>}
          <div className="ssh-form-actions ssh-form-wide">
            <button className="action-button" type="button" onClick={onClose} disabled={saving || testing}>
              {t("cancel")}
            </button>
            <button className="action-button active-action" type="submit" disabled={saving || testing}>
              <Server size={16} />
              {saving ? t("saving") : testing ? t("testingSsh") : t("saveServer")}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function SshTestStatus({ result }: { result: SshTestResult }) {
  const t = useT();
  const tone = result.ok ? "ok" : result.supported === false ? "unsupported" : "failed";
  const label = result.ok ? t("sshTestOk") : result.supported === false ? t("sshTestUnsupported") : t("sshTestFailed");
  const detail = [
    result.hostname,
    result.remoteOs ? `OS ${result.remoteOs}` : "",
    result.pythonPath ? `Python ${result.pythonPath}` : "",
    typeof result.latencyMs === "number" ? `${t("latency")} ${result.latencyMs} ms` : "",
    result.testedAt
  ].filter(Boolean).join(" · ");
  return (
    <div className={`ssh-test-status ${tone}`}>
      <strong>{label}</strong>
      {detail && <span>{detail}</span>}
      {(result.message || result.error) && <em>{result.message || result.error}</em>}
    </div>
  );
}

function ResourceOverview({ host }: { host?: Host }) {
  const t = useT();
  if (!host) {
    return (
      <div className="panel">
        <EmptyPanel title={t("noLocalResource")} body={t("noLocalResourceBody")} />
      </div>
    );
  }

  const gpus = host.gpus ?? [];
  const memoryPercent = memoryUsagePercent(host);
  return (
    <div className="resource-overview">
      <div className="panel nvitop-panel">
        <PanelTitle icon={Zap} title="GPU" />
        {gpus.length ? (
          <div className="gpu-list">
            {gpus.map((gpu) => (
              <div key={gpu.index} className="gpu-row">
                <div className="gpu-name">
                  <strong>GPU {gpu.index}</strong>
                  <span>{gpu.name}</span>
                </div>
                <Meter
                  label={t("gpuMemory")}
                  value={gpu.memoryPercent}
                  detail={`${formatMiB(gpu.memoryUsedMiB)} / ${formatMiB(gpu.memoryTotalMiB)}`}
                  accent="blue"
                />
                <Meter label={t("gpuUtil")} value={gpu.utilization} detail={`${gpu.utilization.toFixed(0)}%`} accent="cyan" />
                <Meter
                  label={t("power")}
                  value={gpuPowerPercent(gpu)}
                  detail={formatGpuPowerDetail(gpu)}
                  accent="amber"
                />
                <div className="temp-pill">{gpu.temperatureC.toFixed(0)}°C</div>
              </div>
            ))}
          </div>
        ) : (
          <EmptyPanel title={t("noNvidiaGpu")} body={t("noNvidiaGpuBody")} />
        )}
      </div>

      <div className="panel memory-panel">
        <PanelTitle icon={MemoryStick} title={t("memoryLabel")} />
        <div className="big-resource-number">{memoryPercent}%</div>
        <Meter
          label={t("systemMemory")}
          value={memoryPercent}
          detail={host.memoryTotalGb ? `${host.memoryUsedGb} / ${host.memoryTotalGb} GB` : t("notConnected")}
          accent="cyan"
        />
      </div>

      <div className="panel cpu-panel-wide">
        <PanelTitle icon={Cpu} title={t("cpuCores")} />
        <div className="cpu-core-strip">
          {host.cores.map((value, index) => (
            <div key={`${host.id}-dashboard-core-${index}`} className="cpu-core-pill">
              <div className="cpu-core-bar">
                <span style={{ height: `${Math.max(value, 3)}%` }} />
              </div>
              <strong>{value.toFixed(0)}%</strong>
              <small>{index}</small>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Meter({
  label,
  value,
  detail,
  accent
}: {
  label: string;
  value: number;
  detail: string;
  accent: "cyan" | "blue" | "amber";
}) {
  const clamped = Math.max(0, Math.min(100, value));
  return (
    <div className={`meter ${accent}`}>
      <div className="meter-label">
        <span>{label}</span>
        <strong>{detail}</strong>
      </div>
      <div className="meter-track">
        <span style={{ width: `${clamped}%` }} />
      </div>
    </div>
  );
}

function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div className="readout">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function EmptyPanel({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-panel">
      <strong>{title}</strong>
      <span>{body}</span>
    </div>
  );
}

function CompactMetricLegend({ keys }: { keys: string[] }) {
  const t = useT();
  const previewKeys = keys.slice(0, 8);
  return (
    <details className="compact-metric-legend">
      <summary>
        <span>{keys.length} {t("metricCountLabel")}</span>
        <em>{previewKeys.join(" · ")}{keys.length > previewKeys.length ? " · ..." : ""}</em>
      </summary>
      <div>
        {keys.map((key, index) => (
          <span key={key}>
            <i style={{ background: chartColors[index % chartColors.length] }} />
            {key}
          </span>
        ))}
      </div>
    </details>
  );
}

function ResourceRing({ value, label }: { value: number; label: string }) {
  return (
    <div className="resource-ring" style={{ "--value": `${value * 3.6}deg` } as React.CSSProperties}>
      <strong>{value}%</strong>
      <span>{label}</span>
    </div>
  );
}

function ProcessTree({ node, depth = 0 }: { node: ProcessNode; depth?: number }) {
  const t = useT();
  return (
    <div className="tree-node">
      <div className="tree-line" style={{ paddingLeft: `${depth * 18}px` }}>
        <span>{node.pid}</span>
        <strong>{node.name}</strong>
        <em>{processRoleLabel(node.role, t)}</em>
        <small>{node.cpu}% · {node.memoryGb.toFixed(1)} GB</small>
      </div>
      {node.children?.map((child) => (
        <ProcessTree key={`${child.pid}-${child.name}`} node={child} depth={depth + 1} />
      ))}
    </div>
  );
}

function processRoleLabel(role: string, t: (key: TextKey) => string) {
  if (role === "root") {
    return t("rootProcess");
  }
  if (role === "child") {
    return t("childProcess");
  }
  return role;
}

function GpuProcessList({ processes }: { processes: GpuProcess[] }) {
  const t = useT();
  if (!processes.length) {
    return <div className="empty-state">{t("noGpuProcessForRun")}</div>;
  }
  return (
    <div className="run-gpu-process-list">
      <div className="run-gpu-process-head">
        <span>GPU</span>
        <span>PID</span>
        <span>{t("kind")}</span>
        <span>{t("memoryLabel")}</span>
      </div>
      {processes.map((process) => (
        <div key={`${process.gpuIndex}-${process.pid}-${process.usedMemoryMiB}`} className="run-gpu-process-row">
          <span>GPU {process.gpuIndex}</span>
          <span>{process.pid}</span>
          <strong>{process.name || t("unmanagedProcess")}</strong>
          <span>{gbFromMiB(process.usedMemoryMiB)} GB</span>
        </div>
      ))}
    </div>
  );
}

function RunMetadataEditor({
  run,
  saving,
  onSave
}: {
  run: Run;
  saving: boolean;
  onSave: (patch: Partial<RunMetadata>) => void;
}) {
  const t = useT();
  const metadata = run.metadata ?? { note: "", mark: "", pinned: false, updatedAt: "" };
  const [note, setNote] = useState(metadata.note);
  const [mark, setMark] = useState(metadata.mark);

  useEffect(() => {
    setNote(metadata.note);
    setMark(metadata.mark);
  }, [metadata.note, metadata.mark, run.id]);

  return (
    <div className="run-metadata-editor">
      <div className="metadata-controls">
        <button
          className={metadata.pinned ? "action-button active-action" : "action-button"}
          onClick={() => onSave({ pinned: !metadata.pinned })}
          disabled={saving}
        >
          {metadata.pinned ? t("pinned") : t("pin")}
        </button>
        <label>
          <span>{t("mark")}</span>
          <select value={mark} onChange={(event) => setMark(event.target.value)}>
            <option value="">{t("none")}</option>
            <option value="baseline">baseline</option>
            <option value="candidate">candidate</option>
            <option value="important">important</option>
            <option value="debug">debug</option>
            <option value="bad">bad</option>
          </select>
        </label>
      </div>
      <textarea
        value={note}
        onChange={(event) => setNote(event.target.value)}
        placeholder={t("addRunNote")}
        rows={5}
      />
      <div className="metadata-footer">
        <span>{metadata.updatedAt ? `${t("updatedAt")} ${metadata.updatedAt}` : t("noNoteSaved")}</span>
        <button
          className="action-button active-action"
          disabled={saving}
          onClick={() => onSave({ note, mark })}
        >
          {saving ? t("savingShort") : t("saveNotes")}
        </button>
      </div>
    </div>
  );
}

function RunSummaryPanel({ summary }: { summary?: RunSummary }) {
  const t = useT();
  if (!summary) {
    return <div className="empty-state">{t("noSummary")}</div>;
  }
  const rows = [
    [t("duration"), summary.duration || "-"],
    [t("gpuHour"), `${summary.gpuHours ?? 0}`],
    [t("avgGpuUtil"), `${summary.avgGpuUtil ?? 0}%`],
    [t("gpuMemory"), `${summary.maxGpuMemoryGb ?? 0} GB`],
    [t("avgCpu"), `${summary.avgCpu ?? 0}%`],
    [t("maxRam"), `${summary.maxMemoryGb ?? 0} GB`],
    [t("totalIo"), `${summary.totalReadMiB ?? 0} / ${summary.totalWriteMiB ?? 0} MiB`],
    [t("bestMetric"), summary.bestMetric || "-"],
    [t("finalMetric"), summary.finalMetric || "-"],
    [t("failReason"), summary.failReason || "-"],
    [t("eventCount"), `${summary.eventCount ?? 0} (${summary.errorCount ?? 0} ${t("errors")})`],
  ];
  return (
    <div className="summary-grid">
      {rows.map(([label, value]) => (
        <Readout key={label} label={label} value={value} />
      ))}
    </div>
  );
}

function EventList({ events }: { events: RunEvent[] }) {
  const t = useT();
  if (!events.length) {
    return <div className="empty-state">{t("noEvents")}</div>;
  }
  return (
    <div className="event-list">
      {events.slice().reverse().map((event, index) => (
        <div key={`${event.time}-${event.type}-${index}`} className={`event-row ${event.severity}`}>
          <span>{event.time}</span>
          <strong>{event.type}</strong>
          <em>{event.message}</em>
          <small>{event.source}</small>
        </div>
      ))}
    </div>
  );
}

function LogView({ lines }: { lines: string[] }) {
  const t = useT();
  const [query, setQuery] = useState("");
  const [level, setLevel] = useState<"all" | "error" | "warning" | "info" | "other">("all");
  const [latestOnly, setLatestOnly] = useState(false);
  const normalizedQuery = query.trim().toLowerCase();
  const visibleLines = useMemo(() => {
    const recentLines = latestOnly ? lines.slice(-200) : lines;
    return recentLines.filter((line) => {
      const severity = logLineSeverity(line);
      const matchesLevel = level === "all" || severity === level;
      const matchesQuery = !normalizedQuery || line.toLowerCase().includes(normalizedQuery);
      return matchesLevel && matchesQuery;
    });
  }, [latestOnly, level, lines, normalizedQuery]);

  return (
    <div className="log-panel">
      <div className="log-toolbar">
        <label className="log-search">
          <Search size={15} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t("searchLogs")}
          />
        </label>
        <select value={level} onChange={(event) => setLevel(event.target.value as typeof level)}>
          <option value="all">{t("logLevelAll")}</option>
          <option value="error">{t("logLevelError")}</option>
          <option value="warning">{t("logLevelWarning")}</option>
          <option value="info">{t("logLevelInfo")}</option>
          <option value="other">{t("logLevelOther")}</option>
        </select>
        <label className="log-toggle">
          <input
            type="checkbox"
            checked={latestOnly}
            onChange={(event) => setLatestOnly(event.target.checked)}
          />
          <span>{t("latestLogs")}</span>
        </label>
        <span className="log-count">{visibleLines.length} / {lines.length} {t("matchingLines")}</span>
      </div>
      {visibleLines.length ? (
        <pre className="log-view">
          {visibleLines.map((line, index) => (
            <span key={`${index}-${line.slice(0, 18)}`} className={`log-line ${logLineSeverity(line)}`}>
              {line}
              {"\n"}
            </span>
          ))}
        </pre>
      ) : (
        <div className="empty-state">{t("noMatchingLogs")}</div>
      )}
    </div>
  );
}

function avg(values: number[]) {
  if (!values.length) {
    return 0;
  }
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function memoryUsagePercent(host: Host) {
  return host.memoryTotalGb > 0 ? Math.round((host.memoryUsedGb / host.memoryTotalGb) * 100) : 0;
}

function memoryBreakdownRows(host: Host): MemoryBreakdown[] {
  if (host.memoryBreakdown?.length) {
    return host.memoryBreakdown
      .filter((row) => Number.isFinite(row.valueGb) && row.valueGb > 0)
      .map((row) => ({
        ...row,
        percent: Number.isFinite(row.percent) ? row.percent : host.memoryTotalGb ? (row.valueGb / host.memoryTotalGb) * 100 : 0
      }))
      .sort((left, right) => memoryBreakdownRank(left.key) - memoryBreakdownRank(right.key));
  }
  if (host.memoryTotalGb <= 0) {
    return [];
  }
  const usedPercent = (host.memoryUsedGb / host.memoryTotalGb) * 100;
  const availableGb = Math.max(0, host.memoryTotalGb - host.memoryUsedGb);
  return [
    { key: "used", label: "Used", valueGb: host.memoryUsedGb, percent: usedPercent },
    { key: "available", label: "Available", valueGb: availableGb, percent: 100 - usedPercent }
  ].filter((row) => row.valueGb > 0);
}

function memoryBreakdownRank(key: string) {
  const order = [
    "windows_used",
    "windows_available",
    "windows_cache",
    "windows_committed",
    "windows_free",
    "linux_used",
    "linux_buffers",
    "linux_cache",
    "linux_shared",
    "linux_available",
    "macos_wired",
    "macos_active",
    "macos_inactive",
    "macos_compressed",
    "macos_free",
    "used",
    "available",
    "free"
  ];
  const index = order.indexOf(key);
  return index >= 0 ? index : order.length;
}

function memoryBreakdownLabel(row: MemoryBreakdown, language: Language) {
  if (language === "en") {
    return row.label || row.key;
  }
  const labels: Record<string, string> = {
    windows_used: "使用中",
    windows_available: "可用",
    windows_cache: "系统缓存",
    windows_committed: "已提交",
    windows_free: "空闲",
    linux_used: "使用中",
    linux_buffers: "Buffers",
    linux_cache: "Cache",
    linux_shared: "Shared",
    linux_available: "可用估算",
    macos_wired: "Wired",
    macos_active: "Active",
    macos_inactive: "Inactive",
    macos_compressed: "Compressed",
    macos_free: "Free",
    used: "使用中",
    available: "可用",
    free: "空闲"
  };
  return labels[row.key] ?? row.label ?? row.key;
}

function memoryBreakdownNote(row: MemoryBreakdown, language: Language) {
  if (language === "en") {
    return row.note || row.label || row.key;
  }
  const notes: Record<string, string> = {
    windows_used: "Windows：正在使用的物理内存",
    windows_available: "Windows：无需换页即可立即分配的内存",
    windows_cache: "Windows：系统文件缓存",
    windows_committed: "Windows：已提交虚拟内存，可能大于物理内存",
    windows_free: "Windows：完全未使用的页面",
    linux_used: "Linux：通常按 MemTotal - MemAvailable 估算",
    linux_buffers: "Linux：块设备缓冲",
    linux_cache: "Linux：文件缓存和可回收 slab",
    linux_shared: "Linux：tmpfs / shared memory",
    linux_available: "Linux：内核估算的新进程可用内存",
    macos_wired: "macOS：不能换出的内存",
    macos_active: "macOS：最近使用的应用内存",
    macos_inactive: "macOS：可回收的 inactive 内存",
    macos_compressed: "macOS：内核压缩内存",
    macos_free: "macOS：空闲页面"
  };
  return notes[row.key] ?? row.note ?? row.label ?? row.key;
}

function averageGpuUtilPercent(host: Host) {
  const gpus = host.gpus ?? [];
  if (!gpus.length) {
    return 0;
  }
  return Math.round(avg(gpus.map((gpu) => gpu.utilization ?? 0)));
}

function gpuMemoryUsagePercent(host: Host) {
  const gpus = host.gpus ?? [];
  const total = gpus.reduce((sum, gpu) => sum + (gpu.memoryTotalMiB ?? 0), 0);
  if (!total) {
    return 0;
  }
  const used = gpus.reduce((sum, gpu) => sum + (gpu.memoryUsedMiB ?? 0), 0);
  return Math.round((used / total) * 100);
}

function hostMixRows(host: Host, t: (key: TextKey) => string) {
  const gpuBusy = host.gpusTotal ? Math.round((host.gpusBusy / host.gpusTotal) * 100) : 0;
  return [
    { label: "CPU", value: host.cpuUsage, detail: `${host.cpuUsage.toFixed(1)}%`, accent: "amber" },
    { label: t("memoryLabel"), value: memoryUsagePercent(host), detail: formatMemory(host, t), accent: "cyan" },
    { label: t("gpuUtil"), value: averageGpuUtilPercent(host), detail: `${averageGpuUtilPercent(host)}%`, accent: "blue" },
    { label: t("gpuMemory"), value: gpuMemoryUsagePercent(host), detail: `${gpuMemoryUsagePercent(host)}%`, accent: "violet" },
    { label: t("busyGpus"), value: gpuBusy, detail: `${host.gpusBusy}/${host.gpusTotal}`, accent: "green" },
  ];
}

function displayHostName(host: Host | undefined, t: (key: TextKey) => string) {
  if (!host) {
    return "";
  }
  if (host.address === "127.0.0.1" || host.id === "local") {
    return t("localHostName");
  }
  return host.name;
}

function formatMemory(host: Host, t: (key: TextKey) => string) {
  if (isRemoteInitializing(host)) {
    return t("remoteInitializing");
  }
  return host.memoryTotalGb > 0 ? `${host.memoryUsedGb}/${host.memoryTotalGb} GB` : t("notConnected");
}

function formatHostWarning(warning: string | undefined, t: (key: TextKey) => string) {
  if (!warning) {
    return undefined;
  }
  if (warning.toLowerCase() === "collector offline") {
    return t("notConnected");
  }
  if (warning.toLowerCase() === "remote initializing") {
    return t("remoteInitializing");
  }
  if (warning.toLowerCase() === "remote resources not loaded") {
    return t("remoteResourcesNotLoaded");
  }
  if (warning.toLowerCase() === "remote resource load failed") {
    return t("remoteResourceLoadFailed");
  }
  return warning;
}

function gbFromMiB(value: number) {
  return (value / 1024).toFixed(1);
}

function formatGpu(host: Host, t: (key: TextKey) => string) {
  if (isRemoteInitializing(host)) {
    return t("remoteInitializing");
  }
  return host.gpusTotal > 0 ? `${host.gpusBusy}/${host.gpusTotal} ${t("runningSuffix")}` : t("notDetected");
}

function isRemoteInitializing(host: Host) {
  return host.warnings.some((warning) => warning.toLowerCase() === "remote initializing");
}

function shortGpuUuid(uuid: string) {
  if (!uuid) {
    return "";
  }
  return uuid.length > 18 ? `${uuid.slice(0, 10)}...${uuid.slice(-6)}` : uuid;
}

function formatGpuProcessOwner(process: GpuProcess) {
  if (process.project || process.runName) {
    return `${process.project || "run"} / ${process.runName || process.runId || process.pid}`;
  }
  if (process.role === "notebook") {
    return `notebook / ${process.pid}`;
  }
  return process.role === "unattributed" ? "unattributed" : (process.role || "-");
}

function logLineSeverity(line: string) {
  const lower = line.toLowerCase();
  if (
    lower.includes("cuda out of memory") ||
    lower.includes("no space left on device") ||
    lower.includes("segmentation fault") ||
    lower.includes("dataloader worker") ||
    /\bkilled\b/.test(lower)
  ) {
    return "error";
  }
  if (lower.includes("warn") || lower.includes("nan") || lower.includes("inf") || lower.includes("nccl")) {
    return "warning";
  }
  if (lower.includes("expmON_event".toLowerCase()) || lower.includes("checkpoint") || lower.includes("eval")) {
    return "info";
  }
  return "";
}

function formatGpuRunUsage(run: Run, t: (key: TextKey) => string) {
  if (run.gpuLabel === "-" || run.gpuUtilPercent <= 0 && run.gpuMemoryGb <= 0) {
    return t("notOccupied");
  }
  const parts = [
    `${run.gpuUtilPercent.toFixed(0)}%`,
    `${run.gpuMemoryGb.toFixed(2)} GB`,
  ];
  if (run.gpuPowerW > 0) {
    parts.push(`${run.gpuPowerW.toFixed(0)} W`);
  }
  if (run.gpuTemperatureC > 0) {
    parts.push(`${run.gpuTemperatureC.toFixed(0)}°C`);
  }
  return parts.join(" / ");
}

function formatMiB(value: number) {
  if (value >= 1024) {
    return `${(value / 1024).toFixed(1)} GB`;
  }
  return `${value.toFixed(0)} MiB`;
}

function formatClock(date: Date) {
  return date.toLocaleTimeString("zh-CN", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit"
  });
}

function numericKeysForRows(rows: Array<Record<string, number | string>>) {
  const keys = new Set<string>();
  rows.forEach((row) => {
    Object.entries(row).forEach(([key, value]) => {
      if (key !== "time" && typeof value === "number" && Number.isFinite(value)) {
        keys.add(key);
      }
    });
  });
  return Array.from(keys);
}

function visualizationKindLabel(kind: string) {
  if (kind === "tensorboard") {
    return "TensorBoard";
  }
  if (kind === "wandb") {
    return "Weights & Biases";
  }
  if (kind === "mlflow") {
    return "MLflow";
  }
  if (kind === "metrics-jsonl") {
    return "JSONL metrics";
  }
  if (kind === "metrics-csv") {
    return "CSV metrics";
  }
  return kind;
}

function resourceLabel(type: ResourceType | "all", t: (key: TextKey) => string) {
  const keyMap: Record<ResourceType | "all", TextKey> = {
    all: "all",
    cpu_only: "cpuOnly",
    gpu: "gpu",
    hybrid: "hybrid",
    unknown: "unknown"
  };
  return t(keyMap[type]);
}

function flattenProcessTree(node: ProcessNode): ProcessNode[] {
  return [node, ...(node.children ?? []).flatMap(flattenProcessTree)];
}

const timeRangeOptions: Array<{ value: TimeRange; label: string; minutes?: number }> = [
  { value: "5m", label: "5m", minutes: 5 },
  { value: "15m", label: "15m", minutes: 15 },
  { value: "1h", label: "1h", minutes: 60 },
  { value: "all", label: "All" }
];

function TimeRangePicker({ value, onChange }: { value: TimeRange; onChange: (value: TimeRange) => void }) {
  const t = useT();
  return (
    <div className="time-range-picker" aria-label="time range">
      {timeRangeOptions.map((option) => (
        <button
          key={option.value}
          className={value === option.value ? "active" : ""}
          onClick={() => onChange(option.value)}
        >
          {option.value === "all" ? t("all") : option.label}
        </button>
      ))}
    </div>
  );
}

function rowTimestampMs(row: Record<string, number | string>) {
  const raw = row.ts ?? row.timestamp;
  if (typeof raw === "number" && Number.isFinite(raw)) {
    return raw > 1_000_000_000_000 ? raw : raw * 1000;
  }
  if (typeof raw === "string" && raw) {
    const parsed = Date.parse(raw);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  if (typeof row.time === "string" && /^\d{2}:\d{2}:\d{2}$/.test(row.time)) {
    const today = new Date();
    const [hour, minute, second] = row.time.split(":").map(Number);
    today.setHours(hour, minute, second, 0);
    return today.getTime();
  }
  return null;
}

function filterSeriesByRange(series: Array<Record<string, number | string>>, range: TimeRange) {
  if (range === "all" || series.length < 2) {
    return series;
  }
  const option = timeRangeOptions.find((item) => item.value === range);
  if (!option?.minutes) {
    return series;
  }
  const stamped = series.map((row) => ({ row, ts: rowTimestampMs(row) })).filter((item): item is { row: Record<string, number | string>; ts: number } => item.ts !== null);
  if (!stamped.length) {
    return series;
  }
  const latest = Math.max(...stamped.map((item) => item.ts));
  const earliest = latest - option.minutes * 60 * 1000;
  const visible = stamped.filter((item) => item.ts >= earliest).map((item) => item.row);
  return visible.length ? visible : series.slice(-1);
}

function resourceHistoryStatus(run: Run, sampleCount: number, t: (key: TextKey) => string) {
  if (sampleCount > 0) {
    return {
      tone: run.status === "running" ? "live" : "stored",
      label: run.status === "running" ? t("samplingNow") : t("historySamples"),
      detail: `${sampleCount} ${t("sampleCount")}`
    };
  }
  if (run.status === "running") {
    return {
      tone: "waiting",
      label: t("waitingForSamples"),
      detail: t("collectorSamplingHint")
    };
  }
  return {
    tone: "missing",
    label: t("noHistorySamples"),
    detail: t("collectorSamplingHint")
  };
}

function makeHostSeries(host: Host) {
  if (host.history?.length) {
    return host.history;
  }
  return [{
    time: formatClock(new Date()),
    read: host.diskRead,
    write: host.diskWrite,
    rx: host.netRx,
    tx: host.netTx
  }];
}

function metricKeys(metrics: Array<Record<string, number | string>>) {
  const keys = new Set<string>();
  metrics.forEach((row) => {
    Object.keys(row).forEach((key) => {
      if (key !== "time" && !key.startsWith("__")) {
        keys.add(key);
      }
    });
  });
  return Array.from(keys);
}

type MetricGroup = {
  id: string;
  title: string;
  subtitle: string;
  keys: string[];
  data: Array<Record<string, number | string>>;
};

type ResourceSeriesConfig = {
  key: string;
  name: string;
};

type ResourceGroup = {
  id: string;
  title: string;
  subtitle: string;
  series: ResourceSeriesConfig[];
  data: Array<Record<string, number | string>>;
};

function groupResourceSeries(series: Array<Record<string, number | string>>, t: (key: TextKey) => string): ResourceGroup[] {
  if (!series.length) {
    return [];
  }
  const groups: Array<{ id: string; title: string; series: ResourceSeriesConfig[] }> = [
    {
      id: "cpu-memory",
      title: t("resourceCpuMemoryGroup"),
      series: [
        { key: "cpu", name: `${t("cpu")} %` },
        { key: "memory", name: `${t("memory")} GB` }
      ]
    },
    {
      id: "disk",
      title: t("resourceDiskGroup"),
      series: [
        { key: "read", name: `${t("read")} MB/s` },
        { key: "write", name: `${t("write")} MB/s` }
      ]
    },
    {
      id: "gpu-usage",
      title: t("resourceGpuUsageGroup"),
      series: [
        { key: "gpuUtil", name: `${t("gpuUtil")} %` },
        { key: "gpuMemory", name: `${t("gpuMemory")} GB` }
      ]
    },
    {
      id: "gpu-thermal",
      title: t("resourceGpuThermalGroup"),
      series: [
        { key: "gpuPower", name: `${t("power")} W` },
        { key: "gpuTemp", name: `${t("temperature")} C` }
      ]
    }
  ];

  return groups
    .map((group) => {
      const visibleSeries = group.series.filter((item) => hasNumericSeries(series, item.key));
      return {
        id: group.id,
        title: group.title,
        subtitle: describeResourceGroup(visibleSeries, series),
        series: visibleSeries,
        data: normalizeSeries(series, visibleSeries.map((item) => item.key))
      };
    })
    .filter((group) => group.series.length);
}

function hasNumericSeries(series: Array<Record<string, number | string>>, key: string) {
  return series.some((row) => Number.isFinite(Number(row[key])));
}

function describeResourceGroup(keys: ResourceSeriesConfig[], series: Array<Record<string, number | string>>) {
  return keys.map((item) => {
    const values = series.map((row) => Number(row[item.key])).filter(Number.isFinite);
    if (!values.length) {
      return `${item.name}: n/a`;
    }
    const min = Math.min(...values);
    const max = Math.max(...values);
    return `${item.name}: ${formatRawSeriesValue(item.key, min, "resource")}-${formatRawSeriesValue(item.key, max, "resource")}`;
  }).join(" · ");
}

function groupMetricSeries(series: Array<Record<string, number | string>>, t: (key: TextKey) => string): MetricGroup[] {
  const keys = metricKeys(series);
  if (!series.length || !keys.length) {
    return [];
  }

  const buckets = new Map<string, { title: string; keys: string[] }>();
  keys.forEach((key) => {
    const bucket = metricBucketForKey(key, series, t);
    const current = buckets.get(bucket.id) ?? { title: bucket.title, keys: [] };
    current.keys.push(key);
    buckets.set(bucket.id, current);
  });

  return Array.from(buckets.entries()).map(([id, bucket]) => ({
    id,
    title: bucket.title,
    subtitle: describeMetricGroup(bucket.keys, series),
    keys: bucket.keys,
    data: normalizeSeries(series, bucket.keys),
  }));
}

function metricBucketForKey(key: string, series: Array<Record<string, number | string>>, t: (key: TextKey) => string) {
  const lower = key.toLowerCase();
  if (/(^|[/_.-])(loss|error|mae|mse|rmse|ce)([/_.-]|$)/.test(lower)) {
    return { id: "loss", title: t("metricLossGroup") };
  }
  if (/(auc|auroc|acc|accuracy|ap|f1|dice|iou|score|balacc)/.test(lower)) {
    return { id: "score", title: t("metricScoreGroup") };
  }
  if (/(^|[/_.-])lr([/_.-]|$)|learning[_-]?rate/.test(lower)) {
    return { id: "lr", title: t("metricLearningRateGroup") };
  }
  if (/(sec|second|time|duration|latency|throughput|speed|ips|samples_per_sec)/.test(lower)) {
    return { id: "time", title: t("metricTimeGroup") };
  }
  return { id: magnitudeBucketForKey(key, series), title: t("metricOtherGroup") };
}

function magnitudeBucketForKey(key: string, series: Array<Record<string, number | string>>) {
  const values = series.map((row) => Number(row[key])).filter((value) => Number.isFinite(value) && value !== 0);
  if (!values.length) {
    return "other-zero";
  }
  const maxAbs = Math.max(...values.map((value) => Math.abs(value)));
  const magnitude = Math.floor(Math.log10(maxAbs));
  return `other-1e${magnitude}`;
}

function describeMetricGroup(keys: string[], series: Array<Record<string, number | string>>) {
  const ranges = keys.map((key) => {
    const values = series.map((row) => Number(row[key])).filter(Number.isFinite);
    if (!values.length) {
      return `${key}: n/a`;
    }
    const min = Math.min(...values);
    const max = Math.max(...values);
    return `${key}: ${formatCompactNumber(min)}-${formatCompactNumber(max)}`;
  });
  return ranges.join(" · ");
}

function formatCompactNumber(value: number) {
  if (Math.abs(value) >= 1000 || Math.abs(value) < 0.001 && value !== 0) {
    return value.toExponential(2);
  }
  return Number.isInteger(value) ? String(value) : value.toPrecision(3);
}

function normalizeSeries(series: Array<Record<string, number | string>>, explicitKeys?: string[]) {
  const keys = explicitKeys ?? metricKeys(series);
  const ranges = Object.fromEntries(
    keys.map((key) => {
      const values = series.map((row) => Number(row[key])).filter(Number.isFinite);
      const min = Math.min(...values);
      const max = Math.max(...values);
      return [key, { min, max }];
    })
  ) as Record<string, { min: number; max: number }>;

  return series.map((row) => {
    const normalized: Record<string, number | string | Record<string, number | string>> = { time: row.time, __raw: row };
    keys.forEach((key) => {
      const value = Number(row[key]);
      const range = ranges[key];
      normalized[key] = range.max === range.min ? clampPercent(value) : ((value - range.min) / (range.max - range.min)) * 100;
    });
    return normalized;
  }) as Array<Record<string, number | string>>;
}

function clampPercent(value: number) {
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.min(100, value));
}

function RawValueTooltip({
  active,
  label,
  payload,
  kind
}: {
  active?: boolean;
  label?: string;
  payload?: Array<{ color?: string; dataKey?: string | number; name?: string; payload?: Record<string, unknown> }>;
  kind: "resource" | "metric";
}) {
  if (!active || !payload?.length) {
    return null;
  }
  const raw = payload[0]?.payload?.__raw as Record<string, number | string> | undefined;
  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      {payload.map((item) => {
        const key = String(item.dataKey);
        if (key === "readTotal" || key === "writeTotal") {
          return null;
        }
        const value = raw?.[key];
        if (typeof value !== "number") {
          return null;
        }
        return (
          <div key={key} style={{ color: item.color }}>
            <span>{item.name ?? key}</span>
            <em>{formatRawSeriesValue(key, value, kind)}</em>
          </div>
        );
      })}
    </div>
  );
}

function formatRawSeriesValue(key: string, value: number, kind: "resource" | "metric") {
  if (kind === "metric") {
    return Number.isInteger(value) ? String(value) : value.toFixed(4);
  }
  if (key === "cpu" || key === "gpuUtil") {
    return `${value.toFixed(1)}%`;
  }
  if (key === "memory" || key === "gpuMemory") {
    return `${value.toFixed(2)} GB`;
  }
  if (key === "read" || key === "write") {
    return `${value.toFixed(2)} MB/s`;
  }
  if (key === "gpuPower") {
    return `${value.toFixed(1)} W`;
  }
  if (key === "gpuTemp") {
    return `${value.toFixed(1)} C`;
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

const chartColors = ["#E7A146", "#7EC7B8", "#7EA4FF", "#D982A6", "#A995FF", "#67D4F2"];

const tooltipStyle = {
  background: "#ffffff",
  border: "1px solid rgba(113, 128, 150, .28)",
  borderRadius: 8,
  color: "#162033"
};

export default App;

