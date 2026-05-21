import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pytest
import yaml

# Add hub package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "hub"))

from plugin_loader import (
    load_plugins,
    get_crawlers,
    get_install_command,
    get_plugin,
    get_source_priority,
    METHOD_MAP,
)

# ---------- Helper ----------
def create_plugin_yaml(plugins: list[dict], tmp_path: Path) -> Path:
    """Write a temporary YAML file with plugin definitions and return its path."""
    content = {"plugins": plugins}
    yaml_file = tmp_path / "test_plugins.yaml"
    with open(yaml_file, "w") as f:
        yaml.dump(content, f)
    return yaml_file

# ---------- Tests ----------
class TestLoadPlugins:
    def test_empty_directory(self, tmp_path):
        load_plugins([tmp_path])
        assert get_crawlers() == {}

    def test_single_plugin(self, tmp_path):
        create_plugin_yaml(
            [{"name": "test-apt", "type": "apt", "index": {"method": "apt-cache"}, "install": {"container": "debian-stable", "command": "apt install -y {package}"}}],
            tmp_path
        )
        load_plugins([tmp_path])
        assert "test-apt" in get_plugin.__globals__['_plugins']
        plugin = get_plugin("test-apt")
        assert plugin["name"] == "test-apt"
        assert plugin["priority"] == 100  # default

    def test_priority_from_yaml(self, tmp_path):
        create_plugin_yaml(
            [{"name": "high-prio", "priority": 5, "type": "aur", "index": {"method": "aur-rpc"}, "install": {"container": "arch-toolbox", "command": "yay -S {package}"}}],
            tmp_path
        )
        load_plugins([tmp_path])
        assert get_plugin("high-prio")["priority"] == 5

    def test_multiple_plugins(self, tmp_path):
        create_plugin_yaml(
            [
                {"name": "p1", "type": "apt", "index": {"method": "apt-cache"}, "install": {"container": "debian-stable", "command": "apt install -y {package}"}},
                {"name": "p2", "type": "pip", "index": {"method": "pypi-json"}, "install": {"container": "python-slim", "command": "pip install {package}"}},
            ],
            tmp_path
        )
        load_plugins([tmp_path])
        plugins = get_plugin.__globals__['_plugins']
        assert len(plugins) == 2
        assert "p1" in plugins
        assert "p2" in plugins

    def test_invalid_yaml(self, tmp_path):
        bad_file = tmp_path / "bad.yaml"
        bad_file.write_text(": invalid: yaml")
        load_plugins([tmp_path])  # should not raise

    def test_missing_name(self, tmp_path):
        create_plugin_yaml(
            [{"type": "apt", "index": {"method": "apt-cache"}}],  # no name
            tmp_path
        )
        load_plugins([tmp_path])
        assert len(get_plugin.__globals__['_plugins']) == 0


class TestGetCrawlers:
    def test_crawler_for_valid_method(self, tmp_path):
        create_plugin_yaml(
            [{"name": "apt", "index": {"method": "apt-cache"}, "install": {"container": "debian-stable", "command": "apt install -y {package}"}}],
            tmp_path
        )
        load_plugins([tmp_path])
        crawlers = get_crawlers()
        assert "apt" in crawlers
        assert callable(crawlers["apt"])

    def test_no_crawler_for_unknown_method(self, tmp_path):
        create_plugin_yaml(
            [{"name": "weird", "index": {"method": "magic"}, "install": {"container": "box", "command": ""}}],
            tmp_path
        )
        load_plugins([tmp_path])
        crawlers = get_crawlers()
        assert "weird" not in crawlers


class TestGetInstallCommand:
    def test_substitution(self, tmp_path):
        create_plugin_yaml(
            [{"name": "demo", "install": {"command": "install {package} --force", "container": "test"}}],
            tmp_path
        )
        load_plugins([tmp_path])
        cmd = get_install_command("demo", "myapp")
        assert cmd == "install myapp --force"

    def test_missing_plugin(self):
        assert get_install_command("ghost", "pkg") is None


class TestGetPlugin:
    def test_existing_plugin(self, tmp_path):
        create_plugin_yaml(
            [{"name": "x", "type": "brew", "install": {"container": "homebrew", "command": "brew install {package}"}}],
            tmp_path
        )
        load_plugins([tmp_path])
        plugin = get_plugin("x")
        assert plugin is not None
        assert plugin["type"] == "brew"

    def test_missing_plugin(self):
        assert get_plugin("nope") is None


class TestGetSourcePriority:
    def test_builtin_apt(self):
        assert get_source_priority("apt") == 0

    def test_builtin_exe(self):
        assert get_source_priority("exe") == 10

    def test_plugin_override(self, tmp_path):
        create_plugin_yaml(
            [{"name": "apt", "priority": 50, "index": {"method": "apt-cache"}, "install": {"container": "debian-stable", "command": "apt install -y {package}"}}],
            tmp_path
        )
        load_plugins([tmp_path])
        assert get_source_priority("apt") == 50  # plugin overrides

    def test_unknown_source(self):
        assert get_source_priority("mystery") == 100


class TestCrawlerMethods:
    """Test that every crawler in METHOD_MAP returns a list."""
    @pytest.mark.asyncio
    async def test_apt_crawl(self):
        plugin = {"name": "apt-test", "index": {"method": "apt-cache", "mirrors": ["http://deb.debian.org/debian/dists/stable/main/binary-arm64/Packages.gz"]}, "install": {"container": "debian-stable", "command": "apt install -y {package}"}}
        with patch('plugin_loader.aiohttp.ClientSession.get') as mock_get:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.read = AsyncMock(return_value=b'\x1f\x8b\x08...')  # minimal gzip data, will fail gracefully
            mock_get.return_value.__aenter__.return_value = mock_resp
            from plugin_loader import _crawl_apt
            result = await _crawl_apt(None, plugin)
            assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_pypi_crawl(self):
        plugin = {"name": "pypi-test", "index": {"method": "pypi-json"}, "install": {"container": "python-slim", "command": "pip install {package}"}}
        with patch('plugin_loader.aiohttp.ClientSession.get') as mock_get:
            mock_resp = AsyncMock()
            mock_resp.status = 200
            mock_resp.text = AsyncMock(return_value='<a href="/simple/numpy/">numpy</a>\n<a href="/simple/pandas/">pandas</a>')
            mock_get.return_value.__aenter__.return_value = mock_resp
            from plugin_loader import _crawl_pypi_json
            result = await _crawl_pypi_json(None, plugin)
            assert len(result) == 2
            assert result[0]["name"] == "numpy"
