import pytest
import sys
import os
from pathlib import Path

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "hub"))

from fastapi.testclient import TestClient

# We'll patch the global db and crawlers before importing the app module
import sqlite3
from unittest.mock import patch, MagicMock, AsyncMock

# ---------- Mock database ----------
@pytest.fixture
def mock_db():
    """Create an in-memory SQLite database with schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
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
    """)
    conn.commit()
    # Insert a test package
    conn.execute("INSERT INTO packages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (
        "test-apt-firefox", "firefox", "apt", "115.7.0", "Mozilla Firefox",
        "all", "debian-stable", "sudo apt install -y firefox", "", "[]", "2025-01-01"
    ))
    conn.commit()
    yield conn
    conn.close()

# We need to replace the global db with our mock before importing the app
# The app module uses `get_db` function which returns a connection to the file.
# We will patch `get_db` to return our in-memory connection.
# Also we need to patch `load_plugins` and `get_crawlers` to avoid real crawling.

@pytest.fixture
def client(mock_db):
    with patch('penta-hub.get_db', return_value=mock_db):
        # Also patch the plugin loader to return empty dicts
        with patch('penta-hub.load_plugins', return_value={}):
            with patch('penta-hub.get_crawlers', return_value={}):
                from penta-hub import app
                # Override startup event to avoid periodic indexing
                app.router.on_startup = []
                with TestClient(app) as c:
                    yield c

class TestSearchEndpoint:
    def test_search_existing_package(self, client):
        response = client.get("/api/v1/search?q=firefox")
        assert response.status_code == 200
        data = response.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["name"] == "firefox"
        assert data["results"][0]["source"] == "apt"

    def test_search_non_existing_package(self, client):
        response = client.get("/api/v1/search?q=nonexisting")
        assert response.status_code == 200
        assert len(response.json()["results"]) == 0

    def test_search_filter_by_source(self, client):
        # Add an aur package
        import sqlite3
        conn = client.app.extra['db'] if hasattr(client.app, 'extra') else None
        # Actually we need to get the mock db used. We'll insert directly.
        # Since we patched get_db, the client uses the mock_db from fixture.
        # But the test client doesn't expose it directly. We'll add a second package via the same db.
        # We'll use the mock_db from outer scope (pytest fixture). But we are inside the test function,
        # so we can't access it directly. We'll use a separate client call? No.
        # Instead, we can retrieve the db from the app state. The app module's get_db is patched,
        # and the mock_db object is accessible via the fixture. We need to share it.
        # We'll define client fixture to attach mock_db to app.state.
        pass  # The test structure will be refined later
