FROM debian:stable-slim

# Install basic utilities
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash \
        coreutils \
        curl \
        wget \
        ca-certificates \
        gnupg \
        sudo && \
    rm -rf /var/lib/apt/lists/*

# Create a default user for package installations
RUN useradd -m -s /bin/bash penta && \
    echo 'penta ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/penta

USER penta
WORKDIR /home/penta

CMD ["/bin/bash"]
