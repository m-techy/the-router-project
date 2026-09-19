from __future__ import annotations
import json, sqlite3, threading, time
from pathlib import Path
from typing import Any

SCHEMA="""
CREATE TABLE IF NOT EXISTS usage_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL NOT NULL, request_id TEXT,
 provider_id TEXT NOT NULL, model_id TEXT NOT NULL, success INTEGER NOT NULL,
 status_code INTEGER, prompt_tokens INTEGER NOT NULL DEFAULT 0,
 completion_tokens INTEGER NOT NULL DEFAULT 0, total_tokens INTEGER NOT NULL DEFAULT 0,
 latency_ms REAL, fallback_count INTEGER NOT NULL DEFAULT 0, error TEXT
);
CREATE INDEX IF NOT EXISTS idx_usage_provider_ts ON usage_events(provider_id, ts);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage_events(ts);
CREATE TABLE IF NOT EXISTS provider_runtime (
 provider_id TEXT PRIMARY KEY, blocked_until REAL NOT NULL DEFAULT 0,
 successes INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0,
 latency_ema_ms REAL, certification_state TEXT NOT NULL DEFAULT 'unknown',
 certification_note TEXT, last_probe_at REAL, last_probe_ok INTEGER,
 provider_quota_json TEXT, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
 key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at REAL NOT NULL
);
"""

class StateStore:
    def __init__(self,path:str|Path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)
        self._lock=threading.RLock()
        self._conn=sqlite3.connect(self.path,check_same_thread=False)
        self._conn.row_factory=sqlite3.Row
        with self._conn:self._conn.executescript(SCHEMA)
    def close(self):
        with self._lock:self._conn.close()
    def record_usage(self,**event:Any):
        cols=["ts","request_id","provider_id","model_id","success","status_code","prompt_tokens","completion_tokens","total_tokens","latency_ms","fallback_count","error"]
        vals=[event.get(c) for c in cols]
        with self._lock,self._conn:
            self._conn.execute(f"INSERT INTO usage_events ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})",vals)
    def recent_usage(self,limit:int=100):
        with self._lock:rows=self._conn.execute("SELECT * FROM usage_events ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
        return [dict(r) for r in rows]
    def usage_since(self,provider_id:str,since:float):
        with self._lock:rows=self._conn.execute("SELECT * FROM usage_events WHERE provider_id=? AND ts>=? ORDER BY ts",(provider_id,since)).fetchall()
        return [dict(r) for r in rows]
    def usage_summary(self,since:float):
        with self._lock:
            totals=self._conn.execute("""SELECT COUNT(*) requests,SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) successes,COALESCE(SUM(total_tokens),0) tokens,COALESCE(AVG(latency_ms),0) avg_latency_ms FROM usage_events WHERE ts>=?""",(since,)).fetchone()
            rows=self._conn.execute("""SELECT provider_id,COUNT(*) requests,SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) successes,COALESCE(SUM(total_tokens),0) tokens,COALESCE(AVG(latency_ms),0) avg_latency_ms FROM usage_events WHERE ts>=? GROUP BY provider_id ORDER BY requests DESC""",(since,)).fetchall()
        return {"totals":dict(totals),"by_provider":[dict(r) for r in rows]}
    def get_runtime(self,provider_id:str):
        with self._lock:r=self._conn.execute("SELECT * FROM provider_runtime WHERE provider_id=?",(provider_id,)).fetchone()
        return dict(r) if r else None
    def upsert_runtime(self,provider_id:str,**values:Any):
        old=self.get_runtime(provider_id) or {}
        data={
          "blocked_until":old.get("blocked_until",0),"successes":old.get("successes",0),
          "failures":old.get("failures",0),"latency_ema_ms":old.get("latency_ema_ms"),
          "certification_state":old.get("certification_state","unknown"),"certification_note":old.get("certification_note"),
          "last_probe_at":old.get("last_probe_at"),"last_probe_ok":old.get("last_probe_ok"),
          "provider_quota_json":old.get("provider_quota_json")
        }
        data.update(values)
        if isinstance(data.get("provider_quota_json"),(dict,list)):data["provider_quota_json"]=json.dumps(data["provider_quota_json"])
        data["updated_at"]=time.time()
        cols=["provider_id","blocked_until","successes","failures","latency_ema_ms","certification_state","certification_note","last_probe_at","last_probe_ok","provider_quota_json","updated_at"]
        params=[provider_id]+[data.get(c) for c in cols[1:]]
        with self._lock,self._conn:
            self._conn.execute(f"""INSERT INTO provider_runtime ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})
            ON CONFLICT(provider_id) DO UPDATE SET {','.join(f'{c}=excluded.{c}' for c in cols[1:])}""",params)
    def all_runtime(self):
        with self._lock:rows=self._conn.execute("SELECT * FROM provider_runtime ORDER BY provider_id").fetchall()
        return [dict(r) for r in rows]
