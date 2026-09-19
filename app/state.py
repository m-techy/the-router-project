from __future__ import annotations

import datetime as dt
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .vault import SecretVault

SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, request_id TEXT,
 provider_id TEXT NOT NULL, model_id TEXT NOT NULL, success INTEGER NOT NULL,
 status_code INTEGER, prompt_tokens INTEGER NOT NULL DEFAULT 0,
 completion_tokens INTEGER NOT NULL DEFAULT 0, total_tokens INTEGER NOT NULL DEFAULT 0,
 latency_ms REAL, fallback_count INTEGER NOT NULL DEFAULT 0, error TEXT
);
CREATE INDEX IF NOT EXISTS idx_usage_provider_ts ON usage_events(provider_id, ts);
CREATE INDEX IF NOT EXISTS idx_usage_request_id ON usage_events(request_id);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage_events(ts);

CREATE TABLE IF NOT EXISTS provider_runtime (
 provider_id TEXT PRIMARY KEY, blocked_until REAL NOT NULL DEFAULT 0,
 successes INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0,
 latency_ema_ms REAL, certification_state TEXT NOT NULL DEFAULT 'unknown',
 certification_note TEXT, last_probe_at REAL, last_probe_ok INTEGER,
 provider_quota_json TEXT, updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS model_runtime (
 provider_id TEXT NOT NULL,
 model_id TEXT NOT NULL,
 blocked_until REAL NOT NULL DEFAULT 0,
 successes INTEGER NOT NULL DEFAULT 0,
 failures INTEGER NOT NULL DEFAULT 0,
 latency_ema_ms REAL,
 updated_at REAL NOT NULL,
 PRIMARY KEY(provider_id, model_id)
);

CREATE TABLE IF NOT EXISTS settings (
 key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS local_secrets (
 key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS project_keys (
 id TEXT PRIMARY KEY,
 name TEXT NOT NULL,
 key_hash TEXT UNIQUE NOT NULL,
 key_prefix TEXT NOT NULL,
 daily_request_limit INTEGER,
 daily_token_limit INTEGER,
 enabled INTEGER NOT NULL DEFAULT 1,
 created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_project_keys_hash ON project_keys(key_hash);

CREATE TABLE IF NOT EXISTS project_usage (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 ts REAL NOT NULL,
 project_id TEXT NOT NULL,
 requests INTEGER NOT NULL DEFAULT 1,
 tokens INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_project_usage_project_ts
 ON project_usage(project_id, ts);
"""


class StateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._vault = SecretVault.from_env()
        with self._conn:
            self._conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def record_usage(self, **event: Any) -> None:
        cols = [
            "ts",
            "request_id",
            "provider_id",
            "model_id",
            "success",
            "status_code",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "latency_ms",
            "fallback_count",
            "error",
        ]
        vals = [event.get(c) for c in cols]
        with self._lock, self._conn:
            self._conn.execute(
                f"INSERT INTO usage_events ({','.join(cols)}) "
                f"VALUES ({','.join('?' for _ in cols)})",
                vals,
            )

    def recent_usage(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM usage_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def usage_after_id(self, last_id: int, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM usage_events WHERE id>? ORDER BY id LIMIT ?",
                (last_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def usage_since(self, provider_id: str, since: float) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM usage_events WHERE provider_id=? AND ts>=? ORDER BY ts",
                (provider_id, since),
            ).fetchall()
        return [dict(r) for r in rows]

    def request_trace(self, request_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM usage_events WHERE request_id=? ORDER BY id",
                (request_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def usage_summary(self, since: float) -> dict[str, Any]:
        with self._lock:
            totals = self._conn.execute(
                """
                SELECT COUNT(*) requests,
                       SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) successes,
                       COALESCE(SUM(total_tokens),0) tokens,
                       COALESCE(AVG(latency_ms),0) avg_latency_ms
                FROM usage_events WHERE ts>=?
                """,
                (since,),
            ).fetchone()
            rows = self._conn.execute(
                """
                SELECT provider_id,
                       COUNT(*) requests,
                       SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) successes,
                       COALESCE(SUM(total_tokens),0) tokens,
                       COALESCE(AVG(latency_ms),0) avg_latency_ms
                FROM usage_events WHERE ts>=?
                GROUP BY provider_id
                ORDER BY requests DESC
                """,
                (since,),
            ).fetchall()
        return {"totals": dict(totals), "by_provider": [dict(r) for r in rows]}

    def get_runtime(self, provider_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM provider_runtime WHERE provider_id=?",
                (provider_id,),
            ).fetchone()
        return dict(row) if row else None

    def upsert_runtime(self, provider_id: str, **values: Any) -> None:
        old = self.get_runtime(provider_id) or {}
        data = {
            "blocked_until": old.get("blocked_until", 0),
            "successes": old.get("successes", 0),
            "failures": old.get("failures", 0),
            "latency_ema_ms": old.get("latency_ema_ms"),
            "certification_state": old.get("certification_state", "unknown"),
            "certification_note": old.get("certification_note"),
            "last_probe_at": old.get("last_probe_at"),
            "last_probe_ok": old.get("last_probe_ok"),
            "provider_quota_json": old.get("provider_quota_json"),
        }
        data.update(values)
        if isinstance(data.get("provider_quota_json"), (dict, list)):
            data["provider_quota_json"] = json.dumps(data["provider_quota_json"])
        data["updated_at"] = time.time()

        cols = [
            "provider_id",
            "blocked_until",
            "successes",
            "failures",
            "latency_ema_ms",
            "certification_state",
            "certification_note",
            "last_probe_at",
            "last_probe_ok",
            "provider_quota_json",
            "updated_at",
        ]
        params = [provider_id] + [data.get(c) for c in cols[1:]]
        with self._lock, self._conn:
            self._conn.execute(
                f"""
                INSERT INTO provider_runtime ({','.join(cols)})
                VALUES ({','.join('?' for _ in cols)})
                ON CONFLICT(provider_id) DO UPDATE SET
                {','.join(f'{c}=excluded.{c}' for c in cols[1:])}
                """,
                params,
            )

    def all_runtime(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM provider_runtime ORDER BY provider_id"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_model_runtime(self, provider_id: str, model_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM model_runtime WHERE provider_id=? AND model_id=?",
                (provider_id, model_id),
            ).fetchone()
        return dict(row) if row else None

    def upsert_model_runtime(
        self,
        provider_id: str,
        model_id: str,
        **values: Any,
    ) -> None:
        old = self.get_model_runtime(provider_id, model_id) or {}
        data = {
            "blocked_until": old.get("blocked_until", 0),
            "successes": old.get("successes", 0),
            "failures": old.get("failures", 0),
            "latency_ema_ms": old.get("latency_ema_ms"),
        }
        data.update(values)
        data["updated_at"] = time.time()
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO model_runtime(
                    provider_id,model_id,blocked_until,successes,failures,latency_ema_ms,updated_at
                ) VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(provider_id,model_id) DO UPDATE SET
                    blocked_until=excluded.blocked_until,
                    successes=excluded.successes,
                    failures=excluded.failures,
                    latency_ema_ms=excluded.latency_ema_ms,
                    updated_at=excluded.updated_at
                """,
                (
                    provider_id,
                    model_id,
                    data["blocked_until"],
                    data["successes"],
                    data["failures"],
                    data["latency_ema_ms"],
                    data["updated_at"],
                ),
            )

    def all_model_runtime(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM model_runtime ORDER BY provider_id, model_id"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM settings WHERE key=?",
                (key,),
            ).fetchone()
        if not row:
            return default
        raw = row["value"]
        try:
            return json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return raw

    def set_setting(self, key: str, value: Any) -> None:
        encoded = json.dumps(value)
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO settings(key,value,updated_at) VALUES(?,?,?)
                ON CONFLICT(key) DO UPDATE SET
                  value=excluded.value,
                  updated_at=excluded.updated_at
                """,
                (key, encoded, time.time()),
            )

    def all_settings(self) -> dict[str, Any]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT key,value FROM settings ORDER BY key"
            ).fetchall()
        result: dict[str, Any] = {}
        for row in rows:
            raw = row["value"]
            try:
                result[str(row["key"])] = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                result[str(row["key"])] = raw
        return result

    def delete_setting(self, key: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM settings WHERE key=?", (key,))

    def get_secret(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM local_secrets WHERE key=?",
                (key,),
            ).fetchone()
        if not row:
            return None

        stored = str(row["value"])
        decoded = self._vault.decrypt(stored)
        if decoded is None:
            return None

        if self._vault.enabled and not self._vault.is_encrypted(stored):
            self.set_secret(key, decoded)
        return decoded

    def set_secret(self, key: str, value: str) -> None:
        stored = self._vault.encrypt(value)
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO local_secrets(key,value,updated_at) VALUES(?,?,?)
                ON CONFLICT(key) DO UPDATE SET
                  value=excluded.value,
                  updated_at=excluded.updated_at
                """,
                (key, stored, time.time()),
            )

    def delete_secret(self, key: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM local_secrets WHERE key=?", (key,))

    def secret_keys(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT key FROM local_secrets ORDER BY key"
            ).fetchall()
        return [str(r["key"]) for r in rows]

    def vault_status(self) -> dict[str, Any]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT value FROM local_secrets"
            ).fetchall()
        encrypted = sum(
            1 for row in rows if self._vault.is_encrypted(str(row["value"]))
        )
        return {
            "enabled": self._vault.enabled,
            "stored_secrets": len(rows),
            "encrypted_secrets": encrypted,
        }

    def create_project(
        self,
        project_id: str,
        *,
        name: str,
        key_hash: str,
        key_prefix: str,
        daily_request_limit: int | None,
        daily_token_limit: int | None,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO project_keys(
                    id,name,key_hash,key_prefix,daily_request_limit,
                    daily_token_limit,enabled,created_at
                ) VALUES(?,?,?,?,?,?,1,?)
                """,
                (
                    project_id,
                    name,
                    key_hash,
                    key_prefix,
                    daily_request_limit,
                    daily_token_limit,
                    time.time(),
                ),
            )

    def list_projects(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT id,name,key_prefix,daily_request_limit,daily_token_limit,
                       enabled,created_at
                FROM project_keys
                ORDER BY created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_project_by_hash(self, key_hash: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM project_keys WHERE key_hash=? AND enabled=1",
                (key_hash,),
            ).fetchone()
        return dict(row) if row else None

    def delete_project(self, project_id: str) -> bool:
        with self._lock, self._conn:
            cursor = self._conn.execute(
                "DELETE FROM project_keys WHERE id=?",
                (project_id,),
            )
        return cursor.rowcount > 0

    def _utc_day_start(self) -> float:
        now = dt.datetime.now(dt.timezone.utc)
        return now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        ).timestamp()

    def project_usage_today(self, project_id: str) -> dict[str, int]:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT COALESCE(SUM(requests),0) requests,
                       COALESCE(SUM(tokens),0) tokens
                FROM project_usage
                WHERE project_id=? AND ts>=?
                """,
                (project_id, self._utc_day_start()),
            ).fetchone()
        return {
            "requests": int(row["requests"] or 0),
            "tokens": int(row["tokens"] or 0),
        }

    def record_project_usage(
        self,
        project_id: str,
        *,
        requests: int = 1,
        tokens: int = 0,
    ) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                """
                INSERT INTO project_usage(ts,project_id,requests,tokens)
                VALUES(?,?,?,?)
                """,
                (time.time(), project_id, max(0, requests), max(0, tokens)),
            )
