#!/usr/bin/env python3
"""
Penta Resolver - Smart Docking Engine (v1.6.4)
===============================================
Accepts installation requests, queries Penta Hub, manages containers,
executes installs, and creates desktop/wrapper files on behalf of the
requesting user.

Changes:
- ensure_container now maps container name → real OCI image via containers.yaml.
- create_wrapper_script / generate_desktop_file accept `home_dir` to write
  files into the correct user's home (passed in the install request).
- Added `username` field to InstallRequest; falls back to 'penta' for server use.
- Full error handling for container and snapshot operations.

Usage:
    uvicorn src.resolver.penta-resolver:app --host 0.0.0.0 --port 8500
"""

import asyncio
import logging
import os
import re
import stat
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any

import aiohttp
import yaml
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

# ---------- Configuration ----------
CONFIG_PATH = Path(os.environ.get("PENTA_CONFIG", "/etc/penta/config.yaml"))
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
try:
    with open(CONTAINERS_YAML, "r") as f:
        containers_def = yaml.safe_load(f).get("toolboxes", {})
except Exception:
    containers_def = {}

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] resolver: %(message)s")
logger = logging.getLogger("penta-resolver")

# ---------- FastAPI ----------
app = FastAPI(title="Penta Resolver", version="1.6.4")

# ---------- Task store ----------
tasks: Dict[str, Dict[str, Any]] = {}

# ---------- Models ----------
class InstallRequest(BaseModel):
    package: str
    source: str = "auto"
    version: str = "latest"
    hardware_profile: str = "auto"
    mode: str = "desktop"
    username: Optional[str] = None   # target user for .desktop/wrappers

class TaskStatus(BaseModel):
    task_id: str
    status: str
    progress: int = 0
    log: list[str] = []
    result: Optional[dict] = None

# ---------- Helpers ----------
async def search_package(package: str, source: str = "all") -> list[dict]:
    async with aiohttp.ClientSession() as session:
        url = f"{HUB_ENDPOINT}/api/v1/search"
        params = {"q": package, "source": source, "limit": 10}
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=502, detail="Hub search failed")
            return (await resp.json()).get("results", [])

def rank_results(results: list[dict]) -> dict:
    if not results:
        return {}
    source_order = {"apt": 0, "flatpak": 1, "snap": 2, "aur": 3, "rpm": 4,
                    "pypi": 5, "homebrew": 6, "github": 7, "exe": 8}
    best, best_score = None, 999
    for r in results:
        score = source_order.get(r.get("source", ""), 100)
        if score < best_score:
            best_score, best = score, r
    return best or results[0]

async def run_command(cmd: str, log_list: list[str]) -> int:
    logger.info(f"Exec: {cmd}")
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    while True:
        line = await proc.stdout.readline()
        if not line:
            break
        log_list.append(line.decode().rstrip())
    await proc.wait()
    return proc.returncode

def get_image_for_container(container_name: str) -> str:
    """Resolve actual OCI image from containers.yaml, or use the name as-is."""
    if container_name in containers_def:
        return containers_def[container_name]["image"]
    logger.warning(f"No container definition for '{container_name}', using as image.")
    return container_name

