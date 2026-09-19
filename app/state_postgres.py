from __future__ import annotations

import datetime as dt
import json
import threading
import time
from typing import Any

import psycopg
from psycopg.rows import dict_row

from .vault import SecretVault

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_events (
 id BIGSERIAL PRIMARY KEY,
 ts DOUBLE PRECISION NOT NULL,
 request_id TEXT,
 provider_id TEXT NOT NULL,
 model_id TEXT NOT NULL,
 success BOOLEAN NOT NULL,
 status_code INTEGER,
 prompt_tokens BIGINT NOT NULL DEFAULT 0,
 completion_tokens BIGINT NOT NULL DEFAULT 0,
 total_tokens BIGINT NOT NULL DEFAULT 0,
 latency_ms DOUBLE PRECISION,
 fallback_count INTEGER NOT NULL DEFAULT 0,
 error TEXT
);
CREATE INDEX IF NOT EXISTS idx_usage_provider_ts ON usage_events(provider_id, ts);
CREATE INDEX IF NOT EXISTS idx_usage_request_id ON usage_events(request_id);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage_events(ts);

CREATE TABLE IF NOT EXISTS provider_runtime (
 provider_id TEXT PRIMARY KEY,
 blocked_until DOUBLE PRECISION NOT NULL DEFAULT 0,
 successes BIGINT NOT NULL DEFAULT 0,
 failures BIGINT NOT NULL DEFAULT 0,
 latency_ema_ms DOUBLE PRECISION,
 certification_state TEXT NOT NULL DEFAULT 'unknown',
 certification_note TEXT,
 last_probe_at DOUBLE PRECISION,
 last_probe_ok BOOLEAN,
 provider_quota_json TEXT,
 updated_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS model_runtime (
 provider_id TEXT NOT NULL,
 model_id TEXT NOT NULL,
 blocked_until DOUBLE PRECISION NOT NULL DEFAULT 0,
 successes BIGINT NOT NULL DEFAULT 0,
 failures BIGINT NOT NULL DEFAULT 0,
 latency_ema_ms DOUBLE PRECISION,
 updated_at DOUBLE PRECISION NOT NULL,
 PRIMARY KEY(provider_id, model_id)
);

CREATE TABLE IF NOT EXISTS settings (
 key TEXT PRIMARY KEY,
 value TEXT NOT NULL,
 updated_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS local_secrets (
 key TEXT PRIMARY KEY,
 value TEXT NOT NULL,
 updated_at DOUBLE PRECISION NOT NULL
);

CREATE TABLE IF NOT EXISTS project_keys (
 id TEXT PRIMARY KEY,
 name TEXT NOT NULL,
 key_hash TEXT UNIQUE NOT NULL,
 key_prefix TEXT NOT NULL,
 daily_request_limit BIGINT,
 daily_token_limit BIGINT,
 enabled BOOLEAN NOT NULL DEFAULT TRUE,
 created_at DOUBLE PRECISION NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_project_keys_hash ON project_keys(key_hash);

CREATE TABLE IF NOT EXISTS project_usage (
 id BIGSERIAL PRIMARY KEY,
 ts DOUBLE PRECISION NOT NULL,
 project_id TEXT NOT NULL,
 requests BIGINT NOT NULL DEFAULT 1,
 tokens BIGINT NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_project_usage_project_ts
 ON project_usage(project_id, ts);
"""


class PostgresStateStore:
    backend_name = "postgres"
    durable = True

    def __init__(self, dsn: str):
        if not dsn:
            raise ValueError("Postgres state backend requires DATABASE_URL or POSTGRES_URL")
        self.dsn = dsn
        self._lock = threading.RLock()
        self._vault = SecretVault.from_env()
        self._conn = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)
        self._apply_schema()

    def _apply_schema(self) -> None:
        with self._lock:
            with self._conn.cursor() as cur:
                for statement in POSTGRES_SCHEMA.split(";"):
                    sql = statement.strip()
                    if sql:
                        cur.execute(sql)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def record_usage(self, **event: Any) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO usage_events(
                    ts,request_id,provider_id,model_id,success,status_code,
                    prompt_tokens,completion_tokens,total_tokens,latency_ms,
                    fallback_count,error
                ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    event.get("ts"),
                    event.get("request_id"),
                    event.get("provider_id"),
                    event.get("model_id"),
                    bool(event.get("success")),
                    event.get("status_code"),
                    event.get("prompt_tokens") or 0,
                    event.get("completion_tokens") or 0,
                    event.get("total_tokens") or 0,
                    event.get("latency_ms"),
                    event.get("fallback_count") or 0,
                    event.get("error"),
                ),
            )

    def recent_usage(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM usage_events ORDER BY id DESC LIMIT %s",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def usage_after_id(self, last_id: int, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM usage_events WHERE id>%s ORDER BY id LIMIT %s",
                (last_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def usage_since(self, provider_id: str, since: float) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM usage_events WHERE provider_id=%s AND ts>=%s ORDER BY ts",
                (provider_id, since),
            ).fetchall()
        return [dict(row) for row in rows]

    def request_trace(self, request_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM usage_events WHERE request_id=%s ORDER BY id",
                (request_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def usage_summary(self, since: float) -> dict[str, Any]:
        with self._lock:
            totals = self._conn.execute(
                """
                SELECT COUNT(*) requests,
                       SUM(CASE WHEN success THEN 1 ELSE 0 END) successes,
                       COALESCE(SUM(total_tokens),0) tokens,
                       COALESCE(AVG(latency_ms),0) avg_latency_ms
                FROM usage_events WHERE ts>=%s
                """,
                (since,),
            ).fetchone()
            rows = self._conn.execute(
                """
                SELECT provider_id,
                       COUNT(*) requests,
                       SUM(CASE WHEN success THEN 1 ELSE 0 END) successes,
                       COALESCE(SUM(total_tokens),0) tokens,
                       COALESCE(AVG(latency_ms),0) avg_latency_ms
                FROM usage_events WHERE ts>=%s
                GROUP BY provider_id
                ORDER BY requests DESC
                """,
                (since,),
            ).fetchall()
        return {
            "totals": dict(totals or {}),
            "by_provider": [dict(row) for row in rows],
        }

    def get_runtime(self, provider_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM provider_runtime WHERE provider_id=%s",
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
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO provider_runtime(
                    provider_id,blocked_until,successes,failures,latency_ema_ms,
                    certification_state,certification_note,last_probe_at,last_probe_ok,
                    provider_quota_json,updated_at
                ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(provider_id) DO UPDATE SET
                    blocked_until=EXCLUDED.blocked_until,
                    successes=EXCLUDED.successes,
                    failures=EXCLUDED.failures,
                    latency_ema_ms=EXCLUDED.latency_ema_ms,
                    certification_state=EXCLUDED.certification_state,
                    certification_note=EXCLUDED.certification_note,
                    last_probe_at=EXCLUDED.last_probe_at,
                    last_probe_ok=EXCLUDED.last_probe_ok,
                    provider_quota_json=EXCLUDED.provider_quota_json,
                    updated_at=EXCLUDED.updated_at
                """,
                (
                    provider_id,
                    data["blocked_until"],
                    data["successes"],
                    data["failures"],
                    data["latency_ema_ms"],
                    data["certification_state"],
                    data["certification_note"],
                    data["last_probe_at"],
                    None
                    if data["last_probe_ok"] is None
                    else bool(data["last_probe_ok"]),
                    data["provider_quota_json"],
                    data["updated_at"],
                ),
            )

    def all_runtime(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM provider_runtime ORDER BY provider_id"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_model_runtime(self, provider_id: str, model_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT * FROM model_runtime
                WHERE provider_id=%s AND model_id=%s
                """,
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
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO model_runtime(
                    provider_id,model_id,blocked_until,successes,failures,
                    latency_ema_ms,updated_at
                ) VALUES(%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(provider_id,model_id) DO UPDATE SET
                    blocked_until=EXCLUDED.blocked_until,
                    successes=EXCLUDED.successes,
                    failures=EXCLUDED.failures,
                    latency_ema_ms=EXCLUDED.latency_ema_ms,
                    updated_at=EXCLUDED.updated_at
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
        return [dict(row) for row in rows]

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM settings WHERE key=%s",
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
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO settings(key,value,updated_at) VALUES(%s,%s,%s)
                ON CONFLICT(key) DO UPDATE SET
                    value=EXCLUDED.value,
                    updated_at=EXCLUDED.updated_at
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
        with self._lock:
            self._conn.execute("DELETE FROM settings WHERE key=%s", (key,))

    def get_secret(self, key: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM local_secrets WHERE key=%s",
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
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO local_secrets(key,value,updated_at) VALUES(%s,%s,%s)
                ON CONFLICT(key) DO UPDATE SET
                    value=EXCLUDED.value,
                    updated_at=EXCLUDED.updated_at
                """,
                (key, stored, time.time()),
            )

    def delete_secret(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM local_secrets WHERE key=%s", (key,))

    def secret_keys(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT key FROM local_secrets ORDER BY key"
            ).fetchall()
        return [str(row["key"]) for row in rows]

    def vault_status(self) -> dict[str, Any]:
        with self._lock:
            rows = self._conn.execute("SELECT value FROM local_secrets").fetchall()
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
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO project_keys(
                    id,name,key_hash,key_prefix,daily_request_limit,
                    daily_token_limit,enabled,created_at
                ) VALUES(%s,%s,%s,%s,%s,%s,TRUE,%s)
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
                "SELECT * FROM project_keys WHERE key_hash=%s AND enabled=TRUE",
                (key_hash,),
            ).fetchone()
        return dict(row) if row else None

    def delete_project(self, project_id: str) -> bool:
        with self._lock:
            cursor = self._conn.execute(
                "DELETE FROM project_keys WHERE id=%s",
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
                WHERE project_id=%s AND ts>=%s
                """,
                (project_id, self._utc_day_start()),
            ).fetchone()
        return {
            "requests": int((row or {}).get("requests") or 0),
            "tokens": int((row or {}).get("tokens") or 0),
        }

    def record_project_usage(
        self,
        project_id: str,
        *,
        requests: int = 1,
        tokens: int = 0,
    ) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO project_usage(ts,project_id,requests,tokens)
                VALUES(%s,%s,%s,%s)
                """,
                (time.time(), project_id, max(0, requests), max(0, tokens)),
            )
