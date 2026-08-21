"use strict";

// ExpMon desktop lightweight SQLite store.
// Runs in the Electron main process and persists UI state plus sampled
// history (power / host / run snapshots) across window refreshes and app
// restarts. Uses the SQLite engine built into Node (node:sqlite), so there
// are no native modules to rebuild or ship.
//
// Record semantics: sampled kinds (host / run) treat one *continuous*
// monitoring period as a single record — consecutive appends within the
// merge window update the same row instead of inserting a new one, and an
// interruption longer than the window starts the next record. Power keeps
// one row per sample (the chart needs the series) and counts episodes by
// gap analysis; events are one row per action.

const { DatabaseSync } = require("node:sqlite");
const fs = require("node:fs");
const path = require("node:path");

const HISTORY_KINDS = new Set(["power", "host", "run", "event", "ui"]);

// Maximum number of rows kept per kind; older rows are pruned on write.
const KIND_LIMITS = {
  power: 20000,
  host: 10000,
  run: 5000,
  event: 2000,
  ui: 500,
};

const MAX_PAYLOAD_CHARS = 512 * 1024;
const KV_KEY_PATTERN = /^[a-z0-9_.-]{1,120}$/i;

// Kinds whose consecutive samples merge into one record per episode.
const MERGE_KINDS = new Set(["host", "run"]);
// A gap longer than this (ms) between samples starts a new record/episode.
const MERGE_WINDOW_MS = 2 * 60 * 1000;

function isValidKind(kind) {
  return HISTORY_KINDS.has(kind);
}

