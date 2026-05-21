FROM python:3.14

# Install build tools for compiling packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
        curl && \
    rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m -s /bin/bash pyuser && \
    mkdir -p /home/pyuser/venvs && chown -R pyuser:pyuser /home/pyuser

USER pyuser
WORKDIR /home/pyuser

# Upgrade pip
RUN pip install --upgrade pip

# Create a default virtual environment
RUN python -m venv /home/pyuser/venvs/default
ENV PATH="/home/pyuser/venvs/default/bin:$PATH"

CMD ["/bin/bash"]
