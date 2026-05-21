import sys
import uuid
import json
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

# Add source packages to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "hub"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "resolver"))

@pytest.fixture
def e2e_clients():
    """Create both Hub and Resolver test clients with mocked backends."""
    # ---------- Hub mock ----------
    import sqlite3
    hub_db = sqlite3.connect(":memory:")
    hub_db.row_factory = sqlite3.Row
    hub_db.execute("PRAGMA journal_mode=WAL")
    hub_db.executescript("""
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
    """)
    hub_db.commit()

    with patch('penta-hub.get_db', return_value=hub_db), \
         patch('penta-hub.load_plugins', return_value={}), \
         patch('penta-hub.get_crawlers', return_value={}), \
         patch('penta-hub.periodic_index', return_value=None):
        import penta_hub
        penta_hub.app.router.on_startup.clear()
        penta_hub.db = hub_db
        hub_client = TestClient(penta_hub.app)

    # ---------- Resolver mock ----------
    with patch('penta-resolver.search_package', new_callable=AsyncMock) as mock_search, \
         patch('penta-resolver.ensure_container', return_value=True), \
         patch('penta-resolver.install_in_container', return_value=0), \
         patch('penta-resolver.run_command', new_callable=AsyncMock, return_value=0), \
         patch('penta-resolver.snapper_snapshot', return_value="42"), \
         patch('penta-resolver.generate_desktop_file', return_value=Path("/tmp/test.desktop")), \
         patch('penta-resolver.create_wrapper_script', return_value="test_wrapper"), \
         patch('penta-resolver.ensure_path', return_value=True):

        # Pre-populate the mock search with a test package from Hub
        async def search_side_effect(package, source="all"):
            # Use the hub client to search (mocked)
            resp = hub_client.get(f"/api/v1/search?q={package}")
            return resp.json().get("results", [])

        mock_search.side_effect = search_side_effect

        import penta_resolver
        penta_resolver.app.router.on_startup.clear()
        resolver_client = TestClient(penta_resolver.app)

    yield hub_client, resolver_client, hub_db
    hub_db.close()

class TestEndToEndInstall:
    def test_full_install_flow(self, e2e_clients):
        hub_client, resolver_client, hub_db = e2e_clients

        # 1. Add a package to the Hub database
        hub_db.execute("INSERT INTO packages VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
            "pkg-1", "firefox", "apt", "120.0", "Browser", "all",
            "debian-stable", "sudo apt install -y firefox", "", "[]", "2025-01-01"
        ))
        hub_db.commit()

        # 2. Verify Hub returns it
        resp = hub_client.get("/api/v1/search?q=firefox")
        assert len(resp.json()["results"]) == 1

        # 3. Trigger installation via Resolver
        install_resp = resolver_client.post("/api/v1/install", json={
            "package": "firefox", "source": "auto"
        })
        assert install_resp.status_code == 200
        task_id = install_resp.json()["task_id"]

        # 4. Poll task until completed (mocked operations finish almost instantly,
        #    but the background coroutine may not have run. We'll wait briefly.)
        import time
        deadline = time.time() + 2
        status = None
        while time.time() < deadline:
            task_resp = resolver_client.get(f"/api/v1/task/{task_id}")
            task_data = task_resp.json()
            status = task_data["status"]
            if status in ("completed", "failed"):
                break
            time.sleep(0.1)

        assert status == "completed"
        assert task_data["progress"] == 100
        assert "test_wrapper" in task_data["result"]
