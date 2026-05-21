# Penta OS — The Universal Computing Platform

![Penta OS Logo](https://via.placeholder.com/200x100?text=Penta+OS)

**Version:** 1.7.0
**Status:** Active Development
**License:** GPL-3.0-or-later
**Website:** [https://pentaos.org](https://pentaos.org) (coming soon)

---

## Table of Contents

1. [What is Penta OS?](#what-is-penta-os)
2. [Key Features](#key-features)
3. [Why Penta OS?](#why-penta-os)
4. [System Requirements](#system-requirements)
5. [Quick Start](#quick-start)
6. [Installation Guide](#installation-guide)
   - [From Prebuilt Image](#from-prebuilt-image)
   - [Build from Source](#build-from-source)
7. [First Boot & Setup](#first-boot--setup)
8. [Using Penta OS](#using-penta-os)
   - [Penta Store (GUI)](#penta-store-gui)
   - [penta CLI](#penta-cli)
   - [Installing Software from Any Source](#installing-software-from-any-source)
   - [Mode Switcher](#mode-switcher)
9. [Core Components](#core-components)
   - [Penta Hub](#penta-hub)
   - [Penta Resolver](#penta-resolver)
   - [pentad (Module Daemon)](#pentad-module-daemon)
   - [psyched (Psycho‑emotional Monitor)](#psyched-psychoemotional-monitor)
   - [PentaCrypt](#pentacrypt)
10. [Extensible Repository System](#extensible-repository-system)
11. [Architecture Overview](#architecture-overview)
12. [Supported Package Ecosystems](#supported-package-ecosystems)
13. [Hardware Integration](#hardware-integration)
14. [Security](#security)
15. [Federation and Clustering](#federation-and-clustering)
16. [Development & Contribution](#development--contribution)
17. [Building Custom Toolbox Images](#building-custom-toolbox-images)
18. [Configuration Reference](#configuration-reference)
19. [Troubleshooting](#troubleshooting)
20. [FAQ](#faq)
21. [Roadmap](#roadmap)
22. [Community](#community)
23. [License & Acknowledgments](#license--acknowledgments)

---

## What is Penta OS?

Penta OS is a Debian‑based operating system that breaks down all barriers between software ecosystems. It allows you to install **any application, from any Linux distribution, macOS (Homebrew), Windows, or developer repository, with a single command or a single click**. No more worrying about package compatibility, missing dependencies, or "this software only runs on Arch". Penta OS handles everything automatically using its **Smart Docking** technology.

At its heart, Penta OS is an **aggregator** and **orchestrator**. It indexes packages from dozens of repositories (APT, AUR, RPM Fusion, PyPI, Homebrew, Flathub, GitHub, and more) and, when you ask for a piece of software, automatically selects the best source, creates an isolated container with the correct environment, installs the package, and integrates it seamlessly into your desktop — complete with icons, shortcuts, and hardware access.

The current GUI (Penta Store) is a **prototype** that demonstrates the concept and works with the Resolver API. It will be replaced with a full Qt6/KDE‑native store in the upcoming releases.

Penta OS is designed for the **PentaFrame** modular hardware platform but runs on any ARM64 (and x86_64) device, from Raspberry Pi to powerful workstations.

---

## Key Features

- **Universal Package Manager**: Install software from APT, AUR, RPM, PyPI, npm, Homebrew, Flatpak, Snap, AppImage, GitHub, and even Windows executables.
- **One‑Click Installation**: The Penta Store GUI (prototype) and `penta` CLI offer a unified interface. All applications appear in the system menu after install.
- **Smart Containerisation**: Every non‑base application runs in its own container (Distrobox + Docker), keeping your system clean and secure.
- **Windows App Support**: Run x86_64 Windows applications on ARM64 via integrated Box64 + Wine + DXVK — at near‑native speed.
- **Cross‑Architecture**: Automatic multi‑arch handling (binfmt_misc, qemu‑user, Box64) makes ARM and x86 binaries coexist.
- **Hardware Passthrough**: RF modules, GPUs, USB devices, and NVMe storage are automatically made available to containers that need them.
- **Mode Switcher**: Instantly transform your device into a phone, desktop, pentest platform, router, smart home hub, or AI node.
- **Btrfs + Snapper**: Instant snapshots and one‑command rollback protect you from bad installations.
- **Hardened Security**: Unix socket API, TPM‑backed measured boot, AppArmor, seccomp filters, per‑app encryption, and a physical kill‑switch for radios.
- **Extensible Repository System**: Teach Penta OS to use **any** new package source (private PPA, corporate Artifactory, niche format) by writing a simple YAML plugin — no code changes needed.

---

## Why Penta OS?

- **One OS to run them all**: Stop choosing between Debian, Arch, or Fedora. Penta OS gives you the best of all worlds simultaneously.
- **No more dependency hell**: Each app lives in its own environment with exactly the libraries it needs.
- **Unmatched software catalogue**: Access nearly every Linux application ever packaged, plus Windows and macOS utilities.
- **Truly portable computing**: Carry your entire working environment on a modular device and attach the hardware modules you need for the task (SDR, AI accelerator, extra battery).
- **Open‑source & sovereign**: No cloud lock‑in; Penta Hub can run locally or as a peer‑to‑peer network.

---

## System Requirements

**Minimum:**
- ARM64 CPU (e.g., Raspberry Pi 5, 4 GB RAM)
- 32 GB storage (microSD or USB)
- Network connectivity

**Recommended:**
- ARM64 CPU with at least 4 cores (Cortex‑A76 or better)
- 8 GB RAM
- NVMe SSD (via HAT or integrated)
- Vulkan‑capable GPU for Windows/gaming workloads

**x86_64:** Penta OS also works natively on amd64; the Windows emulation layer is simpler (no Box64 needed, just Wine). Development is focused on ARM64 first.

---

## Quick Start

If you just want to try Penta OS on a Raspberry Pi:

1. Download the latest prebuilt image (`penta-os-1.7.0-rpi5.img.xz`) from the [releases page](https://github.com/penta-os/core/releases).
2. Flash it to an SD card using [Raspberry Pi Imager](https://www.raspberrypi.com/software/) or `dd`.
3. Insert the card, power on, and connect via SSH (user: `penta`, password: `penta`; change immediately).
4. Run the setup wizard: `penta setup` (if available, else proceed with CLI).
5. Open Penta Store by typing `penta-store` on the desktop or via the application menu.
6. Search for software (e.g., `firefox`, `metasploit`, `notepad++`), click Install, and watch the magic happen.

---

## Installation Guide

### From Prebuilt Image

1. Download the appropriate image for your device.
2. Decompress: `xz -d penta-os-*.img.xz`.
3. Write to medium: `sudo dd if=penta-os-*.img of=/dev/mmcblk0 bs=4M status=progress conv=fsync`.
4. Resize the root filesystem to fill the card (automatic on first boot).
5. Boot and follow the on‑screen configuration.

### Build from Source

Building Penta OS from scratch is the best way to customise the kernel, preinstalled packages, and security profiles.

**Prerequisites:** A Debian 12/13 build machine with `debootstrap`, `btrfs-progs`, `qemu-user-static`, and `git`.

1. Clone the repository:
   ```bash
   git clone https://github.com/penta-os/core.git
   cd core

Install build dependencies:
bash

sudo apt install -y debootstrap btrfs-progs qemu-user-static binfmt-support \
    curl wget git make gcc-aarch64-linux-gnu

Run the build script:
bash

sudo ./build.sh --arch arm64 --variant desktop

    This will create a minimal rootfs, install all Penta components, configure Btrfs subvolumes, and pack everything into a compressed image file in output/.

    Flash the image as described above.

For detailed build options (e.g., custom kernel config, additional packages), see BUILDING.md.
First Boot & Setup

After flashing, boot the device. The first‑boot wizard (if installed) will:

    Expand the filesystem to use all available space.

    Create Btrfs subvolumes and enable Snapper.

    Prompt you to set a new password and locale.

    Offer to connect to Wi‑Fi.

    Download the latest Penta Hub index (can be skipped for offline mode).

Once completed, you are ready to install software.
Using Penta OS
Penta Store (GUI)

Launch the Penta Store from the application menu or by running penta-store in a terminal. The current prototype has a searchable interface and allows one‑click installation. It will be replaced by a full KDE‑native store in a future release.

    Search: type a name and see results from all indexed repositories.

    Details: click any app to see version, source, dependencies, and required hardware.

    Install: click the Install button; a progress dialog shows logs in real time. No further interaction needed.

    Update & Remove: manage installed apps from the “Installed” tab.

penta CLI

The command‑line interface is just as powerful:
bash

penta install firefox                      # install the best available version
penta install --source aur metasploit       # force a specific source
penta install --source github user/repo     # install from GitHub
penta install --source appimage <url>       # install an AppImage
penta search wireshark                      # find all matching packages
penta list                                  # list installed apps
penta remove firefox                        # uninstall
penta mode set pentest                      # switch to Pentest mode
penta module list                           # show connected hardware modules
penta system info                           # health and resource usage

Installing Software from Any Source

Penta Resolver automatically decides the best installation method, but you can also force a specific source:
bash

penta install --source aur metasploit
penta install --source github user/repo
penta install --source pypi flask
penta install --source appimage https://...
penta install --source exe setup.exe   # Windows installer

For Windows executables, if no source is specified, Penta searches Wine compatibility databases and AUR for community recipes.
Mode Switcher

Modes change the entire device personality:
Mode	Active Services & Containers
Phone	Waydroid, modem, lightweight UI
Desktop	Full KDE Plasma, office apps, background services
Pentest	Kali container, monitor‑mode WiFi, Wireshark
Server	Headless, SSH, LAMP, Docker
Router	OpenWrt container, hostapd, firewall
SmartHome	Home Assistant, Zigbee2MQTT
AI Node	Ollama, local LLMs, Whisper

Switching modes can be done from the GUI or with penta mode set <mode>. The system stops unnecessary services, starts new ones, and adjusts the desktop layout accordingly.
Core Components
Penta Hub

A RESTful microservice that aggregates package metadata from all configured repositories and plugins. It listens on a Unix socket (/run/penta/hub.sock) and periodically updates its index. Endpoints:

    GET /api/v1/search?q=<query> – search for packages

    GET /api/v1/package/<id> – full package info

    POST /api/v1/reindex – trigger manual reindex

    GET /api/v1/plugins – list loaded repository plugins

Penta Resolver

The brain of the operation. Resolver takes an installation request, queries the Hub, ranks results, ensures the required container environment exists, executes the install command (using the plugin's install template), and creates desktop integration files. It also handles dependency walking and hardware passthrough decisions. All actions are wrapped in Btrfs snapshots for easy rollback. Listens on /run/penta/resolver.sock.
pentad (Module Daemon)

Daemon that scans the I²C bus for attached PMC‑128 modules, reads their EEPROMs, and publishes attach/detach events to MQTT. It also provides a REST API for power control and module status. Hardened with seccomp and AppArmor.
psyched (Psycho‑emotional Monitor)

An experimental component that monitors biometric signals (heart rate, stress) and can restrict dangerous actions when the user is under stress, or suggest breaks when fatigue is detected. It integrates with the UI to adjust colours and brightness.
PentaCrypt

Provides per‑application encryption using Ed25519 and X25519. App data is stored on LUKS2 volumes with keys sealed to the TPM. Inter‑app communication uses the Noise Protocol with Double Ratchet forward secrecy.
Extensible Repository System

Penta OS is not limited to the built‑in sources. You can teach it to index and install packages from any repository – a private company Artifactory, a niche Linux distribution, a custom Flatpak remote, even a plain web directory – by dropping a simple YAML plugin file into /etc/penta/plugins/.
How It Works

    Plugins define a source – a YAML file describes:

        name: unique identifier for the source (e.g., corporate-deb-repo).

        type: category of package manager (apt, generic, rest-api, script).

        index: how to discover packages (URL to a REST API, command to run inside a container, or a custom script).

        install: command template to install a package (sudo apt install -y {package}).

        container: which toolbox container to use for installation (must exist).

    Penta Hub loads plugins automatically – on startup, the Hub scans /etc/penta/plugins/ for *.yaml files and registers every source.

    Crawlers index the new source – the plugin's index method tells the Hub how to fetch a list of available packages. The retrieved data populates the Hub's database.

    Installation uses the plugin template – when a user requests a package from that source, the Resolver takes the install command from the plugin, substitutes the package name, and runs it inside the specified container.

    Everything stays isolated – even if a plugin defines dangerous operations, they are confined to the container (Distrobox). The host system remains untouched.

Example Plugins
Private APT repository (corporate mirror)
yaml

plugins:
  - name: "acme-corp-apt"
    type: "apt"
    index:
      method: "apt-cache"
      mirrors:
        - "https://packages.acme.com/ubuntu/dists/stable/main/binary-arm64/Packages.gz"
    install:
      command: "sudo apt install -y -o Acquire::Check-Valid-Until=false {package}"
      container: "debian-stable"

Internal Python package index
yaml

plugins:
  - name: "devpi-server"
    type: "pip"
    index:
      method: "rest-api"
      url: "http://devpi.local/+simple/"
    install:
      command: "pip install --index-url http://devpi.local/ {package}"
      container: "python-slim"

Custom script that queries a proprietary database
yaml

plugins:
  - name: "license-server"
    type: "script"
    index:
      method: "script"
      script: "/opt/penta/plugins/license-fetch.sh"
    install:
      command: "install-license {package}"
      container: "debian-stable"

Adding a Plugin

    Create a .yaml file in /etc/penta/plugins/ (e.g., my-repo.yaml).

    Write the plugin definition following the structure above.

    Restart the Hub: sudo systemctl restart penta-hub.

    Verify it loaded: curl unix:///run/penta/hub.sock/api/v1/plugins (if using TCP fallback, http://localhost:8400).

    Trigger a reindex: penta hub reindex or curl -X POST .../api/v1/reindex.

    Install packages from your new source: penta install --source my-repo <package>.

This system ensures that Penta OS can evolve with the software ecosystem, without waiting for upstream changes. Community members can share plugin files, and enterprises can integrate their internal infrastructure seamlessly.
Architecture Overview

Penta OS follows a layered architecture:
text

[User Interface]  (Qt/QML GUI / CLI)
        |
[ Penta Resolver ] – decision engine, container orchestrator
        |
[ Penta Hub ]        [ Container Runtime ]   [ Module Daemon (pentad) ]
   (metadata + plugins)  (Distrobox/Docker)      (I²C, GPIO, MQTT)

All components communicate via REST and MQTT (Mosquitto broker). Hub and Resolver listen on Unix domain sockets (/run/penta/*.sock) owned by penta:penta with mode 660 – only processes in the penta group can access them. The host OS is a stripped‑down Debian with Btrfs, Snapper, and a hardened kernel.
Supported Package Ecosystems
Source	Install Method	Status
Debian/Ubuntu	Native APT or container	Stable
Kali Linux	Kali container (APT)	Stable
AUR (Arch)	Arch container + yay	Stable
Fedora/RPM	Fedora container + dnf	Beta
PyPI	pip in Python container or venv	Stable
npm	npm in Node container	Stable
Homebrew	Linuxbrew on host or container	Beta
Flathub	Flatpak on host/container	Stable
Snap Store	Snapd on host	Beta
AppImage	Direct download + integration	Stable
GitHub/GitLab	Clone, auto-detect build system, install	Alpha
Windows .exe	Wine + Box64 container, community recipes	Alpha (ARM)
Android APK	Waydroid container	Experimental
Custom	Via plugin system (YAML)	Extensible
Hardware Integration

Penta OS is built for modular hardware. The PMC‑128 connector provides I²C, GPIO, and power control. When a module (e.g., HackRF, NVMe drive, AI accelerator) is attached, pentad detects it and publishes an MQTT event. The Resolver uses this information to automatically grant hardware access to containers that require it — for example, passing /dev/bus/usb to a container running SDR software.

All RF modules are linked to a physical kill‑switch that cuts power directly. The OS enforces that no software can re‑enable them until the switch is toggled.
Security

Security is a first‑class design principle:

    API isolation: Hub and Resolver listen on Unix domain sockets (/run/penta/hub.sock, /run/penta/resolver.sock), accessible only by the penta group. No network ports are exposed to localhost or the internet.

    Boot integrity: U‑Boot/GRUB with Secure Boot, fTPM measured boot, dm‑verity rootfs.

    Kernel hardening: AppArmor, seccomp, hardened config (Yama, SYN cookies, etc.).

    Application isolation: Every app runs in a container with restricted capabilities; no process can see others without explicit MQTT permission.

    Data protection: PentaCrypt encrypts app data at rest, unsealed only when the TPM measurements match.

    Kill switch: Hardware cut‑off for all wireless and audio modules.

    Plugin safety: Repository plugins run inside containers; they cannot alter the host system.

The daemons themselves run with minimal privileges and strict seccomp profiles. For example, pentad is limited to I²C device nodes and MQTT socket.
Federation and Clustering

Penta OS devices can form a cluster (swarm) to share resources. A lightweight orchestration layer (Nomad or k3s) distributes workloads, and Penta Hub instances synchronise their indices. This allows, for instance, offloading a heavy build to a more powerful node, or sharing a single SDR module among several users.

The cluster dashboard (in Penta Store) shows all nodes, their status, and resource usage. Modes can be applied globally or per‑node.
Development & Contribution

We welcome contributions of all kinds! Here’s how to get started:

    Fork the core repository.

    Set up a development environment (see DEVELOPMENT.md).

    Pick an issue from the issue tracker.

    Join our Discord / Matrix for discussion.

Coding conventions:

    Python: PEP 8, type hints, asyncio where appropriate.

    Bash: POSIX‑compatible, shellcheck clean.

    QML: Qt 6, Material style.

    All daemons must include seccomp filters and AppArmor profiles.

Testing: Run unit tests with pytest, integration tests with QEMU‑based CI, and hardware tests on real devices.
Building Custom Toolbox Images

Toolbox container images are defined in containers/. To add a new environment:
dockerfile

# containers/ubuntu-toolbox/Dockerfile
FROM ubuntu:24.04
RUN apt update && apt install -y build-essential curl

Then run make containers to build and push to a local registry. Update /etc/penta/containers.yaml to register the new image.
Configuration Reference

The master configuration is /etc/penta/config.yaml:
yaml

hub:
  endpoint: "unix:///run/penta/hub.sock"
  refresh_interval: 21600   # 6 hours
resolver:
  default_user: "penta"
  container_engine: "distrobox"   # or "docker"
  auto_snapshot: true
  hardware_profile: "auto"
modes:
  default: "desktop"
  services_dir: "/etc/penta/modes"
security:
  apparmor_enforce: true
  seccomp_enforce: true
  tpm: false   # enable if hardware TPM available

Repository plugins are configured in /etc/penta/plugins/. See the Extensible Repository System section.
Troubleshooting

    Installation fails: Check logs at /var/log/penta/resolver.log. Use penta log install to see the last attempt.

    Container won't start: Ensure Docker is running (systemctl status docker). Try distrobox list to see all containers.

    Hardware not detected: Run i2cdetect -y 1 to check if the module is visible. Restart pentad: systemctl restart pentad.

    Windows app crashes: Check Wine logs inside the container (distrobox enter winbox -- winecfg). Update Box64 and Wine to latest using penta upgrade winbox.

    Rollback: sudo snapper list and sudo snapper undochange <old>..<new>.

    Plugin not loaded: Verify the YAML syntax, restart penta-hub, check /var/log/penta/hub.log.

    Socket connection refused: Ensure the Hub and Resolver services are running and their socket files exist (ls -l /run/penta/). Make sure you are in the penta group.

For more, see the Troubleshooting Guide.
FAQ

Q: Can I run Penta OS on a regular laptop?
A: Yes, the x86_64 version works natively. ARM64 is recommended for the full cross‑architecture experience.

Q: Does it replace my current OS?
A: Penta OS is designed as a primary OS for dedicated devices, but you can also run it in a VM or on a spare SD card.

Q: Is it safe to install packages from untrusted sources?
A: Containers isolate apps, so they cannot harm the host. Plugins run in the same container sandbox. However, malicious software could still access user data in the home directory if not properly restricted. We recommend using verified sources and paying attention to permission prompts.

Q: How much overhead do containers add?
A: Very little. CPU overhead is typically <3%, and memory footprint depends on the container base image. Distrobox shares the host kernel, so there’s no hypervisor layer.

Q: Can I use Penta OS without internet?
A: You can install local packages (.deb, .appimage, etc.) offline. Repository searches require a connection to Penta Hub or a local cache. Plugins with local index methods also work.

Q: How do I add my company's private repository?
A: Write a YAML plugin file, place it in /etc/penta/plugins/, and restart the Hub. See the Extensible Repository System section for examples.
Roadmap

    Q3 2026: Full KDE‑native Penta Store, improved Windows support, Flatpak/Snap deep integration.

    Q4 2026: Cluster federation, P2P Hub, AI‑powered recommendations.

    2027: 1.0 release.

Community

    GitHub: https://github.com/penta-os

    Discord: [invite link]

    Matrix: #pentaos:matrix.org

    Forum: https://community.pentaos.org (planned)

We follow a Code of Conduct.
License & Acknowledgments

Penta OS is free software licensed under the GPL‑3.0-or-later.
Built with love using:

    DietPi

    Distrobox

    balenaEngine

    Box64/Box86

    Wine

    Qt

    and many other wonderful open‑source projects.

Penta OS — Your software, your rules, no compromises.
