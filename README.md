#Penta OS — The Universal Computing Platform

https://via.placeholder.com/200x100?text=Penta+OS

Version: 1.5.0 (Prototype)
Status: Active Development
License: GPL-3.0-or-later
Website: https://pentaos.org (coming soon)
Table of Contents

    What is Penta OS?

    Key Features

    Why Penta OS?

    System Requirements

    Quick Start

    Installation Guide

        From Prebuilt Image

        Build from Source

    First Boot & Setup

    Using Penta OS

        Penta Store (GUI)

        penta CLI

        Installing Software from Any Source

        Mode Switcher

    Core Components

        Penta Hub

        Penta Resolver

        pentad (Module Daemon)

        psyched (Psycho‑emotional Monitor)

        PentaCrypt

    Architecture Overview

    Supported Package Ecosystems

    Hardware Integration

    Security

    Federation and Clustering

    Development & Contribution

    Building Custom Toolbox Images

    Configuration Reference

    Troubleshooting

    FAQ

    Roadmap

    Community

    License & Acknowledgments

What is Penta OS?

Penta OS is a Debian‑based operating system that breaks down all barriers between software ecosystems. It allows you to install any application, from any Linux distribution, macOS (Homebrew), Windows, or developer repository, with a single command or a single click. No more worrying about package compatibility, missing dependencies, or "this software only runs on Arch". Penta OS handles everything automatically using its Smart Docking technology.

At its heart, Penta OS is an aggregator and orchestrator. It indexes packages from dozens of repositories (APT, AUR, RPM Fusion, PyPI, Homebrew, Flathub, GitHub, and more) and, when you ask for a piece of software, automatically selects the best source, creates an isolated container with the correct environment, installs the package, and integrates it seamlessly into your desktop — complete with icons, shortcuts, and hardware access.

Penta OS is designed for the PentaFrame modular hardware platform but runs on any ARM64 (and soon x86_64) device, from Raspberry Pi to powerful workstations.
Key Features

    Universal Package Manager: Install software from APT, AUR, RPM, PyPI, npm, Homebrew, Snap, Flatpak, AppImage, GitHub, and even Windows executables.

    One‑Click Installation: The Penta Store GUI offers a unified app catalog, ranking packages by version, popularity, and compatibility.

    Smart Containerisation: Every non‑base application runs in its own container (using Distrobox + balenaEngine), keeping your system clean and secure.

    Windows App Support: Run x86_64 Windows applications on ARM64 via integrated Box64 + Wine + DXVK — at near‑native speed.

    Cross‑Architecture: Automatic multi‑arch handling (binfmt_misc, qemu‑user, Box64) makes ARM and x86 binaries coexist.

    Hardware Passthrough: RF modules, GPUs, USB devices, and NVMe storage are automatically made available to containers that need them.

    Mode Switcher: Instantly transform your device into a phone, desktop, pentest platform, router, smart home hub, or AI node.

    Btrfs + Snapper: Instant snapshots and one‑command rollback protect you from bad installations.

    Hardened Security: TPM‑backed measured boot, AppArmor, seccomp filters, per‑app encryption, and a physical kill‑switch for radios.

Why Penta OS?

    One OS to run them all: Stop choosing between Debian, Arch, or Fedora. Penta OS gives you the best of all worlds simultaneously.

    No more dependency hell: Each app lives in its own environment with exactly the libraries it needs.

    Unmatched software catalogue: Access nearly every Linux application ever packaged, plus Windows and macOS utilities.

    Truly portable computing: Carry your entire working environment on a modular device and attach the hardware modules you need for the task (SDR, AI accelerator, extra battery).

    Open‑source & sovereign: No cloud lock‑in; Penta Hub can run locally or as a peer‑to‑peer network.

System Requirements

Minimum:

    ARM64 CPU (e.g., Raspberry Pi 5, 4 GB RAM)

    32 GB storage (microSD or USB)

    Network connectivity

Recommended:

    ARM64 CPU with at least 4 cores (Cortex‑A76 or better)

    8 GB RAM

    NVMe SSD (via HAT or integrated)

    Vulkan‑capable GPU for Windows/gaming workloads

x86_64: Penta OS also works natively on amd64, but the Windows emulation layer is simpler (no Box64 needed, just Wine). Development is focused on ARM64 first.
Quick Start

If you just want to try Penta OS on a Raspberry Pi:

    Download the latest prebuilt image (penta-os-1.5.0-rpi5.img.xz) from the releases page.

    Flash it to an SD card using Raspberry Pi Imager or dd.

    Insert the card, power on, and connect via SSH (user: penta, password: penta; change immediately).

    Run the setup wizard: penta setup.

    Open Penta Store by typing penta-store on the desktop or via the application menu.

    Search for software (e.g., firefox, metasploit, notepad++), click Install, and watch the magic happen.

Installation Guide
From Prebuilt Image

    Download the appropriate image for your device.

    Decompress: xz -d penta-os-*.img.xz.

    Write to medium: sudo dd if=penta-os-*.img of=/dev/mmcblk0 bs=4M status=progress conv=fsync.

    Resize the root filesystem to fill the card (automatic on first boot).

    Boot and follow the on‑screen configuration.

Build from Source

Building Penta OS from scratch is the best way to customise the kernel, preinstalled packages, and security profiles.

Prerequisites: A Debian 12/13 build machine with debootstrap, btrfs-progs, qemu-user-static, and git.

    Clone the repository:
    bash

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

Launch the Penta Store from the application menu or by running penta-store in a terminal. The store has a clean, searchable interface with categories like Pentest, SDR, Productivity, Games, and more.

    Search: type a name and see results from all indexed repositories.

    Details: click any app to see version, source, dependencies, and required hardware.

    Install: click the Install button; a progress dialog shows logs in real time. No further interaction needed.

    Update & Remove: manage installed apps from the “Installed” tab.

