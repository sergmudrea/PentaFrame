# Penta OS — Full System Audit & Improvements Plan v1.7

**Date:** 2026-05-21  
**Scope:** Entire codebase, configuration, security, performance, documentation, DevOps.  
**Goal:** Identify all critical, major, and minor issues; propose concrete fixes and enhancements.

---

## 1. Critical Issues (Will prevent the system from working)

### 1.1 Resolver cannot reach Hub over Unix socket
- **Problem:** Resolver uses `HUB_ENDPOINT = config.get("hub", {}).get("endpoint", "http://localhost:8400")`. After switching Hub to a Unix socket (`/run/penta/hub.sock`), the Resolver’s HTTP client cannot connect to the socket.  
- **Impact:** Installation requests fail immediately with connection error.  
- **Fix:** Change Hub endpoint to Unix socket URL: `unix:///run/penta/hub.sock`. Update `aiohttp` to use `aiohttp.UnixConnector`. Same for `penta` CLI and `mode-watcher`.

### 1.2 CLI and GUI still use TCP endpoints for services
- **Problem:** `penta` CLI hardcodes `RESOLVER_URL = "http://localhost:8500"`. Resolver now runs on `/run/penta/resolver.sock`.  
- **Impact:** CLI commands (install, list, etc.) fail.  
- **Fix:** Switch to Unix socket client using `requests_unixsocket`.

### 1.3 Missing `requests-unixsocket` dependency
- **Problem:** After migrating to Unix sockets, `requests` library cannot connect to `unix://` URLs without `requests-unixsocket`.  
- **Fix:** Add `requests-unixsocket==0.3.0` to `requirements.txt`.

### 1.4 `build.sh` copies `src/` into `/opt/penta/` incorrectly
- **Problem:** The build script copies entire `src/` tree with `cp -r "$SCRIPT_DIR/src/"* "$ROOTFS/opt/penta/"`. This creates `/opt/penta/hub/`, `/opt/penta/resolver/`, etc., matching the corrected service paths. However, the `mode-watcher` directory is new and must be included, but `build.sh` doesn't copy it because it only copies `src/` contents; `src/mode-watcher/` will be copied. Need to ensure the service file is also copied.  
- **Action:** Verify `build.sh` line `cp -r "$SCRIPT_DIR/src/"* "$ROOTFS/opt/penta/"` covers all directories; it should. But the `services/mode-watcher.service` must be copied into `/etc/systemd/system/`. Currently `build.sh` copies services using a loop that expects `penta-hub`, `penta-resolver`, `pentad`, `psyched`. Add `mode-watcher` to that loop.

### 1.5 Hub crawlers still not inserting into database
- **Problem:** In `penta-hub.py` v1.6.4 (latest), the `run_crawlers` function calls `insert_packages`, which works. But the earlier version had a bug: `insert_packages` was not awaited? The current code seems correct. However, `plugin_loader.py` returns lists of dicts, and `insert_packages` expects them. This is fine.  
- **Potential:** Some crawlers (`_crawl_apt`) import `gzip` inside function; that's okay. No critical issue.

### 1.6 `ensure_container` fails when Distrobox is not installed
- **Problem:** No check for `distrobox` binary existence. Resolver will crash with `FileNotFoundError`.  
- **Fix:** Add a pre-check and return a clear error message.

---

## 2. Major Issues (Will cause partial or intermittent failures)

### 2.1 No error handling for missing hardware (I²C, GPIO) in pentad
- **Problem:** `pentad` tries to import `smbus2` and falls back to `i2cdetect`, but if both fail, it logs and continues with empty module list. That's acceptable, but the fallback command parsing may break on different outputs. Need more robust parsing.  
- **Fix:** Use `i2c-tools` python wrapper or a well-tested parser.

### 2.2 `psyched` uses random uniform in fatigue calculation
- **Problem:** The fatigue formula adds `random.uniform(0,5)`, making it non-deterministic and not realistic. For a demo it's fine, but for production it must be replaced with a proper model.  
- **Fix:** Remove random jitter; use only temperature drift.

### 2.3 `mode-watcher` only switches to the first matching rule, not handling multiple simultaneous modules
- **Problem:** If both HackRF and Zigbee are attached, it will switch to pentest (first match) and not evaluate the rest. Possibly the user wants a combined mode or a priority-based decision.  
- **Fix:** Define priority among rules or combine modes (e.g., pentest+smarthome). Currently harmless.

### 2.4 No mechanism to rollback mode changes
- **Problem:** When a module is detached, the mode does not revert. The mode-watcher does not listen for detach events.  
- **Fix:** On detach, if no other module triggering a mode, revert to default mode.

### 2.5 `uninstall` only removes wrappers and desktop, but not the app's data in home
- **Problem:** User data for applications (e.g., `.config/appname`) remains, bloat over time.  
- **Fix:** Not critical, but could be added as a manual clean command.

### 2.6 Flatpak/Snap installations require `flatpak`/`snapd` to be installed on host, but may conflict with container isolation
- **Problem:** The install commands for Flatpak/Snap (`flatpak install ...`) run inside the container, but the container may not have `flatpak` binary. The Hub expects these to be installed in the toolbox, but the toolboxes (e.g., `debian-stable`) do not include Flatpak or Snap.  
- **Fix:** Add `flatpak`/`snapd` to the respective toolboxes, or document that these sources need a custom container.

### 2.7 Windows installer always runs `/silent` and assumes success
- **Problem:** Many Windows installers don't support `/silent` or have different switches. The installation may hang or fail without feedback.  
- **Fix:** Implement a timeout and better detection.

## 3. Minor Issues (Enhancements, polish)

### 3.1 Missing unit tests for `plugin_loader`, `mode-watcher`, `install_appimage`, `install_github`.
### 3.2 `README.md` still mentions `penta-store` GUI but the Qt app is basic and not fully integrated.
### 3.3 Documentation `API_REFERENCE.md` still shows TCP endpoints, need to document Unix socket usage.
### 3.4 `CHANGELOG.md` not updated with v1.6.x changes.
### 3.5 `RESEARCH.md` performance benchmarks not updated after improvements.
### 3.6 No `.env` file or example for development.
### 3.7 `docker-compose.yml` exposes TCP ports, should be changed to Unix sockets or at least mapped ports only for local dev.
### 3.8 CI workflows don't test Unix socket scenario.
### 3.9 `build.sh` sets up `mosquitto.conf` but doesn't copy a default config; the generated `mosquitto.conf` in the repo should be placed.
### 3.10 `pentad` REST API not documented in API_REFERENCE.

## 4. Proposed Improvements (Future releases)

### 4.1 Implement a plugin marketplace
- Allow users to browse and install community plugins from within Penta Store.

### 4.2 Add OTA (Over-The-Air) update mechanism
- Use OSTree + Btrfs snapshots to perform atomic system upgrades.

### 4.3 Multi-node cluster management GUI
- Dashboard to manage multiple PentaFrame devices, deploy workloads, and share hardware.

### 4.4 AI-powered package recommendation
- Integrate a lightweight neural model that predicts what software the user might need based on mode and usage patterns.

### 4.5 Offline installation repository
- Pre-seed the Hub database with a curated set of packages for completely offline operation.

---

## 5. Audit Summary

| Category | Count | Status |
|----------|-------|--------|
| Critical | 6 | Must be fixed before v1.0 |
| Major    | 7 | Should be fixed before beta |
| Minor    | 10 | Can be addressed incrementally |
| Proposed | 5 | Roadmap items |

---

*End of document.*
