#!/usr/bin/env python3#!/usr/bin/env python3
"""
Penta Resolver - Smart Docking Engine (v1.6)
=============================================
Takes installation requests, queries Penta Hub, provisions containers,
executes package installation, integrates applications into the desktop
AND generates unified CLI wrapper scripts so any installed program
can be called directly from the host terminal.

New in v1.6:
  - Creates wrapper scripts in ~/.local/bin for every installed app.
  - Wrapper format: `distrobox enter <container> -- <command> "$@"`.
  - Supports Windows apps via `box64 wine` prefix.
  - Removes wrappers on uninstall.
  - Ensures ~/.local/bin is in PATH (warns if not).

Usage:
    uvicorn src.resolver.penta-resolver:app --host 0.0.0.0 --port 8500
"""

import asyncio
import json
import logging
import os
import shlex
import stat
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

# User's local bin directory for wrappers
USER_BIN_DIR = Path.home() / ".local" / "bin"

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
app = FastAPI(title="Penta Resolver", version="1.6.0")

# ---------- In-memory task store ----------
tasks: dict[str, dict] = {}

# ---------- Pydantic Models ----------
class InstallRequest(BaseModel):
    package: str
    source: str = "auto"
    version: str = "latest"
    hardware_profile: str = "auto"
    mode: str = "desktop"

class TaskStatus(BaseModel):
    task_id: str
    status: str
    progress: int = 0
    log: list[str] = []
    result: Optional[str] = None

# ---------- Helper Functions ----------
async def search_package(package: str, source: str = "all") -> list[dict]:
    async with aiohttp.ClientSession() as session:
        url = f"{HUB_ENDPOINT}/api/v1/search"
        params = {"q": package, "source": source, "limit": 10}
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=502, detail="Hub search failed")
            data = await resp.json()
            return data.get("results", [])

def rank_results(results: list[dict]) -> dict:
    if not results:
        return {}
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
    prefix = f"{CONTAINER_ENGINE} enter {container_name}"
    if user:
        prefix += f" --user {user}"
    full_cmd = f"{prefix} -- {command}"
    return asyncio.run(run_command(full_cmd, log_list))

def determine_executable_name(package_name: str, source: str) -> str:
    """
    Heuristically guess the executable name from the package name.
    For most packages it's the same; some known mappings can be added.
    """
    # Simple mapping for common cases
    mapping = {
        "metasploit": "msfconsole",
        "metasploit-framework": "msfconsole",
        "wireshark": "wireshark",
        "firefox": "firefox",
    }
    return mapping.get(package_name, package_name)

