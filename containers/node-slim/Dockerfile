FROM node:24-slim

# Install build tools for compiling native addons
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
        python3 \
        curl && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m -s /bin/bash nodeuser && \
    mkdir -p /home/nodeuser/.npm-global && \
    chown -R nodeuser:nodeuser /home/nodeuser

USER nodeuser
WORKDIR /home/nodeuser

# Configure npm to use global directory
RUN npm config set prefix '/home/nodeuser/.npm-global'
ENV PATH="/home/nodeuser/.npm-global/bin:$PATH"

CMD ["/bin/bash"]
