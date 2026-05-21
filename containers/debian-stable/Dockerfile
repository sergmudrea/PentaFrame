FROM debian:stable-slim

# Install basic utilities, flatpak, and snapd
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash \
        coreutils \
        curl \
        wget \
        ca-certificates \
        gnupg \
        sudo \
        flatpak \
        snapd \
        fuse \
        squashfuse \
        && \
    rm -rf /var/lib/apt/lists/*

# Create default user
RUN useradd -m -s /bin/bash penta && \
    echo 'penta ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/penta

# Add Flathub remote
RUN flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo

# snapd requires systemd to operate properly; running it in a container needs
# privileged mode and manual socket activation. For production, consider using
# a separate toolbox with --privileged or install snapd on the host.
# We'll leave it installed but disabled by default.

USER penta
WORKDIR /home/penta

CMD ["/bin/bash"]