def ensure_container(name: str, image: str, init: bool = False) -> bool:
    try:
        res = subprocess.run(f"{CONTAINER_ENGINE} list | grep -w {name}",
                             shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            return True
    except Exception:
        pass

    logger.info(f"Creating container {name} from {image}")
    cmd = f"{CONTAINER_ENGINE} create --name {name} --image {image}"
    if init:
        cmd += " --init"
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Container creation failed: {proc.stderr.strip()}")
    return True

def install_in_container(container_name: str, command: str, log_list: list[str], user: str = None) -> int:
    prefix = f"{CONTAINER_ENGINE} enter {container_name}"
    if user:
        prefix += f" --user {user}"
    return asyncio.run(run_command(f"{prefix} -- {command}", log_list))

def install_exe(container_name: str, installer_url: str, log_list: list[str]) -> int:
    log_list.append(f"Downloading {installer_url}")
    dl_cmd = f"wget -O /tmp/installer.exe '{installer_url}'"
    ret = asyncio.run(run_command(
        f"{CONTAINER_ENGINE} enter {container_name} -- bash -c '{dl_cmd}'", log_list))
    if ret != 0:
        return ret
    log_list.append("Running installer...")
    return asyncio.run(run_command(
        f"{CONTAINER_ENGINE} enter {container_name} -- bash -c 'box64 wine /tmp/installer.exe /silent'", log_list))

def create_wrapper_script(app_name: str, container_name: str, exec_command: str,
                         is_windows: bool, home_dir: Path) -> str:
    bin_dir = home_dir / ".local" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    wrapper_path = bin_dir / app_name
    # resolve name conflicts
    suffix = 0
    base = app_name
    while wrapper_path.exists():
        suffix += 1
        app_name = f"{base}_{suffix}"
        wrapper_path = bin_dir / app_name

    launch = f"box64 wine {exec_command}" if is_windows else exec_command
    script = f"""#!/bin/bash
# Penta OS wrapper for {app_name}
exec {CONTAINER_ENGINE} enter {container_name} -- {launch} "$@"
"""
    wrapper_path.write_text(script)
    wrapper_path.chmod(wrapper_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    logger.info(f"Wrapper created: {wrapper_path}")
    return app_name

def generate_desktop_file(name: str, wrapper_name: str, icon: str, home_dir: Path, terminal: bool = False) -> Path:
    desktop_dir = home_dir / ".local" / "share" / "applications"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    desktop_file = desktop_dir / f"{name.replace(' ', '_')}.desktop"
    exec_cmd = str(home_dir / ".local" / "bin" / wrapper_name)
    content = f"""[Desktop Entry]
Name={name}
Exec={exec_cmd}
Icon={icon}
Type=Application
Terminal={'true' if terminal else 'false'}
Categories=Utility;
"""
    desktop_file.write_text(content)
    desktop_file.chmod(0o755)
    subprocess.run(["update-desktop-database", str(desktop_dir)], capture_output=True)
    logger.info(f"Desktop entry: {desktop_file}")
    return desktop_file

def ensure_path_in_profile(home_dir: Path):
    """Add ~/.local/bin to PATH in .profile if missing."""
    profile = home_dir / ".profile"
    line = 'export PATH="$HOME/.local/bin:$PATH"'
    if profile.exists():
        content = profile.read_text()
        if line not in content:
            with profile.open("a") as f:
                f.write(f"\n# Penta OS\n{line}\n")
            logger.info(f"Added {line} to {profile}")

async def perform_install(task_id: str, request: InstallRequest):
    log = []
    tasks[task_id]["status"] = "running"
    tasks[task_id]["log"] = log
    snap_num = None
    try:
        log.append("Searching Hub...")
        results = await search_package(request.package, request.source)
        if not results:
            raise Exception("No package found.")
        chosen = rank_results(results)
        log.append(f"Selected {chosen['name']} ({chosen['source']})")

        source = chosen.get("source", request.source)
        container_name = chosen.get("container", f"{source}-toolbox")
        init = containers_def.get(container_name, {}).get("init", False)
        image = get_image_for_container(container_name)

        log.append(f"Preparing {container_name} (image {image})")
        ensure_container(container_name, image, init)

        if AUTO_ROLLBACK:
            try:
                res = subprocess.run(["sudo", "snapper", "create", "--type", "pre", "--print-number",
                                      "--description", "penta-install", "--cleanup-algorithm", "number"],
                                     capture_output=True, text=True, check=True)
                snap_num = res.stdout.strip()
                log.append(f"Snapshot {snap_num}")
            except Exception as e:
                logger.warning(f"Snapshot failed: {e}")

        # Install
        if source == "exe" and request.package.startswith("http"):
            ret = install_exe(container_name, request.package, log)
            exec_name = chosen.get("executable", "app")
        else:
            install_cmd = chosen.get("install_command", f"echo install {chosen['name']}")
            user = containers_def.get(container_name, {}).get("user")
            ret = install_in_container(container_name, install_cmd, log, user)
            exec_name = chosen.get("executable", chosen["name"])

        if ret != 0:
            raise Exception(f"Install failed, exit code {ret}")

        # Determine user home
        username = request.username or "penta"
        home_dir = Path(f"/home/{username}")
        if not home_dir.exists():
            home_dir = Path(f"/home/penta")
        log.append(f"Placing launcher in {home_dir}")

        is_win = (source == "exe")
        wrapper_name = create_wrapper_script(exec_name, container_name, exec_name, is_win, home_dir)
        generate_desktop_file(chosen["name"], wrapper_name, chosen.get("icon_url", ""), home_dir)
        ensure_path_in_profile(home_dir)

        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["result"] = {"name": chosen["name"], "wrapper": wrapper_name}
    except Exception as e:
        logger.exception("Install error")
        log.append(f"ERROR: {e}")
        tasks[task_id]["status"] = "failed"
        if snap_num:
            try:
                subprocess.run(["sudo", "snapper", "undochange", f"{snap_num}..0"], check=True)
                log.append("Rollback done.")
            except Exception as e2:
                log.append(f"Rollback failed: {e2}")

# ---------- API endpoints ----------
@app.post("/api/v1/install")
async def api_install(req: InstallRequest):
    task_id = str(uuid.uuid4())
    tasks[task_id] = {"task_id": task_id, "status": "queued", "progress": 0, "log": [], "result": None}
    asyncio.create_task(perform_install(task_id, req))
    return {"task_id": task_id, "status": "queued"}

@app.get("/api/v1/task/{task_id}")
async def api_task_status(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

@app.get("/api/v1/installed")
async def api_installed():
    desktop_dir = Path.home() / ".local" / "share" / "applications"
    apps = []
    if desktop_dir.exists():
        for f in desktop_dir.glob("*.desktop"):
            with open(f, "r") as fp:
                for line in fp:
                    if line.startswith("Name="):
                        apps.append({"name": line.split("=",1)[1].strip(), "file": str(f)})
    return {"installed": apps}

@app.post("/api/v1/uninstall/{app_name}")
async def api_uninstall(app_name: str):
    home = Path.home()
    desktop_file = home / ".local" / "share" / "applications" / f"{app_name.replace(' ', '_')}.desktop"
    if desktop_file.exists():
        desktop_file.unlink()
    for f in (home / ".local" / "bin").glob(f"{app_name}*"):
        f.unlink()
    return {"status": "removed"}

@app.post("/api/v1/mode/switch")
async def api_mode_switch(mode: str = Query("desktop")):
    logger.info(f"Mode switch requested: {mode}")
    return {"status": "switched", "mode": mode}

@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}
