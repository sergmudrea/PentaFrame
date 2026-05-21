FROM kalilinux/kali-rolling

# Update and install common tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        bash \
        coreutils \
        curl \
        wget \
        ca-certificates \
        gnupg \
        sudo \
        git && \
    rm -rf /var/lib/apt/lists/*

# Create default user for package operations
RUN useradd -m -s /bin/bash pentester && \
    echo 'pentester ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/pentester

USER pentester
WORKDIR /home/pentester

CMD ["/bin/bash"]
