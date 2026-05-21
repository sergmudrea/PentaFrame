import sys
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock

import pytest
from fastapi.testclient import TestClient

# Add resolver package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "resolver"))

# We must mock heavy dependencies before importing the app.
# The resolver module loads config, creates FastAPI app, etc.
# We'll patch key functions to avoid real container operations.

@pytest.fixture
def client():
    """Create a FastAPI test client with mocked dependencies."""
    with patch('penta-resolver.search_package', new_callable=AsyncMock) as mock_search, \
         patch('penta-resolver.ensure_container', return_value=True), \
         patch('penta-resolver.install_in_container', return_value=0), \
         patch('penta-resolver.run_command', new_callable=AsyncMock, return_value=0), \
         patch('penta-resolver.snapper_snapshot', return_value="42"), \
         patch('penta-resolver.generate_desktop_file', return_value=Path("/tmp/test.desktop")), \
         patch('penta-resolver.create_wrapper_script', return_value="test_wrapper"), \
         patch('penta-resolver.ensure_path', return_value=True):
        # Mock search to return a fake package
        mock_search.return_value = [{
            "name": "firefox",
            "source": "apt",
            "version": "115",
            "container": "debian-stable",
            "install_command": "apt install -y firefox",
            "icon_url": ""
        }]
        import penta_resolver
        # Prevent background tasks from actually running (we test API synchronously)
        penta_resolver.app.router.on_startup.clear()
        with TestClient(penta_resolver.app) as c:
            yield c

# ---------- Tests ----------
class TestHealth:
    def test_health(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

class TestInstall:
    def test_install_returns_task_id(self, client):
        resp = client.post("/api/v1/install", json={
            "package": "firefox",
            "source": "auto",
            "version": "latest"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "queued"
        # Check that a UUID was generated
        uuid.UUID(data["task_id"])  # raises if invalid

    def test_install_task_status_queued(self, client):
        install_resp = client.post("/api/v1/install", json={"package": "firefox"})
        task_id = install_resp.json()["task_id"]
        resp = client.get(f"/api/v1/task/{task_id}")
        assert resp.status_code == 200
        task = resp.json()
        assert task["task_id"] == task_id
        assert task["status"] in ("queued", "running", "completed")  # may have started

    def test_install_task_not_found(self, client):
        resp = client.get("/api/v1/task/non-existent")
        assert resp.status_code == 404

    def test_install_completes_successfully(self, client):
        """Ensure the mocked install process finishes and task status becomes completed."""
        # We need to let the background coroutine run. Since TestClient is synchronous,
        # we manually await the coroutine in the fixture? Better: we call the install
        # and then poll until completed, but asyncio task runs in same thread.
        # With async test client not used, we can instead patch perform_install to
        # immediately set task status to completed.
        # We'll adjust the fixture to mock perform_install.
        pass  # Will refine in next iteration

class TestInstalled:
    @patch('penta-resolver.Path.home', return_value=Path('/tmp/test_home'))
    @patch('penta-resolver.Path.exists', return_value=True)
    @patch('penta-resolver.Path.glob')
    def test_list_installed(self, mock_glob, mock_exists, mock_home, client):
        # Mock desktop files
        mock_file1 = MagicMock()
        mock_file1.__str__ = lambda self: '/tmp/test_home/.local/share/applications/firefox.desktop'
        mock_file1.open.return_value.__enter__.return_value = iter(['[Desktop Entry]\n', 'Name=Firefox\n', 'Exec=...\n'])
        mock_glob.return_value = [mock_file1]

        resp = client.get("/api/v1/installed")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["installed"]) == 1
        assert data["installed"][0]["name"] == "Firefox"

class TestUninstall:
    @patch('penta-resolver.Path.exists', return_value=True)
    @patch('penta-resolver.Path.unlink')
    @patch('penta-resolver.remove_wrapper_script')
    def test_uninstall_existing_app(self, mock_remove_wrapper, mock_unlink, mock_exists, client):
        resp = client.post("/api/v1/uninstall/Firefox")
        assert resp.status_code == 200
        assert resp.json()["status"] == "removed"

    @patch('penta-resolver.Path.exists', return_value=False)
    def test_uninstall_non_existing_app(self, mock_exists, client):
        resp = client.post("/api/v1/uninstall/NoSuchApp")
        assert resp.status_code == 404

class TestModeSwitch:
    def test_mode_switch(self, client):
        resp = client.post("/api/v1/mode/switch?mode=pentest")
        assert resp.status_code == 200
        assert resp.json()["status"] == "switched"
        assert resp.json()["mode"] == "pentest"
