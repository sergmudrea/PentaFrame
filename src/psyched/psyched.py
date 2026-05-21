#!/usr/bin/env python3
"""
psyched - Psycho‑emotional Monitor Daemon
==========================================
Subscribes to biometric sensor data over MQTT, computes stress and fatigue
indices, publishes results, and can trigger UI warnings or command restrictions
when user state is degraded.

Current version (v0.1) uses emulated data for prototyping.

Usage:
    python3 src/psyched/psyched.py
"""

import json
import logging
import os
import random
import time
from pathlib import Path
from typing import Optional

import paho.mqtt.client as mqtt
import yaml

# ---------- Configuration ----------
CONFIG_PATH = Path("/etc/penta/config.yaml")
if not CONFIG_PATH.exists():
    CONFIG_PATH = Path("config/penta.conf.example")

with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

PSYCHED_CONFIG = config.get("psyched", {})
MQTT_CONFIG = config.get("mqtt", {})

MQTT_BROKER = MQTT_CONFIG.get("broker", "localhost")
MQTT_PORT = MQTT_CONFIG.get("port", 1883)
MQTT_CLIENT_ID = "psyched"

TOPIC_BIOMETRICS = "penta/biometrics"
TOPIC_PSYCHE = "penta/psyche"
TOPIC_COMMAND_FILTER = "penta/command/filter"

# Thresholds (can be overridden in config)
STRESS_THRESHOLD = PSYCHED_CONFIG.get("stress_threshold", 70)    # percent
FATIGUE_THRESHOLD = PSYCHED_CONFIG.get("fatigue_threshold", 80)  # percent

# Emulation mode
EMULATE = PSYCHED_CONFIG.get("emulate", True)
EMULATE_INTERVAL = PSYCHED_CONFIG.get("emulate_interval", 5)     # seconds

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] psyched: %(message)s")
logger = logging.getLogger("psyched")

# ---------- MQTT Client ----------
mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Connected to MQTT broker")
        # Subscribe to biometric data topic
        client.subscribe(TOPIC_BIOMETRICS, qos=1)
    else:
        logger.error(f"MQTT connection failed, rc={rc}")

def on_message(client, userdata, msg):
    """Process incoming biometric data."""
    try:
        payload = json.loads(msg.payload.decode())
        # Expected: {"heart_rate": 72, "gsr": 1500, "temperature": 36.6, ...}
        # Compute stress and fatigue
        stress, fatigue = compute_state(payload)
        # Publish psyche state
        state = {
            "stress": stress,
            "fatigue": fatigue,
            "timestamp": time.time()
        }
        mqtt_client.publish(TOPIC_PSYCHE, json.dumps(state), qos=1)
        # Check thresholds and possibly send command filter
        if stress > STRESS_THRESHOLD or fatigue > FATIGUE_THRESHOLD:
            mqtt_client.publish(TOPIC_COMMAND_FILTER, json.dumps({"block_dangerous": True, "reason": "stress/fatigue"}))
            logger.warning(f"High stress ({stress}) or fatigue ({fatigue}) – dangerous commands blocked.")
        else:
            mqtt_client.publish(TOPIC_COMMAND_FILTER, json.dumps({"block_dangerous": False}))
    except Exception as e:
        logger.error(f"Error processing biometrics: {e}")

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

# ---------- State Computation ----------
def compute_state(biometrics: dict) -> tuple[float, float]:
    """
    Calculate stress (0–100) and fatigue (0–100) from biometric data.
    This is a placeholder algorithm; replace with real models.
    """
    # Example: higher heart rate increases stress, lower GSR (skin conductance) decreases stress.
    hr = biometrics.get("heart_rate", 70)
    gsr = biometrics.get("gsr", 1500)
    temp = biometrics.get("temperature", 36.6)

    # Very simple linear model
    stress = max(0.0, min(100.0, (hr - 60) * 2.0 + (2000 - gsr) * 0.02))
    fatigue = max(0.0, min(100.0, (temp - 36.0) * 50.0 + random.uniform(0, 5)))  # random for demo
    return stress, fatigue

def emulate_biometrics():
    """Generate fake biometric data for testing."""
    return {
        "heart_rate": random.randint(60, 100),
        "gsr": random.randint(800, 2500),
        "temperature": round(random.uniform(36.0, 37.5), 1)
    }

# ---------- Main Loop ----------
def main():
    logger.info("Starting psyched...")
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
    except Exception as e:
        logger.warning(f"Could not connect to MQTT: {e}. Running in offline mode.")
        mqtt_client.loop_start()  # will try to reconnect

    if EMULATE:
        # If no real sensors, publish emulated biometrics periodically
        logger.info("Emulation mode active.")
        while True:
            data = emulate_biometrics()
            mqtt_client.publish(TOPIC_BIOMETRICS, json.dumps(data))
            time.sleep(EMULATE_INTERVAL)
    else:
        # Just listen for incoming messages
        while True:
            time.sleep(1)

if __name__ == "__main__":
    main()
