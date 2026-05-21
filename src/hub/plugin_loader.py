#!/usr/bin/env python3
"""
Penta Hub - Repository Plugin Loader
=====================================
Dynamically loads repository plugin definitions from YAML files,
enabling the Hub to index and install from arbitrary external sources
without modifying core code.

Plugins can define:
  - name, type, index method (URL/command/script)
  - install command template
  - target container

Usage:
    from plugin_loader import load_plugins, get_crawlers
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

async def _crawl_apt(session: aiohttp.ClientSession, plugin: dict):
    """APT plugin: parse Packages.gz from mirror (simplified)."""
    logger.info(f"Crawling APT via plugin '{plugin['name']}'")
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
                # This is a minimal parser; in production, use python-debian.
                for entry in data.split("\n\n"):
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
                        # Insert into DB (use global db from hub? For now, print)
                        logger.debug(f"APT plugin found: {pkg['name']} {pkg.get('version')}")
        except Exception as e:
            logger.error(f"APT plugin crawl error {url}: {e}")

async def _crawl_aur_rpc(session: aiohttp.ClientSession, plugin: dict):
    """AUR RPC search."""
    logger.info(f"Crawling AUR via plugin '{plugin['name']}'")
    try:
        url = plugin.get("index", {}).get("url", "https://aur.archlinux.org/rpc/v5/search/any")
        # Without a query, this endpoint returns random packages? We'll use 'any'
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                for result in data.get("results", []):
                    logger.debug(f"AUR plugin found: {result.get('Name')} {result.get('Version')}")
    except Exception as e:
        logger.error(f"AUR plugin crawl error: {e}")

async def _crawl_pypi_json(session: aiohttp.ClientSession, plugin: dict):
    """PyPI simple index (list packages)."""
    logger.info(f"Crawling PyPI via plugin '{plugin['name']}'")
    try:
        async with session.get("https://pypi.org/simple/") as resp:
            if resp.status == 200:
                html = await resp.text()
                names = re.findall(r'<a href="/simple/([^/"]+)/">', html)[:500]
                for name in names:
                    logger.debug(f"PyPI plugin found: {name}")
    except Exception as e:
        logger.error(f"PyPI plugin crawl error: {e}")

async def _crawl_npm_registry(session: aiohttp.ClientSession, plugin: dict):
    """npm registry search (limited to popular keywords)."""
    logger.info(f"Crawling npm via plugin '{plugin['name']}'")
    try:
        # npm search API requires text; we could use a static list of keywords.
        keywords = plugin.get("index", {}).get("keywords", ["node", "react", "express"])
        for kw in keywords:
            url = f"https://registry.npmjs.org/-/v1/search?text={kw}&size=50"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for obj in data.get("objects", []):
                        logger.debug(f"npm plugin found: {obj['package']['name']}")
    except Exception as e:
        logger.error(f"npm plugin crawl error: {e}")

async def _crawl_brew_search(session: aiohttp.ClientSession, plugin: dict):
    """Homebrew: we can't really crawl from outside; for demo, fake entries."""
    logger.info(f"Crawling Homebrew via plugin '{plugin['name']}'")
    # Real implementation would exec into homebrew container and run `brew search`.
    # For now, do nothing.
    pass

async def _crawl_crates_io(session: aiohttp.ClientSession, plugin: dict):
    """crates.io API."""
    logger.info(f"Crawling crates.io via plugin '{plugin['name']}'")
    try:
        url = plugin.get("index", {}).get("url", "https://crates.io/api/v1/crates?q=rust")
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                for c in data.get("crates", []):
                    logger.debug(f"Crates.io plugin found: {c['name']} {c.get('newest_version')}")
    except Exception as e:
        logger.error(f"Crates.io crawl error: {e}")

async def _crawl_github_api(session: aiohttp.ClientSession, plugin: dict):
    """GitHub repository search (requires token for higher rate limit)."""
    logger.info(f"Crawling GitHub via plugin '{plugin['name']}'")
    try:
        url = plugin.get("index", {}).get("url", "https://api.github.com/search/repositories?q=stars:>100")
        headers = {}
        if "headers" in plugin.get("index", {}):
            headers.update(plugin["index"]["headers"])
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                for item in data.get("items", []):
                    logger.debug(f"GitHub plugin found: {item['full_name']} ⭐{item.get('stargazers_count', 0)}")
    except Exception as e:
        logger.error(f"GitHub crawl error: {e}")

async def _crawl_rest_api(session: aiohttp.ClientSession, plugin: dict):
    """Generic REST API crawler."""
    logger.info(f"Crawling REST API via plugin '{plugin['name']}'")
    try:
        url = plugin.get("index", {}).get("url")
        if not url:
            return
        headers = plugin.get("index", {}).get("headers", {})
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                # Expecting a list or dict; log first few items for debugging
                logger.debug(f"REST API response received for plugin {plugin['name']}")
    except Exception as e:
        logger.error(f"REST API crawl error: {e}")

async def _crawl_script(session: aiohttp.ClientSession, plugin: dict):
    """Execute a custom script inside the container to fetch package list."""
    logger.info(f"Executing script for plugin '{plugin['name']}'")
    # This would require Distrobox or Docker exec; place holder
    pass

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
    """
    Scan directories for YAML plugin definitions and register them.
    Returns dict of plugin_name -> plugin_config.
    """
    global _plugins
    _plugins.clear()
    if plugin_dirs is None:
        plugin_dirs = [
            Path("/etc/penta/plugins"),
            Path("config"),  # fallback for development
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
    """
    Build and return a dictionary of crawler functions for all loaded plugins.
    """
    global _crawlers
    _crawlers.clear()
    for name, plugin in _plugins.items():
        method = plugin.get("index", {}).get("method", "")
        crawler = METHOD_MAP.get(method)
        if crawler:
            # Create a wrapper that passes the plugin config
            async def wrapper(session, p=plugin, c=crawler):
                await c(session, p)
            _crawlers[name] = wrapper
        else:
            logger.warning(f"No crawler available for method '{method}' in plugin '{name}'")
    return _crawlers

def get_install_command(plugin_name: str, package: str) -> Optional[str]:
    """
    Return the install command for a given package using the specified plugin.
    Substitutes {package} in the template.
    """
    plugin = _plugins.get(plugin_name)
    if not plugin:
        return None
    cmd_template = plugin.get("install", {}).get("command", "")
    return cmd_template.replace("{package}", package)

def get_plugin(plugin_name: str) -> Optional[dict]:
    return _plugins.get(plugin_name)