def create_wrapper_script(app_name: str, container_name: str, exec_command: str, is_windows: bool = False):
    """
    Create an executable script in ~/.local/bin that launches the app in its container.
    """
    USER_BIN_DIR.mkdir(parents=True, exist_ok=True)
    wrapper_path = USER_BIN_DIR / app_name

    # If the wrapper already exists and belongs to another container, add suffix
    if wrapper_path.exists():
        logger.warning(f"Wrapper {wrapper_path} already exists; appending .penta")
        wrapper_path = USER_BIN_DIR / f"{app_name}.penta"

    if is_windows:
        launch_cmd = f"box64 wine {exec_command}"
    else:
        launch_cmd = exec_command

    script_content = f"""#!/bin/bash
# Penta OS wrapper for {app_name}
# Runs inside container: {container_name}
exec {CONTAINER_ENGINE} enter {container_name} -- {launch_cmd} "$@"
"""
    wrapper_path.write_text(script_content)
    wrapper_path.chmod(wrapper_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    logger.info(f"Wrapper created: {wrapper_path}")

def remove_wrapper_script(app_name: str):
    """Remove the wrapper script if it exists."""
    wrapper_path = USER_BIN_DIR / app_name
    if wrapper_path.exists():
        wrapper_path.unlink()
        logger.info(f"Wrapper removed: {wrapper_path}")
        return True
    # Also try with .penta suffix
    wrapper_path_alt = USER_BIN_DIR / f"{app_name}.penta"
    if wrapper_path_alt.exists():
        wrapper_path_alt.unlink()
        return True
    return False

def ensure_path():
    """
    Warn if ~/.local/bin is not in PATH.
    Could also add it to ~/.bashrc automatically.
    """
    bin_dir_str = str(USER_BIN_DIR)
    current_path = os.environ.get("PATH", "")
    if bin_dir_str not in current_path:
        logger.warning(f"{bin_dir_str} is not in your PATH. Add it to your shell profile to use global commands.")
        # In future, could append to ~/.profile automatically.
        return False
    return True

def generate_desktop_file(name: str, exec_command: str, icon: str = "", terminal: bool = False) -> Path:
    desktop_dir = Path.home() / ".local" / "share" / "applications"
    desktop_dir.mkdir(parents=True, exist_ok=True)
    desktop_file = desktop_dir / f"{name.replace(' ', '_')}.desktop"
    # Use wrapper script instead of direct distrobox call
    wrapper_cmd = str(USER_BIN_DIR / name)
    content = f"""[Desktop Entry]
Name={name}
Exec={wrapper_cmd}
Icon={icon}
Type=Application
Terminal={'true' if terminal else 'false'}
Categories=Utility;
"""
    desktop_file.write_text(content)
    desktop_file.chmod(0o755)
    subprocess.run(["update-desktop-database", str(desktop_dir)], capture_output=True)
    logger.info(f"Desktop file created: {desktop_file}")
    return desktop_file

def snapper_snapshot() -> Optional[str]:
    if not AUTO_ROLLBACK:
        return None
    try:
        result = subprocess.run(["sudo", "snapper", "create", "--type", "pre", "--print-number",
                                "--description", "penta-install", "--cleanup-algorithm", "number"],
                               capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except Exception as e:
        logger.warning(f"Snapshot creation failed: {e}")
        return None

def snapper_rollback(snap_num: str):
    try:
        subprocess.run(["sudo", "snapper", "undochange", f"{snap_num}..0"], check=True)
        logger.info(f"Rolled back to snapshot {snap_num}")
    except Exception as e:
        logger.error(f"Rollback failed: {e}")

# ---------- Installation Flow ----------
async def perform_install(task_id: str, request: InstallRequest):
    log: list[str] = []
    tasks[task_id]["status"] = "running"
    tasks[task_id]["log"] = log
    snap_num = None
    try:
        # 1. Search Hub
        log.append("Searching Penta Hub...")
        results = await search_package(request.package, request.source)
        if not results:
            raise Exception("No package found.")
        chosen = rank_results(results)
        log.append(f"Selected: {chosen['name']} from {chosen['source']} (version {chosen.get('version','unknown')})")

        # 2. Ensure container exists
        container_image = chosen.get("container", "debian-stable")
        container_name = f"{chosen['source']}-toolbox"
        init = containers_def.get(container_name, {}).get("init", False)
        log.append(f"Ensuring container {container_name} exists...")
        ensure_container(container_name, container_image, init)

        # 3. Snapshot before install
        snap_num = snapper_snapshot()
        if snap_num:
            log.append(f"Snapshot {snap_num} created.")

        # 4. Execute install command
        install_cmd = chosen.get("install_command", f"echo install {chosen['name']}")
        user = containers_def.get(container_name, {}).get("user")
        log.append(f"Running: {install_cmd}")
        ret = install_in_container(container_name, install_cmd, log, user)
        if ret != 0:
            raise Exception(f"Installation failed with exit code {ret}")

        # 5. Determine executable name and create wrapper
        app_name = determine_executable_name(chosen['name'], chosen['source'])
        is_windows = chosen['source'] == 'exe' or 'wine' in install_cmd.lower()
        exec_command = app_name  # for now, assume the app can be launched by its name inside the container
        create_wrapper_script(app_name, container_name, exec_command, is_windows)
        log.append(f"CLI wrapper created: {USER_BIN_DIR / app_name}")

        # 6. Generate desktop file (using wrapper)
        desktop_file = generate_desktop_file(chosen['name'], exec_command, chosen.get("icon_url", ""))
        log.append(f"Desktop shortcut created: {desktop_file}")

        # Ensure PATH
        ensure_path()

        tasks[task_id]["status"] = "completed"
        tasks[task_id]["progress"] = 100
        tasks[task_id]["result"] = str(desktop_file)
    except Exception as e:
        logger.exception("Installation error")
        log.append(f"ERROR: {e}")
        tasks[task_id]["status"] = "failed"
        if snap_num:
            log.append("Rolling back...")
            snapper_rollback(snap_num)

# ---------- API Endpoints ----------
@app.post("/api/v1/install")
async def api_install(request: InstallRequest):
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "task_id": task_id,
        "status": "queued",
        "progress": 0,
        "log": [],
        "result": None
    }
    asyncio.create_task(perform_install(task_id, request))
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
                        app_name = line.split("=",1)[1].strip()
                        apps.append({"name": app_name, "file": str(f)})
                        break
    return {"installed": apps}

@app.post("/api/v1/uninstall/{app_name}")
async def api_uninstall(app_name: str):
    # Remove desktop file
    desktop_file = Path.home() / ".local" / "share" / "applications" / f"{app_name.replace(' ', '_')}.desktop"
    if desktop_file.exists():
        desktop_file.unlink()
    # Remove wrapper script
    removed = remove_wrapper_script(app_name)
    if desktop_file.exists() or removed:
        return {"status": "removed"}
    raise HTTPException(status_code=404, detail="Application not found")

@app.post("/api/v1/mode/switch")
async def api_mode_switch(mode: str = Query("desktop")):
    logger.info(f"Mode switch requested: {mode}")
    return {"status": "switched", "mode": mode}

@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}
