// Renderer-side helpers for the ExpMon desktop SQLite history store.
// All functions are safe no-ops / empty results when the app runs in a
// plain browser (vite dev / preview) where window.expmonDesktop is absent.

export type DbHistoryRow = {
  id: number;
  kind: string;
  recordedAt: string;
  payload: string;
};

export type DbKindStats = {
  kind: string;
  count: number;
  /** Continuous episodes (host/run/power); equals count for merged kinds. */
  episodes?: number;
  limit: number | null;
};

export type DbStats = {
  kvCount: number;
  kinds: DbKindStats[];
  /** Raw history rows across kinds. */
  total: number;
  /** Continuous episodes across kinds — the "local history" counter. */
  episodesTotal?: number;
  /** Gap (ms) after which a new record starts. */
  mergeWindowMs?: number;
  dbPath: string;
  dbBytes: number;
};

export type DesktopDbApi = {
  get: (key: string) => Promise<string | null>;
  set: (key: string, value: string) => Promise<boolean>;
  append: (kind: string, payload: string) => Promise<{ kind: string }>;
  list: (kind: string, options?: { limit?: number; beforeId?: number }) => Promise<DbHistoryRow[]>;
  clear: (kind?: string) => Promise<{ deleted: boolean }>;
  stats: () => Promise<DbStats>;
};

export type ExpMonDesktopBridge = {
  collectorUrl: string;
  apiToken: string;
  platform: string;
  version: string;
  db?: DesktopDbApi;
  pickDirectory?: () => Promise<{ canceled: boolean; path?: string }>;
};

export const HISTORY_KIND = {
  power: "power",
  host: "host",
  run: "run",
  event: "event",
  ui: "ui",
} as const;

export const UI_KV = {
  uiState: "ui.state",
  lastSnapshot: "ui.lastSnapshot",
} as const;

const MAX_STORED_UI_BYTES = 200 * 1024;
const MAX_HISTORY_PAYLOAD_BYTES = 400 * 1024;

function bridge(): ExpMonDesktopBridge | undefined {
  return (window as { expmonDesktop?: ExpMonDesktopBridge }).expmonDesktop;
}

export function dbAvailable(): boolean {
  return Boolean(bridge()?.db);
}

export async function dbGetJson<T>(key: string): Promise<T | null> {
  try {
    const raw = await bridge()?.db?.get(key);
    if (raw == null) {
      return null;
    }
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export async function dbSetJson(key: string, value: unknown): Promise<boolean> {
  try {
    const raw = JSON.stringify(value);
    if (raw.length > MAX_STORED_UI_BYTES) {
      return false;
    }
    return Boolean(await bridge()?.db?.set(key, raw));
  } catch {
    return false;
  }
}

/** Fire-and-forget append; never throws. */
export function dbAppend(kind: string, payload: unknown): void {
  try {
    const raw = typeof payload === "string" ? payload : JSON.stringify(payload);
    if (raw.length > MAX_HISTORY_PAYLOAD_BYTES) {
      return;
    }
    void bridge()?.db?.append(kind, raw).catch(() => undefined);
  } catch {
    // No-op outside the desktop client.
  }
}

export async function dbList(kind: string, options?: { limit?: number; beforeId?: number }): Promise<DbHistoryRow[]> {
  try {
    return (await bridge()?.db?.list(kind, options)) ?? [];
  } catch {
    return [];
  }
}

export async function dbClear(kind?: string): Promise<boolean> {
  try {
    return Boolean(await bridge()?.db?.clear(kind));
  } catch {
    return false;
  }
}

export async function dbStats(): Promise<DbStats | null> {
  try {
    return (await bridge()?.db?.stats()) ?? null;
  } catch {
    return null;
  }
}
