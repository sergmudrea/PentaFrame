FROM ubuntu:22.04

# Install Homebrew dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        git \
        procps \
        file \
        ca-certificates \
        sudo && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user for Homebrew
RUN useradd -m -s /bin/bash brewuser && \
    echo 'brewuser ALL=(ALL) NOPASSWD: ALL' > /etc/sudoers.d/brewuser

USER brewuser
WORKDIR /home/brewuser

# Install Homebrew
RUN /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Add Homebrew to PATH
ENV PATH="/home/brewuser/.linuxbrew/bin:${PATH}"

# Run brew doctor to verify installation
RUN brew doctor || true

CMD ["/bin/bash"]
