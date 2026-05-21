# Changelog

All notable changes to Penta OS will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.7.0] - 2026-05-21

### Added
- **Plugin priority system**: Hub returns `priority` for each source; Resolver sorts results by priority instead of hardcoded order.
- **Container-side uninstall**: `containers.yaml` now includes optional `uninstall_command` templates; Resolver attempts to remove packages from containers before deleting wrappers.
- **Unix domain socket authentication**: Hub, Resolver (and later pentad) listen on `/run/penta/*.sock` (owned by `penta:penta`, mode `660`), eliminating network exposure.
- **GitHub source installation**: Resolver supports `penta install --source github user/repo` (clone, auto-detect build system, build, install).
- **AppImage source installation**: Resolver supports `penta install --source appimage <url>` (download, make executable, wrap).
- **Flatpak & Snap tooling**: `debian-stable` and `fedora-toolbox` Dockerfiles now include `flatpak` and `snapd` so the respective install commands can work inside containers.
- **Automatic Mode Watcher** (`mode-watcher`): New daemon subscribes to MQTT module attach/detach events and switches system mode according to configurable rules. Supports priority and fallback to default mode.
- **Improved psyched**: Deterministic fatigue model (removed random jitter); supports real sensor topics or emulation.
- **User data cleanup notice**: Uninstall now logs standard locations of residual user data (`~/.config/<app>`, `~/.local/share/<app>`, `~/.cache/<app>`).
- **New unit tests**: `test_plugin_loader.py`, `test_mode_watcher.py`.
- **API Reference v2.0**: Documented Unix socket endpoints and usage examples.

### Changed
- Resolver and CLI now connect to Hub and Resolver via Unix sockets by default (TCP fallback with `PENTA_TCP=1` env var).
- `penta` CLI creates wrapper scripts and desktop entries on the client side, using metadata from Resolver.
- `containers.yaml` and repository plugins now carry `install_command` and `uninstall_command` templates.
- `build.sh` copies `mode-watcher` and its service, ensures all users and groups are created, installs Python dependencies globally.
- `psyched` computation is deterministic; no longer adds random jitter to fatigue.
- `pentad` I²C fallback parsing made more robust across `i2cdetect` versions.
- `api/v1/search` results include `priority` field and are sorted ascending.

### Fixed
- Resolver: `ensure_container` now resolves actual OCI image from `containers.yaml` instead of using the container name as image.
- Resolver: Windows .exe install now downloads and runs `wine` inside `winbox`.
- Systemd units: corrected `ExecStart` paths (removed erroneous `src/` segment) and added `PENTA_CONFIG` environment variable.
- `requirements.txt`: added `requests-unixsocket`, `smbus2`, `psutil`, `python-seccomp`.
- `build.sh`: added `i2c-dev` module load, creation of `penta` and `pentad` users, installation of `i2c-tools`.
- CLI: now uses `requests_unixsocket.Session()` for Unix socket connections.
- Hub: thread‑safe DB writes with lock; crawlers now insert packages into the database.
- Plugin loader: crawlers return package dicts; new `get_source_priority()` function.

## [1.5.0] - 2026-05-21

### Added
- Initial public release of Penta OS architecture and prototype.
- Penta Hub metadata aggregator with support for APT, AUR, PyPI, Homebrew, and GitHub.
- Penta Resolver (Smart Docking Engine) CLI and internal API.
- Distrobox integration with balenaEngine for container management.
- Arch Linux, Fedora, Kali, and Python toolbox container definitions.
- Windows compatibility layer via Box64 + Wine (experimental).
- `penta` CLI tool for install/remove/search/mode operations.
- Penta Store GUI prototype (Qt6/PySide6).
- Btrfs + Snapper integration for pre-install snapshots and rollback.
- pentad module daemon with I²C scanning and MQTT attach/detach events.
- psyched stress monitor placeholder.
- Mode Switcher systemd targets.
- Security hardening (AppArmor profiles, seccomp filters).
- Comprehensive architecture, research, and README documentation.
- Code of Conduct and contribution guidelines.

## [0.0.0] - Pre-release

- Concept development and prototyping.
