#!/bin/bash
# Penta OS Smoke Tests
# Requires: docker-compose up -d running
set -euo pipefail

HUB_URL="http://localhost:8400"
RESOLVER_URL="http://localhost:8500"
PENTAD_URL="http://localhost:8600"
MQTT_HOST="localhost"
MQTT_PORT=1883

PASS=0
FAIL=0

check() {
    local desc="$1"
    local cmd="$2"
    if eval "$cmd"; then
        echo "✓ $desc"
        ((PASS++))
    else
        echo "✗ $desc"
        ((FAIL++))
    fi
}

echo "=== Penta OS Smoke Tests ==="

# Wait for services to be ready
sleep 3

# ---------- Penta Hub ----------
check "Hub health endpoint" \
    "curl -sf $HUB_URL/api/v1/health | grep -q 'ok'"

check "Hub search returns JSON" \
    "curl -sf '$HUB_URL/api/v1/search?q=test' | grep -q 'results'"

check "Hub plugins endpoint" \
    "curl -sf $HUB_URL/api/v1/plugins | grep -q 'plugins'"

# ---------- Penta Resolver ----------
check "Resolver health endpoint" \
    "curl -sf $RESOLVER_URL/api/v1/health | grep -q 'ok'"

check "Resolver installed list" \
    "curl -sf $RESOLVER_URL/api/v1/installed | grep -q 'installed'"

# Trigger an install (will fail gracefully because Hub returns no package)
check "Resolver install returns task ID" \
    "curl -sf -X POST $RESOLVER_URL/api/v1/install \
        -H 'Content-Type: application/json' \
        -d '{\"package\":\"test\"}' | grep -q 'task_id'"

# ---------- MQTT Broker ----------
check "Mosquitto broker reachable" \
    "mosquitto_pub -h $MQTT_HOST -p $MQTT_PORT -t 'penta/smoke' -m 'test' -q 0"

# ---------- pentad (if available) ----------
if curl -sf $PENTAD_URL/api/v1/status > /dev/null 2>&1; then
    check "pentad status endpoint" \
        "curl -sf $PENTAD_URL/api/v1/status | grep -q 'modules'"
else
    echo "⚠ pentad not running (skipping)"
fi

echo "=== Results: $PASS passed, $FAIL failed ==="
exit $FAIL
