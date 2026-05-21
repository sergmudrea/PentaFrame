#!/bin/bash
# setup-dev-env.sh - Bootstrap a Penta OS development environment on a Debian/Ubuntu host
set -euo pipefail

echo "Setting up Penta OS development environment..."

# Update package lists
sudo apt update

# Install core development tools
sudo apt install -y \
    build-essential \
    git \
    curl \
    wget \
    ca-certificates \
    python3 \
    python3-pip \
    python3-venv \
    shellcheck \
    pylint \
    black \
    docker.io \
    podman \
    qemu-user-static \
    binfmt-support \
    distrobox \
    mosquitto \
    mosquitto-clients

# Enable and start Docker
sudo systemctl enable docker --now

# Add current user to docker group for non-root access
sudo usermod -aG docker "$USER"

# Install Distrobox if not present
if ! command -v distrobox &> /dev/null; then
    curl -s https://raw.githubusercontent.com/89luca89/distrobox/main/install | sudo sh
fi

# Install Python development tools
pip3 install --user --upgrade pip
pip3 install --user -r src/requirements.txt

# Install pre-commit hooks
pip3 install --user pre-commit
pre-commit install

# Create default configuration directories
sudo mkdir -p /etc/penta/{modes,apparmor,seccomp}
sudo cp config/penta.conf.example /etc/penta/config.yaml 2>/dev/null || true
sudo cp config/containers.yaml /etc/penta/containers.yaml 2>/dev/null || true

# Pull base container images for offline use (optional)
if systemctl is-active --quiet docker; then
    for img in debian:stable-slim archlinux:latest fedora:latest kalilinux/kali-rolling python:3.12-slim node:20-slim ubuntu:22.04; do
        docker pull "$img" || true
    done
fi

echo ""
echo "=================================================="
echo "Penta OS development environment setup complete!"
echo "Please log out and back in for Docker group changes."
echo ""
echo "Next steps:"
echo "  make test        - run unit tests"
echo "  make containers  - build all toolboxes"
echo "  make run         - start Penta Hub and Resolver locally"
echo "=================================================="
