FROM fedora:latest

# Install base development tools, flatpak, and snapd
RUN dnf -y update && \
    dnf -y install \
        dnf-plugins-core \
        @development-tools \
        git \
        sudo \
        curl \
        wget \
        rpm-build \
        flatpak \
        snapd \
        squashfuse \
        fuse && \
    dnf clean all

# Enable RPM Fusion repositories
RUN dnf install -y \
    https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm \
    https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm

# Create default user
RUN useradd -m -G wheel penta && \
    echo 'penta ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/penta

# Add Flathub remote
RUN flatpak remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo

# Snap needs special handling (systemd) inside container; leave it installed but inactive.

USER penta
WORKDIR /home/penta

CMD ["/bin/bash"]