function createStore(dbPath, options) {
  fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  const opts = options || {};
  const mergeWindowMs = Number(opts.mergeWindowMs) > 0 ? Number(opts.mergeWindowMs) : MERGE_WINDOW_MS;
  const mergeKinds = opts.mergeKinds instanceof Set ? opts.mergeKinds : MERGE_KINDS;

  const db = new DatabaseSync(dbPath);
  db.exec("PRAGMA journal_mode = WAL");
  db.exec("PRAGMA synchronous = NORMAL");
  db.exec("PRAGMA user_version = 2");
  db.exec(`
    CREATE TABLE IF NOT EXISTS kv (
      key TEXT PRIMARY KEY,
      value TEXT NOT NULL,
      updated_at TEXT NOT NULL
    )
  `);
  db.exec(`
    CREATE TABLE IF NOT EXISTS history (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      kind TEXT NOT NULL,
      recorded_at TEXT NOT NULL,
      payload TEXT NOT NULL
    )
  `);
  db.exec("CREATE INDEX IF NOT EXISTS idx_history_kind_id ON history(kind, id)");

  const insertHistory = db.prepare(
    "INSERT INTO history (kind, recorded_at, payload) VALUES (?, ?, ?)"
  );
  const selectLatestRow = db.prepare(
    "SELECT id, recorded_at FROM history WHERE kind = ? ORDER BY id DESC LIMIT 1"
  );
  const updateRow = db.prepare("UPDATE history SET payload = ?, recorded_at = ? WHERE id = ?");
  const selectRowsChronological = db.prepare(
    "SELECT id, recorded_at FROM history WHERE kind = ? ORDER BY id ASC"
  );
  const deleteRow = db.prepare("DELETE FROM history WHERE id = ?");
  const selectKv = db.prepare("SELECT value FROM kv WHERE key = ?");
  const upsertKv = db.prepare(`
    INSERT INTO kv (key, value, updated_at) VALUES (?, ?, ?)
    ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
  `);
  const pruneStmt = db.prepare(`
    DELETE FROM history
    WHERE kind = ? AND id NOT IN (
      SELECT id FROM history WHERE kind = ? ORDER BY id DESC LIMIT ?
    )
  `);
  const selectHistory = db.prepare(`
    SELECT id, kind, recorded_at, payload
    FROM history
    WHERE kind = ? AND (? IS NULL OR id < ?)
    ORDER BY id DESC
    LIMIT ?
  `);
  const deleteKind = db.prepare("DELETE FROM history WHERE kind = ?");
  const countAll = db.prepare("SELECT kind, COUNT(*) AS count FROM history GROUP BY kind ORDER BY kind");
  const countKv = db.prepare("SELECT COUNT(*) AS count FROM kv");

  // One-time compaction of legacy data written before episode merging:
  // for merge kinds, collapse consecutive rows (gap <= window) into the
  // newest payload of each episode.
  function compactHistory() {
    for (const kind of mergeKinds) {
      const rows = selectRowsChronological.all(kind);
      let keptId = null;
      let keptTs = 0;
      for (const row of rows) {
        const ts = Date.parse(row.recorded_at);
        if (keptId !== null && ts - keptTs <= mergeWindowMs) {
          deleteRow.run(keptId);
        }
        keptId = Number(row.id);
        keptTs = ts;
      }
    }
  }
  compactHistory();

  function getKv(key) {
    const row = selectKv.get(key);
    return row ? row.value : null;
  }

  function setKv(key, value) {
    if (typeof key !== "string" || !KV_KEY_PATTERN.test(key)) {
      throw new Error(`invalid kv key: ${key}`);
    }
    if (typeof value !== "string") {
      throw new Error("kv value must be a string");
    }
    if (value.length > MAX_PAYLOAD_CHARS) {
      throw new Error("kv value too large");
    }
    upsertKv.run(key, value, new Date().toISOString());
  }

  function append(kind, payload) {
    if (!isValidKind(kind)) {
      throw new Error(`invalid history kind: ${kind}`);
    }
    let text = payload;
    if (typeof payload !== "string") {
      text = JSON.stringify(payload);
    }
    if (typeof text !== "string" || text.length > MAX_PAYLOAD_CHARS) {
      throw new Error("history payload must be a string of reasonable size");
    }
    const nowIso = new Date().toISOString();
    if (mergeKinds.has(kind)) {
      const latest = selectLatestRow.get(kind);
      if (latest && Date.now() - Date.parse(latest.recorded_at) <= mergeWindowMs) {
        updateRow.run(text, nowIso, latest.id);
        return { kind, merged: true, id: Number(latest.id) };
      }
    }
    insertHistory.run(kind, nowIso, text);
    const limit = KIND_LIMITS[kind] ?? 5000;
    pruneStmt.run(kind, kind, limit);
    return { kind, merged: false };
  }

  // Returns rows oldest-first (id ascending) so charts can append directly.
  function list(kind, options) {
    if (!isValidKind(kind)) {
      throw new Error(`invalid history kind: ${kind}`);
    }
    const opts = options || {};
    const limit = Math.min(Math.max(Number(opts.limit) || 1000, 1), 20000);
    const beforeId = opts.beforeId == null ? null : Number(opts.beforeId);
    // The query has four placeholders; beforeId is bound twice (the NULL
    // check and the id < ? comparison).
    const rows = selectHistory.all(kind, beforeId, beforeId, limit);
    rows.reverse();
    return rows.map((row) => ({
      id: Number(row.id),
      kind: row.kind,
      recordedAt: row.recorded_at,
      payload: row.payload,
    }));
  }

  // Number of continuous episodes for a kind: rows whose gap from the
  // previous row exceeds the merge window start a new episode.
  function countEpisodes(kind) {
    const rows = selectRowsChronological.all(kind);
    let episodes = 0;
    let previousTs = 0;
    for (const row of rows) {
      const ts = Date.parse(row.recorded_at);
      if (previousTs === 0 || ts - previousTs > mergeWindowMs) {
        episodes += 1;
      }
      previousTs = ts;
    }
    return episodes;
  }

  function clear(kind) {
    if (kind != null && !isValidKind(kind)) {
      throw new Error(`invalid history kind: ${kind}`);
    }
    if (kind == null) {
      db.exec("DELETE FROM history");
      return { deleted: true };
    }
    const result = deleteKind.run(kind);
    return { deleted: Number(result.changes) > 0 };
  }

  function stats() {
    const rows = countAll.all().map((row) => ({
      kind: row.kind,
      count: Number(row.count),
    }));
    let episodesTotal = 0;
    const kinds = rows.map((row) => {
      const episodes = row.kind === "event" ? row.count : countEpisodes(row.kind);
      episodesTotal += episodes;
      return {
        kind: row.kind,
        count: row.count,
        episodes,
        limit: KIND_LIMITS[row.kind] ?? null,
      };
    });
    return {
      kvCount: Number(countKv.get().count),
      kinds,
      total: rows.reduce((sum, row) => sum + row.count, 0),
      episodesTotal,
      mergeWindowMs,
      dbPath,
      dbBytes: fs.existsSync(dbPath) ? fs.statSync(dbPath).size : 0,
    };
  }

  function close() {
    try {
      db.close();
    } catch {
      // Already closed.
    }
  }

  return { getKv, setKv, append, list, clear, stats, close, dbPath, isValidKind };
}

module.exports = { createStore, HISTORY_KINDS, KIND_LIMITS, MERGE_KINDS, MERGE_WINDOW_MS, isValidKind };
