# Penta OS Build System
# Usage:
#   make build          - Build all Penta OS components (containers, daemons)
#   make test           - Run unit and integration tests
#   make lint           - Run linters (shellcheck, pylint)
#   make clean          - Remove build artifacts
#   make run            - Start Penta OS services locally (dev mode)
#   make image          - Build full OS image (requires build.sh)

SHELL := /bin/bash
PYTHON := python3
PIP := pip3
DISTROBOX := distrobox
DOCKER := docker

# Directories
SRC_DIR := src
TEST_DIR := tests
CONTAINERS_DIR := containers
BUILD_DIR := build
OUTPUT_DIR := output

# Container images
TOOLBOXES := debian-stable arch-toolbox fedora-toolbox kali winbox python-slim node-slim homebrew

.PHONY: all build test lint clean run image containers

all: build

# Build all Python components and daemons
build:
	@echo "Building Penta OS daemons and tools..."
	$(PYTHON) -m compileall $(SRC_DIR)
	@echo "Installing Python dependencies..."
	$(PIP) install -r requirements.txt --quiet
	@echo "Build complete."

# Run unit tests
test:
	@echo "Running unit tests..."
	$(PYTHON) -m pytest $(TEST_DIR)/unit -v
	@echo "Running integration tests (requires containers)..."
	@if [ -x "$(DISTROBOX)" ]; then \
		$(PYTHON) -m pytest $(TEST_DIR)/integration -v; \
	else \
		echo "Skipping integration tests (distrobox not found)"; \
	fi

# Lint code
lint:
	@echo "Linting Python code..."
	pylint $(SRC_DIR) || true
	@echo "Linting shell scripts..."
	shellcheck scripts/*.sh

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	find . -type d -name __pycache__ -exec rm -rf {} +
	rm -rf $(BUILD_DIR) $(OUTPUT_DIR) *.egg-info .pytest_cache
	@echo "Clean complete."

# Start development services locally
run:
	@echo "Starting Penta Hub..."
	$(PYTHON) $(SRC_DIR)/hub/penta-hub.py &
	@sleep 2
	@echo "Starting Penta Resolver..."
	$(PYTHON) $(SRC_DIR)/resolver/penta-resolver.py &
	@echo "Services running in background. Use 'make stop' to stop."

# Stop development services
stop:
	@echo "Stopping Penta services..."
	-pkill -f penta-hub.py
	-pkill -f penta-resolver.py

# Build all container toolboxes
containers:
	@for img in $(TOOLBOXES); do \
		echo "Building $$img container..."; \
		if [ -f "$(CONTAINERS_DIR)/$$img/Dockerfile" ]; then \
			$(DOCKER) build -t ghcr.io/penta-os/$$img:latest $(CONTAINERS_DIR)/$$img; \
		else \
			echo "Skipping $$img (no Dockerfile)"; \
		fi; \
	done

# Build full OS image (requires privileged access)
image:
	@if [ $$(id -u) -ne 0 ]; then \
		echo "Image build must be run as root. Use 'sudo make image'"; \
		exit 1; \
	fi
	./build.sh --arch arm64 --variant desktop --output $(OUTPUT_DIR)

# Generate documentation
docs:
	@echo "Generating documentation..."
	@if command -v pdoc3 &> /dev/null; then \
		pdoc3 --html -o docs/api $(SRC_DIR); \
	else \
		echo "pdoc3 not installed, skipping."; \
	fi

# Help
help:
	@echo "Available targets:"
	@echo "  build      - Build Penta OS components"
	@echo "  test       - Run tests"
	@echo "  lint       - Lint code"
	@echo "  clean      - Remove build artifacts"
	@echo "  run        - Start services (dev mode)"
	@echo "  stop       - Stop services"
	@echo "  containers - Build all toolbox images"
	@echo "  image      - Build full OS image"
	@echo "  docs       - Generate API documentation"