penta CLI

The command‑line interface is just as powerful:
bash

penta install metasploit            # install the best available version
penta install notepad++ from github # install from GitHub
penta search wireshark              # find all matching packages
penta list                          # list installed apps
penta remove firefox                # uninstall
penta mode set pentest              # switch to Pentest mode
penta module list                   # show connected hardware modules
penta system info                   # health and resource usage

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

A RESTful microservice that aggregates package metadata from all configured repositories. It runs locally (localhost:8400) and periodically updates its index. In cluster setups, multiple hubs can synchronise over a gossip protocol. Endpoints:

    GET /api/v1/search?q=<query> – search for packages

    GET /api/v1/package/<id> – full package info

    POST /api/v1/reindex – trigger manual reindex

Penta Resolver

The brain of the operation. Resolver takes an installation request, queries the Hub, ranks results, ensures the required container environment exists, executes the install command, and creates desktop integration files. It also handles dependency walking and hardware passthrough decisions. All actions are wrapped in Btrfs snapshots for easy rollback.
pentad (Module Daemon)

Daemon that scans the I²C bus for attached PMC‑128 modules, reads their EEPROMs, and publishes attach/detach events to MQTT. It also provides a REST API for power control and module status. Hardened with seccomp and AppArmor.
psyched (Psycho‑emotional Monitor)

An experimental component that monitors biometric signals (heart rate, stress) and can restrict dangerous actions when the user is under stress, or suggest breaks when fatigue is detected. It integrates with the UI to adjust colours and brightness.
PentaCrypt

Provides per‑application encryption using Ed25519 and X25519. App data is stored on LUKS2 volumes with keys sealed to the TPM. Inter‑app communication uses the Noise Protocol with Double Ratchet forward secrecy.
Architecture Overview

Penta OS follows a layered architecture:
text

[User Interface]  (Qt/QML GUI / CLI)
        |
[ Penta Resolver ] – decision engine, container orchestrator
        |
[ Penta Hub ]        [ Container Runtime ]   [ Module Daemon (pentad) ]
   (metadata)            (Distrobox/balenaEngine)      (I²C, GPIO, MQTT)

All components communicate via REST and MQTT (Mosquitto broker). Containers share the host kernel but use separate userspaces with security profiles.

The host OS is a stripped‑down Debian with Btrfs, Snapper, and a hardened kernel. Container images are pre‑built for Arch, Fedora, Kali, and Windows (Wine), among others.
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
GitHub/GitLab	Clone, build system auto‑detect, install	Alpha
Windows .exe	Wine + Box64 container, community recipes	Alpha (ARM)
Android APK	Waydroid container	Experimental
Hardware Integration

Penta OS is built for modular hardware. The PMC‑128 connector provides I²C, GPIO, and power control. When a module (e.g., HackRF, NVMe drive, AI accelerator) is attached, pentad detects it and publishes an MQTT event. The Resolver uses this information to automatically grant hardware access to containers that require it — for example, passing /dev/bus/usb to a container running SDR software.

All RF modules are linked to a physical kill‑switch that cuts power directly. The OS enforces that no software can re‑enable them until the switch is toggled.
Security

Security is a first‑class design principle:

    Boot integrity: U‑Boot/GRUB with Secure Boot, fTPM measured boot, dm‑verity rootfs.

    Kernel hardening: AppArmor, seccomp, hardened config (Yama, SYN cookies, etc.).

    Application isolation: Every app runs in a container with restricted capabilities; no process can see others without explicit MQTT permission.

    Data protection: PentaCrypt encrypts app data at rest, unsealed only when the TPM measurements match.

    Kill switch: Hardware cut‑off for all wireless and audio modules.

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
  endpoint: "http://localhost:8400"
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

Each mode directory contains systemd service files that are started/stopped on mode switch.
Troubleshooting

    Installation fails: Check logs at /var/log/penta/resolver.log. Use penta log install to see the last attempt.

    Container won't start: Ensure balena-engine is running (systemctl status balena-engine). Try distrobox list to see all containers.

    Hardware not detected: Run i2cdetect -y 1 to check if the module is visible. Restart pentad: systemctl restart pentad.

    Windows app crashes: Check Wine logs inside the container (distrobox enter winbox -- winecfg). Update Box64 and Wine to latest using penta upgrade winbox.

    Rollback: sudo snapper list and sudo snapper undochange <old>..<new>.

For more, see the Troubleshooting Guide.
FAQ

Q: Can I run Penta OS on a regular laptop?
A: Yes, the x86_64 version works natively. ARM64 is recommended for the full cross‑architecture experience.

Q: Does it replace my current OS?
A: Penta OS is designed as a primary OS for dedicated devices, but you can also run it in a VM or on a spare SD card.

Q: Is it safe to install packages from untrusted sources?
A: Containers isolate apps, so they cannot harm the host. However, malicious software could still access user data in the home directory if not properly restricted. We recommend using verified sources and paying attention to permission prompts.

Q: How much overhead do containers add?
A: Very little. CPU overhead is typically <3%, and memory footprint depends on the container base image. Distrobox shares the host kernel, so there’s no hypervisor layer.

Q: Can I use Penta OS without internet?
A: You can install local packages (.deb, .appimage, etc.) offline. Repository searches require a connection to Penta Hub or a local cache.
Roadmap

    Q2 2025: Stable CLI, GUI beta, AUR/APT/Flatpak/pip support.

    Q3 2025: Windows support (Box64+Wine) fully integrated, GitHub installer, Mode Switcher v1.

    Q4 2025: Cluster federation, AI node mode, P2P Hub.

    2026: Android app interoperability, security audit, 1.0 release.

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
