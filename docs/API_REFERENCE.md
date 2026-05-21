# Penta OS API Reference v2.0

Base URLs (local only, protected by Unix domain sockets):

- Penta Hub: `unix:///run/penta/hub.sock`
- Penta Resolver: `unix:///run/penta/resolver.sock`
- pentad: `http://localhost:8600` (still TCP until pentad socket is implemented; planned)

All endpoints except health require filesystem access to the socket file.  
The socket files are owned by `penta:penta` with mode `660`.  
Members of the `penta` group (including the CLI, GUI, resolver, and mode‑watcher) can communicate.

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
q	string	required	Search term (case‑insensitive partial match)
source	string	all	Comma‑separated: apt,aur,pypi,homebrew,...
limit	int	20	Max results (1‑100)

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
      "last_updated": "2026-05-01T00:00:00Z",
      "priority": 0
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
    "apt": {"type":"apt","index_method":"apt-cache","container":"debian-stable","priority":0},
    "aur": {"type":"pacman","index_method":"aur-rpc","container":"arch-toolbox","priority":3}
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
  "mode": "desktop",
  "username": "penta"
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
  "log":["Searching Hub...","Selected: firefox from apt"],
  "result":null
}

Statuses: queued → running → completed | failed
2.4 List Installed Apps
text

GET /api/v1/installed

Response 200
json

{"installed":[{"name":"Firefox"},{"name":"Metasploit"}]}

2.5 Uninstall App
text

POST /api/v1/uninstall/{app_name}

Optionally include ?username=<user> to target another user.
Response 200 – {"status":"removed","log":["Note: user data directories still exist..."]}
Response 404 – app not found
2.6 Switch Mode
text

POST /api/v1/mode/switch?mode=pentest

Response 200 – {"status":"switched","mode":"pentest"}
3. pentad (Module Daemon)

Currently still TCP, Unix socket planned for v1.7.
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

Triggers I²C scan, returns same structure as status.
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
4. psyche (Psycho‑emotional Monitor)

Does not expose an API. Communicates via MQTT topics:

    penta/biometrics — input data (JSON with heart_rate, gsr, temperature)

    penta/psyche — output state (JSON with stress, fatigue, timestamp)

    penta/command/filter — block dangerous commands if stress/fatigue exceeds threshold

5. Mode Watcher (Automatic Mode Switcher)

No API. Subscribes to MQTT topics penta/module/attach and penta/module/detach.
Calls Resolver’s /api/v1/mode/switch when rules match.
6. Authentication & Security

    Socket ownership: penta:penta

    File permissions: 660 (read‑write for owner and group only)

    The group penta includes the Resolver, CLI, GUI, mode‑watcher, and administrator.

    Third‑party processes cannot reach the Hub or Resolver unless added to the penta group.

    pentad still listens on TCP localhost:8600 – limited to localhost; will be migrated to socket in next release.

7. Client Examples
CLI with Unix socket
python

import requests_unixsocket

session = requests_unixsocket.Session()
resp = session.get("unix:///run/penta/hub.sock/api/v1/search?q=firefox")
print(resp.json())

GUI (Qt) – use the same session object as CLI.
