# Penta OS API Reference v1.6

Base URLs (local development):
- Penta Hub: `http://localhost:8400`
- Penta Resolver: `http://localhost:8500`
- pentad: `http://localhost:8600`

All responses are JSON. Authenticated endpoints (future) use Bearer tokens.

---

## 1. Penta Hub (Repository Aggregator)

### 1.1 Health Check

GET /api/v1/health
text

**Response 200**
```json
{"status":"ok","timestamp":"2026-05-21T12:00:00Z"}

1.2 Search Packages
text

GET /api/v1/search?q=<query>&source=<source>&limit=<limit>

Param	Type	Default	Description
q	string	required	Search term (case-insensitive partial match)
source	string	all	Comma-separated: apt,aur,pypi,homebrew,...
limit	int	20	Max results (1-100)

Response 200
json

{
  "results": [
    {
      "id": "apt-firefox",
      "name": "firefox",
      "source": "apt",
      "version": "115.7.0esr",
      "description": "Mozilla Firefox web browser",
      "architecture": "arm64",
      "container": "debian-stable",
      "install_command": "sudo apt install -y firefox",
      "icon_url": "",
      "dependencies": "[]",
      "last_updated": "2026-05-01T00:00:00Z"
    }
  ]
}

1.3 Get Package by ID
text

GET /api/v1/package/{pkg_id}

Response 200 – same schema as single result above.
Response 404 – {"detail":"Package not found"}
1.4 Trigger Reindex
text

POST /api/v1/reindex
Content-Type: application/json

{"source":"aur","force":false}

Response 202
json

{"status":"reindex started","source":"aur"}

1.5 List Plugins
text

GET /api/v1/plugins

Response 200
json

{
  "plugins": {
    "apt": {"type":"apt","index_method":"apt-cache","container":"debian-stable"},
    "aur": {"type":"pacman","index_method":"aur-rpc","container":"arch-toolbox"}
  }
}

2. Penta Resolver (Smart Docking Engine)
2.1 Health Check
text

GET /api/v1/health

2.2 Install Package
text

POST /api/v1/install
Content-Type: application/json

{
  "package": "firefox",
  "source": "auto",
  "version": "latest",
  "hardware_profile": "auto",
  "mode": "desktop"
}

Response 200
json

{"task_id":"550e8400-e29b-...","status":"queued"}

2.3 Get Task Status
text

GET /api/v1/task/{task_id}

Response 200
json

{
  "task_id":"...",
  "status":"running",
  "progress":45,
  "log":["Searching Penta Hub...","Selected: firefox from apt"],
  "result":null
}

Statuses: queued → running → completed | failed
2.4 List Installed Apps
text

GET /api/v1/installed

Response 200
json

{"installed":[{"name":"Firefox","file":"/home/user/.local/.../firefox.desktop"}]}

2.5 Uninstall App
text

POST /api/v1/uninstall/{app_name}

Response 200 – {"status":"removed"}
Response 404 – app not found
2.6 Switch Mode
text

POST /api/v1/mode/switch?mode=pentest

Response 200 – {"status":"switched","mode":"pentest"}
3. pentad (Module Daemon)
3.1 Status
text

GET /api/v1/status

Response 200
json

{
  "modules": [
    {"addr":"0x10","type":"HackRF","serial":"12345"},
    {"addr":"0x20","type":"NVMe","serial":"67890"}
  ],
  "count":2,
  "uptime":3600.0
}

3.2 Force Scan
text

GET /api/v1/scan

Triggers I²C bus scan, returns same structure as status.
3.3 Module Power Control
text

POST /api/v1/module/{addr}/power
Content-Type: application/json

{"state":"off"}

Response 200 – {"addr":"0x10","state":"off","result":"ok"}
Response 400 – invalid state
Response 404 – module not found
3.4 System Resources
text

GET /api/v1/resources

Response 200 (if psutil installed)
json

{"cpu_percent":25.3,"memory_total_mb":8192,"memory_used_mb":2048}

Response 501 – psutil not installed
