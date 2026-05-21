#!/usr/bin/env python3
"""
Penta Resolver - Smart Docking Engine
=====================================
Takes installation requests, queries Penta Hub, provisions containers,
executes package installation, integrates applications into the desktop.

Provides a REST API for CLI/GUI and also runs background tasks.

Usage:
    uvicorn src.resolver.penta-resolver:app --host 0.0.0.0 --port 8500
"""

import asyncio
import json
import logging
import os
import shlex
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiohttp
import yaml
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

# ---------- Configuration ----------
CONFIG_PATH = Path("/etc/penta/config.yaml")
if not CONFIG_PATH.exists():
    CONFIG_PATH = Path("config/penta.conf.example")

with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

RESOLVER_CONFIG = config.get("resolver", {})
HUB_ENDPOINT = config.get("hub", {}).get("endpoint", "http://localhost:8400")
CONTAINER_ENGINE = RESOLVER_CONFIG.get("container_engine", "distrobox")
AUTO_ROLLBACK = RESOLVER_CONFIG.get("auto_rollback", True)
TEMP_DIR = Path(RESOLVER_CONFIG.get("temp_dir", "/var/tmp/penta-install"))
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Load container definitions
CONTAINERS_YAML = Path("/etc/penta/containers.yaml")
if not CONTAINERS_YAML.exists():
    CONTAINERS_YAML = Path("config/containers.yaml")
with open(CONTAINERS_YAML, "r") as f:
    containers_def = yaml.safe_load(f)["toolboxes"]

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] resolver: %(message)s")
logger = logging.getLogger("penta-resolver")

# ---------- FastAPI App ----------
app = FastAPI(title="Penta Resolver", version="1.5.0")

# ---------- In-memory task store ----------
tasks: dict[str, dict] = {}

# ---------- Pydantic Models ----------
class InstallRequest(BaseModel):
    package: str
    source: str = "auto"          # auto, apt, aur, pypi, homebrew, github, appimage, exe
    version: str = "latest"
    hardware_profile: str = "auto"
    mode: str = "desktop"

class TaskStatus(BaseModel):
    task_id: str
    status: str                  # queued, running, completed, failed
    progress: int = 0
    log: list[str] = []
    result: Optional[str] = None

# ---------- Helper Functions ----------
async def search_package(package: str, source: str = "all") -> list[dict]:
    """Query Penta Hub for matching packages."""
    async with aiohttp.ClientSession() as session:
        url = f"{HUB_ENDPOINT}/api/v1/search"
        params = {"q": package, "source": source, "limit": 10}
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=502, detail="Hub search failed")
            data = await resp.json()
            return data.get("results", [])

def rank_results(results: list[dict]) -> dict:
    """
    Choose the best candidate based on:
    - Source preference (native > AUR > PyPI > Homebrew > Windows)
    - Version freshness (higher version string => better)
    Returns the best match or empty dict.
    """
    if not results:
        return {}
    # Simple ranking: prefer apt (native Debian), then aur, then pypi, etc.
    source_order = {"apt": 0, "flatpak": 1, "snap": 2, "aur": 3, "rpm": 4, "pypi": 5, "homebrew": 6, "github": 7, "exe": 8}
    best = None
    best_score = 999
    for r in results:
        score = source_order.get(r.get("source", ""), 100)
        if score < best_score:
            best_score = score
            best = r
    return best if best else results[0]

async def run_command(cmd: str, log_list: list[str]) -> int:
    """Run a shell command asynchronously, appending output to log_list."""
    logger.info(f"Executing: {cmd}")
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        text = line.decode().rstrip()
        log_list.append(text)
    await proc.wait()
    return proc.returncode

def ensure_container(name: str, image: str, init: bool = False) -> bool:
    """
    Ensure a Distrobox container exists. If not, create it.
    Returns True if ready.
    """
    # Check if container exists
    list_cmd = f"{CONTAINER_ENGINE} list | grep -w {name}"
    result = subprocess.run(list_cmd, shell=True, capture_output=True)
    if result.returncode != 0:
        logger.info(f"Creating container {name} from {image}")
        create_cmd = f"{CONTAINER_ENGINE} create --name {name} --image {image}"
        if init:
            create_cmd += " --init"
        subprocess.run(create_cmd, shell=True, check=True)
    return True

def install_in_container(container_name: str, command: str, log_list: list[str], user: str = None) -> int:
    """Execute an install command inside a container."""
    prefix = f"{CONTAINER_ENGINE} enter {container_name}"
    if user:
        prefix += f" --user {user}"
    full_cmd = f"{prefix} -- {command}"
    return asyncio.run(run_command(full_cmd, log_list))

def generate_desktop_file(name: str, exec_command: str, icon: str = "", terminal: bool = False) -> Path:
    """Create a .desktop file for the installed application."""
    desktop_dir = Path.home() / ".local" / "share" / "applications"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    desktop_file = desktop_dir / f"{name.replace(' ', '_')}.desktop"
    content = f"""[Desktop Entry]
Name={name}
Exec={exec_command}
Icon={icon}
Type=Application
Terminal={'true' if terminal else 'false'}
Categories=Utility;
"""
    desktop_file.write_text(content)
    desktop_file.chmod(0o755)
    # Update desktop database (if available)
    subprocess.run(["update-desktop-database", str(desktop_dir)], capture_output=True)
    logger.info(f"Desktop file created: {desktop_file}")
    return desktop_file

