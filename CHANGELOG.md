# Changelog

All notable changes to Penta OS will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

### Changed
- N/A (initial release).

### Deprecated
- N/A.

### Removed
- N/A.

### Fixed
- N/A.

### Security
- Enforced AppArmor profiles for pentad and resolver.
- seccomp‑bpf filters for core daemons.
- TPM‑backed key storage for PentaCrypt (design).
- Physical kill‑switch integration plan.

## [0.0.0] - Pre-release

- Concept development and prototyping.
