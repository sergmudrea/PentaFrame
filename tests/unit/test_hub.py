import sys
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

# Add hub package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "hub"))

# We need to mock the global db and plugin loader before importing the app.
# The app module creates a global `db` and calls `init_schema` at import time,
# so we must replace `get_db` to return an in‑memory database.

@pytest.fixture
def in_memory_db():
    """Return a fresh in-memory SQLite database with the Penta Hub schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
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
    conn.commit()
    yield conn
    conn.close()

@pytest.fixture
def client(in_memory_db):
    """Create a FastAPI test client with mocked database and plugins."""
    # Patch get_db so every call returns our in‑memory connection
    with patch('penta-hub.get_db', return_value=in_memory_db):
        # Stop plugin loading and crawlers
        with patch('penta-hub.load_plugins', return_value={}):
            with patch('penta-hub.get_crawlers', return_value={}):
                # We must also prevent the background periodic task from starting
                with patch('penta-hub.periodic_index', return_value=None):
                    # Import the app after patches are in place
                    import penta_hub
                    # Clear the startup event so it doesn't try to run the periodic task
                    penta_hub.app.router.on_startup.clear()
                    # Override the global db reference inside the module (if any)
                    penta_hub.db = in_memory_db
                    with TestClient(penta_hub.app) as c:
                        yield c

# ---------- Test helpers ----------
def insert_package(db: sqlite3.Connection, pkg_id: str, name: str, source: str,
                   version: str = "1.0", description: str = "", container: str = "debian-stable",
                   install_command: str = "apt install -y"):
    db.execute(
        "INSERT OR REPLACE INTO packages VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (pkg_id, name, source, version, description, "all", container, install_command, "", "[]", "2025-01-01")
    )
    db.commit()

# ---------- Tests ----------
class TestHealth:
    def test_health(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "timestamp" in data

class TestSearch:
    def test_no_results(self, client):
        resp = client.get("/api/v1/search?q=nonexistent")
        assert resp.status_code == 200
        assert resp.json()["results"] == []

    def test_find_by_name(self, client, in_memory_db):
        insert_package(in_memory_db, "p1", "firefox", "apt", version="120.0")
        resp = client.get("/api/v1/search?q=firefox")
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["name"] == "firefox"
        assert results[0]["source"] == "apt"
        assert results[0]["version"] == "120.0"

    def test_search_case_insensitive(self, client, in_memory_db):
        insert_package(in_memory_db, "p1", "FireFox", "apt", version="1.0")
        resp = client.get("/api/v1/search?q=firefox")
        assert len(resp.json()["results"]) == 1  # LIKE is case-insensitive in SQLite

    def test_filter_by_source(self, client, in_memory_db):
        insert_package(in_memory_db, "p1", "metasploit", "aur", version="6.4.1")
        insert_package(in_memory_db, "p2", "metasploit", "apt", version="5.0.0")
        resp = client.get("/api/v1/search?q=metasploit&source=aur")
        results = resp.json()["results"]
        assert len(results) == 1
        assert results[0]["source"] == "aur"

    def test_limit(self, client, in_memory_db):
        for i in range(5):
            insert_package(in_memory_db, f"p{i}", f"pkg{i}", "apt")
        resp = client.get("/api/v1/search?q=pkg&limit=3")
        assert len(resp.json()["results"]) == 3

class TestGetPackage:
    def test_existing_package(self, client, in_memory_db):
        insert_package(in_memory_db, "p1", "curl", "apt", version="7.88")
        resp = client.get("/api/v1/package/p1")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "curl"
        assert data["version"] == "7.88"

    def test_non_existing_package(self, client):
        resp = client.get("/api/v1/package/fake-id")
        assert resp.status_code == 404

class TestReindex:
    def test_reindex_triggers(self, client):
        # Reindex spawns an async task; we just check the response
        resp = client.post("/api/v1/reindex", json={"source": "apt"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "reindex started"

class TestPlugins:
    def test_plugins_empty(self, client):
        resp = client.get("/api/v1/plugins")
        assert resp.status_code == 200
        assert resp.json()["plugins"] == {}
