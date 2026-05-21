#!/usr/bin/env python3
"""
Penta Hub - Repository Plugin Loader (v1.6.1)
==============================================
Dynamically loads repository plugin definitions from YAML files,
enabling the Hub to index and install from arbitrary external sources
without modifying core code.

Changes in v1.6.1:
  - Crawler functions now return a list of dicts with package metadata.
  - The Hub's run_crawlers() collects these lists and inserts them into the DB.
  - Added install_command to each returned dict so DB insertion is complete.

Usage:
    from plugin_loader import load_plugins, get_crawlers, get_install_command
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

import aiohttp
import yaml

logger = logging.getLogger("penta-hub.plugins")

# Global registry
_plugins: Dict[str, dict] = {}
_crawlers: Dict[str, Callable[[aiohttp.ClientSession], Coroutine]] = {}

# Standard method implementations ------------------------------------------

async def _crawl_apt(session: aiohttp.ClientSession, plugin: dict) -> List[Dict[str, Any]]:
    """APT plugin: parse Packages.gz from mirrors, return package dicts."""
    logger.info(f"Crawling APT via plugin '{plugin['name']}'")
    packages = []
    mirrors = plugin.get("index", {}).get("mirrors", [
        "http://deb.debian.org/debian/dists/stable/main/binary-arm64/Packages.gz",
    ])
    for url in mirrors:
        try:
            async with session.get(url) as resp:
                if resp.status != 200:
                    continue
                raw = await resp.read()
                import gzip
                data = gzip.decompress(raw).decode("utf-8", errors="replace")
                entries = data.split("\n\n")
                for entry in entries:
                    pkg = {}
                    for line in entry.splitlines():
                        if line.startswith("Package:"):
                            pkg["name"] = line.split(":", 1)[1].strip()
                        elif line.startswith("Version:"):
                            pkg["version"] = line.split(":", 1)[1].strip()
                        elif line.startswith("Description:"):
                            pkg["description"] = line.split(":", 1)[1].strip()
                        elif line.startswith("Architecture:"):
                            pkg["arch"] = line.split(":", 1)[1].strip()
                    if "name" in pkg:
                        pkg["id"] = f"apt-{pkg['name']}"
                        pkg["source"] = "apt"
                        pkg["container"] = plugin.get("install", {}).get("container", "debian-stable")
                        pkg["install_command"] = plugin.get("install", {}).get("command",
                            f"sudo apt install -y {pkg['name']}").replace("{package}", pkg['name'])
                        packages.append(pkg)
        except Exception as e:
            logger.error(f"APT crawl error {url}: {e}")
    return packages


async def _crawl_aur_rpc(session: aiohttp.ClientSession, plugin: dict) -> List[Dict[str, Any]]:
    """AUR RPC search."""
    logger.info(f"Crawling AUR via plugin '{plugin['name']}'")
    packages = []
    try:
        url = plugin.get("index", {}).get("url", "https://aur.archlinux.org/rpc/v5/search/any")
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                for result in data.get("results", []):
                    pkg = {
                        "id": f"aur-{result['Name']}",
                        "name": result["Name"],
                        "source": "aur",
                        "version": result.get("Version", "unknown"),
                        "description": result.get("Description", ""),
                        "container": plugin.get("install", {}).get("container", "arch-toolbox"),
                        "install_command": f"yay -S --noconfirm {result['Name']}"
                    }
                    packages.append(pkg)
    except Exception as e:
        logger.error(f"AUR crawl error: {e}")
    return packages


async def _crawl_pypi_json(session: aiohttp.ClientSession, plugin: dict) -> List[Dict[str, Any]]:
    """PyPI simple index (list packages)."""
    logger.info(f"Crawling PyPI via plugin '{plugin['name']}'")
    packages = []
    try:
        async with session.get("https://pypi.org/simple/") as resp:
            if resp.status == 200:
                html = await resp.text()
                names = re.findall(r'<a href="/simple/([^/"]+)/">', html)[:500]
                for name in names:
                    pkg = {
                        "id": f"pypi-{name}",
                        "name": name,
                        "source": "pypi",
                        "version": "latest",
                        "description": "",
                        "container": plugin.get("install", {}).get("container", "python-slim"),
                        "install_command": f"pip install {name}"
                    }
                    packages.append(pkg)
    except Exception as e:
        logger.error(f"PyPI crawl error: {e}")
    return packages


async def _crawl_npm_registry(session: aiohttp.ClientSession, plugin: dict) -> List[Dict[str, Any]]:
    """npm registry search."""
    logger.info(f"Crawling npm via plugin '{plugin['name']}'")
    packages = []
    try:
        keywords = plugin.get("index", {}).get("keywords", ["node", "react", "express"])
        for kw in keywords:
            url = f"https://registry.npmjs.org/-/v1/search?text={kw}&size=50"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for obj in data.get("objects", []):
                        name = obj["package"]["name"]
                        pkg = {
                            "id": f"npm-{name}",
                            "name": name,
                            "source": "npm",
                            "version": obj["package"].get("version", "unknown"),
                            "description": obj.get("package", {}).get("description", ""),
                            "container": plugin.get("install", {}).get("container", "node-slim"),
                            "install_command": f"npm install -g {name}"
                        }
                        packages.append(pkg)
    except Exception as e:
        logger.error(f"npm crawl error: {e}")
    return packages


async def _crawl_brew_search(session: aiohttp.ClientSession, plugin: dict) -> List[Dict[str, Any]]:
    """Homebrew: for demo, return a few well‑known formulae."""
    logger.info(f"Crawling Homebrew via plugin '{plugin['name']}'")
    # In real life, we'd exec into container; here we return a static list.
    demo = ["wget", "node", "python", "gcc"]
    packages = []
    for name in demo:
        packages.append({
            "id": f"brew-{name}",
            "name": name,
            "source": "homebrew",
            "version": "latest",
            "description": "",
            "container": plugin.get("install", {}).get("container", "homebrew"),
            "install_command": f"brew install {name}"
        })
    return packages


async def _crawl_crates_io(session: aiohttp.ClientSession, plugin: dict) -> List[Dict[str, Any]]:
    """crates.io API."""
    logger.info(f"Crawling crates.io via plugin '{plugin['name']}'")
    packages = []
    try:
        url = plugin.get("index", {}).get("url", "https://crates.io/api/v1/crates?q=rust")
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                for c in data.get("crates", []):
                    name = c["name"]
                    packages.append({
                        "id": f"crate-{name}",
                        "name": name,
                        "source": "crates.io",
                        "version": c.get("newest_version", "unknown"),
                        "description": c.get("description", ""),
                        "container": plugin.get("install", {}).get("container", "rust-toolbox"),
                        "install_command": f"cargo install {name}"
                    })
    except Exception as e:
        logger.error(f"Crates.io crawl error: {e}")
    return packages


async def _crawl_github_api(session: aiohttp.ClientSession, plugin: dict) -> List[Dict[str, Any]]:
    """GitHub repository search."""
    logger.info(f"Crawling GitHub via plugin '{plugin['name']}'")
    packages = []
    try:
        url = plugin.get("index", {}).get("url", "https://api.github.com/search/repositories?q=stars:>100")
        headers = {}
        if "headers" in plugin.get("index", {}):
            headers.update(plugin["index"]["headers"])
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                for item in data.get("items", []):
                    full_name = item["full_name"]
                    packages.append({
                        "id": f"github-{full_name.replace('/', '-')}",
                        "name": full_name,
                        "source": "github",
                        "version": item.get("default_branch", "main"),
                        "description": item.get("description", ""),
                        "container": plugin.get("install", {}).get("container", "debian-stable"),
                        "install_command": f"penta-github-install {full_name}"
                    })
    except Exception as e:
        logger.error(f"GitHub crawl error: {e}")
    return packages


async def _crawl_rest_api(session: aiohttp.ClientSession, plugin: dict) -> List[Dict[str, Any]]:
    """Generic REST API crawler."""
    logger.info(f"Crawling REST API via plugin '{plugin['name']}'")
    packages = []
    try:
        url = plugin.get("index", {}).get("url")
        if not url:
            return packages
        headers = plugin.get("index", {}).get("headers", {})
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                # Expect a list of objects with at least 'name'
                items = data if isinstance(data, list) else data.get("items", [])
                for obj in items:
                    name = obj.get("name") or obj.get("package")
                    if name:
                        packages.append({
                            "id": f"rest-{plugin['name']}-{name}",
                            "name": name,
                            "source": plugin["name"],
                            "version": obj.get("version", "unknown"),
                            "description": obj.get("description", ""),
                            "container": plugin.get("install", {}).get("container", "debian-stable"),
                            "install_command": plugin.get("install", {}).get("command", "").replace("{package}", name)
                        })
    except Exception as e:
        logger.error(f"REST API crawl error: {e}")
    return packages


async def _crawl_script(session: aiohttp.ClientSession, plugin: dict) -> List[Dict[str, Any]]:
    """Execute a custom script inside the container to fetch package list."""
    logger.info(f"Executing script for plugin '{plugin['name']}'")
    # For now, return empty; real implementation would exec into container and parse output.
    return []


# Mapping of method name to crawler factory
METHOD_MAP = {
    "apt-cache": _crawl_apt,
    "aur-rpc": _crawl_aur_rpc,
    "pypi-json": _crawl_pypi_json,
    "npm-registry": _crawl_npm_registry,
    "brew-search": _crawl_brew_search,
    "crates-io-api": _crawl_crates_io,
    "github-api": _crawl_github_api,
    "rest-api": _crawl_rest_api,
    "script": _crawl_script,
}


def load_plugins(plugin_dirs: List[Path] = None) -> Dict[str, dict]:
    global _plugins
    _plugins.clear()
    if plugin_dirs is None:
        plugin_dirs = [
            Path("/etc/penta/plugins"),
            Path("config"),
        ]
    for directory in plugin_dirs:
        if not directory.exists():
            continue
        for yaml_file in directory.glob("*.yaml"):
            try:
                with open(yaml_file, "r") as f:
                    data = yaml.safe_load(f)
                    if not data or "plugins" not in data:
                        continue
                    for plugin in data["plugins"]:
                        name = plugin.get("name")
                        if not name:
                            continue
                        _plugins[name] = plugin
                        logger.info(f"Loaded plugin '{name}' from {yaml_file}")
            except Exception as e:
                logger.warning(f"Failed to load plugin file {yaml_file}: {e}")
    return _plugins


def get_crawlers() -> Dict[str, Callable[[aiohttp.ClientSession], Coroutine]]:
    global _crawlers
    _crawlers.clear()
    for name, plugin in _plugins.items():
        method = plugin.get("index", {}).get("method", "")
        crawler = METHOD_MAP.get(method)
        if crawler:
            async def wrapper(session, p=plugin, c=crawler):
                return await c(session, p)
            _crawlers[name] = wrapper
        else:
            logger.warning(f"No crawler for method '{method}' in plugin '{name}'")
    return _crawlers


def get_install_command(plugin_name: str, package: str) -> Optional[str]:
    plugin = _plugins.get(plugin_name)
    if not plugin:
        return None
    cmd_template = plugin.get("install", {}).get("command", "")
    return cmd_template.replace("{package}", package)


def get_plugin(plugin_name: str) -> Optional[dict]:
    return _plugins.get(plugin_name)
