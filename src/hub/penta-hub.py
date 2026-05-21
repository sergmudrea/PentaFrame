#!/usr/bin/env python3
"""
Penta Hub - Metadata Aggregator Service (v1.6)
===============================================
FastAPI-based microservice that indexes package metadata from multiple
repositories (built-in and user-defined via plugins).

New in v1.6:
  - Dynamically loads repository plugins from /etc/penta/plugins/.
  - Uses plugin_loader for crawling and install command generation.
  - Supports community-contributed repository definitions without core changes.

Usage:
    uvicorn src.hub.penta-hub:app --host 0.0.0.0 --port 8400
"""

import asyncio
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiohttp
import yaml
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

# ---------- Plugin Loader ----------
from plugin_loader import load_plugins, get_crawlers, get_install_command, get_plugin

# ---------- Configuration ----------
CONFIG_PATH = Path("/etc/penta/config.yaml")
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
app = FastAPI(title="Penta Hub", version="1.6.0")

# ---------- Database Setup ----------
def get_db() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

db = get_db()

def init_schema():
    db.executescript("""
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
    db.commit()

init_schema()

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

# ---------- Plugin-aware Crawling ----------
async def run_crawlers(session: aiohttp.ClientSession, source: str = None):
    """
    Execute crawler functions for all loaded plugins, or for a specific source.
    """
    crawlers = get_crawlers()
    if source:
        crawler = crawlers.get(source)
        if crawler:
            await crawler(session)
        else:
            logger.warning(f"No crawler found for source '{source}'")
    else:
        for name, crawler in crawlers.items():
            try:
                await crawler(session)
            except Exception as e:
                logger.error(f"Crawler '{name}' failed: {e}")

# ---------- Background Task ----------
async def periodic_index():
    """Run crawlers for all plugin-defined sources periodically."""
    # Load plugins on startup
    load_plugins()
    async with aiohttp.ClientSession() as session:
        while True:
            await run_crawlers(session)
            await asyncio.sleep(REFRESH_INTERVAL)

@app.on_event("startup")
async def startup():
    load_plugins()
    asyncio.create_task(periodic_index())

# ---------- API Endpoints ----------
@app.get("/api/v1/search")
async def search(
    q: str = Query(..., description="Search query"),
    source: str = Query("all", description="Comma-separated sources or 'all'"),
    limit: int = Query(20, ge=1, le=100)
):
    """Search for packages by name across all indexed repositories."""
    try:
        if source == "all":
            query = "SELECT * FROM packages WHERE name LIKE ? LIMIT ?"
            params = (f"%{q}%", limit)
        else:
            sources = [s.strip() for s in source.split(",")]
            placeholders = ",".join(["?"] * len(sources))
            query = f"SELECT * FROM packages WHERE name LIKE ? AND source IN ({placeholders}) LIMIT ?"
            params = (f"%{q}%", *sources, limit)

        cur = db.execute(query, params)
        rows = cur.fetchall()
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
    """Return details of a single package by its ID."""
    cur = db.execute("SELECT * FROM packages WHERE id = ?", (pkg_id,))
    row = cur.fetchone()
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
    """Trigger reindexing of one or all sources (uses plugin crawlers)."""
    async def do_crawl():
        async with aiohttp.ClientSession() as session:
            await run_crawlers(session, req.source)
    asyncio.create_task(do_crawl())
    return {"status": "reindex started", "source": req.source or "all"}

@app.get("/api/v1/health")
async def health():
    """Simple health check."""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}

@app.get("/api/v1/plugins")
async def list_plugins():
    """List all currently loaded repository plugins."""
    plugins = {}
    for name, plugin in get_plugin.__globals__['_plugins'].items():
        plugins[name] = {
            "type": plugin.get("type", "unknown"),
            "index_method": plugin.get("index", {}).get("method", "unknown"),
            "container": plugin.get("install", {}).get("container", "unknown"),
        }
    return {"plugins": plugins}
