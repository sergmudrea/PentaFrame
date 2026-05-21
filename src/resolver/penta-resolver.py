#!/usr/bin/env python3
"""
Penta Resolver - Smart Docking Engine (v1.6.5)
===============================================
Accepts installation requests, queries Penta Hub, manages containers,
executes installs/uninstalls, and manages desktop/wrapper files.

Changes in v1.6.5:
  - Uses 'priority' from Hub search results (no hardcoded source_order).
  - On successful install, stores metadata in ~/.local/share/penta/installed.json.
  - On uninstall, reads metadata, attempts container-side removal, then deletes local files.
  - uninstall now accepts 'username' to locate the correct home directory.
  - All previous fixes (image resolution, client-side launchers) retained.

Usage:
    uvicorn src.resolver.penta-resolver:app --host 0.0.0.0 --port 8500
"""

import asyncio
import json
import logging
import os
import stat
import subprocess
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List

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
app = FastAPI(title="Penta Resolver", version="1.6.5")

# In-memory task store
tasks: Dict[str, Dict[str, Any]] = {}

# ---------- Pydantic Models ----------
class InstallRequest(BaseModel):
    package: str
    source: str = "auto"
    version: str = "latest"
    hardware_profile: str = "auto"
    mode: str = "desktop"
    username: Optional[str] = None

class UninstallRequest(BaseModel):
    app_name: str
    username: Optional[str] = None

class TaskStatus(BaseModel):
    task_id: str
    status: str
    progress: int = 0
    log: list[str] = []
    result: Optional[dict] = None

# ---------- Helpers ----------
def get_user_home(username: Optional[str]) -> Path:
    if username:
        home = Path(f"/home/{username}")
        if home.exists():
            return home
    return Path.home()

def get_metadata_file(home: Path) -> Path:
    meta_dir = home / ".local" / "share" / "penta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    return meta_dir / "installed.json"

def load_metadata(home: Path) -> List[Dict[str, Any]]:
    file = get_metadata_file(home)
    if file.exists():
        try:
            with open(file, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_metadata(home: Path, entry: Dict[str, Any]):
    entries = load_metadata(home)
    # Remove existing entry with same name if any
    entries = [e for e in entries if e.get("name") != entry["name"]]
    entries.append(entry)
    with open(get_metadata_file(home), "w") as f:
        json.dump(entries, f, indent=2)

def remove_metadata(home: Path, app_name: str) -> Optional[Dict[str, Any]]:
    entries = load_metadata(home)
    for entry in entries:
        if entry["name"] == app_name:
            entries.remove(entry)
            with open(get_metadata_file(home), "w") as f:
                json.dump(entries, f, indent=2)
            return entry
    return None

async def search_package(package: str, source: str = "all") -> list[dict]:
    async with aiohttp.ClientSession() as session:
        url = f"{HUB_ENDPOINT}/api/v1/search"
        params = {"q": package, "source": source, "limit": 10}
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=502, detail="Hub search failed")
            return (await resp.json()).get("results", [])

def rank_results(results: list[dict]) -> dict:
    # Hub already sorts by priority ascending; return first
    return results[0] if results else {}

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
    profile = home_dir / ".profile"
    line = 'export PATH="$HOME/.local/bin:$PATH"'
    if profile.exists():
        content = profile.read_text()
        if line not in content:
            with profile.open("a") as f:
                f.write(f"\n# Penta OS\n{line}\n")
    else:
        profile.write_text(f"{line}\n")
    logger.info(f"PATH updated in {profile}")

def remove_wrappers_and_desktop(home_dir: Path, app_name: str):
    # Remove desktop file
    desktop_file = home_dir / ".local" / "share" / "applications" / f"{app_name.replace(' ', '_')}.desktop"
    if desktop_file.exists():
        desktop_file.unlink()
        logger.info(f"Removed {desktop_file}")
    # Remove wrapper scripts (may have numeric suffixes)
    bin_dir = home_dir / ".local" / "bin"
    for f in bin_dir.glob(f"{app_name}*"):
        f.unlink()
        logger.info(f"Removed wrapper {f}")

async def perform_install(task_id: str, request: InstallRequest):
    log: list[str] = []
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
            uninstall_cmd = ""   # Windows uninstall is manual for now
        else:
            install_cmd = chosen.get("install_command", f"echo install {chosen['name']}")
            user = containers_def.get(container_name, {}).get("user")
            ret = install_in_container(container_name, install_cmd, log, user)
            exec_name = chosen.get("executable", chosen["name"])
            # Determine uninstall command
            uninstall_cmd = containers_def.get(container_name, {}).get("uninstall_command", "")
            if uninstall_cmd:
                uninstall_cmd = uninstall_cmd.replace("{package}", exec_name)

        if ret != 0:
            raise Exception(f"Install failed, exit code {ret}")

        username = request.username or "penta"
        home_dir = get_user_home(username)
        log.append(f"Placing launcher in {home_dir}")

        is_win = (source == "exe")
        wrapper_name = create_wrapper_script(exec_name, container_name, exec_name, is_win, home_dir)
        generate_desktop_file(chosen["name"], wrapper_name, chosen.get("icon_url", ""), home_dir)
        ensure_path_in_profile(home_dir)

        # Save metadata for uninstall
        meta_entry = {
            "name": chosen["name"],
            "container": container_name,
            "uninstall_command": uninstall_cmd,
            "wrapper_name": wrapper_name,
            "source": source,
        }
        save_metadata(home_dir, meta_entry)

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

async def perform_uninstall(request: UninstallRequest):
    username = request.username or "penta"
    home_dir = get_user_home(username)
    app_name = request.app_name

    # Load metadata
    meta = remove_metadata(home_dir, app_name)
    if meta:
        container_name = meta.get("container")
        uninstall_cmd = meta.get("uninstall_command", "")
        # Attempt container-side uninstall
        if container_name and uninstall_cmd:
            log_lines = []
            ret = install_in_container(container_name, uninstall_cmd, log_lines)
            if ret != 0:
                logger.warning(f"Container uninstall returned non-zero: {ret}")
            # Log output?
    # Remove wrappers and desktop files regardless
    remove_wrappers_and_desktop(home_dir, app_name)
    return True

# ---------- API Endpoints ----------
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
    home_dir = Path.home()
    entries = load_metadata(home_dir)
    # Return list of installed names; also can read desktop dir
    apps = []
    if entries:
        apps = [{"name": e["name"]} for e in entries]
    return {"installed": apps}

@app.post("/api/v1/uninstall/{app_name}")
async def api_uninstall(app_name: str, username: Optional[str] = None):
    req = UninstallRequest(app_name=app_name, username=username)
    try:
        await perform_uninstall(req)
        return {"status": "removed"}
    except Exception as e:
        logger.error(f"Uninstall error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/mode/switch")
async def api_mode_switch(mode: str = Query("desktop")):
    logger.info(f"Mode switch requested: {mode}")
    return {"status": "switched", "mode": mode}

@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}
