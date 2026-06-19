from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import sqlite3
import os
from datetime import datetime

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.environ.get("DB_PATH", "ddos.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            country TEXT,
            city TEXT,
            org TEXT,
            is_datacenter INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            country TEXT,
            isp TEXT,
            action TEXT NOT NULL,
            source TEXT DEFAULT 'cloudflare',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ── Models ──

class VisitIn(BaseModel):
    ip: str
    country: Optional[str] = None
    city: Optional[str] = None
    org: Optional[str] = None
    is_datacenter: Optional[bool] = False

class EventIn(BaseModel):
    ip: str
    country: Optional[str] = None
    isp: Optional[str] = None
    action: str  # block / allow / warn
    source: Optional[str] = "cloudflare"

# ── Endpoints ──

@app.post("/visit")
def register_visit(data: VisitIn):
    conn = get_db()
    conn.execute(
        "INSERT INTO visits (ip, country, city, org, is_datacenter) VALUES (?, ?, ?, ?, ?)",
        (data.ip, data.country, data.city, data.org, int(data.is_datacenter or False))
    )
    conn.commit()
    conn.close()
    return {"ok": True}

@app.post("/event")
def register_event(data: EventIn):
    conn = get_db()
    conn.execute(
        "INSERT INTO events (ip, country, isp, action, source) VALUES (?, ?, ?, ?, ?)",
        (data.ip, data.country, data.isp, data.action, data.source)
    )
    conn.commit()
    conn.close()
    return {"ok": True}

@app.get("/stats")
def get_stats():
    conn = get_db()

    total_visits = conn.execute("SELECT COUNT(*) as c FROM visits").fetchone()["c"]
    unique_ips   = conn.execute("SELECT COUNT(DISTINCT ip) as c FROM visits").fetchone()["c"]
    datacenters  = conn.execute("SELECT COUNT(*) as c FROM visits WHERE is_datacenter = 1").fetchone()["c"]

    total_events  = conn.execute("SELECT COUNT(*) as c FROM events").fetchone()["c"]
    total_blocked = conn.execute("SELECT COUNT(*) as c FROM events WHERE action = 'block'").fetchone()["c"]
    total_warned  = conn.execute("SELECT COUNT(*) as c FROM events WHERE action = 'warn'").fetchone()["c"]
    total_allowed = conn.execute("SELECT COUNT(*) as c FROM events WHERE action = 'allow'").fetchone()["c"]

    clean_pct = round(max(0, 100 - (total_blocked / total_events * 100)), 1) if total_events > 0 else 100.0

    # Top 5 IPs bloqueadas
    top_blocked = conn.execute("""
        SELECT ip, country, COUNT(*) as hits
        FROM events WHERE action = 'block'
        GROUP BY ip ORDER BY hits DESC LIMIT 5
    """).fetchall()

    conn.close()

    return {
        "visits": {
            "total": total_visits,
            "unique_ips": unique_ips,
            "datacenters": datacenters,
        },
        "events": {
            "total": total_events,
            "blocked": total_blocked,
            "warned": total_warned,
            "allowed": total_allowed,
            "clean_pct": clean_pct,
        },
        "top_blocked": [dict(r) for r in top_blocked]
    }

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}
