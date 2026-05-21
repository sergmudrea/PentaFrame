#!/usr/bin/env python3
"""
Penta Hub - Metadata Aggregator Service (v1.6.2)
=================================================
FastAPI-based microservice that indexes package metadata from multiple
repositories (built-in and user-defined via plugins).

Changes in v1.6.2:
  - Crawlers now return package lists; run_crawlers inserts them into DB.
  - Uses db_execute for thread-safe writes.
  - All previous fixes (config via env, plugin import, thread-safe SQLite) retained.

Usage:
    uvicorn src.hub.penta-hub:app --host 0.0.0.0 --port 8400
"""

import asyncio
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Optional, List, Dict, Any

import aiohttp
import yaml
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

# ---------- Plugin Loader ----------
import sys
sys.path.insert(0, str(Path(__file__).parent))  # ensure local imports work
from plugin_loader import load_plugins, get_crawlers, get_plugin

# ---------- Configuration ----------
CONFIG_PATH = Path(os.environ.get("PENTA_CONFIG", "/etc/penta/config.yaml"))
if not CONFIG_PATH.exists():
    CONFIG_PATH = Path("config/penta.conf.example")

with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

HUB_CONFIG = config.get("hub", {})
DB_PATH = HUB_CONFIG.get("db_path", "/var/lib/penta/hub.db")
REFRESH_INTERVAL = HUB_CONFIG.get("refresh_interval", 21600)

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] hub: %(message)s")
logger = logging.getLogger("penta-hub")

# ---------- FastAPI App ----------
app = FastAPI(title="Penta Hub", version="1.6.2")

# ---------- Thread-Safe Database ----------
def get_db() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_schema(conn: sqlite3.Connection):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS packages (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            source TEXT NOT NULL,
            version TEXT NOT NULL,
            description TEXT,
            architecture TEXT DEFAULT 'all',
            container TEXT NOT NULL,
            install_command TEXT NOT NULL,
            icon_url TEXT,
            dependencies TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_pkg_name ON packages(name);
        CREATE INDEX IF NOT EXISTS idx_pkg_source ON packages(source);
    """)
    conn.commit()

init_conn = get_db()
init_schema(init_conn)
init_conn.close()

db_lock = Lock()

async def db_execute(query: str, params: tuple = ()):
    def _exec():
        conn = get_db()
        with db_lock:
            conn.execute(query, params)
            conn.commit()
        conn.close()
    await asyncio.to_thread(_exec)

async def db_fetchall(query: str, params: tuple = ()):
    def _fetch():
        conn = get_db()
        cur = conn.execute(query, params)
        rows = cur.fetchall()
        conn.close()
        return rows
    return await asyncio.to_thread(_fetch)

async def db_fetchone(query: str, params: tuple = ()):
    rows = await db_fetchall(query, params)
    return rows[0] if rows else None

# ---------- Pydantic Models ----------
class PackageInfo(BaseModel):
    id: str
    name: str
    source: str
    version: str
    description: Optional[str] = None
    architecture: str = "all"
    container: str
    install_command: str
    icon_url: Optional[str] = None
    dependencies: Optional[list[str]] = []
    last_updated: Optional[str] = None

class ReindexRequest(BaseModel):
    source: Optional[str] = None
    force: bool = False

# ---------- Plugin-aware Crawling with DB insert ----------
async def run_crawlers(session: aiohttp.ClientSession, source: str = None):
    crawlers = get_crawlers()
    if source:
        crawler = crawlers.get(source)
        if crawler:
            packages = await crawler(session)
            await insert_packages(packages)
        else:
            logger.warning(f"No crawler found for source '{source}'")
    else:
        for name, crawler in crawlers.items():
            try:
                packages = await crawler(session)
                await insert_packages(packages)
            except Exception as e:
                logger.error(f"Crawler '{name}' failed: {e}")

async def insert_packages(packages: List[Dict[str, Any]]):
    """Insert or replace package records into the database."""
    for pkg in packages:
        await db_execute(
            "INSERT OR REPLACE INTO packages (id, name, source, version, description, architecture, container, install_command, icon_url, dependencies) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                pkg.get("id", f"{pkg.get('source','')}-{pkg.get('name','')}"),
                pkg.get("name", ""),
                pkg.get("source", ""),
                pkg.get("version", "unknown"),
                pkg.get("description", ""),
                pkg.get("architecture", "all"),
                pkg.get("container", "debian-stable"),
                pkg.get("install_command", ""),
                pkg.get("icon_url", ""),
                pkg.get("dependencies", "[]")
            )
        )
    logger.info(f"Inserted/updated {len(packages)} packages from crawl.")

# ---------- Background Task ----------
async def periodic_index():
    load_plugins()
    async with aiohttp.ClientSession() as session:
        while True:
            await run_crawlers(session)
            await asyncio.sleep(REFRESH_INTERVAL)

@app.on_event("startup")
async def startup():
    load_plugins()
    asyncio.create_task(periodic_index())

# ---------- API Endpoints (same as v1.6.1) ----------
@app.get("/api/v1/search")
async def search(
    q: str = Query(..., description="Search query"),
    source: str = Query("all", description="Comma-separated sources or 'all'"),
    limit: int = Query(20, ge=1, le=100)
):
    try:
        if source == "all":
            query = "SELECT * FROM packages WHERE name LIKE ? LIMIT ?"
            params = (f"%{q}%", limit)
        else:
            sources = [s.strip() for s in source.split(",")]
            placeholders = ",".join(["?"] * len(sources))
            query = f"SELECT * FROM packages WHERE name LIKE ? AND source IN ({placeholders}) LIMIT ?"
            params = (f"%{q}%", *sources, limit)

        rows = await db_fetchall(query, params)
        return {
            "results": [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "source": row["source"],
                    "version": row["version"],
                    "description": row["description"],
                    "architecture": row["architecture"],
                    "container": row["container"],
                    "install_command": row["install_command"],
                    "icon_url": row["icon_url"],
                    "dependencies": row["dependencies"],
                    "last_updated": row["last_updated"],
                }
                for row in rows
            ]
        }
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail="Search failed")

@app.get("/api/v1/package/{pkg_id}")
async def get_package(pkg_id: str):
    row = await db_fetchone("SELECT * FROM packages WHERE id = ?", (pkg_id,))
    if not row:
        raise HTTPException(status_code=404, detail="Package not found")
    return {
        "id": row["id"],
        "name": row["name"],
        "source": row["source"],
        "version": row["version"],
        "description": row["description"],
        "architecture": row["architecture"],
        "container": row["container"],
        "install_command": row["install_command"],
        "icon_url": row["icon_url"],
        "dependencies": row["dependencies"],
        "last_updated": row["last_updated"],
    }

@app.post("/api/v1/reindex")
async def reindex(req: ReindexRequest = ReindexRequest()):
    async def do_crawl():
        async with aiohttp.ClientSession() as session:
            await run_crawlers(session, req.source)
    asyncio.create_task(do_crawl())
    return {"status": "reindex started", "source": req.source or "all"}

@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/api/v1/plugins")
async def list_plugins():
    plugins = {}
    for name, plugin in get_plugin.__globals__['_plugins'].items():
        plugins[name] = {
            "type": plugin.get("type", "unknown"),
            "index_method": plugin.get("index", {}).get("method", "unknown"),
            "container": plugin.get("install", {}).get("container", "unknown"),
        }
    return {"plugins": plugins}