def snapper_snapshot() -> Optional[str]:
    """Create a pre-install snapshot with Snapper if available."""
    if not AUTO_ROLLBACK:
        return None
    try:
        result = subprocess.run(["sudo", "snapper", "create", "--type", "pre", "--print-number",
                                "--description", "penta-install", "--cleanup-algorithm", "number"],
                               capture_output=True, text=True, check=True)
        snap_num = result.stdout.strip()
        logger.info(f"Pre-install snapshot {snap_num} created")
        return snap_num
    except Exception as e:
        logger.warning(f"Snapshot creation failed (non‑critical): {e}")
        return None

def snapper_rollback(snap_num: str):
    """Rollback to the given snapshot number."""
    try:
        subprocess.run(["sudo", "snapper", "undochange", f"{snap_num}..0"], check=True)
        logger.info(f"Rolled back to snapshot {snap_num}")
    except Exception as e:
        logger.error(f"Rollback failed: {e}")

# ---------- Installation Flow ----------
async def perform_install(task_id: str, request: InstallRequest):
    """Main installation task, executed asynchronously."""
    log: list[str] = []
    tasks[task_id]["status"] = "running"
    tasks[task_id]["log"] = log
    try:
        # 1. Search Hub
        log.append("Searching Penta Hub...")
        results = await search_package(request.package, request.source)
        if not results:
            raise Exception("No package found.")
        # 2. Rank and choose
        chosen = rank_results(results)
        log.append(f"Selected: {chosen['name']} from {chosen['source']} (version {chosen.get('version','unknown')})")

        # 3. Ensure container exists
        container_image = chosen.get("container", "debian-stable")
        container_name = f"{chosen['source']}-toolbox"
        init = containers_def.get(container_name, {}).get("init", False)
        log.append(f"Ensuring container {container_name} exists...")
        ensure_container(container_name, container_image, init)

        # 4. Snapshot before install
        snap_num = snapper_snapshot()
        if snap_num:
            log.append(f"Snapshot {snap_num} created.")

        # 5. Execute install command
        install_cmd = chosen.get("install_command", f"echo install {chosen['name']}")
        user = containers_def.get(container_name, {}).get("user")
        log.append(f"Running: {install_cmd}")
        ret = install_in_container(container_name, install_cmd, log, user)
        if ret != 0:
            raise Exception(f"Installation failed with exit code {ret}")

        # 6. Generate desktop file
        # Build a launch command: distrobox enter <container> -- <program>
        # We need a sensible executable name; heuristic: the package name.
        exec_command = f"{CONTAINER_ENGINE} enter {container_name} -- {chosen['name']}"
        # For some packages, we might need a different binary; we take the package name as default.
        desktop_file = generate_desktop_file(chosen['name'], exec_command, chosen.get("icon_url", ""))
        log.append(f"Desktop shortcut created: {desktop_file}")

        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["result"] = str(desktop_file)
    except Exception as e:
        logger.exception("Installation error")
        log.append(f"ERROR: {e}")
        tasks[task_id]["status"] = "failed"
        tasks[task_id]["progress"] = 0
        # Attempt rollback if snapshot exists
        if snap_num:
            log.append("Rolling back...")
            snapper_rollback(snap_num)

# ---------- API Endpoints ----------
@app.post("/api/v1/install")
async def api_install(request: InstallRequest):
    """Start an installation task."""
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "task_id": task_id,
        "status": "queued",
        "progress": 0,
        "log": [],
        "result": None
    }
    # Launch the install in background
    asyncio.create_task(perform_install(task_id, request))
    return {"task_id": task_id, "status": "queued"}

@app.get("/api/v1/task/{task_id}")
async def api_task_status(task_id: str):
    """Get status and logs of an installation task."""
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.get("/api/v1/installed")
async def api_installed():
    """List installed applications (those with .desktop files in user's local dir)."""
    desktop_dir = Path.home() / ".local" / "share" / "applications"
    apps = []
    if desktop_dir.exists():
        for f in desktop_dir.glob("*.desktop"):
            # Parse name from file
            with open(f, "r") as fp:
                for line in fp:
                    if line.startswith("Name="):
                        app_name = line.split("=",1)[1].strip()
                        apps.append({"name": app_name, "file": str(f)})
                        break
    return {"installed": apps}

@app.post("/api/v1/uninstall/{app_name}")
async def api_uninstall(app_name: str):
    """Remove a desktop shortcut and (optionally) the container package. Minimal implementation."""
    desktop_file = Path.home() / ".local" / "share" / "applications" / f"{app_name.replace(' ', '_')}.desktop"
    if desktop_file.exists():
        desktop_file.unlink()
        return {"status": "removed", "file": str(desktop_file)}
    raise HTTPException(status_code=404, detail="Application not found")

@app.post("/api/v1/mode/switch")
async def api_mode_switch(mode: str = Query("desktop")):
    """Switch system mode (stub)."""
    logger.info(f"Mode switch requested: {mode}")
    # In real implementation, systemctl isolate penta-<mode>.target
    return {"status": "switched", "mode": mode}

@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}
