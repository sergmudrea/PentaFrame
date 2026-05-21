FROM fedora:latest

# Install base development tools and utilities
RUN dnf -y update && \
    dnf -y install \
        dnf-plugins-core \
        @development-tools \
        git \
        sudo \
        curl \
        wget \
        rpm-build && \
    dnf clean all

# Enable RPM Fusion repositories
RUN dnf install -y \
    https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm \
    https://download1.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-$(rpm -E %fedora).noarch.rpm

# Create a default user for package installations
RUN useradd -m -G wheel penta && \
    echo 'penta ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/penta

USER penta
WORKDIR /home/penta

# Create directory for Penta Resolver build operations
RUN mkdir -p /home/penta/penta-build

CMD ["/bin/bash"]
